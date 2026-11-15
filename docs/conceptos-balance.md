# El mercado de balance europeo: conceptos y datos para el observatorio

Documento de trabajo del segundo proyecto de portfolio de Magic Byte (observatorio del mercado de balance +
calidad de previsión renovable y de carga). Primera parte: entender el dominio. Segunda parte: qué datos públicos
existen y qué hemos comprobado. Tercera parte: qué va a medir el proyecto. Se escribe en español mientras se
trabaja; se pasará a inglés cuando esté cerrado.

Fuentes: Reglamento (UE) 543/2013 (transparencia), Reglamento (UE) 2017/2195 (Guideline de balance, "EB GL"),
documentación pública de ENTSO-E sobre PICASSO, MARI e IGCC, informes de monitorización de ACER, documentación de
Elia Open Data, y la exploración de la API del Transparency Platform del 14/11/2026 (`docs/catalogo_balancing.txt`).

---

## 0. Resumen para alguien ajeno al sector

La red eléctrica es como una bañera con el grifo abierto y el desagüe destapado: lo que entra (generación) tiene
que ser igual a lo que sale (consumo) en todo momento, porque la electricidad no se puede acumular en los cables.
Si entra más de lo que sale, el "nivel" (la frecuencia de la red, 50 Hz en Europa) sube; si sale más, baja. Y si se
desvía demasiado, las protecciones desconectan centrales y consumidores y puede haber un apagón.

Hay una empresa en cada país encargada de vigilar ese nivel: el **operador del sistema** o **TSO** (Elia en Bélgica,
Red Eléctrica en España, RTE en Francia). No produce ni vende electricidad: gestiona la red de alta tensión y
mantiene el equilibrio.

La mayor parte del equilibrio se organiza por adelantado. El día anterior, productores y comercializadores compran
y venden en un mercado la energía de cada cuarto de hora del día siguiente, y cada uno se compromete a un programa:
"a las 10:00 yo inyectaré 200 MW". Pero el programa nunca se cumple exactamente: el viento sopla más o menos de lo
previsto, una central se avería, hace más frío. La diferencia entre lo prometido y lo real es el **desvío**, y a
quien se desvía se le cobra (o se le paga, si su error ayudó al sistema) un **precio de desvío** por cada MWh. Los
que tienen esa responsabilidad se llaman **BRP**.

Para corregir los desvíos en tiempo real el TSO tiene contratadas **reservas**: centrales, baterías y consumidores
flexibles que, a cambio de un pago, están disponibles para subir o bajar potencia en segundos o minutos cuando el
TSO se lo pide. Quien ofrece esas reservas es un **BSP**. Hay reservas rápidas y automáticas (aFRR) y más lentas y
manuales (mFRR). Al conjunto de todo esto (desvíos, reservas, su activación y sus precios) se le llama el
**mercado de balance**.

Hasta hace poco cada país gestionaba su balance por su cuenta. Desde 2022 los TSO europeos han conectado sus
reservas en **plataformas comunes** (PICASSO para las automáticas, MARI para las manuales): cuando a Bélgica le
falta energía y la reserva más barata está en Austria, se activa la austríaca y la energía cruza las fronteras.
Eso abarata el balance, pero también hace que los precios de un país dependan de lo que pase en los demás, y a veces
produce picos de precio espectaculares cuando una frontera se llena.

Todos estos datos (cuánto se desvía cada país, qué reservas se activan, a qué precio, qué precio de desvío se cobra,
y qué previsiones de viento, sol y consumo hizo cada operador) son públicos por obligación legal europea y se
publican en una web de ENTSO-E, la asociación de operadores. Pero están en bruto, en formatos difíciles, con
criterios distintos por país, y nadie los junta de forma sistemática salvo el regulador europeo, que publica
informes una vez al año.

**Este proyecto** construye un sistema que descarga esos datos cada día para diez zonas (Bélgica, Países Bajos,
Francia, Austria, Chequia, Dinamarca y las cuatro áreas alemanas), los limpia y los hace comparables, y responde con
cifras a preguntas como: ¿cuánto cuesta desviarse en cada país?, ¿han convergido de verdad los precios europeos de
reservas?, ¿qué operador prevé mejor el viento y el sol, y cuánto le cuesta a quien prevé mal? Es, a la vez, una
demostración técnica (cómo montar un sistema de datos moderno y barato sobre fuentes públicas) y un producto que
un operador, un regulador o un participante del mercado podría querer tener.

