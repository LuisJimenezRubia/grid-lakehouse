"""Score the document path and the router against the golden question set.

For every 'doc' question:
  retrieval  one of the expected source files is among the passages retrieved (automatic);
  citation   the answer cites one of the expected source files (automatic);
  key points share of the expected key points found in the answer. This one is judged by the same
             local model, so read it as an indication and check the saved answers by eye.
A question passes with retrieval, citation and at least two thirds of its key points.

Routing: every 'sql' question must go to the data path and every 'doc' question to the concept path.

Usage (from the project root):
    python eval/run_eval_docs.py                              # default model
    python eval/run_eval_docs.py --model qwen2.5-coder:14b
    python eval/run_eval_docs.py --selftest                   # plumbing only, no Ollama needed
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant import llm                       # noqa: E402
from assistant.ask import GridAssistant         # noqa: E402
from assistant.retriever import Retriever       # noqa: E402

QUESTIONS = ROOT / "eval" / "golden_questions.yaml"
RESULTS = ROOT / "eval" / "results"
JUDGE = ("You check whether an answer states a given point. The wording and the language may differ. "
         "Reply with one word: YES or NO.")


def fake_embed(texts):
    """Self-test only: a bag-of-words vector, so retrieval works on shared words without a model."""
    vectors = []
    for text in texts:
        vector = [0.0] * 512
        for word in re.findall(r"[a-záéíóúñ_0-9]{3,}", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 512] += 1.0
        vectors.append(vector)
    return vectors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=llm.DEFAULT_MODEL)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    by_question = {q["question"]: q for q in questions}

    def fake_generate(messages):        # the "model" of the self-test: routes by type, cites the first passage
        system, user = messages[0]["content"], messages[-1]["content"]
        if system.startswith("Classify"):
            return "CONCEPT" if by_question[user]["type"] == "doc" else "DATA"
        if system.startswith("You check"):
            return "YES"
        return "Answer [1]"

    if args.selftest:
        assistant = GridAssistant(generate=fake_generate, retriever=Retriever(embed=fake_embed, model="selftest", index_path=None))
    else:
        assistant = GridAssistant(model=args.model)

    try:
        routed = [(q, assistant.route(q["question"])) for q in questions if q["type"] in ("sql", "doc")]
        wrong = [q["id"] for q, route in routed if route != ("concept" if q["type"] == "doc" else "data")]

        records = []
        for q in [q for q in questions if q["type"] == "doc"]:
            started = time.time()
            result = assistant.docs.ask(q["question"])
            retrieved = [path for passage in result["retrieved"] for path in passage["sources"]]
            retrieval = any(path in retrieved for path in q["sources"])
            citation = any(path in result["cited"] for path in q["sources"])
            covered = [assistant.generate([{"role": "system", "content": JUDGE}, {"role": "user", "content":
                       f"Answer:\n{result['answer']}\n\nPoint: {point}"}]).strip().upper().startswith("YES")
                       for point in q["key_points"]]
            passed = retrieval and citation and sum(covered) >= 2 * len(covered) / 3
            records.append({"id": q["id"], "question": q["question"], "passed": passed, "retrieval": retrieval,
                            "citation": citation, "key_points": dict(zip(q["key_points"], covered)),
                            "seconds": round(time.time() - started, 1), "answer": result["answer"],
                            "retrieved": [f"{p['score']} {p['sources'][0]} - {p['title']}" for p in result["retrieved"]],
                            "cited": result["cited"], "expected_sources": q["sources"]})
            print(f"{'PASS' if passed else 'FAIL'}  {q['id']}  retrieval={'yes' if retrieval else 'NO '}  "
                  f"citation={'yes' if citation else 'NO '}  key points {sum(covered)}/{len(covered)}  "
                  f"{records[-1]['seconds']:>5}s  {q['question'][:50]}")
    except llm.LLMError as exc:
        sys.exit(str(exc))

    total = len(records)
    points = [value for record in records for value in record["key_points"].values()]
    summary = {"passed": f"{sum(r['passed'] for r in records)}/{total}",
               "retrieval": f"{sum(r['retrieval'] for r in records)}/{total}",
               "citation": f"{sum(r['citation'] for r in records)}/{total}",
               "key_points_model_judged": f"{sum(points)}/{len(points)}",
               "routing": f"{len(routed) - len(wrong)}/{len(routed)}", "routing_wrong": wrong}
    print()
    for key, value in summary.items():
        print(f"{key:<26} {value}")
    if args.selftest:
        print("\nSelf-test: only checks that every step runs. Its word-count retrieval and canned answers "
              "say nothing about quality.")
        return
    RESULTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out = RESULTS / f"docs_{re.sub(r'[^A-Za-z0-9.-]', '_', args.model)}_{stamp}.json"
    out.write_text(json.dumps({"model": args.model, "embed_model": llm.EMBED_MODEL, "run_at": stamp,
                               "summary": summary, "questions": records}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDetails in {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
