#!/usr/bin/env python3
"""Explora los datos de balance y previsiones del ENTSO-E Transparency Platform para el observatorio de balance.

Para cada combinación (dato, área) pide un día de mercado y muestra: código HTTP, formato (XML o ZIP de XMLs),
nº de documentos y TimeSeries, resoluciones, tipos de negocio / producto / dirección encontrados y valores de
ejemplo. Para los datos clave repite la petición en fechas antiguas para ver desde cuándo hay historia.

Reutiliza el token, el cliente HTTP y la ventana de día de mercado de ingest/bronze.py.

Uso:  python3 scripts/explorar_balancing.py > docs/catalogo_balancing.txt 2>&1
      python3 scripts/explorar_balancing.py --only A85 --area BE       (una sola prueba, para depurar)
"""
import argparse
import datetime as dt
import io
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from bronze import ENTSOE_URL, descargar, leer_token, ventana_utc  # noqa: E402

DIA = dt.date(2026, 10, 14)                                    # día reciente y ya consolidado
FECHAS_HISTORIA = [dt.date(2025, 10, 14), dt.date(2024, 6, 12), dt.date(2022, 11, 15)]  # ¿desde cuándo hay datos?

# Áreas: zona de oferta para previsiones; área de control (LFC) para balance. Alemania tiene cuatro TSO.
AREAS = {
    "BE":      "10YBE----------2",
    "NL":      "10YNL----------L",
    "FR":      "10YFR-RTE------C",
    "AT":      "10YAT-APG------L",
    "CZ":      "10YCZ-CEPS-----N",
    "DK1":     "10YDK-1--------W",
    "DE_LU":   "10Y1001A1001A82H",     # zona de oferta (precios, previsiones)
    "DE_50Hz": "10YDE-VE-------2",     # áreas de control alemanas (balance)
    "DE_AMP":  "10YDE-RWENET---I",
    "DE_TTG":  "10YDE-EON------1",
    "DE_TNG":  "10YDE-ENBW-----N",
}
AREAS_BALANCE = ["BE", "NL", "FR", "AT", "CZ", "DK1", "DE_LU", "DE_50Hz", "DE_AMP", "DE_TTG", "DE_TNG"]
AREAS_PREVISION = ["BE", "NL", "FR", "AT", "CZ", "DK1", "DE_LU"]

