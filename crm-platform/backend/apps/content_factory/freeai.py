"""Безкоштовні ліміти (25.09.2026, рішення Олега «де можна — безкоштовно, якість — платно»). По ОДНОМУ акаунту на сервіс.

| Сервіс | Ключ у .env | Безкоштовно | Для чого |
| Groq Whisper | GROQ_API_KEY | ≈8 год аудіо/день | розшифровка голосових асистента (замість Gemini) |
| Cloudflare Workers AI (FLUX.1 schnell) | CF_ACCOUNT_ID, CF_API_TOKEN | ≈500 картинок/день | чернеткові ШІ-кадри (не фактура Wallcov) |
| YouTube Data API v3 | YOUTUBE_API_KEY | 100 пошуків/день | пошук Shorts (скрапінг — запасний) |
| Tavily | TAVILY_API_KEY | 1 000 пошуків/міс | запасний пошук, коли Serper не відповів |
| Meta Business Discovery | META_MARKETING_ACCESS_TOKEN | в межах лімітів Graph API | відео Instagram бізнес-акаунтів за посиланням |
Кожна функція повертає None/[] при збої — виклик падає на платний/старий шлях, а не ламає роботу.
"""
import base64
import json
import os
import re
import urllib.parse
import urllib.request

UA = "wallcov-crm/1.0"


def _post(url, body, headers, timeout=60):
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _usage(source, model):
    try:
        from apps.crm.models import AiUsage
        AiUsage.objects.create(source=source, model=model, in_tok=0, out_tok=0, cost_usd=0)
    except Exception:
        pass


# ── Groq Whisper ────────────────────────────────────────────────────────────────────────────────

def groq_transcribe(audio, filename="audio.ogg", mime="audio/ogg", language=None, source="freeai.groq"):
    """Розшифровка через Groq (whisper-large-v3-turbo). Файл до 25 МБ. None — якщо ключа нема або збій."""
    key = os.environ.get("GROQ_API_KEY")
    if not key or not audio or len(audio) > 25 * 1024 * 1024:
        return None
    b = "----wallcov" + base64.b16encode(os.urandom(6)).decode()
    fields = [("model", "whisper-large-v3-turbo"), ("response_format", "text")] + ([("language", language)] if language else [])
    body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields)
    body += f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
    body += audio + f"\r\n--{b}--\r\n".encode()
    try:
        out = _post("https://api.groq.com/openai/v1/audio/transcriptions", body,
                    {"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={b}"}, timeout=120)
    except Exception:
        return None
    _usage(source, "groq/whisper-large-v3-turbo")
    return out.decode("utf8", "ignore").strip()


# ── Cloudflare FLUX (чернеткові картинки) ───────────────────────────────────────────────────────

