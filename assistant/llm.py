"""Call a local model through Ollama's HTTP API (standard library only, nothing leaves the machine)."""
import json
import os
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
# Ollama's default context window is too small for the schema description; without this the
# prompt is silently truncated and the model never sees the last tables.
NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "12288"))


class LLMError(Exception):
    pass


def chat(messages, model=DEFAULT_MODEL):
    """messages: [{'role': 'system'|'user'|'assistant', 'content': str}] -> the model's reply."""
    body = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0, "seed": 0, "num_ctx": NUM_CTX},
    }).encode("utf-8")
    request = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read())["message"]["content"]
    except urllib.error.HTTPError as exc:
        raise LLMError(f"Ollama answered {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"cannot reach Ollama at {OLLAMA_URL} ({exc.reason}); is it running?") from exc
