"""Describe the gold layer to the model: tables, columns, meaning and conventions.

Everything comes from what the project already documents - the dbt schema.yml descriptions,
the comment at the top of each model and the database itself - so the description cannot drift
from the data. Rebuilt on every start; nothing is stored.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MARTS = ROOT / "gold" / "models" / "marts"
SCHEMAS = ("gold", "reference")
MAX_DISTINCT = 20      # text columns with at most this many values get their values listed
# Grain of the models that have no uniqueness test in schema.yml to read it from.
GRAIN_FALLBACK = {
    "mart_daily_price_spread": ["market_date", "neighbour"],
    "mart_daily_forecast_accuracy": ["market_date", "metric"],
    "mart_monthly_active_constraints": ["month", "tso", "cnec_name", "contingency_name", "direction", "hub_from", "hub_to"],
    "bidding_zones": ["bidding_zone"], "borders": ["neighbour"], "tsos": ["tso"],
}


def _dbt_docs():
    """Model and column descriptions, and accepted values, from the marts schema.yml."""
    docs = {}
    for model in yaml.safe_load((MARTS / "schema.yml").read_text(encoding="utf-8"))["models"]:
        columns, grain = {}, None
        for test in model.get("tests", []):            # the uniqueness tests state the grain
            if isinstance(test, dict) and "unique_combination" in test:
                grain = test["unique_combination"]["arguments"]["columns"]
        for column in model.get("columns", []):
            if column.get("description"):
                columns[column["name"]] = " ".join(column["description"].split())
            if "unique" in column.get("tests", []):
                grain = [column["name"]]
        docs[model["name"]] = {"description": " ".join(model.get("description", "").split()),
                               "columns": columns, "grain": grain}
    return docs


def _model_comment(table):
    """The comment block at the top of the model's SQL (the author's notes on meaning and sign)."""
    path = MARTS / f"{table}.sql"
    if not path.exists():
        return ""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("--"):
            break
        lines.append(line[2:].strip())
    return "\n".join(line for line in lines if line)


def build(con):
    docs = _dbt_docs()
    first_day, last_day = con.sql("select min(market_date), max(market_date) from gold.dim_date").fetchone()
    parts = []
    tables = con.sql(
        "select table_schema, table_name from information_schema.tables "
        f"where table_schema in {SCHEMAS} order by table_schema, table_name").fetchall()
    for schema, table in tables:
        doc = docs.get(table, {"description": "", "columns": {}, "grain": None})
        block = [f"TABLE {schema}.{table}"]
        if doc["description"]:
            block.append(f"  {doc['description']}")
        grain = doc["grain"] or GRAIN_FALLBACK.get(table)
        if grain:
            block.append(f"  One row per: {', '.join(grain)}")
        comment = _model_comment(table)
        if comment:
            block.append("  Notes (author's, in Spanish):\n" + "\n".join(f"    {line}" for line in comment.splitlines()))
        columns = con.sql(
            "select column_name, data_type from information_schema.columns "
            f"where table_schema = '{schema}' and table_name = '{table}' order by ordinal_position").fetchall()
        for name, data_type in columns:
            line = f"  - {name} {data_type}"
            if data_type == "VARCHAR":
                values = [row[0] for row in con.sql(
                    f'select distinct "{name}" from {schema}.{table} where "{name}" is not null '
                    f"limit {MAX_DISTINCT + 1}").fetchall()]
                if len(values) <= MAX_DISTINCT:
                    line += " values: " + ", ".join(sorted(map(str, values)))
            if name in doc["columns"]:
                line += f" -- {doc['columns'][name]}"
            block.append(line)
        parts.append("\n".join(block))

    conventions = f"""CONVENTIONS
- Data covers market days {first_day} to {last_day}. There is no data outside this range.
- market_date is the market day in Brussels time. interval_start_utc is UTC; interval_start_local is Brussels time.
- month columns are the first day of the month (DATE), e.g. DATE '2026-07-01' for July 2026.
- Fact tables are quarter-hourly unless the name says hourly. Energy in MWh = MW * 0.25 per quarter-hour.
- Net export is positive when Belgium exports and negative when Belgium imports.
- neighbour is the country on the other side of a Belgian border; bidding_zone is a price zone (Germany is DE_LU).
- Spreads are Belgium minus the neighbour.

FACTS THAT QUERIES OFTEN MISS
- Period: if the question names no period, or says "over the whole period", use all the data. Never add a month
  or date filter that the question does not ask for.
- Elia: "Elia", "Elia's" or "Belgian" for a CNEC or constraint means tso = 'ELIA' (or the boolean is_elia).
  Without that filter the result covers every TSO.
- Core TSOs: gold.fct_cnec_hourly also holds TSOs outside Core (e.g. SWISSGRID). "Core TSO" means
  JOIN reference.tsos t ON t.tso = c.tso AND t.is_core_tso.
- gold.fct_day_ahead_price has one row per bidding_zone and quarter-hour: a Belgian price needs bidding_zone = 'BE'.
- year, month, day_name, is_weekend and quarters_in_day exist only in gold.dim_date; join it on market_date.
  Weekend versus weekday is GROUP BY is_weekend, not by day_name.
- Hour of the day in Brussels time is hour(interval_start_local), an integer from 0 to 23, not a time value.
- Boolean columns (meets_min_ram_target, has_amr, has_iva, is_elia, is_weekend, is_core_tso) go inside
  count(*) FILTER (WHERE column). They cannot be summed.
- pct_ columns are already percentages from 0 to 100 for one month; never multiply them by 100 or by a count.
- Additive columns of the monthly marts, safe to SUM over months with GROUP BY: quarters_active,
  sum_shadow_price_eur_mw, cnec_hours. Everything else in them (pct_, avg_, distinct_) is not additive:
  recompute it from the fact table (fct_cnec_hourly, fct_border_flow_price, fct_border_commercial_physical).
- A CNEC is identified by tso and cnec_name (cne_name in gold.fct_cnec_hourly). To rank CNECs over a period,
  GROUP BY tso, cnec_name and SUM; one monthly row is not the ranking.

GLOSSARY
- CNEC / critical network element / constraint: a line or an external constraint monitored in Core flow-based
  capacity calculation. gold.fct_cnec_hourly holds every CNEC of the final domain (cne_name) with its margin.
- Binding or active constraint, bottleneck, "limits the market": a CNEC with shadow price > 0;
  see gold.mart_monthly_active_constraints (cnec_name, quarters_active, sum_shadow_price_eur_mw).
- External constraint: an import or export limit of a bidding zone, not a line; its name starts with 'External Constraint'.
- minRAM target / 70 % rule: meets_min_ram_target in gold.fct_cnec_hourly, per CNEC and hour (a CNEC-hour).
- AMR: adjustment to reach the minimum RAM (has_amr). IVA: reduction by a TSO in validation (has_iva).
- Price convergence: Belgian and neighbour prices are equal (flow_vs_price = 'converged').
- Meaningful price signal: flow_vs_price is 'with_price' or 'against_price'. Shares of flow against price
  are computed over those quarter-hours only.
- Unscheduled flow: physical minus commercial net export (loop and transit flows).
- Residual load: load minus wind and solar."""
    return conventions + "\n\n" + "\n\n".join(parts)
