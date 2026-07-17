# -*- coding: utf-8 -*-
"""
Читання поштової скриньки накладних (Gmail IMAP) → чернетки IncomingDoc.
Акти Нової Пошти (є Специфікація .xlsx) розбираються одразу; накладні постачальників
зберігаються як чернетки для ручної обробки. Ідемпотентно за IMAP UID (last_uid у конфізі).
НЕ змінює прапорці листів (readonly). Реальні кредиторки/приходи створюються тільки при підтвердженні.
"""
import imaplib
import email
import re
import base64
import io
from email.header import decode_header


def _dec(h):
    if not h:
        return ""
    out = []
    for txt, enc in decode_header(h):
        if isinstance(txt, bytes):
            try:
                out.append(txt.decode(enc or "utf-8", "ignore"))
            except (LookupError, TypeError):
                out.append(txt.decode("utf-8", "ignore"))
        else:
            out.append(txt)
    return "".join(out)


def _body_text(msg):
    import re as _re
    import html as _html
    text = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain" and not part.get_filename():
            try:
                text += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
            except Exception:
                pass
    if not text:
        for part in msg.walk():
            if part.get_content_type() == "text/html" and not part.get_filename():
                try:
                    html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                    html = _re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
                    html = _re.sub(r"(?i)<br\s*/?>", "\n", html)
                    html = _re.sub(r"(?i)</(p|div|tr|li|h[1-6])>", "\n", html)
                    text = _html.unescape(_re.sub(r"<[^>]+>", "", html))
                except Exception:
                    pass
    # прибрати google-redirect та задовгі tracking-URL
    text = _re.sub(r"https?://www\.google\.com/url\?[^\s>]+", "", text)
    text = _re.sub(r"<https?://\S+>", "", text)
    text = _re.sub(r"https?://\S{70,}", "", text)
    text = _re.sub(r"[ \t]+", " ", text)
    lines = [l.strip() for l in text.splitlines()]
    out = []
    for l in lines:
        if l or (out and out[-1]):
            out.append(l)
    return "\n".join(out).strip()[:4000]


def _contact_senders():
    """Пошти постачальників, у яких у картці стоїть «Моніторити накладні».
    Так список ведеться з CRM (картка контрагента), а не рядком у налаштуваннях."""
    try:
        from apps.crm.models import Contact
    except Exception:
        return []
    out = []
    for c in Contact.objects.filter(monitor_docs=True).only("id", "email", "doc_email"):
        e = ((c.doc_email or "").strip() or (c.email or "").strip()).lower()
        if e and "@" in e:
            out.append(e)
    return out


def _load():
    from .models import IntegrationSettings
    o = IntegrationSettings.objects.filter(provider="email_invoices").first()
    return o, ((o.config if o else {}) or {})


def _attachments(msg):
    atts = []
    for part in msg.walk():
        fn = part.get_filename()
        if not fn:
            continue
        fn = _dec(fn)
        if fn.lower().endswith((".xlsx", ".xls")):
            payload = part.get_payload(decode=True)
            if payload:
                atts.append((fn, payload))
    return atts