## 1. El problema: la red tiene que estar en equilibrio cada segundo

La electricidad no se almacena en la red: en cada instante la generación tiene que ser igual al consumo más las
pérdidas. Cuando se consume más de lo que se genera, los generadores síncronos frenan y la frecuencia baja de
50 Hz; cuando sobra generación, sube. Desviaciones de unas décimas de Hz ya obligan a actuar; de ±1 Hz,
provocan desconexiones en cascada.

El mercado organiza la mayor parte del equilibrio por adelantado: el día anterior (day-ahead) y durante el día
(intradía) los participantes compran y venden energía hasta dejar un programa cuadrado para cada cuarto de hora.
Pero el programa nunca se cumple exactamente: el viento sopla más o menos de lo previsto, una central falla, el
consumo se desvía. La diferencia entre el programa y la realidad se corrige en tiempo real, y esa corrección es
el **balance** (balancing). Lo opera el TSO, y es lo que mide este proyecto.

## 2. Los actores

**TSO** (Transmission System Operator): el operador de la red de transporte de un país o región (Elia en Bélgica,
RTE en Francia, TenneT en Países Bajos, los cuatro alemanes 50Hertz, Amprion, TenneT DE y TransnetBW, APG en
Austria, ČEPS en Chequia, Energinet en Dinamarca). Es el responsable final de la frecuencia en su área de control.
Compra reservas, las activa y liquida los desvíos. Es el cliente natural de este proyecto.

**BRP** (Balance Responsible Party, responsable de balance): cualquier participante con la obligación contractual
de que su cartera (generación, consumo, compras y ventas) esté equilibrada en cada cuarto de hora. Envía un
programa; si en tiempo real inyecta o consume distinto, incurre en un **desvío** (imbalance) y el TSO se lo cobra
o se lo paga al **precio de desvío**. Ejemplos: un comercializador, un productor eólico, una gran industria, un
agregador. Para el BRP el desvío es un coste y la previsión, su principal herramienta para reducirlo.

**BSP** (Balancing Service Provider, proveedor de servicios de balance): quien vende al TSO la capacidad de corregir
el desequilibrio. Tiene activos flexibles (una central de gas, una batería, una planta hidráulica, un consumo
industrial interrumpible) y ofrece **reservas**. Vende dos cosas distintas: *capacidad* (comprometerse a estar
disponible, pagado en EUR/MW por hora, se active o no) y *energía* (cuando el TSO le activa de verdad, cobra por
cada MWh subido o bajado). Una misma empresa puede ser BRP de su cartera y BSP con sus baterías.

**RCC** (Regional Coordination Centre, como Coreso): coordina entre TSO el cálculo de capacidad, el análisis de
seguridad, las indisponibilidades y la adecuación a corto plazo. **No interviene en el balance**: el balance es una
competencia exclusiva del TSO. Por eso este proyecto no se solapa con el trabajo de un RCC.

**Regulador** (CREG en Bélgica, BNetzA en Alemania, CRE en Francia) y **ACER** (la agencia europea): supervisan el
funcionamiento de los mercados de balance y publican informes anuales de monitorización. Son los que hacen las
preguntas que el observatorio intenta responder con meses de antelación.

## 3. Las reservas: tres escalones de velocidad

Los TSO mantienen reservas contratadas para restaurar la frecuencia, en escalones cada vez más lentos y baratos:

