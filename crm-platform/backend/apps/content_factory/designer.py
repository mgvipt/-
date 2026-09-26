"""ШІ-дизайнер кадрів рилса (27.09.2026, запит Олега: «агент має підбирати варіанти як дизайнер, краще за мене»).

Дивиться ПОТОЧНІ кадри ролика і найкращі реальні фото матеріалу з бібліотеки CRM (оцінка PhotoScore) і для кожного
кадру вибирає, що краще: лишити поточний чи поставити фото. Критерії — світло, різкість, видно фактуру чи інтерʼєр,
пасує до тексту кадру й аудиторії блогу, кадри різні, перший — найефектніший. Одне звернення до Gemini (≈$0.01).
Фото з бібліотеки справжні — мітка «ШІ» на них не ставиться.
"""
import base64

PROMPT = """Ти — арт-директор коротких відео для Instagram. Блог: «{blog}». Аудиторія: {audience}.
Ролик: «{title}». Кадри (текст на екрані):
{beats}

Нижче картинки: K1…K{nk} — поточні кадри ролика (у тому ж порядку), C1…C{nc} — справжні фото нашого матеріалу з бібліотеки.
Для КОЖНОГО кадру ролика вибери найкращу картинку: лишити поточну (K з тим самим номером) або поставити фото C.
Критерії: гарне світло й різкість (сірі, розмиті, темні, криві кадри — замінити); видно фактуру або гарний інтерʼєр;
картинка пасує до тексту кадру; кадри різні між собою; кадр 1 — найефектніший, бо це гачок; одне фото C не повторюй.
Якщо текст кадру про процес (нанесення, інструмент), а на фото C лише готова стіна — краще лишити K, якщо він не жахливий.
Відповідай ЛИШЕ JSON: {{"picks":[{{"beat":1,"pick":"K1","why":"до 12 слів українською"}}]}}"""


def pick(reel, limit_photos=14):
    """Підібрати кадри. Повертає список {beat, pick, why}; заміни вже застосовано до ролика."""
    from apps.inbox.models import MediaLibraryItem
    from . import reels as R
    from .carousels import best_photos
    from .material_specs import find_material
    from .photofix import small_jpeg

    blog = reel.blog
    material = find_material(f"{reel.material} {reel.title}") or reel.material
    photos = []
    for lib_id in (best_photos(material, limit=limit_photos) if material else []):
        m = MediaLibraryItem.objects.filter(pk=lib_id).select_related("file").first()
        if m and m.file_id and m.file.data:
            photos.append(m)
    if not photos:
        raise R.ReelError(f"У бібліотеці немає справжніх фото матеріалу «{material or '—'}» — дизайнеру нема з чого вибирати.")
    img = lambda b: {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(small_jpeg(b)).decode()}}
    parts = []
    for k in range(len(reel.beats)):
        try:
            data, _ = R.frame_bytes(reel, k)
            parts += [{"text": f"K{k + 1}"}, img(data)]
        except Exception:
            parts.append({"text": f"K{k + 1}: кадру немає"})
    for n, m in enumerate(photos):
        parts += [{"text": f"C{n + 1}"}, img(bytes(m.file.data))]
    audience = "жінки 28–50, які роблять ремонт і самі обирають матеріал; майстри-оздоблювачі" if blog and blog.slug == "wallcov" else (blog.about if blog else "")
    beats = "\n".join(f"{i + 1}. «{b.get('text', '')}» ({b.get('seconds')} с)" for i, b in enumerate(reel.beats))
    parts.append({"text": PROMPT.format(blog=blog.name if blog else "Wallcov", audience=audience or "—", title=reel.title,
                                        beats=beats, nk=len(reel.beats), nc=len(photos))})
    r = None
    for _ in range(2):  # відповідь інколи обрізається («думання» теж у ліміті) — одна повторна спроба
        try:
            r = R._gemini(parts, max_tokens=5000)
            break
        except ValueError:
            continue
    if r is None:
        raise R.ReelError("Дизайнер не зміг відповісти — спробуйте ще раз.")
    picks = r if isinstance(r, list) else (r.get("picks") or [])  # Gemini інколи віддає одразу список
    if picks and isinstance(picks[0], dict) and "picks" in picks[0]:
        picks = picks[0]["picks"]
    out, used = [], set()
    for p in picks:
        try:
            beat = int(p.get("beat")) - 1
        except (TypeError, ValueError):
            continue
        choice = str(p.get("pick") or "").strip().upper()
        if not 0 <= beat < len(reel.beats) or not choice:
            continue
        why = str(p.get("why") or "")[:120]
        if choice.startswith("C"):
            try:
                m = photos[int(choice[1:]) - 1]
            except (ValueError, IndexError):
                continue
            if m.id in used:
                continue
            used.add(m.id)
            R.photo_frame(reel, beat, m.id)
            reel.refresh_from_db()
            out.append({"beat": beat, "pick": "photo", "lib_id": m.id, "why": why})
        else:
            out.append({"beat": beat, "pick": "keep", "why": why})
    brief = dict(reel.brief or {}, designer=out)
    reel.brief = brief
    reel.save(update_fields=["brief"])
    return out
