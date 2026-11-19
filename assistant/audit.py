"""Keep a record of every question and answer.

One JSON line per question in data/assistant/log/questions.jsonl (data/ is not in the repository):
when, what was asked, which path and models answered, the SQL that ran or the files cited, the
answer given and how long it took. It is what allows a wrong answer to be traced back afterwards.
The log stays on this machine. Questions are stored as typed, so do not put personal data in them.
"""
import datetime as dt
import json
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "data" / "assistant" / "log" / "questions.jsonl"


def record(question, result, models, seconds, path=LOG):
    entry = {
        "at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "question": question,
        "route": result["route"],
        "models": models,
        "status": result.get("status", "ok"),
        "sql": result.get("sql"),
        "rows_returned": len(result["rows"]) if "rows" in result else None,
        "retrieved": [p["sources"][0] for p in result.get("retrieved", [])] or None,
        "cited": result.get("cited"),
        "answer": result["answer"],
        "seconds": round(seconds, 1),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