| Reserva | Nombre | Activación | Cómo | Plataforma europea |
|---|---|---|---|---|
| **FCR** | Frequency Containment Reserve ("primaria") | segundos | automática, proporcional a la desviación de frecuencia; solo *contiene* la caída, no la corrige | FCR Cooperation (subasta común de capacidad) |
| **aFRR** | automatic Frequency Restoration Reserve ("secundaria") | completa en 5 min | el controlador del TSO manda cada 4 s una consigna a las unidades contratadas hasta devolver la frecuencia a 50 Hz | **PICASSO** (energía) |
| **mFRR** | manual Frequency Restoration Reserve ("terciaria") | completa en 12,5 min | un operador del TSO decide activar bloques de potencia, para liberar la aFRR y cubrir desvíos largos; puede ser *programada* (SA, para el cuarto de hora siguiente) o *directa* (DA, inmediata) | **MARI** (energía) |
| **RR** | Replacement Reserve | 30 min o más | reposición de las anteriores en incidentes largos; no todos los TSO la usan | TERRE |

Dos ideas que importan para los datos:

- **Capacidad y energía son mercados distintos.** La capacidad se contrata por adelantado (diaria o semanal) y se
  paga por estar disponible. La energía se activa en tiempo real y se paga por lo activado. Un TSO puede tener
  mucha capacidad contratada y activar poca energía, o al revés.
- **Dirección.** Toda reserva tiene sentido *up* (el sistema tiene déficit: hay que generar más o consumir menos)
  y *down* (sobra energía: generar menos o consumir más). Los datos siempre vienen en dos series, una por sentido.

## 4. La cadena de un cuarto de hora

1. Los BRP se desvían de sus programas. La suma de todos los desvíos es el **desequilibrio del sistema**
   (system imbalance), positivo o negativo, en MW.
2. El TSO lo corrige activando reservas: primero la FCR lo contiene, la aFRR lo corrige automáticamente y, si dura
   o es grande, el operador activa mFRR. Antes de activar nada, el desequilibrio se **netea** con el de las zonas
   vecinas: si Francia tiene déficit y Alemania excedente, se compensan a través de la frontera (IGCC).
3. Las activaciones tienen un precio: el de las ofertas de los BSP que ha habido que activar.
4. El coste de esas activaciones se traslada a los BRP mediante el **precio de desvío** (imbalance price): un único
   precio por cuarto de hora y zona que cobran o pagan por cada MWh de desvío. Con *single pricing* (el modelo
   europeo desde 2021-2022), el BRP que se desvía en el sentido que ayuda al sistema cobra, y el que agrava el
   desequilibrio paga. El periodo de liquidación de desvíos (**ISP**, imbalance settlement period) es de 15 minutos
   en toda Europa desde 2025.

El observatorio mide cada eslabón (desequilibrio, activaciones, precio de la energía de balance, precio de desvío)
y la relación entre ellos.

## 5. Las plataformas europeas

Hasta hace pocos años cada TSO compraba y activaba sus reservas en su mercado nacional, con reglas y precios
propios. La EB GL (2017) obligó a crear plataformas comunes, una por producto, operadas por los propios TSO:

- **IGCC** (International Grid Control Cooperation): neteo de desequilibrios entre áreas de control. Evita activar
  aFRR en sentidos opuestos a los dos lados de una frontera. En operación desde 2010 y extendido a casi toda Europa
  continental.
- **PICASSO** (Platform for the International Coordination of Automated frequency restoration and Stable System
  Operation): plataforma de **energía aFRR**. Cada 4 segundos cada TSO conectado envía su demanda de aFRR y todas
  las ofertas de sus BSP; la función de optimización (AOF) junta las ofertas en una única lista de mérito común y
  activa las más baratas de todo el conjunto, respetando la capacidad disponible en cada frontera. En operación
  desde junio de 2022 (Alemania, Austria y Chequia primero; Bélgica, Países Bajos, Francia, Italia y otros
  después). La aloja TransnetBW.
- **MARI** (Manually Activated Reserves Initiative): lo mismo para la **energía mFRR**, con activaciones programadas
  y directas y clearing cada cuarto de hora. En operación desde octubre de 2022. Elia se conectó en mayo de 2024.
- **TERRE**: lo mismo para RR, desde 2020, con menos TSO.

Las tres usan la capacidad de interconexión que queda libre tras los mercados day-ahead e intradía, en este orden:
primero MARI, luego PICASSO, luego IGCC. Cuando una frontera se satura, la plataforma deja de poder activar al otro
lado y los precios se separan.

### El CBMP

