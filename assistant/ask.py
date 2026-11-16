"""Ask the assistant anything about the lakehouse: it picks the path and answers in words.

  DATA     a number, date, name or ranking -> text-to-SQL over the gold layer, then a short answer
           that shows the SQL it ran.
  CONCEPT  what something means, why it happens, how the project handles it -> the project's
           documents, with the files cited.

Usage (from the project root):
    python -m assistant.ask "What is the shadow price of a CNEC?"
    python -m assistant.ask "Which month had the highest average solar generation in Belgium?"
"""
import argparse
import sys

from assistant import llm
from assistant.doc_rag import DocAssistant
from assistant.text_to_sql import Assistant as SqlAssistant

ROUTER = """Classify the question about an electricity-market data warehouse. Answer with one word.

CONCEPT - asks what a term, column, status or indicator means, why something happens, what the
          difference between two things is, or how the project handles or measures something.
DATA    - asks for a number, a date, a name, a count, a ranking or a comparison computed from the
          data; or asks to change data; or anything else."""

WRITER = """Write the answer to the question from the query result. Rules:
- One to three sentences, in the language of the question, with units.
- Use only the numbers in the result. Say which period the figure covers.
- Net export: positive means Belgium exports, negative means Belgium imports.
- minRAM and 70 % figures are indicative: never say that a TSO complies with or breaks the law;
  say that derogations and action plans apply and that this is not a legal assessment.
- If the result has no rows, say that there is no data for what was asked."""


class GridAssistant:
    def __init__(self, model=llm.DEFAULT_MODEL, generate=None, retriever=None):
        self.generate = generate or (lambda messages: llm.chat(messages, model=model))
        self.sql = SqlAssistant(model=model, generate=self.generate)
        self._docs, self._retriever = None, retriever

    @property
    def docs(self):                     # built on first use: the document index needs the embedding model
        if self._docs is None:
            self._docs = DocAssistant(generate=self.generate, retriever=self._retriever)
        return self._docs

    def route(self, question):
        reply = self.generate([{"role": "system", "content": ROUTER}, {"role": "user", "content": question}])
        return "concept" if "CONCEPT" in reply.upper() else "data"

    def ask(self, question):
        """Returns a dict: route, answer, and the evidence (sql + rows, or retrieved + cited)."""
        if self.route(question) == "concept":
            return {"route": "concept", **self.docs.ask(question)}
        result = self.sql.ask(question)
        if result["status"] == "ok":
            table = "\n".join(" | ".join(str(v) for v in row) for row in [result["columns"]] + result["rows"][:20])
            answer = self.generate([{"role": "system", "content": WRITER}, {"role": "user", "content":
                                    f"Question: {question}\n\nSQL:\n{result['sql']}\n\nResult:\n{table}"}]).strip()
        elif result["status"] == "no_sql":
            answer = result["message"].split(":", 1)[-1].strip()
        else:
            answer = f"I could not write a working query for this question ({result['message']})."
        return {"route": "data", "answer": answer, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    parser.add_argument("--model", default=llm.DEFAULT_MODEL)
    args = parser.parse_args()
    try:
        result = GridAssistant(model=args.model).ask(args.question)
    except llm.LLMError as exc:
        sys.exit(str(exc))
    print(result["answer"], "\n")
    if result["route"] == "concept":
        for passage in result["retrieved"]:
            print(f"  source ({passage['score']}): {passage['sources'][0]} - {passage['title']}")
    elif result["sql"]:
        print(result["sql"])


if __name__ == "__main__":
    main()
