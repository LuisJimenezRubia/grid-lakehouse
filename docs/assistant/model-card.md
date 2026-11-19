# Assistant — system card

Version 1, 16 November 2026. Owner: Luis Jimenez Rubia (Magic Byte SRL).

## What it is

A question-answering assistant over this lakehouse. It answers two kinds of question:

- **Data questions** ("What was the average Belgian day-ahead price in January 2026?"). A model writes
  one SQL query, the query runs read-only on the gold layer, and a short answer is written from the
  result. The SQL is always shown.
- **Concept questions** ("What does `against_price` mean?"). The closest passages of the project's own
  documentation are retrieved and the answer is written from them, citing the file of each statement.

It runs entirely on one machine. No question, data or answer leaves it.

## Intended use and limits of use

| | |
|---|---|
| Intended use | Exploring the gold layer and its documentation; a demonstration of how to build and evaluate such an assistant. |
| Intended users | The author, and readers of the repository who run it themselves. |
| Not for | Operational, trading or regulatory decisions; statements on whether a TSO complies with the 70 % rule; forecasts; any use without a person checking the SQL or the sources. |
| Human oversight | The assistant only answers. It takes no action and changes no data. Every answer comes with the evidence needed to check it. |

## Components

| Step | What does it | Model |
|---|---|---|
| Routing: data or concept | `assistant/ask.py` | gemma3:12b |
| Writing the SQL | `assistant/text_to_sql.py` | qwen2.5-coder:14b |
| Running the SQL | `assistant/guard.py` on DuckDB | none |
| Finding passages | `assistant/retriever.py` | bge-m3 (embeddings) |
| Writing the answer | `assistant/ask.py`, `assistant/doc_rag.py` | gemma3:12b |

All three are open-weight models served locally by Ollama, at temperature 0. They are used as
published; nothing is fine-tuned. Their licences are on each model's page and should be checked
before any commercial use.

## Data

- **Gold layer** (`data/gold/grid.duckdb`): public data from the ENTSO-E Transparency Platform, Elia
  Open Data and the JAO Publication Tool, 1 October 2025 to 12 October 2026. No personal data.
- **Documents**: `README.md`, `docs/*.md`, the dbt variables and one passage per gold model (its
  description and its commented SQL). 50 passages. Regulations and third-party documentation are
  not included.
- **What the SQL model is told**: tables, columns, grain, a glossary and conventions, all generated
  from the dbt project and the database (`assistant/context.py`).

## Lineage of an answer

Source API → bronze (raw response per market day) → silver (Delta, MERGE on the natural key) → gold
(dbt models with tests) → the query the model wrote → the answer. For a concept question: file in
this repository → passage → answer with the file cited. Each question is logged with its SQL or its
cited files (`assistant/audit.py`, log in `data/assistant/log/`, not in the repository).

## Evaluation

Golden set of 48 questions (`eval/golden_questions.yaml`): 32 data questions with reference SQL,
9 concept questions with expected key points and sources, 7 traps. Results in `eval/results/`.

**Data questions** (`eval/run_eval.py`; the result must match the reference within 1 %):

| Run | Data questions | Traps declined |
|---|---|---|
| qwen2.5-coder:7b, first context | 8/32 (25 %) | 4/6 |
| qwen2.5-coder:7b, context with grain, glossary and examples | 14/32 (44 %) | 5/6 |
| qwen2.5-coder:14b, same context | 26/32 (81 %) | 6/6 |

By topic, for the 14b run: prices 10/10, Belgian system 4/4, calendar 1/1, flow-based 6/8,
flows 3/5, forecasts 1/2, data quality 1/2.

**Concept questions and routing** (`eval/run_eval_docs.py`, gemma3:12b with bge-m3):

| Measure | Result |
|---|---|
| Expected file among the 4 passages retrieved | 9/9 |
| Answer cites an expected file | 9/9 |
| Expected key points found in the answer (judged by the model itself) | 14/18 |
| Questions passed (retrieval, citation and two thirds of the key points) | 7/9 |
| Routing of the 41 data and concept questions | 41/41 |

**How far to trust these numbers**

- The context given to the SQL model was improved after reading the failures of this same set, so
  81 % is optimistic. A held-out set of new questions is pending.
- Key points are judged by the model that wrote the answer. A manual read found one answer wrongly
  failed by the judge and one error the judge missed in an earlier run.
- Small set, one run per configuration.
- The trap on legal judgement (figures plus a caveat) is not scored automatically.

## Known limitations

- About one data answer in five is wrong on the test set, and a wrong answer looks as confident as a
  right one. The typical error is averaging monthly percentages instead of recomputing them over the
  whole period.
- The 7b model is not usable for this task; 14b needs roughly 10 GB of memory and 5 to 30 seconds per
  question on a laptop.
- Answers to broad concept questions can be correct but incomplete.
- It does not warn when a figure rests on days still marked `provisional`.
- "Last month" and similar expressions have no anchor: the assistant does not know today's date and
  the data ends on a fixed day.
- English, Spanish and French questions work; the test set is mostly English.

## Safeguards

See [risk-assessment.md](risk-assessment.md) for the risks and the EU AI Act self-assessment.