El **CBMP** (Cross-Border Marginal Price) es el precio que resulta de la optimización de PICASSO. Como se activa en
orden de mérito, el precio de cada ciclo de 4 segundos es el de la oferta más cara que ha hecho falta activar
("pay-as-clear"), y todos los BSP activados cobran ese precio. Es *cross-border* porque, mientras las fronteras
tengan capacidad, es el mismo en todas las zonas conectadas: un único precio europeo de aFRR en ese instante. Cuando
una frontera se satura, la zona que queda aislada tiene su propio CBMP, más alto o más bajo, y ahí aparecen los
picos que llegan a la prensa (varios episodios en Alemania y Austria en 2024, Chequia el 1 de enero de 2026). Hay un
CBMP para subir y otro para bajar. El TP lo publica a 4 segundos; para la liquidación cada TSO calcula un precio
medio ponderado por volumen (VWAP) por cuarto de hora.

## 6. Marco regulatorio y por qué los datos son públicos

- **Reglamento (UE) 543/2013** ("Transparency Regulation"): obliga a los TSO a publicar en el ENTSO-E Transparency
  Platform (TP) datos de carga, generación, transporte, balance y congestión, con plazos concretos. Sus artículos
  son las etiquetas de los datos (6.1.A carga real, 14.1.D previsión renovable, 17.1.F precios de energía de
  balance activada, 17.1.G precios de desvío…).
- **Reglamento (UE) 2017/2195** (EB GL): crea las plataformas y añade publicaciones nuevas (artículo 12.3: ofertas,
  capacidad adquirida, volúmenes neteados e intercambiados). Sus etiquetas son 12.3.E, 12.3.F…
- **ACER** publica cada año el *Market Monitoring Report* y los informes de monitorización de las plataformas, con
  tablas descargables (CHEST). Son la referencia para validar lo que calcule el observatorio y el lenguaje con el
  que se expresa el regulador.

## 7. Los datos: cómo se codifica una petición al Transparency Platform

Cada petición combina parámetros que responden a preguntas distintas. Los códigos son los del estándar ENTSO-E
(lista de códigos CIM/ESMP).

**¿Qué documento quiero?** → `documentType`

| Código | Dato | Artículo |
|---|---|---|
| A85 | Precios de desvío | 17.1.G |
| A86 | Volumen total de desvío | 17.1.H |
| A84 | Precios de la energía de balance activada (incluye el CBMP con el proceso adecuado) | 17.1.F |
| A24 | Ofertas agregadas y energía de balance activada | 12.3.E |
| A81 | Reservas contratadas: volumen y precio | 17.1.B/C |
| A15 | Capacidad de balance adquirida (formato nuevo) | 12.3.F |
| A87 | Gastos e ingresos del TSO por balance, mensual | 17.1.I |
| B17 | Volúmenes neteados e intercambiados entre áreas | 12.3 |
| A69 | Previsión eólica y solar | 14.1.D |
| A74 / A75 | Generación real eólica y solar / real por tecnología | 16.1.B/C |
| A65 | Carga del sistema, previsión o real según el proceso | 6.1.A/B/C |
| A44 / A11 | Precios day-ahead / flujos físicos (ya en grid-lakehouse) | 12.1.D / 12.1.G |

**¿En qué fase del proceso?** → `processType`

| Código | Significado |
|---|---|
| A01 / A40 / A18 | Day-ahead / intradía / "current" (última previsión) |
| A31 / A32 / A33 | Semana / mes / año vista |
| A16 | Realizado (valor real) |
| A51 / A47 | aFRR / mFRR |
| A60 / A61 | mFRR activación programada (SA) / directa (DA) |
| A67 / A68 | aFRR selección central (PICASSO) / selección local (el TSO por su cuenta) |
| A63 | Imbalance netting (IGCC) |

**Etiquetas dentro de la respuesta** (no son parámetros, aparecen en cada TimeSeries):

