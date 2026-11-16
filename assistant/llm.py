"""Call a local model through Ollama's HTTP API (standard library only, nothing leaves the machine)."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
# Ollama's default context window is too small for the schema description; without this the
# prompt is silently truncated and the model never sees the last tables.
NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "12288"))


# A general multilingual model reads the documents, writes the answers and routes the questions;
# the code model above only writes SQL.
WRITER_MODEL = os.environ.get("OLLAMA_WRITER_MODEL", "gemma3:12b")
# Multilingual embedding model: the project's notes are in Spanish and English, questions come in three languages.
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3")


class LLMError(Exception):
    pass


def _post(path, payload, attempts=3):
    """POST to Ollama. A crashed model runner (HTTP 5xx) is retried: Ollama reloads the model on the next call."""
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(f"{OLLAMA_URL}{path}", data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            if exc.code < 500 or attempt == attempts:
                raise LLMError(f"Ollama answered {exc.code}: {detail}") from exc
            print(f"  Ollama answered {exc.code}, retrying ({attempt}/{attempts - 1})...", file=sys.stderr)
            time.sleep(10)
        except urllib.error.URLError as exc:
            raise LLMError(f"cannot reach Ollama at {OLLAMA_URL} ({exc.reason}); is it running?") from exc


def embed(texts, model=EMBED_MODEL):
    """One vector per text."""
    return _post("/api/embed", {"model": model, "input": list(texts)})["embeddings"]


def chat(messages, model=DEFAULT_MODEL):
    """messages: [{'role': 'system'|'user'|'assistant', 'content': str}] -> the model's reply."""
    return _post("/api/chat", {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0, "seed": 0, "num_ctx": NUM_CTX},
    })["message"]["content"]