# (id, descripción, parámetros, nombre del parámetro de área, áreas, ¿probar historia?)
# Los códigos vienen de la guía REST de ENTSO-E, de entsoe-py y de entsoeapi (R); los marcados "a verificar"
# son los menos documentados.
PRUEBAS = [
    ("A85", "17.1.G imbalance prices (ZIP)",
     {"documentType": "A85"}, "controlArea_Domain", AREAS_BALANCE, True),
    ("A86", "17.1.H imbalance volumes (ZIP)",
     {"documentType": "A86"}, "controlArea_Domain", AREAS_BALANCE, False),
    ("A84", "17.1.F prices of activated balancing energy",
     {"documentType": "A84", "processType": "A16"}, "controlArea_Domain", AREAS_BALANCE, True),
    ("A84-CS", "17.1.F aFRR central selection = CBMP PICASSO (a verificar)",
     {"documentType": "A84", "processType": "A67"}, "controlArea_Domain", AREAS_BALANCE, True),
    ("A84-LS", "17.1.F aFRR local selection (a verificar)",
     {"documentType": "A84", "processType": "A68"}, "controlArea_Domain", ["BE", "DE_50Hz", "AT"], False),
    ("A83-aFRR", "17.1.E activated balancing energy aFRR (legacy)",
     {"documentType": "A83", "businessType": "A96"}, "controlArea_Domain", AREAS_BALANCE, False),
    ("A83-mFRR", "17.1.E activated balancing energy mFRR (legacy)",
     {"documentType": "A83", "businessType": "A97"}, "controlArea_Domain", AREAS_BALANCE, False),
    ("A24-aFRR", "12.3.E aggregated balancing energy bids aFRR",
     {"documentType": "A24", "processType": "A51"}, "area_Domain", AREAS_BALANCE, True),
    ("A24-mFRR", "12.3.E aggregated balancing energy bids mFRR",
     {"documentType": "A24", "processType": "A47"}, "area_Domain", AREAS_BALANCE, False),
    ("A24-mFRR-SA", "12.3.E aggregated bids mFRR scheduled activation",
     {"documentType": "A24", "processType": "A60"}, "area_Domain", ["BE", "DE_50Hz", "AT", "CZ"], False),
    ("A24-mFRR-DA", "12.3.E aggregated bids mFRR direct activation",
     {"documentType": "A24", "processType": "A61"}, "area_Domain", ["BE", "DE_50Hz", "AT", "CZ"], False),
    ("A15-aFRR", "12.3.F procured balancing capacity aFRR",
     {"documentType": "A15", "processType": "A51"}, "area_Domain", AREAS_BALANCE, False),
    ("A15-mFRR", "12.3.F procured balancing capacity mFRR",
     {"documentType": "A15", "processType": "A47"}, "area_Domain", AREAS_BALANCE, False),
    ("A81", "17.1.B contracted reserves, daily",
     {"documentType": "A81", "businessType": "B95", "type_MarketAgreement.Type": "A01"}, "controlArea_Domain", AREAS_BALANCE, False),
    ("A89", "17.1.C prices of contracted reserves, daily",
     {"documentType": "A89", "businessType": "B95", "type_MarketAgreement.Type": "A01"}, "controlArea_Domain", AREAS_BALANCE, False),
    ("A87", "17.1.I financial expenses and income",
     {"documentType": "A87"}, "controlArea_Domain", AREAS_BALANCE, False),
    ("B17", "12.3 netted and exchanged volumes, imbalance netting (a verificar)",
     {"documentType": "B17", "processType": "A63"}, "area_Domain", ["BE", "NL", "DE_50Hz", "AT"], False),
    ("A88", "17.1.J cross-border balancing (legacy)",
     {"documentType": "A88", "businessType": "A46"}, "acquiring_Domain", ["BE", "NL", "DE_50Hz"], False),
    # ---- previsiones y reales (proyecto 3)
    ("A69-DA", "14.1.D wind & solar forecast day-ahead",
     {"documentType": "A69", "processType": "A01"}, "in_Domain", AREAS_PREVISION, True),
    ("A69-ID", "14.1.D wind & solar forecast intraday",
     {"documentType": "A69", "processType": "A40"}, "in_Domain", AREAS_PREVISION, False),
    ("A69-CUR", "14.1.D wind & solar forecast current",
     {"documentType": "A69", "processType": "A18"}, "in_Domain", AREAS_PREVISION, False),
    ("A74", "16.1.B/C actual wind & solar generation",
     {"documentType": "A74", "processType": "A16"}, "in_Domain", AREAS_PREVISION, False),
    ("A75-solar", "16.1.B/C actual generation per type, solar",
     {"documentType": "A75", "processType": "A16", "psrType": "B16"}, "in_Domain", AREAS_PREVISION, False),
    ("A65-DA", "6.1.B load forecast day-ahead",
     {"documentType": "A65", "processType": "A01"}, "outBiddingZone_Domain", AREAS_PREVISION, True),
    ("A65-WA", "6.1.C load forecast week-ahead",
     {"documentType": "A65", "processType": "A31"}, "outBiddingZone_Domain", AREAS_PREVISION, False),
    ("A65-ACT", "6.1.A actual total load",
     {"documentType": "A65", "processType": "A16"}, "outBiddingZone_Domain", AREAS_PREVISION, False),
]


def local(el):
    return el.tag.split("}")[-1]


def documentos(cuerpo):
    """Devuelve la lista de XML que trae la respuesta: uno suelto, o varios dentro de un ZIP."""
    if cuerpo[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(cuerpo)) as z:
            return "zip", [z.read(n) for n in z.namelist()]
    return "xml", [cuerpo]


def resumir(xmls):
    """Recorre los documentos y cuenta lo que hay dentro, sin suponer el esquema."""
    tipos_doc, series, resoluciones, atributos = Counter(), 0, Counter(), {}
    puntos, ejemplos, periodo = 0, [], [None, None]
    ack = None
    for x in xmls:
        try:
            raiz = ET.fromstring(x)
        except ET.ParseError as e:
            tipos_doc[f"XML ilegible: {e}"] += 1
            continue
        tipos_doc[local(raiz)] += 1
        if local(raiz) == "Acknowledgement_MarketDocument":
            ack = " ".join(el.text.strip() for el in raiz.iter() if local(el) == "text" and el.text)
            continue
        for ts in raiz:
            if local(ts) != "TimeSeries":
                continue
            series += 1
            for el in ts:
                nombre = local(el)
                if nombre in ("businessType", "flowDirection.direction", "standard_MarketProduct.marketProductType",
                              "original_MarketProduct.marketProductType", "psrType", "curveType", "type_MarketAgreement.type",
                              "imbalance_Price.category", "mktPSRType", "currency_Unit.name", "quantity_Measure_Unit.name",
                              "price_Measure_Unit.name"):
                    atributos.setdefault(nombre, Counter())[(el.text or "").strip()] += 1
                if nombre == "MktPSRType":
                    for sub in el:
                        if local(sub) == "psrType":
                            atributos.setdefault("psrType", Counter())[(sub.text or "").strip()] += 1
                if nombre == "Period":
                    res = ini = fin = None
                    for sub in el:
                        if local(sub) == "resolution":
                            res = sub.text
                        elif local(sub) == "timeInterval":
                            for t in sub:
                                if local(t) == "start":
                                    ini = t.text
                                elif local(t) == "end":
                                    fin = t.text
                        elif local(sub) == "Point":
                            puntos += 1
                            if len(ejemplos) < 3:
                                ejemplos.append({local(c): (c.text or "").strip() for c in sub})
                    resoluciones[res] += 1
                    if ini and (periodo[0] is None or ini < periodo[0]):
                        periodo[0] = ini
                    if fin and (periodo[1] is None or fin > periodo[1]):
                        periodo[1] = fin
    return tipos_doc, series, resoluciones, atributos, puntos, ejemplos, periodo, ack