| Campo | Valores |
|---|---|
| `businessType` | A95 FRR, A96 aFRR, A97 mFRR, A98 RR, A19 balance, A14 ofertas agregadas, B95 reservas contratadas, A93 eólica, A94 solar, A04 consumo |
| `flowDirection.direction` | A01 up, A02 down |
| `standard_MarketProduct.marketProductType` | A01 producto estándar europeo (intercambiable en las plataformas) |
| `original_MarketProduct.marketProductType` | producto nacional de origen (A02, A04…) |
| `imbalance_Price.category` | A04 excedente, A05 déficit, A06 precio medio |
| `curveType` | A01 todos los puntos; **A03 omite las posiciones cuyo valor se repite** (hay que hacer forward-fill, nunca rellenar con cero) |
| `resolution` | PT4S, PT15M, PT60M |

**¿Qué zona?** El nombre del parámetro cambia según el dato: `in_Domain` (previsiones, generación),
`outBiddingZone_Domain` (carga), `controlArea_Domain` (balance), `area_Domain` (ofertas agregadas),
`Acquiring_Domain` + `Connecting_Domain` (intercambios por frontera). Y la geografía también cambia: precios y
previsiones van por **zona de oferta** (bidding zone: DE-LU es una), el balance por **área de control** (LFC area:
Alemania son cuatro, una por TSO). Códigos EIC usados:

| Área | EIC | Tipo |
|---|---|---|
| BE | 10YBE----------2 | zona y área de control |
| NL | 10YNL----------L | idem |
| FR | 10YFR-RTE------C | idem |
| AT | 10YAT-APG------L | idem |
| CZ | 10YCZ-CEPS-----N | idem |
| DK1 / DK2 | 10YDK-1--------W / 10YDK-2--------M | zonas (Energinet oeste / este) |
| DE país | 10Y1001A1001A83F | país: único EIC bajo el que sale el precio de desvío alemán (reBAP) |
| DE-LU | 10Y1001A1001A82H | zona de oferta |
| 50Hertz / Amprion / TenneT DE / TransnetBW | 10YDE-VE-------2 / 10YDE-RWENET---I / 10YDE-EON------1 / 10YDE-ENBW-----N | áreas de control |

## 8. Resultado de la exploración (14/11/2026, día de prueba 14/10/2026)

Scripts: `scripts/explorar_balancing.py` (primera pasada, 247 peticiones) y `scripts/explorar_balancing_2.py` (segunda, 107). Salida completa: `docs/catalogo_balancing.txt`.

| Dato | BE | NL | FR | AT | CZ | DK1 | DE-LU | 50Hz | AMP | TTG | TNG | Resolución | Historia (BE / 50Hz) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A85 precios de desvío | ok | ok | ok | ok | ok | ok | –¹ | – | – | – | – | 15 min, ZIP | BE ≥ nov 2022 |
| A86 volumen de desvío | ok | ok | ok | ok | ok | – | – | ok | ok | ok | ok | 15 min, ZIP | — |
| A84+A16 precios activación 15 min | – | ok | ok | ok | ok | ok | – | ok | – | ok | ok | 15 min | BE solo hasta 2024 (luego A67/A68); 50Hz ≥ nov 2022 |
| **A84+A67 CBMP PICASSO** | ok | ok | ok | ok | ok | ok | – | ok | – | ok | ok | **4 s**, ~3 MB/día/área | BE desde 2024-25; 50Hz ≥ nov 2022 |
| A84+A68 aFRR local | ok | · | · | ok | · | · | · | – | · | · | · | 15 min | — |
| A24+A51 ofertas aFRR | ok | – | – | ok | – | – | – | – | – | – | – | 15 min | BE y 50Hz en 2022, no en 2024-25 (migrado a A67/A68) |
| A24+A47 ofertas mFRR | ok | – | ok | ok | ok | ok | – | ok | – | ok | ok | 15 min (CZ 60) | — |
| A24+A60/A61 mFRR SA / DA | ok | · | · | ok | ok | · | · | ok | · | · | · | 15 min | — |
| A81 reservas contratadas | ok | ok | ok | ok | ok | ok | – | ok | ok | ok | ok | diario, ZIP de 3-5 docs | — |
| A69+A01/A40 previsión eólica+solar | ok | ok | ok | ok | ok | ok | ok | · | · | · | · | 60 min BE/CZ, 15 min resto; 2-3 series (solar, eólica on/offshore) | BE y DE ≥ nov 2022 |
| A69+A18 previsión current | ok | – | ok | ok | – | ok | ok | · | · | · | · | idem | — |
| A74 real eólica+solar | ok | ok | ok | ok | ok | ok | ok | · | · | · | · | 15/60 min, muchas series (por tecnología, generación y consumo) | — |
| A65+A01 previsión de carga | ok | ok | ok | ok | ok | ok | ok | · | · | · | · | 15 min (DK1 60) | BE ≥ 2024 probado |
| A65+A31 carga semana vista | ok | ok | ok | ok | ok | – | ok | · | · | · | · | — | — |
| A65+A16 carga real | ok | ok | ok | ok | ok | ok | ok | · | · | · | · | 15 min (DK1 60) | — |
| B17+A63 neteo IGCC | ok | ok | ok | ok | ok | · | – | ok | · | ok | · | 15 min, ZIP | — |
| B17+A51 intercambio aFRR PICASSO | ok | · | · | · | · | · | · | ok | · | · | · | 4 s, ZIP ~200 KB/día | — |

