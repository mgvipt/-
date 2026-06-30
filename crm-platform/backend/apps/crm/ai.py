"""Виклик Claude (Anthropic) для AI-помічника у картці сделки."""
import json, os, re, urllib.request

PRICING = {  # $/1M: in, out, cache_read, cache_write
    "claude-haiku-4-5": (0.80, 4.0, 0.08, 1.0),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-4-5": (3.0, 15.0, 0.30, 3.75),
    "claude-opus-4-8": (15.0, 75.0, 1.50, 18.75),
    "claude-opus-4-7": (15.0, 75.0, 1.50, 18.75),
}


def _log_usage(source, model, usage):
    try:
        from apps.crm.models import AiUsage
        it = int(usage.get("input_tokens", 0) or 0); ot = int(usage.get("output_tokens", 0) or 0)
        cr = int(usage.get("cache_read_input_tokens", 0) or 0); cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
        pin, pout, pcr, pcw = PRICING.get(model, (3.0, 15.0, 0.30, 3.75))
        cost = (it * pin + ot * pout + cr * pcr + cw * pcw) / 1_000_000.0
        AiUsage.objects.create(source=(source or "other")[:60], model=model, in_tok=it, out_tok=ot,
                               cache_read=cr, cache_write=cw, cost_usd=cost)
    except Exception:
        pass


def claude_json(prompt, model="claude-sonnet-4-6", max_tokens=700, system=None, cache=False, source="other"):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY не налаштовано на сервері")
    payload = {"model": model, "max_tokens": max_tokens,
               "messages": [{"role": "user", "content": prompt}]}
    if system:
        sb = {"type": "text", "text": system}
        if cache:
            sb["cache_control"] = {"type": "ephemeral"}  # кешуємо статичний промпт (TTL 5хв)
        payload["system"] = [sb]
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "anthropic-beta": "prompt-caching-2024-07-31", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        resp = json.load(r)
    _log_usage(source, model, resp.get("usage") or {})
    text = resp["content"][0]["text"]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"context": "", "suggestion": text}
