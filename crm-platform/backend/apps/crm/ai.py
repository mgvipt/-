"""Виклик Claude (Anthropic) для AI-помічника у картці сделки."""
import json, os, re, urllib.request


def claude_json(prompt, model="claude-sonnet-4-6", max_tokens=700):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY не налаштовано на сервері")
    body = json.dumps({
        "model": model, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        resp = json.load(r)
    text = resp["content"][0]["text"]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"context": "", "suggestion": text}
