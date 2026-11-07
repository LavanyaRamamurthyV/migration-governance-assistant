"""Model-agnostic LLM layer.

One function, `generate()`, works with:
  gemini      Google Gemini (default; free tier from aistudio.google.com)
  claude      Anthropic Claude (needs ANTHROPIC_API_KEY)
  ollama      a local open model such as Llama, running on this machine (no key, works offline)
  extractive  no LLM at all: returns the best-matching passage (used for tests and as a safety net)

Switching providers is a setting, not a code change.
"""
import json
import os
import re
import urllib.request

PROVIDERS = ["gemini", "claude", "ollama", "extractive"]

SYSTEM_PROMPT = """You are the Migration & Governance Assistant for a data migration from a legacy platform to a Target Platform.
Rules:
1. Answer ONLY from the CONTEXT passages below. Never use outside knowledge.
2. Cite every statement with the passage tags in square brackets, for example [S1] or [S1][S3].
3. If the CONTEXT does not contain the answer, reply with exactly: NOT_FOUND
4. Be concise: at most 120 words. Use a short list only when it helps.
5. Values shown as [ID-MASKED], [PHONE-MASKED] and similar are masked on purpose. Never guess them."""


class LlmError(Exception):
    pass


def build_prompt(question: str, chunks) -> str:
    blocks = [f"[S{i}] {c['file']} > {c['section']}\n{c['text']}" for i, c in enumerate(chunks, 1)]
    return "CONTEXT:\n\n" + "\n\n".join(blocks) + f"\n\nQUESTION: {question}\n\nANSWER:"


# ------------------------------------------------------------------ Gemini
_gemini_model = None


def _gemini_candidates(client):
    """Find current Flash models for this API key. Model names change often, so we ask the API."""
    forced = os.getenv("GEMINI_MODEL", "").strip()
    if forced:
        return [forced]
    names = []
    try:
        for m in client.models.list():
            if "generateContent" in (getattr(m, "supported_actions", None) or []):
                names.append(m.name.replace("models/", ""))
    except Exception:
        pass

    def rank(name):
        m = re.match(r"gemini-(\d+(?:\.\d+)?)-flash(-lite)?(-preview.*)?$", name)
        # prefer: full Flash over Flash-Lite, then stable over preview, then newest version
        return None if not m else (0 if m.group(2) else 1, 0 if m.group(3) else 1, float(m.group(1)))

    ranked = sorted((n for n in names if rank(n)), key=rank, reverse=True)
    guesses = ["gemini-flash-latest", "gemini-2.5-flash"]
    seen, out = set(), []
    for n in ranked + guesses:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:4]


def _gemini(prompt, system=None):
    global _gemini_model
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise LlmError("GEMINI_API_KEY is not set (put it in .env or in your Codespaces secrets).")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    candidates = [_gemini_model] if _gemini_model else _gemini_candidates(client)
    last = None
    for model in candidates:
        try:
            resp = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system or SYSTEM_PROMPT, temperature=0))
            _gemini_model = model
            usage = getattr(resp, "usage_metadata", None)
            return dict(text=(resp.text or "").strip(), model=model,
                        in_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                        out_tokens=getattr(usage, "candidates_token_count", 0) or 0)
        except Exception as exc:   # wrong name, quota, network ... try the next candidate
            last = exc
            _gemini_model = None
    raise LlmError(f"Gemini call failed ({type(last).__name__}): {last}")


# ------------------------------------------------------------------ Claude
def _claude(prompt, system=None):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise LlmError("ANTHROPIC_API_KEY is not set.")
    import anthropic
    model = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
    try:
        resp = anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=800, system=system or SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}])
    except Exception as exc:
        raise LlmError(f"Claude call failed ({type(exc).__name__}): {exc}")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    return dict(text=text, model=model, in_tokens=resp.usage.input_tokens, out_tokens=resp.usage.output_tokens)


# ------------------------------------------------------------------ Ollama (local)
def _ollama(prompt, system=None):
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    body = json.dumps({"model": model, "stream": False, "options": {"temperature": 0},
                       "messages": [{"role": "system", "content": system or SYSTEM_PROMPT},
                                    {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
    except Exception as exc:
        raise LlmError(f"Ollama is not reachable at {host} ({type(exc).__name__}). Is it running, and did you pull '{model}'?")
    return dict(text=data["message"]["content"].strip(), model=model,
                in_tokens=data.get("prompt_eval_count", 0), out_tokens=data.get("eval_count", 0))


# ------------------------------------------------------------------ no LLM
def extractive(chunks):
    """No-LLM mode: show the best passages and cite them. It cannot reason, only retrieve."""
    parts = []
    for i, c in enumerate(chunks[:3], 1):
        body = c["text"].split("\n", 1)[-1].strip()
        body = body if len(body) <= 450 else body[:450].rsplit(" ", 1)[0] + " ..."
        parts.append(f"{body} [S{i}]")
    return dict(text="Best matching passages (no-LLM mode):\n\n" + "\n\n".join(parts),
                model="none", in_tokens=0, out_tokens=0)


def generate(question: str, chunks, provider: str) -> dict:
    if provider == "extractive":
        return extractive(chunks)
    prompt = build_prompt(question, chunks)
    if provider == "gemini":
        return _gemini(prompt)
    if provider == "claude":
        return _claude(prompt)
    if provider == "ollama":
        return _ollama(prompt)
    raise LlmError(f"Unknown provider '{provider}'. Choose one of: {', '.join(PROVIDERS)}")


def complete(prompt: str, provider: str, system: str) -> dict:
    """Plain LLM call with a custom system prompt (used by the data-question engine)."""
    fn = {"gemini": _gemini, "claude": _claude, "ollama": _ollama}.get(provider)
    if fn is None:
        raise LlmError("Data questions need an LLM to write the SQL. Pick gemini, claude or ollama in the sidebar.")
    return fn(prompt, system)
