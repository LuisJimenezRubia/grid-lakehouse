#!/usr/bin/env python3
"""Segunda pasada de exploración del Transparency Platform: las dudas que dejó scripts/explorar_balancing.py.

1. B17 volúmenes neteados e intercambiados: con controlArea_Domain, y por frontera (Acquiring + Connecting).
2. A15 capacidad adquirida: con type_MarketAgreement.Type (el 400 de la primera pasada venía sin él).
3. A89 precios de reservas contratadas: exige type_MarketAgreement.Type y controlArea_Domain; businessType A96/A97.
4. A87 gastos e ingresos: mensual, pedir el mes entero.
5. Alemania en A85/A84: probar otros EIC (bloque LFC DE-LU, Alemania país, DK) para el reBAP y Amprion.
6. Tamaño y tiempo de un mes de CBMP (A84+A67) para una sola área.

Reutiliza las utilidades de scripts/explorar_balancing.py y de ingest/bronze.py.

Uso:  python3 scripts/explorar_balancing_2.py >> docs/catalogo_balancing.txt 2>&1
"""
import datetime as dt
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from bronze import ENTSOE_URL, descargar, leer_token, ventana_utc  # noqa: E402
from explorar_balancing import AREAS, DIA, imprimir  # noqa: E402

EIC_EXTRA = {
    "DE_LFC_block": "10Y1001A1001A63L",   # bloque LFC DE-LU (antes DE-AT-LU)
    "DE_country":   "10Y1001A1001A83F",   # Alemania como país (usado en A11 flujos)
    "DE_AT_LU_old": "10Y1001A1001A63L",
    "DK":           "10Y1001A1001A65H",   # Dinamarca país
    "DK2":          "10YDK-2--------M",
    "NL_TTG":       "10YNL----------L",
}
AREAS_X = {**AREAS, **EIC_EXTRA}


def pedir(token, params, dia_ini, dia_fin=None):
    inicio = ventana_utc(dia_ini)[0]
    fin = ventana_utc(dia_fin or dia_ini)[1]
    q = {"securityToken": token, **params,
         "periodStart": inicio.strftime("%Y%m%d%H%M"), "periodEnd": fin.strftime("%Y%m%d%H%M")}
    t0 = time.time()
    try:
        codigo, cuerpo = descargar(f"{ENTSOE_URL}?{urllib.parse.urlencode(q)}")
    except Exception as e:
        codigo, cuerpo = 0, f"{type(e).__name__}: {e}".encode()
    return codigo, cuerpo, time.time() - t0


def bloque(titulo, ident, pruebas, token, dia_ini=DIA, dia_fin=None):
    """pruebas: lista de (etiqueta_area, params)."""
    print(f"\n===== {ident} · {titulo}")
    for etiqueta, params in pruebas:
        codigo, cuerpo, seg = pedir(token, params, dia_ini, dia_fin)
        imprimir(ident, titulo, etiqueta, dia_ini if not dia_fin else f"{dia_ini}..{dia_fin}", codigo, cuerpo, seg)
        time.sleep(0.5)