¹ El reBAP alemán sale con el EIC de Alemania país (`10Y1001A1001A83F`), no con la zona DE-LU ni las áreas de control. (· = no probado, – = sin datos)

Segunda pasada (15/11/2026, `scripts/explorar_balancing_2.py`, 107 peticiones más; total 354):

| Duda | Resultado |
|---|---|
| **B17** volúmenes neteados e intercambiados | Funciona con `controlArea_Domain`. Con `processType` A63 (IGCC): neteo a 15 min, MWh, 2 series, en las 7 áreas. Con A51 (PICASSO): intercambio de aFRR a **4 s**, 43.200 puntos y ~200 KB/día/área. Con A47 (MARI): "parámetros no válidos", hay que buscar el proceso correcto. La vista por frontera no existe: `Acquiring_Domain` y `Connecting_Domain` deben ser el mismo EIC. |
| **A15** capacidad adquirida | Existe. NL responde (86 series diarias de aFRR). BE, AT y FR dan 400 porque devuelven 467 instancias y la API corta en 100: hay que pedir por tramos u `offset`. 50Hertz no publica. A81 ya cubre la capacidad para todos → fase 2. |
| **A89** precios de reservas contratadas | No existe en la API ("combinación no válida"). El precio va dentro de A81 (en BE, 384 puntos para 4 series = volumen + precio). Descartado. A81 solo acepta `businessType` B95, no `processType`. |
| **A87** gastos e ingresos | Mensual, 1 punto por mes y área. Publican NL, FR y AT; BE y Alemania no. Fase 2. |
| **Alemania** en A85 | El reBAP sale con el EIC de Alemania país `10Y1001A1001A83F` (192 puntos, 2 series, 15 min). También DK2 (`10YDK-2--------M`). |
| **Alemania** en A84 / Amprion | El CBMP y los precios de activación no salen ni por país ni por bloque LFC; Amprion no publica A84 bajo ningún EIC probado. Para aFRR Alemania se cubre con 50Hertz, TenneT y TransnetBW (el CBMP de PICASSO es el mismo para todo el bloque alemán). A86 solo por área de control. |
| **Tamaño de un mes** | CBMP (A84+A67) BE sep 2026: **100 MB, 91 s, 407.790 puntos**; comprimido gzip ≈ 5 MB. Precios de desvío (A85) un mes: 59 KB, 13 s. |

Descartados: A83 y A88 (legacy, sustituidos por A24 y B17), A89 (no existe en la API).

**Decisión de alcance tras las dos pasadas**