def probar(token, params, param_area, eic, dia):
    inicio, fin = ventana_utc(dia)
    q = {"securityToken": token, **params, param_area: eic,
         "periodStart": inicio.strftime("%Y%m%d%H%M"), "periodEnd": fin.strftime("%Y%m%d%H%M")}
    t0 = time.time()
    try:
        codigo, cuerpo = descargar(f"{ENTSOE_URL}?{urllib.parse.urlencode(q)}")
    except Exception as e:  # timeout de lectura, caída de red… se anota y se sigue con la siguiente
        codigo, cuerpo = 0, f"{type(e).__name__}: {e}".encode()
    return codigo, cuerpo, time.time() - t0


def imprimir(ident, descripcion, area, dia, codigo, cuerpo, segundos):
    cabecera = f"[{ident}] {area} {dia} · HTTP {codigo} · {len(cuerpo):,} bytes · {segundos:.1f} s"
    if codigo != 200:
        texto = cuerpo.decode("utf-8", "replace")
        motivo = " ".join(m.strip() for m in re.findall(r"<(?:\w+:)?text>(.*?)</", texto, re.S)) or texto[:300]
        print(f"{cabecera}\n    {motivo[:400]}")
        return "error"
    formato, xmls = documentos(cuerpo)
    tipos, series, res, attrs, puntos, ejemplos, periodo, ack = resumir(xmls)
    if ack is not None and series == 0:
        print(f"{cabecera} · sin datos: {ack[:160]}")
        return "sin_datos"
    print(f"{cabecera} · {formato}, {len(xmls)} doc · {dict(tipos)} · {series} TimeSeries · {puntos} puntos")
    print(f"    periodo {periodo[0]} → {periodo[1]} · resoluciones {dict(res)}")
    for k, v in attrs.items():
        print(f"    {k}: {dict(v)}")
    for e in ejemplos:
        print(f"    ej: {e}")
    return "ok"


def main():
    p = argparse.ArgumentParser(description="Explora los datos de balance y previsiones del Transparency Platform")
    p.add_argument("--only", metavar="ID", help="solo esta prueba (p. ej. A85, A84-CS, A69-DA)")
    p.add_argument("--area", help="solo esta área (p. ej. BE, DE_50Hz)")
    p.add_argument("--no-history", action="store_true", help="no probar fechas antiguas")
    p.add_argument("--from", dest="desde", metavar="ID", help="reanudar: empezar en esta prueba (p. ej. A81)")
    a = p.parse_args()
    token = leer_token()
    resumen = {}
    print(f"Exploración del Transparency Platform · día de prueba {DIA} · {dt.datetime.now():%Y-%m-%d %H:%M}\n")
    ids_todas = [t[0] for t in PRUEBAS]
    primera = ids_todas.index(a.desde) if a.desde else 0
    for ident, descripcion, params, param_area, areas, historia in PRUEBAS[primera:]:
        if a.only and ident != a.only:
            continue
        print(f"\n===== {ident} · {descripcion} · {params} · {param_area}")
        for area in areas:
            if a.area and area != a.area:
                continue
            codigo, cuerpo, seg = probar(token, params, param_area, AREAS[area], DIA)
            resumen[(ident, area)] = imprimir(ident, descripcion, area, DIA, codigo, cuerpo, seg)
            time.sleep(0.5)
        if historia and not a.no_history:
            # la historia se prueba solo en BE y en una alemana, que es donde más cambió el mercado
            for area in [x for x in ("BE", "DE_50Hz", "DE_LU") if x in areas and (not a.area or x == a.area)]:
                for fecha in FECHAS_HISTORIA:
                    codigo, cuerpo, seg = probar(token, params, param_area, AREAS[area], fecha)
                    imprimir(ident, descripcion, area, fecha, codigo, cuerpo, seg)
                    time.sleep(0.5)

    print("\n\n===== RESUMEN (ok / sin_datos / error) por prueba y área")
    ids = [t[0] for t in PRUEBAS[primera:] if not a.only or t[0] == a.only]
    areas = [x for x in AREAS if not a.area or x == a.area]
    ancho = max(len(i) for i in ids) + 2
    print(" " * ancho + "".join(f"{x:>9}" for x in areas))
    simbolo = {"ok": "ok", "sin_datos": "-", "error": "ERR"}
    for i in ids:
        fila = "".join(f"{simbolo.get(resumen.get((i, x), ''), '·'):>9}" for x in areas)
        print(f"{i:<{ancho}}{fila}")


if __name__ == "__main__":
    main()
