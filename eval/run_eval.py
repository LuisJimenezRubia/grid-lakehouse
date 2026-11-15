"""Score the text-to-SQL assistant against the golden question set.

For every 'sql' question the assistant writes a query, the query runs read-only, and its result
is compared with eval/expected_answers.json. Numbers match within 1 % (or 0.06 absolute, for
rounding); names and dates must be equal. Column names are ignored: each expected value must
appear somewhere in the matching row. Scoring is strict on purpose - a right answer in another
shape (a fraction instead of a percentage, "July" instead of 2026-07-01) counts as a miss, and
the saved file shows both results so the miss can be judged by eye.

'trap' questions pass when the assistant declines (NO_SQL) instead of running a query. The
legal-judgement trap is skipped: its right answer is figures plus a caveat, which needs the
written answer. 'doc' questions belong to the document-RAG path and are skipped here.

Usage (from the project root):
    python eval/run_eval.py                        # default model
    python eval/run_eval.py --model llama3.1:8b    # another Ollama model
    python eval/run_eval.py --selftest             # check the harness itself: feeds the reference SQL
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant import llm                       # noqa: E402
from assistant.text_to_sql import Assistant     # noqa: E402

QUESTIONS = ROOT / "eval" / "golden_questions.yaml"
EXPECTED = ROOT / "eval" / "expected_answers.json"
RESULTS = ROOT / "eval" / "results"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def to_json(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if hasattr(value, "__float__") and not isinstance(value, (int, float, bool)):
        return float(value)
    return value


def value_matches(expected, actual):
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)):
        if not isinstance(actual, (int, float)):
            return False
        return abs(actual - expected) <= max(0.01 * abs(expected), 0.06)
    expected, actual = str(expected).strip(), str(actual).strip()
    if ISO_DATE.match(expected):        # dates and timestamps: compare the part the expected answer gives
        return actual.replace(" ", "T").startswith(expected)
    return expected.lower() == actual.lower()


def row_matches(expected_row, actual_row):
    """Every expected value is found in the actual row, each actual value used at most once."""
    remaining = list(actual_row)
    for expected in expected_row.values():
        for index, actual in enumerate(remaining):
            if value_matches(expected, actual):
                del remaining[index]
                break
        else:
            return False
    return True


def result_matches(expected_rows, actual_rows):
    if len(expected_rows) == 1:         # a single answer must be the first row, not buried in a ranking
        return bool(actual_rows) and row_matches(expected_rows[0], actual_rows[0])
    remaining = list(actual_rows)
    for expected in expected_rows:
        for index, actual in enumerate(remaining):
            if row_matches(expected, actual):
                del remaining[index]
                break
        else:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=llm.DEFAULT_MODEL)
    parser.add_argument("--selftest", action="store_true", help="feed the reference SQL instead of calling a model")
    parser.add_argument("--only", nargs="*", help="question ids to run, e.g. --only N01 N17")
    args = parser.parse_args()

    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))["answers"]
    by_question = {q["question"]: q for q in questions}

    def reference(messages):            # the "model" of the self-test
        q = by_question[messages[1]["content"]]
        return f"```sql\n{q['reference_sql']}```" if q["type"] == "sql" else "NO_SQL: declined"

    model = "selftest" if args.selftest else args.model
    assistant = Assistant(model=model, generate=reference if args.selftest else None)

    records, totals = [], defaultdict(lambda: [0, 0])
    for q in questions:
        if q["type"] == "doc" or q["category"] == "legal_judgement" or (args.only and q["id"] not in args.only):
            continue
        started = time.time()
        try:
            answer = assistant.ask(q["question"])
        except llm.LLMError as exc:
            sys.exit(str(exc))
        rows = [[to_json(value) for value in row] for row in answer["rows"]]
        if q["type"] == "sql":
            passed = answer["status"] == "ok" and result_matches(expected[q["id"]]["rows"], rows)
            wanted = expected[q["id"]]["rows"]
        else:
            passed = answer["status"] == "no_sql"
            wanted = q["expected_behaviour"]
        for key in ("all", q["type"], f"{q['type']}/{q['category']}"):
            totals[key][0] += passed
            totals[key][1] += 1
        records.append({"id": q["id"], "type": q["type"], "category": q["category"], "question": q["question"],
                        "passed": passed, "status": answer["status"], "attempts": answer["attempts"],
                        "seconds": round(time.time() - started, 1), "sql": answer["sql"],
                        "message": answer["message"], "expected": wanted, "actual": rows[:5]})
        print(f"{'PASS' if passed else 'FAIL'}  {q['id']}  {answer['status']:<6}  {records[-1]['seconds']:>5}s  {q['question'][:70]}")

    print()
    for key in sorted(totals):
        ok, total = totals[key]
        print(f"{key:<24} {ok:>2}/{total:<2}  {100 * ok / total:5.1f} %")

    if args.selftest:                   # nothing to keep: the self-test only proves the harness
        return
    RESULTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out = RESULTS / f"text_to_sql_{re.sub(r'[^A-Za-z0-9.-]', '_', model)}_{stamp}.json"
    out.write_text(json.dumps({"model": model, "run_at": stamp, "totals": totals, "questions": records},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDetails in {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
