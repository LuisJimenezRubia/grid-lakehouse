"""Compute the expected answers of the golden question set from the gold layer.

Runs each reference_sql of eval/golden_questions.yaml against data/gold/grid.duckdb (read-only)
and writes eval/expected_answers.json. Rerun after every gold refresh so the expected answers
follow the data.

Usage (from the project root):  python3 eval/build_expected.py
"""
import datetime as dt
import json
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "golden_questions.yaml"
DB = ROOT / "data" / "gold" / "grid.duckdb"
OUT = ROOT / "eval" / "expected_answers.json"


def to_json(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if hasattr(value, "__float__") and not isinstance(value, (int, float, bool)):
        return float(value)
    return value


def main():
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    con = duckdb.connect(str(DB), read_only=True)
    data_range = con.sql("select min(market_date), max(market_date) from gold.dim_date").fetchone()

    answers, errors = {}, []
    for q in questions:
        if q["type"] != "sql":
            continue
        try:
            rel = con.sql(q["reference_sql"])
            cols = rel.columns
            rows = [{c: to_json(v) for c, v in zip(cols, row)} for row in rel.fetchall()]
            answers[q["id"]] = {"question": q["question"], "rows": rows}
        except Exception as exc:  # report every broken query, not just the first
            errors.append(f"{q['id']}: {exc}")

    OUT.write_text(json.dumps({
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "data_range": [d.isoformat() for d in data_range],
        "answers": answers,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{len(answers)} answers written to {OUT.relative_to(ROOT)}; data {data_range[0]} to {data_range[1]}")
    if errors:
        print("Errors:\n  " + "\n  ".join(errors))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