| Entra en la v1 | Fase 2 | Fuera |
|---|---|---|
| A85 precios de desvío (BE, NL, FR, AT, CZ, DK1, DK2, DE país) | A15 capacidad adquirida (paginar) | A83, A88 legacy |
| A86 volumen de desvío (todas salvo DK1, DE-LU) | A87 gastos e ingresos (NL, FR, AT) | A89 |
| A84+A67 CBMP a 4 s (todas salvo DE-LU, Amprion) | A69 intradía y current | vista por frontera de B17 |
| A84+A16 y +A68 precios activación 15 min | B17 mFRR (buscar proceso) | |
| A24 ofertas aFRR/mFRR, SA/DA | A65 semana vista | |
| A81 reservas contratadas (volumen y precio) | Fingrid, Elia componentes | |
| B17+A63 neteo IGCC 15 min y B17+A51 intercambio aFRR 4 s | | |
| A69+A01, A74, A65+A01, A65+A16 (previsión y real) | | |

Peculiaridades técnicas encontradas:

- Los endpoints de balance tardan 10-30 s por petición (los de precios day-ahead, 1-3 s), y ENTSO-E corta la conexión
  de vez en cuando: la ingesta necesita timeout largo, reintento y reanudación.
- A85, A86 y A81 devuelven un **ZIP con uno o varios XML**, no un XML suelto.
- El CBMP viene a 4 s con `curveType` A03 (posiciones omitidas cuando el valor se repite) y 13.000-17.000 puntos por
  día y sentido; un mes por área son 100 MB en XML y 90 s de descarga. Hay que guardar comprimido (gzip ≈ 5 %),
  pedir por meses con un solo hilo y timeout de 5 min, y agregar a 15 min en silver (VWAP, mín., máx., nº ciclos).
  Para 10 áreas y 4 años: ~500 peticiones mensuales y ~2 GB comprimidos.
- La API corta en 100 documentos por petición (lo sufre A15); el resto de datasets caben en una petición mensual.
- Cada TSO publica bajo procesos distintos (A16, A67, A68) y cambia con el tiempo al conectarse a las plataformas:
  la reconciliación por TSO y fecha es parte del trabajo.

## 9. Fuentes complementarias

- **Elia Open Data** (ya hay cliente en grid-lakehouse): precios de desvío por cuarto de hora (`ods134`, desde
  22/05/2024; `ods047` anterior) y por minuto, componentes del precio (`ods168`), volúmenes y precios activados por
  producto (`ods082`, `ods167`), desequilibrio del sistema y ACE por minuto, previsión de desequilibrio del
  siguiente cuarto de hora. Permite validar Bélgica contra el TP y bajar al minuto.
- **Fingrid Open Data** (API REST, CC-BY): CBMP aFRR cada 3 min, volúmenes con precio marginal, VWAP por cuarto de
  hora. Segunda referencia nacional si se añade Finlandia.
- **ACER CHEST**: tablas de los informes de monitorización (distribución del CBMP por país, precios antes y después
  de conectarse a PICASSO), en CSV. Referencia de validación, no fuente de ingesta.

## 10. El proyecto

**Preguntas que responde**

1. ¿Cuánto cuesta el desvío en cada zona (EUR/MWh desviado, por mes, por hora del día) y cómo ha evolucionado
   desde que los TSO se conectaron a PICASSO y MARI?
2. ¿Convergen los precios de aFRR entre zonas? Porcentaje de cuartos de hora con el mismo CBMP, spread medio y
   máximo, en qué horas y condiciones diverge (saturación de frontera, rampas solares, incidentes).
3. ¿Cuánto se activa en casa y cuánto llega a través de las fronteras (B17 frente a A24)?
4. ¿Qué calidad tiene la previsión renovable y de carga de cada TSO (error absoluto medio, sesgo, por hora del día y
   estación) y cuánto explica del desequilibrio y del precio de desvío?
5. ¿Cuánto cuesta reservar capacidad frente a activar energía, por zona y producto?

**Por qué importa (y a quién)**

- Para un **TSO**: el regulador le pregunta cada año por el coste de su balance y por el efecto de las plataformas;
  compararse con los vecinos con datos públicos, sin esperar al informe de ACER, es útil para su propia narrativa.
- Para un **BRP** (comercializador, productor renovable, agregador): el precio de desvío es un coste directo; saber qué
  horas son caras y cuánto le cuesta cada MW de error de previsión le dice cuánto vale mejorar sus previsiones.
- Para un **BSP** (baterías, centrales flexibles): el CBMP es su ingreso; su evolución y sus picos deciden dónde y
  cuándo merece la pena ofrecer.
