"""The documents the assistant can quote: the project's own documentation, cut into passages.

Sources: README, docs/*.md, the dbt variables, and one passage per gold model (its schema.yml
description plus the SQL with the author's comments). Raw catalogues (docs/catalogo_*.txt) are
left out. Each passage keeps the path of the file it came from, so every answer can cite it.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MARTS = ROOT / "gold" / "models" / "marts"
MARKDOWN = ["README.md", "docs/decisions.md", "docs/notas-fuentes.md", "docs/report-design.md"]
MAX_CHARS = 1500
HEADING = re.compile(r"^(#{1,3})\s+(.*)")
DBT_VAR = re.compile(r"\{\{\s*var\('(\w+)'\)\s*\}\}")


def _split(text):
    """Pack paragraphs into pieces of at most MAX_CHARS (a longer single paragraph stays whole)."""
    pieces, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        if current and len(current) + len(paragraph) > MAX_CHARS:
            pieces.append(current)
            current = ""
        current = f"{current}\n\n{paragraph}".strip()
    if current:
        pieces.append(current)
    return pieces


def _markdown(path):
    title, heading, body, sections = path, "", [], []
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line)
        if match:
            sections.append((heading, "\n".join(body)))
            heading, body = match.group(2).strip(), []
            if match.group(1) == "#":
                title = heading
        else:
            body.append(line)
    sections.append((heading, "\n".join(body)))
    for heading, text in sections:
        for piece in _split(text) if text.strip() else []:
            label = title if heading in ("", title) else f"{title} - {heading}"
            yield {"sources": [path], "title": label, "text": f"{label}\n{piece}"}


def _models():
    schema_path = "gold/models/marts/schema.yml"
    docs = {m["name"]: m for m in yaml.safe_load((ROOT / schema_path).read_text(encoding="utf-8"))["models"]}
    variables = yaml.safe_load((ROOT / "gold" / "dbt_project.yml").read_text(encoding="utf-8")).get("vars", {})
    for sql_file in sorted(MARTS.glob("*.sql")):
        name = sql_file.stem
        doc = docs.get(name, {})
        lines = [f"Gold model {name}", " ".join(doc.get("description", "").split())]
        for column in doc.get("columns", []):
            if column.get("description"):
                lines.append(f"Column {column['name']}: {' '.join(column['description'].split())}")
        # Show thresholds with their value: {{ var('revision_days') }} reads as "7 /* revision_days */".
        sql = DBT_VAR.sub(lambda m: f"{variables[m.group(1)]} /* {m.group(1)} */" if m.group(1) in variables
                          else m.group(0), sql_file.read_text(encoding="utf-8"))
        lines.append(sql[:3000])
        yield {"sources": [f"gold/models/marts/{name}.sql", schema_path], "title": f"Gold model {name}",
               "text": "\n".join(line for line in lines if line)}


def chunks():
    passages = [passage for path in MARKDOWN for passage in _markdown(path)]
    passages += list(_models())
    passages.append({"sources": ["gold/dbt_project.yml"], "title": "dbt variables (tolerances and thresholds)",
                     "text": "dbt variables (tolerances and thresholds)\n"
                             + (ROOT / "gold" / "dbt_project.yml").read_text(encoding="utf-8")})
    for number, passage in enumerate(passages):
        passage["id"] = number
    return passages
