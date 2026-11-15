"""Answer a question about the gold layer by having the model write one SELECT.

Flow: question -> model writes SQL -> guard checks it is a single read-only SELECT -> DuckDB runs it.
If the SQL fails, the error goes back to the model once. The SQL is always returned, so every
number can be checked.

Usage (from the project root):
    python -m assistant.text_to_sql "What was the average Belgian day-ahead price in January 2026?"
"""
import argparse
import re
import sys

import duckdb

from assistant import context, guard, llm

SYSTEM = """You write DuckDB SQL to answer questions about a Belgian electricity-market data warehouse.

Rules:
- Answer with exactly one SELECT statement inside a ```sql block, and nothing else.
- Use only the tables and columns described below, with the schema prefix (gold.x, reference.x).
  Never use a column that is not listed for that table.
- Read "One row per" before writing: filter or group by every column of the grain that the question
  fixes. A table with one row per bidding_zone needs bidding_zone = 'BE' for a Belgian figure.
- "What was the highest/lowest X and when": ORDER BY X DESC (or ASC) LIMIT 1 and select the time
  column. Never use ANY_VALUE.
- "Which ... highest/lowest": GROUP BY the thing asked, ORDER BY the measure, LIMIT 1.
- mart_monthly_ tables have one row per month. Use them as they are only for a question about one
  month. For a longer period never average their percentages or averages: recompute from the fct_
  table, or SUM their counts and sums with GROUP BY.
- A share or percentage is 100.0 * count(*) FILTER (WHERE condition) / count(*) over the right rows.
- For a month that is not a column, use date_trunc('month', market_date)::date.
- An average flow in MW is avg(), not sum(). Energy: MWh = sum(MW) * 0.25, GWh = MWh / 1000.
- When the question asks for two things (a total and the top item, or a value for each of two days),
  return all of them, one row per item when the items are separate.
- Round results to 2 decimals. Percentages go from 0 to 100.
- You cannot change data. If the question asks to modify or delete anything, asks for something
  that is not in these tables (another country, a date outside the data range, a forecast of the
  future, files, secrets), or cannot be answered without guessing a date such as "last month",
  do not write SQL. Answer with one line starting with NO_SQL: and the reason.
- Do not answer NO_SQL because of an unfamiliar word: check the GLOSSARY first.

Examples (the pattern matters, not the numbers):

Q: What was the lowest French day-ahead price and when?
```sql
SELECT price_eur_mwh, interval_start_local
FROM gold.fct_day_ahead_price
WHERE bidding_zone = 'FR'
ORDER BY price_eur_mwh ASC
LIMIT 1
```

Q: Over the whole period, in what share of quarter-hours did Belgium export to Germany?
```sql
SELECT round(100.0 * count(*) FILTER (WHERE net_export_mw_elia > 0) / count(*), 2) AS pct_exporting
FROM gold.fct_cross_border_flow
WHERE neighbour = 'DE'
```

Q: Which month had the highest average Belgian load?
```sql
SELECT date_trunc('month', market_date)::date AS month, round(avg(load_mw), 2) AS avg_load_mw
FROM gold.fct_be_system
GROUP BY 1
ORDER BY avg_load_mw DESC
LIMIT 1
```

Q: Over the whole period, which Core TSO had the highest share of CNEC-hours with a validation reduction (IVA)?
```sql
SELECT c.tso, round(100.0 * count(*) FILTER (WHERE c.has_iva) / count(*), 2) AS pct_with_iva
FROM gold.fct_cnec_hourly c
JOIN reference.tsos t ON t.tso = c.tso AND t.is_core_tso
GROUP BY c.tso
ORDER BY pct_with_iva DESC
LIMIT 1
```

Q: Which RTE constraint was active in the most quarter-hours?
```sql
SELECT cnec_name, sum(quarters_active) AS quarters_active
FROM gold.mart_monthly_active_constraints
WHERE tso = 'RTE'
GROUP BY cnec_name
ORDER BY quarters_active DESC
LIMIT 1
```

{context}"""

SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_sql(reply):
    match = SQL_BLOCK.search(reply)
    sql = (match.group(1) if match else reply).strip()
    return sql.rstrip(";").strip()


class Assistant:
    def __init__(self, model=llm.DEFAULT_MODEL, generate=None):
        """generate(messages) -> reply text; defaults to the local Ollama model."""
        self.con = guard.connect()
        self.model = model
        self.system = SYSTEM.format(context=context.build(self.con))
        self.generate = generate or (lambda messages: llm.chat(messages, model=model))

    def ask(self, question, max_attempts=2):
        """Returns a dict: status ('ok' | 'no_sql' | 'error'), sql, columns, rows, message, attempts."""
        messages = [{"role": "system", "content": self.system}, {"role": "user", "content": question}]
        result = {"status": "error", "sql": None, "columns": [], "rows": [], "message": "", "attempts": 0}
        for attempt in range(1, max_attempts + 1):
            result["attempts"] = attempt
            reply = self.generate(messages)
            if reply.strip().upper().startswith("NO_SQL"):
                return {**result, "status": "no_sql", "message": reply.strip()}
            sql = extract_sql(reply)
            result["sql"] = sql
            try:
                columns, rows = guard.run(self.con, sql)
                return {**result, "status": "ok", "columns": columns, "rows": rows}
            except (guard.RejectedSQL, duckdb.Error) as exc:
                result["message"] = f"{type(exc).__name__}: {exc}"
                messages += [{"role": "assistant", "content": reply},
                             {"role": "user", "content": f"That query failed:\n{exc}\nWrite a corrected query."}]
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    parser.add_argument("--model", default=llm.DEFAULT_MODEL)
    args = parser.parse_args()
    try:
        answer = Assistant(model=args.model).ask(args.question)
    except llm.LLMError as exc:
        sys.exit(str(exc))
    if answer["sql"]:
        print(answer["sql"], "\n")
    if answer["status"] == "ok":
        print(" | ".join(answer["columns"]))
        for row in answer["rows"][:20]:
            print(" | ".join(str(value) for value in row))
    else:
        print(answer["message"])


if __name__ == "__main__":
    main()