- Para un **regulador o analista**: la convergencia de precios entre zonas es el indicador principal de si la
  integración europea del balance funciona.

**Alcance propuesto para la primera versión**

- Áreas: BE, NL, FR, AT, CZ, DK1, DK2 y Alemania (precio de desvío por país; balance por área de control 50Hertz,
  TenneT, TransnetBW; Amprion no publica A84).
- Ventana: CBMP desde junio 2022 (arranque de PICASSO) donde exista; el resto, un año (oct 2025 - oct 2026), como
  en grid-lakehouse.
- Datasets: A85, A86, A84 (A16, A67, A68), A24 (A47, A51, A60, A61), A81, B17 (A63 y A51); y A69 (A01), A74,
  A65 (A01, A16) para la previsión. A87, A15, B17 mFRR y las previsiones intradía quedan para una fase 2.
- Stack y estructura iguales que grid-lakehouse: bronze crudo con log de carga y ventana de revisión (2 días para
  el CBMP, 7 para el resto), silver en Delta/UTC/15 min con MERGE idempotente, gold en dbt sobre DuckDB con tests,
  exportación Parquet y modelo Power BI como código.
- Validación: Bélgica contra Elia Open Data; agregados contra las tablas de ACER.

**Métricas principales (gold)**

- `imbalance_cost_eur_per_mwh`: Σ(|desvío| × precio) / Σ|desvío|, por zona y mes.
- `cbmp_convergence_share`: % de cuartos de hora en que el CBMP (VWAP 15 min) de una zona es igual al de la zona de
  referencia (±1 EUR/MWh); `cbmp_spread_mean`, `cbmp_spread_p95`.
- `cbmp_extreme_share`: % de cuartos de hora con CBMP fuera de [-500, 1000] EUR/MWh (umbral parametrizable).
- `forecast_mae_mw`, `forecast_bias_mw`, `forecast_mape`: por zona, tecnología, hora del día y mes.
- `imbalance_vs_forecast_error_corr`: correlación entre error de previsión y desequilibrio / precio de desvío.
- `capacity_vs_energy_cost`: coste de reservas contratadas frente a coste de energía activada, por zona y producto.

---

## Glosario

| Término | Significado |
|---|---|
| ACE | Area Control Error: desviación instantánea del área de control respecto a su programa de intercambio, corregida por frecuencia |
| ACER | Agencia europea de cooperación de reguladores de energía |
| aFRR | Reserva de restauración de frecuencia automática ("secundaria"), 5 min |
| AOF | Activation Optimisation Function: el algoritmo de PICASSO/MARI que elige qué ofertas activar |
| BRP | Balance Responsible Party: responsable de que su cartera esté en equilibrio; paga el desvío |
| BSP | Balancing Service Provider: vende reservas y energía de balance al TSO |
| CBMP | Cross-Border Marginal Price: precio marginal común de aFRR calculado por PICASSO cada 4 s |
| DA / SA | Direct / Scheduled Activation de mFRR |
| EB GL | Electricity Balancing Guideline, Reglamento (UE) 2017/2195 |
| EIC | Energy Identification Code: identificador de áreas, zonas y participantes |
| FCR | Reserva de contención de frecuencia ("primaria"), segundos |
| IGCC | International Grid Control Cooperation: neteo de desequilibrios entre áreas |
| ISP | Imbalance Settlement Period: periodo de liquidación de desvíos, 15 min |
| LFC area / block | Load-Frequency Control area: área de control de un TSO; varias forman un bloque |
| MARI | Plataforma europea de energía mFRR |
| mFRR | Reserva de restauración de frecuencia manual ("terciaria"), 12,5 min |
| PICASSO | Plataforma europea de energía aFRR |
| RCC | Regional Coordination Centre (Coreso, TSCNET…); no interviene en el balance |
| RR | Replacement Reserve, 30 min; plataforma TERRE |
| Single pricing | Un único precio de desvío por ISP para excedente y déficit |
| TP | ENTSO-E Transparency Platform |
| TSO | Transmission System Operator |
| VWAP | Volume-Weighted Average Price: precio medio ponderado por volumen |
