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
- Prefer a mart_ table when it already holds the answer; otherwise aggregate a fct_ table.
- Return only what the question asks: for "which ... highest/lowest" return the top row with LIMIT 1.
- Round results to 2 decimals. Percentages go from 0 to 100.
- You cannot change data. If the question asks to modify or delete anything, asks for something
  that is not in these tables (another country, a date outside the data range, a forecast of the
  future, files, secrets), or cannot be answered without guessing a date such as "last month",
  do not write SQL. Answer with one line starting with NO_SQL: and the reason.

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
