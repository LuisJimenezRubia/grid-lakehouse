"""Read-only execution of model-written SQL.

Three independent locks, so one failing does not open the database:
  1. the DuckDB file is opened read-only;
  2. external access is switched off and the configuration locked, so a query cannot read
     files on disk (read_csv('.env')), attach other databases or install extensions;
  3. the text must be exactly one SELECT statement, checked with DuckDB's own parser.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "gold" / "grid.duckdb"
MAX_ROWS = 200


class RejectedSQL(Exception):
    """The SQL is not a single read-only SELECT."""


def connect(db_path=DB):
    con = duckdb.connect(str(db_path), read_only=True)
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def check(sql):
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as exc:
        raise RejectedSQL(f"not valid SQL: {exc}") from exc
    if len(statements) != 1:
        raise RejectedSQL(f"expected exactly one statement, got {len(statements)}")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise RejectedSQL(f"only SELECT is allowed, got {statements[0].type.name}")
    first_word = sql.lstrip().split(None, 1)[0].lower() if sql.strip() else ""
    if first_word not in ("select", "with", "from"):   # PRAGMA and CALL also parse as SELECT
        raise RejectedSQL(f"the query must start with SELECT or WITH, not {first_word.upper()}")


def run(con, sql):
    """Check and run one SELECT. Returns (column names, rows), at most MAX_ROWS rows."""
    check(sql)
    rel = con.sql(sql)
    return rel.columns, rel.fetchmany(MAX_ROWS)