def cf_image(prompt, aspect="9:16", source="freeai.flux"):
    """Картинка FLUX.1 schnell через Cloudflare Workers AI. Повертає (bytes, "image/jpeg") або None.
    Без референсів: персонажі й фактура не гарантовані — лише для чернеток і фонів."""
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not acc or not tok:
        return None
    hint = {"9:16": " Vertical 9:16 composition.", "4:5": " Portrait 4:5 composition.", "1:1": ""}.get(aspect, "")
    try:
        out = _post(f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                    json.dumps({"prompt": (prompt + hint + " No text, no letters, no watermark.")[:2000], "steps": 8}).encode(),
                    {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, timeout=90)
        img = base64.b64decode(json.loads(out)["result"]["image"])
    except Exception:
        return None
    _usage(source, "cf/flux-1-schnell")
    return img, "image/jpeg"


# ── YouTube Data API ────────────────────────────────────────────────────────────────────────────

def youtube_search(q, lang="uk", limit=20):
    """Shorts через офіційний API (search.list = 100 од. із 10 000/добу → ≈100 пошуків). [] — якщо ключа нема/квота."""
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return []
    p = {"part": "snippet", "q": q, "type": "video", "videoDuration": "short", "maxResults": min(50, limit),
         "relevanceLanguage": lang, "order": "relevance", "key": key}
    try:
        with urllib.request.urlopen("https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(p), timeout=20) as r:
            items = json.load(r).get("items") or []
        ids = [i["id"]["videoId"] for i in items if (i.get("id") or {}).get("videoId")]
        stats = {}
        if ids:  # videos.list = 1 од. — перегляди
            with urllib.request.urlopen("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(
                    {"part": "statistics", "id": ",".join(ids), "key": key}), timeout=20) as r:
                stats = {v["id"]: v.get("statistics") or {} for v in json.load(r).get("items") or []}
    except Exception:
        return []
    out = []
    for i in items:
        vid = (i.get("id") or {}).get("videoId")
        if not vid:
            continue
        sn = i.get("snippet") or {}
        views = int((stats.get(vid) or {}).get("viewCount") or 0)
        out.append({"url": f"https://www.youtube.com/shorts/{vid}", "title": sn.get("title", "")[:160],
                    "views": (f"{views:,} переглядів".replace(",", " ") if views else ""), "author": sn.get("channelTitle", "")[:80],
                    "thumb": ((sn.get("thumbnails") or {}).get("high") or {}).get("url") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "date": (sn.get("publishedAt") or "")[:10]})
    return out


# ── Tavily (запасний пошук) ─────────────────────────────────────────────────────────────────────

def tavily_search(q, limit=10):
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return []
    try:
        out = json.loads(_post("https://api.tavily.com/search", json.dumps({"query": q, "max_results": limit}).encode(),
                               {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, timeout=30))
    except Exception:
        return []
    return [{"url": x.get("url", ""), "title": x.get("title", ""), "why": x.get("content", "")[:240], "thumb": ""}
            for x in out.get("results") or []]


# ── Instagram: відео бізнес-акаунта за посиланням (офіційно, Business Discovery) ────────────────

def ig_username_from_snippet(text):
    """«28 likes, 0 comments - color.studio.gomel on February 6, 2026: …» → color.studio.gomel."""
    m = re.search(r"comments?\s*[-–]\s*([A-Za-z0-9_.]{2,30})\s+on\s", text or "")
    return m.group(1) if m else ""


def ig_shortcode(url):
    m = re.search(r"instagram\.com/(?:[\w.]+/)?(?:reel|reels|p|tv)/([\w-]+)", url or "")
    return m.group(1) if m else ""


def ig_media(url, username, pages=3):
    """Знайти публікацію бізнес/автор-акаунта за посиланням → {"media_url", "caption", "like_count", ...} або None."""
    tok, ig = os.environ.get("META_MARKETING_ACCESS_TOKEN"), os.environ.get("META_IG_ID") or os.environ.get("META_IG_ACCOUNT_ID")
    code = ig_shortcode(url)
    if not (tok and ig and code and username):
        return None
    ver = os.environ.get("META_MARKETING_GRAPH_VERSION") or "v23.0"
    after = ""
    for _ in range(pages):
        fields = ("business_discovery.username(%s){media%s{permalink,media_type,media_url,thumbnail_url,caption,like_count,comments_count}}"
                  % (username, f".after({after}).limit(50)" if after else ".limit(50)"))
        try:
            with urllib.request.urlopen(f"https://graph.facebook.com/{ver}/{ig}?" + urllib.parse.urlencode(
                    {"fields": fields, "access_token": tok}), timeout=30) as r:
                media = (json.load(r).get("business_discovery") or {}).get("media") or {}
        except Exception:
            return None
        for m in media.get("data") or []:
            if code in (m.get("permalink") or ""):
                return m
        after = ((media.get("paging") or {}).get("cursors") or {}).get("after")
        if not after:
            break
    return None


# ── ElevenLabs (платно, тариф Starter Олега: комерція дозволена, ≈40 тис. символів/міс спільно з мультсеріалом) ──

def eleven_voices():
    """Голоси акаунта для озвучки: клон Олега, голоси героїв «Стіни в шоці», диктор. Кеш на добу."""
    from django.core.cache import cache
    hit = cache.get("cf-eleven-voices2")
    if hit is not None:
        return hit
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return []
    try:
        req = urllib.request.Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            vs = json.load(r).get("voices") or []
    except Exception:
        return []
    out = [{"id": v["voice_id"], "name": v["name"], "kind": v.get("category", ""), "preview_url": v.get("preview_url") or ""}
           for v in vs if v.get("category") in ("cloned", "professional")]
    out.sort(key=lambda v: (0 if "Олег" in v["name"] or "Кріжев" in v["name"] else 1, v["name"]))
    cache.set("cf-eleven-voices2", out, 24 * 3600)
    return out


def eleven_tts(text, voice_id, source="content_factory.voice"):
    """Озвучка тексту (mp3). Кожен символ — з місячного ліміту ElevenLabs."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    text = (text or "").strip()
    if not key or not text or not voice_id:
        return None
    body = json.dumps({"text": text[:800], "model_id": "eleven_multilingual_v2",
                       "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}).encode()
    try:
        out = _post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128", body,
                    {"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"}, timeout=90)
    except Exception:
        return None
    try:
        from apps.crm.models import AiUsage
        AiUsage.objects.create(source=source, model="elevenlabs/multilingual_v2", in_tok=len(text), out_tok=0, cost_usd=0)
    except Exception:
        pass
    return out if len(out) > 1000 else None


# ── Groq LLM (безкоштовно): дрібні правки тексту, де не потрібна платна модель ────────────────────

def groq_chat(system, user, model="openai/gpt-oss-120b", max_tokens=600, source="freeai.groq_chat"):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    body = json.dumps({"model": model, "max_tokens": max_tokens, "temperature": 0.2,
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    try:
        out = json.loads(_post("https://api.groq.com/openai/v1/chat/completions", body,
                               {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60))
        text = out["choices"][0]["message"]["content"]
    except Exception:
        return None
    _usage(source, "groq/" + model)
    return (text or "").strip()


SAMPLE_TEXT = "Привіт! Це Wallcov. Декоративна штукатурка, яка по-різному оживає вдень і ввечері."


def voice_sample(voice_id):
    """Зразок голосу для кнопки «Прослухати» (27.09): готовий preview ElevenLabs або одна коротка фраза, озвучена
    раз і збережена в CRM (≈80 символів з місячного ліміту на голос). Повертає SharedLink або None."""
    from apps.inbox.models import SharedLink
    from secrets import token_urlsafe
    name = f"voice-sample-{voice_id}.mp3"
    hit = SharedLink.objects.filter(filename=name).order_by("-id").first()
    if hit:
        return hit
    v = next((x for x in eleven_voices() if x["id"] == voice_id), None)
    if not v:
        return None
    data = None
    if v.get("preview_url"):
        try:
            req = urllib.request.Request(v["preview_url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read(5 * 1024 * 1024)
        except Exception:
            data = None
    data = data or eleven_tts(SAMPLE_TEXT, voice_id, source="content_factory.voice_sample")
    if not data:
        return None
    return SharedLink.objects.create(token=token_urlsafe(24), filename=name, content_type="audio/mpeg", data=data)

