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


def _dbt_docs():
    """Model and column descriptions, and accepted values, from the marts schema.yml."""
    docs = {}
    for model in yaml.safe_load((MARTS / "schema.yml").read_text(encoding="utf-8"))["models"]:
        columns = {}
        for column in model.get("columns", []):
            if column.get("description"):
                columns[column["name"]] = " ".join(column["description"].split())
        docs[model["name"]] = {"description": " ".join(model.get("description", "").split()), "columns": columns}
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
        doc = docs.get(table, {"description": "", "columns": {}})
        block = [f"TABLE {schema}.{table}"]
        if doc["description"]:
            block.append(f"  {doc['description']}")
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
- Spreads are Belgium minus the neighbour."""
    return conventions + "\n\n" + "\n\n".join(parts)