def main():
    token = leer_token()
    print(f"\n\n######## SEGUNDA PASADA · {dt.datetime.now():%Y-%m-%d %H:%M} · día de prueba {DIA}\n")

    # 1. B17 netted and exchanged volumes
    bloque("12.3 netted & exchanged volumes, por área de control", "B17-area",
           [(a, {"documentType": "B17", "processType": "A63", "controlArea_Domain": AREAS_X[a]})
            for a in ("BE", "NL", "FR", "AT", "CZ", "DE_50Hz", "DE_TTG", "DE_LFC_block")], token)
    bloque("12.3 netted & exchanged volumes, por área, sin processType", "B17-area-np",
           [(a, {"documentType": "B17", "controlArea_Domain": AREAS_X[a]}) for a in ("BE", "DE_50Hz")], token)
    bloque("12.3 netted & exchanged volumes, por área, processType aFRR (PICASSO)", "B17-area-aFRR",
           [(a, {"documentType": "B17", "processType": "A51", "controlArea_Domain": AREAS_X[a]}) for a in ("BE", "DE_50Hz")], token)
    bloque("12.3 netted & exchanged volumes, por área, processType mFRR (MARI)", "B17-area-mFRR",
           [(a, {"documentType": "B17", "processType": "A47", "controlArea_Domain": AREAS_X[a]}) for a in ("BE", "DE_50Hz")], token)
    fronteras = [("BE>NL", "BE", "NL"), ("NL>BE", "NL", "BE"), ("BE>FR", "BE", "FR"), ("BE>DE_TTG", "BE", "DE_TTG"),
                 ("DE_50Hz>CZ", "DE_50Hz", "CZ"), ("DE_TTG>NL", "DE_TTG", "NL")]
    bloque("12.3 netted & exchanged volumes, por frontera (Acquiring/Connecting)", "B17-border",
           [(e, {"documentType": "B17", "processType": "A63",
                 "Acquiring_Domain": AREAS_X[a], "Connecting_Domain": AREAS_X[c]}) for e, a, c in fronteras], token)
    bloque("12.3 netted & exchanged volumes, por frontera, sin processType", "B17-border-np",
           [(e, {"documentType": "B17", "Acquiring_Domain": AREAS_X[a], "Connecting_Domain": AREAS_X[c]})
            for e, a, c in fronteras[:2]], token)

    # 2. A15 procured balancing capacity
    for mat, nombre in (("A01", "daily"), ("A02", "weekly"), ("A03", "monthly"), ("A04", "yearly")):
        bloque(f"12.3.F procured balancing capacity aFRR, agreement {nombre}", f"A15-aFRR-{nombre}",
               [(a, {"documentType": "A15", "processType": "A51", "type_MarketAgreement.Type": mat, "area_Domain": AREAS_X[a]})
                for a in ("BE", "NL", "DE_50Hz", "AT")], token)
    bloque("12.3.F procured balancing capacity mFRR, agreement daily", "A15-mFRR-daily",
           [(a, {"documentType": "A15", "processType": "A47", "type_MarketAgreement.Type": "A01", "area_Domain": AREAS_X[a]})
            for a in ("BE", "NL", "DE_50Hz", "AT", "FR")], token)
    bloque("12.3.F procured balancing capacity FCR, agreement daily", "A15-FCR-daily",
           [(a, {"documentType": "A15", "processType": "A52", "type_MarketAgreement.Type": "A01", "area_Domain": AREAS_X[a]})
            for a in ("BE", "DE_50Hz")], token)

    # 3. A89 prices of contracted reserves
    for mat, nombre in (("A01", "daily"), ("A13", "hourly"), ("A02", "weekly")):
        bloque(f"17.1.C prices of contracted reserves, agreement {nombre}", f"A89-{nombre}",
               [(a, {"documentType": "A89", "type_MarketAgreement.Type": mat, "controlArea_Domain": AREAS_X[a]})
                for a in ("BE", "NL", "FR", "AT", "DE_50Hz")], token)
    bloque("17.1.C prices of contracted reserves daily, businessType aFRR", "A89-daily-aFRR",
           [(a, {"documentType": "A89", "type_MarketAgreement.Type": "A01", "businessType": "A96", "controlArea_Domain": AREAS_X[a]})
            for a in ("BE", "DE_50Hz")], token)
    # y A81 con los parámetros documentados (processType), por si trae más que la primera pasada
    bloque("17.1.B/C contracted reserves daily, processType aFRR", "A81-aFRR",
           [(a, {"documentType": "A81", "processType": "A51", "type_MarketAgreement.Type": "A01", "controlArea_Domain": AREAS_X[a]})
            for a in ("BE", "NL", "DE_50Hz")], token)
    bloque("17.1.B/C contracted reserves daily, processType mFRR", "A81-mFRR",
           [(a, {"documentType": "A81", "processType": "A47", "type_MarketAgreement.Type": "A01", "controlArea_Domain": AREAS_X[a]})
            for a in ("BE", "NL", "DE_50Hz")], token)

    # 4. A87 financial expenses and income: mes entero de septiembre 2026
    bloque("17.1.I financial expenses & income, mes completo sep 2026", "A87-mes",
           [(a, {"documentType": "A87", "controlArea_Domain": AREAS_X[a]}) for a in ("BE", "NL", "FR", "AT", "DE_50Hz", "DE_LFC_block")],
           token, dt.date(2026, 9, 1), dt.date(2026, 9, 30))

    # 5. Alemania: reBAP y Amprion
    bloque("17.1.G imbalance prices, EIC alternativos para Alemania", "A85-DE",
           [(a, {"documentType": "A85", "controlArea_Domain": AREAS_X[a]}) for a in ("DE_LFC_block", "DE_country", "DK", "DK2")], token)
    bloque("17.1.F CBMP aFRR, EIC alternativos para Alemania y Amprion", "A84-CS-DE",
           [(a, {"documentType": "A84", "processType": "A67", "controlArea_Domain": AREAS_X[a]}) for a in ("DE_LFC_block", "DE_country")], token)
    bloque("17.1.F precios activación 15 min, EIC alternativos", "A84-DE",
           [(a, {"documentType": "A84", "processType": "A16", "controlArea_Domain": AREAS_X[a]}) for a in ("DE_LFC_block", "DE_country", "DE_AMP")], token)
    bloque("17.1.H imbalance volumes, EIC alternativos", "A86-DE",
           [(a, {"documentType": "A86", "controlArea_Domain": AREAS_X[a]}) for a in ("DE_LFC_block", "DE_country", "DK", "DK2")], token)

    # 6. Un mes de CBMP para una sola área
    bloque("17.1.F CBMP aFRR, un mes entero (sep 2026) para BE", "A84-CS-mes",
           [("BE", {"documentType": "A84", "processType": "A67", "controlArea_Domain": AREAS_X["BE"]})],
           token, dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    bloque("17.1.G imbalance prices, un mes entero (sep 2026) para BE", "A85-mes",
           [("BE", {"documentType": "A85", "controlArea_Domain": AREAS_X["BE"]})],
           token, dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    print("\n######## FIN SEGUNDA PASADA")


if __name__ == "__main__":
    main()
