# Assistant — risk assessment and EU AI Act self-assessment

16 November 2026. A self-assessment by the author, not legal advice.

## EU AI Act classification

Regulation (EU) 2024/1689 as amended by the AI Omnibus, Regulation (EU) 2026/1744, in force since
27 July 2026.

| Question | Answer | Why |
|---|---|---|
| Is it an AI system? | Yes | It uses language models to generate SQL and text from a question. |
| Prohibited practice (Article 5)? | No | No manipulation, scoring of people, biometric use or any other listed practice. |
| High-risk under Annex III, point 2 (critical infrastructure)? | No | That point covers AI systems intended to be used as safety components in the management and operation of critical infrastructure, including the supply of electricity. This assistant reads published historical market data; it is not part of managing or operating a grid and no safety function depends on it. |
| High-risk under Annex I (safety component of a regulated product)? | No | It is not a product or part of one. |
| Other Annex III areas (employment, credit, law enforcement and so on)? | No | It processes no data about people. |
| Result | Not high-risk; minimal risk | |

**Obligations that still matter**

- **Transparency (Article 50), applicable since 2 August 2026.** A system that interacts directly with
  people must make clear that they are dealing with AI. The command line prints a notice with every
  answer; a future user interface must do the same.
- **AI literacy (Article 4).** Whoever uses the assistant should understand what it can get wrong.
  The system card states it.
- **General-purpose AI models.** The obligations for the models themselves sit with their providers.
  This project only uses them.

High-risk obligations for Annex III systems apply from 2 December 2027 and do not apply here.

**What would change this assessment**

- Using the answers in the operation of a grid, in capacity calculation or in any process a TSO or
  a coordination centre relies on: reassess against Annex III, point 2.
- Adding data about people (operators, traders, users of the tool): GDPR applies and the Annex III
  areas must be checked again.
- Offering it to other people or organisations as a service: the provider obligations, including
  Article 50 in full, apply to whoever offers it, and the user organisation's own AI policy and
  inventory apply too.
- The Commission's guidelines on high-risk classification were in draft when this was written and
  were not reviewed for this assessment.

## Risk register

| # | Risk | Seen in testing | Safeguard | What remains |
|---|---|---|---|---|
| 1 | A plausible query gives a wrong number | Yes: 6 of 32 with the 14b model | SQL always shown; table grain and glossary given to the model; golden set rerun on every change | About one in five wrong on the test set. A person must read the SQL before using a figure. |
| 2 | An explanation states something the documents do not say | Yes: "two days" for a 7-day window, an invented meaning of an acronym | Answers only from retrieved passages, with the file cited; a general model writes instead of the code model; dbt variables shown with their value | Not zero. The cited file must be opened for anything that matters. |
| 3 | The model is talked into changing or deleting data | Attempted in the trap set; declined | Database opened read-only; one SELECT only, checked with the database's own parser | None known. |
| 4 | The model is talked into reading files or secrets | Attempted in the trap set; declined, and the query path cannot read files | External file access switched off and configuration locked in DuckDB; the token is not in the corpus or the database | None known. |
| 5 | Instructions hidden in a document steer the answer | Not tested | The corpus is only this repository's own files; the model is told that source text is material, not instructions | Open if third-party documents are added. |
| 6 | An indicative figure is read as a legal finding (70 % rule) | Not scored | Writing rule: never state compliance or breach, mention derogations and action plans | Not evaluated automatically. |
| 7 | A figure rests on provisional days | Not tested | Gold marks those days | The assistant does not warn about it. |
| 8 | Test results flatter the system | Yes, by construction | Stated in the system card | Held-out questions and a second judge are pending. |
| 9 | Data or questions leave the machine | No | Everything runs locally; the log is local and outside the repository | None while it stays local. |
| 10 | The model runner crashes mid-answer | Yes, once | Automatic retry | Slow answers on a laptop. |

## Open actions

1. Write and run a held-out set of about ten questions.
2. Score the legal-judgement trap, with a written answer and a second judge.
3. Warn when the queried period includes provisional days.
4. Show the AI notice in the user interface when there is one.
5. Review this assessment when the Commission's high-risk guidelines are final.