def poll(limit=60, backfill=False, log=lambda m: None):
    """Забирає нові листи від відправників білого списку, робить чернетки.
    backfill=True — ігнорує last_uid (для ручного першого затягування)."""
    from .models import IncomingDoc
    from apps.finance.np_act import parse_act

    obj, cfg = _load()
    if obj is None:
        return {"error": "not_configured"}
    host = (cfg.get("imap_host") or "imap.gmail.com").strip()
    user = (cfg.get("email") or "").strip()
    pwd = (cfg.get("app_password") or "").strip()
    senders = [x.strip().lower() for x in re.split(r"[,;\s]+", cfg.get("senders") or "") if x.strip()]
    # + постачальники, позначені в CRM «Моніторити накладні» (дедуп, порядок збережено)
    senders = list(dict.fromkeys(senders + _contact_senders()))
    if not user or not pwd:
        return {"error": "not_configured"}

    last_uid = dict(cfg.get("last_uid") or {})
    M = imaplib.IMAP4_SSL(host)
    M.login(user, pwd)
    M.select("INBOX", readonly=True)
    scanned = created = np_created = sup_created = 0

    for snd in (senders or [None]):
        typ, data = (M.uid("search", None, "FROM", '"%s"' % snd) if snd else M.uid("search", None, "ALL"))
        uids = sorted(int(x) for x in data[0].split()) if (data and data[0]) else []
        if not uids:
            continue
        prev = 0 if backfill else int(last_uid.get(snd or "*", 0))
        new = [u for u in uids if u > prev]
        if prev == 0 and not backfill:
            new = uids[-limit:]        # перший запуск — останні N
        else:
            new = new[-limit:]
        for u in new:
            scanned += 1
            typ, md = M.uid("fetch", str(u), "(RFC822)")
            if not md or not md[0]:
                continue
            msg = email.message_from_bytes(md[0][1])
            frm = _dec(msg.get("From"))
            subj = _dec(msg.get("Subject"))
            date_hdr = msg.get("Date")
            body = _body_text(msg)
            if IncomingDoc.objects.filter(mailbox=user, message_uid=str(u)).exists():
                continue
            atts = _attachments(msg)
            spec = next((p for n, p in atts if "специф" in n.lower()), None)
            rah = next((p for n, p in atts if "рахун" in n.lower()), None)
            is_np = ("novaposhta" in (frm or "").lower()) or (spec is not None)

            b64 = [{"name": n, "b64": base64.b64encode(p).decode()} for n, p in atts][:4]
            if is_np and spec:
                try:
                    act = parse_act(io.BytesIO(spec), io.BytesIO(rah) if rah else None)
                except Exception as e:  # noqa
                    log("parse fail uid=%s: %s" % (u, e))
                    act = None
                if act and act.get("invoice_number"):
                    if IncomingDoc.objects.filter(doc_type="np_act", parsed__invoice_number=act["invoice_number"]).exists():
                        continue  # вже є чернетка/проведено цього акта
                    IncomingDoc.objects.create(
                        mailbox=user, message_uid=str(u), sender=frm[:200], subject=subj[:300],
                        doc_type="np_act", status="draft",
                        parsed={"invoice_number": act["invoice_number"], "invoice_date": act.get("invoice_date"),
                                "amount": act.get("amount"), "vat": act.get("vat"),
                                "contract": act.get("contract"), "counterparty": act.get("counterparty"),
                                "shipments": act.get("shipments"), "checks": act.get("checks"),
                                "email_date": date_hdr, "email_text": body},
                        attachments_b64=b64)
                    created += 1
                    np_created += 1
            elif atts:
                from .supplier_act import parse_korzh
                xls = next((pp for nn, pp in atts if nn.lower().endswith((".xls", ".xlsx"))), None)
                sp = {"files": [n for n, _ in atts], "email_date": date_hdr, "email_text": body}
                if xls:
                    try:
                        sa = parse_korzh(xls)
                        if sa.get("invoice_number") and IncomingDoc.objects.filter(doc_type="supplier", parsed__invoice_number=sa["invoice_number"]).exists():
                            continue
                        sp.update({"invoice_number": sa.get("invoice_number"), "invoice_date": sa.get("invoice_date"),
                                   "supplier": sa.get("supplier"), "lines": sa.get("lines"), "amount": sa.get("total")})
                    except Exception as e:  # noqa
                        log("supplier parse fail uid=%s: %s" % (u, e))
                IncomingDoc.objects.create(
                    mailbox=user, message_uid=str(u), sender=frm[:200], subject=subj[:300],
                    doc_type="supplier", status="draft", parsed=sp, attachments_b64=b64)
                created += 1
                sup_created += 1
        if uids:
            last_uid[snd or "*"] = max(uids)

    M.logout()
    # зберегти last_uid (тільки якщо не backfill, щоб не збити прогрес)
    if not backfill:
        cfg["last_uid"] = last_uid
        obj.config = cfg
        obj.save(update_fields=["config"])
    return {"scanned": scanned, "created": created, "np": np_created, "supplier": sup_created}
