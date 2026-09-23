import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

const box: any = { width: "100%", padding: 9, border: "1px solid #d7dee8", borderRadius: 7, boxSizing: "border-box" };
const labels: Record<string, string> = { name: "Ім’я", phone: "Телефон", email: "Email", viber: "Viber", whatsapp: "WhatsApp", telegram: "Telegram" };

export default function SettingsAutomations() {
  const { t } = useLang();
  const [funnels, setFunnels] = useState<any[]>([]);
  const [rules, setRules] = useState<any[]>([]);
  const [fid, setFid] = useState<number | null>(null);
  const [content, setContent] = useState<any>({ forms: [], automations: [], instructions: [], recent: {} });
  const [form, setForm] = useState<any>(null);
  const [automation, setAutomation] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  function loadRules() { api.get<any>("/api/automation-rules/").then((d) => setRules(d.results || d)); }
  async function loadContent(select = true) {
    const d = await api.get<any>("/api/content-library/automations/");
    setContent(d);
    if (select) {
      if (d.forms[0]) setForm({ ...d.forms[0] });
      if (d.automations[0]) setAutomation({ ...d.automations[0] });
    }
  }
  useEffect(() => {
    api.get<any>("/api/funnels/").then((d) => { const fs = d.results || d; setFunnels(fs); if (fs[0]) setFid(fs[0].id); });
    loadRules(); loadContent().catch(() => undefined);
  }, []);

  async function patch(id: number, body: any) { try { await api.patch(`/api/automation-rules/${id}/`, body); } catch { /* */ } }
  async function action(body: any) {
    setBusy(body.action); setNotice("");
    try {
      const r: any = await api.post("/api/content-library/automations/", body);
      setNotice(body.action === "sync_automation" ? "Синхронізовано з ChatPlace і увімкнено." : "Збережено в CRM.");
      await loadContent(false);
      if (r.form) setForm({ ...r.form });
      if (r.automation) setAutomation({ ...r.automation });
    } catch (e: any) { setNotice(e?.response?.data?.detail || "Не вдалося зберегти."); }
    finally { setBusy(""); }
  }
  function toggleList(obj: any, setObj: any, key: string, value: string) {
    const values = new Set(obj[key] || []); values.has(value) ? values.delete(value) : values.add(value);
    setObj({ ...obj, [key]: Array.from(values) });
  }
  const funnel = funnels.find((f) => f.id === fid);
  const fRules = rules.filter((r) => r.funnel === fid);

  return (
    <div>
      <div className="note">{t(
        "Логика движения по воронке: при каком событии лид/сделка переходит на следующую стадию.",
        "Логіка руху по воронці: за якої події лід/угода переходить на наступну стадію.")}</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "10px 0 14px" }}>
        {funnels.map((f) => <button key={f.id} onClick={() => setFid(f.id)} style={{ fontSize: 13, padding: "6px 12px", borderRadius: 16, cursor: "pointer", border: "1px solid " + (fid === f.id ? "var(--brand)" : "#e2e8f0"), background: fid === f.id ? "var(--brand)" : "#fff", color: fid === f.id ? "#fff" : "#475569" }}>{f.name}</button>)}
      </div>
      {(funnel?.stages || []).slice().sort((a: any, b: any) => a.order - b.order).map((st: any) => {
        const into = fRules.filter((r) => r.to_stage === st.id);
        return <div key={st.id} className="panel" style={{ margin: "0 0 10px" }}>
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 6, display: "flex", alignItems: "center", gap: 8 }}><span style={{ width: 12, height: 12, borderRadius: 4, background: st.color || "#94a3b8", display: "inline-block" }} />{st.name}</div>
          {into.length === 0 && <div className="muted" style={{ fontSize: 12 }}>{t("Сюда не ведёт ни одно авто-правило (только вручную).", "Сюди не веде жодне авто-правило (тільки вручну).")}</div>}
          {into.map((r) => <div key={r.id} style={{ borderLeft: "3px solid var(--brand)", padding: "6px 10px", marginBottom: 6, background: "#f8fafc", borderRadius: "0 8px 8px 0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}><span>{t("Когда", "Коли")}: <b>{r.trigger_display}</b> {t("на стадии", "на стадії")} «{r.from_stage_name}» → «{r.to_stage_name}»</span><div style={{ flex: 1 }} /><span className={"toggle" + (r.enabled ? " on" : "")} onClick={() => { patch(r.id, { enabled: !r.enabled }); setRules((rs) => rs.map((x) => x.id === r.id ? { ...x, enabled: !x.enabled } : x)); }} /></div>
            <textarea defaultValue={r.description} onBlur={(e) => patch(r.id, { description: e.target.value })} style={{ ...box, minHeight: 44, marginTop: 6, resize: "vertical" }} />
          </div>)}
        </div>;
      })}

      <div className="panel" style={{ marginTop: 24 }}>
        <h2 style={{ marginTop: 0 }}>Форми та кодові слова</h2>
        <p className="muted">Налаштування зберігаються в CRM. Сайт читає активну форму звідси. ChatPlace відповідає під коментарем, переводить людину в Direct і дає кнопку на форму. SMS не використовується.</p>
        {notice && <div className="note" style={{ marginBottom: 12 }}>{notice}</div>}
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 18 }}>
          <section>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}><b>1. Форма контакту</b><select value={form?.id || ""} onChange={(e) => setForm({ ...content.forms.find((x: any) => x.id === Number(e.target.value)) })} style={{ ...box, width: "auto", flex: 1 }}><option value="">Оберіть форму</option>{content.forms.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select><button onClick={() => setForm({ slug: "", name: "", title: "", intro: "", instruction_id: content.instructions[0]?.id, fields: ["name", "phone", "email"], channels: ["viber", "whatsapp", "telegram", "email"], consent_text: "Хочу отримувати нові інструкції та пропозиції Wallcov", submit_text: "Відкрити повну інструкцію", enabled: true })}>Нова</button></div>
            {form && <div style={{ display: "grid", gap: 9 }}>
              <input style={box} value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Назва форми в CRM" />
              <input style={box} value={form.slug || ""} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="Адреса, наприклад microcement" />
              <select style={box} value={form.instruction_id || ""} onChange={(e) => setForm({ ...form, instruction_id: Number(e.target.value) })}>{content.instructions.map((x: any) => <option key={x.id} value={x.id}>{x.title}</option>)}</select>
              <input style={box} value={form.title || ""} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Заголовок для клієнта" />
              <textarea style={{ ...box, minHeight: 70 }} value={form.intro || ""} onChange={(e) => setForm({ ...form, intro: e.target.value })} placeholder="Коротке пояснення" />
              <div><b style={{ fontSize: 13 }}>Поля</b><div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 6 }}>{["name", "phone", "email"].map((x) => <label key={x}><input type="checkbox" checked={(form.fields || []).includes(x)} onChange={() => toggleList(form, setForm, "fields", x)} /> {labels[x]}</label>)}</div></div>
              <div><b style={{ fontSize: 13 }}>Канали</b><div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 6 }}>{["viber", "whatsapp", "telegram", "email"].map((x) => <label key={x}><input type="checkbox" checked={(form.channels || []).includes(x)} onChange={() => toggleList(form, setForm, "channels", x)} /> {labels[x]}</label>)}</div></div>
              <input style={box} value={form.consent_text || ""} onChange={(e) => setForm({ ...form, consent_text: e.target.value })} placeholder="Текст згоди на повідомлення" />
              <input style={box} value={form.submit_text || ""} onChange={(e) => setForm({ ...form, submit_text: e.target.value })} placeholder="Текст кнопки" />
              <label><input type="checkbox" checked={!!form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> Форма активна</label>
              <button className="button" disabled={!!busy} onClick={() => action({ action: "save_form", ...form })}>Зберегти форму</button>
            </div>}
          </section>

          <section>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}><b>2. Коментарі + Direct</b><select value={automation?.id || ""} onChange={(e) => setAutomation({ ...content.automations.find((x: any) => x.id === Number(e.target.value)) })} style={{ ...box, width: "auto", flex: 1 }}><option value="">Оберіть правило</option>{content.automations.map((x: any) => <option key={x.id} value={x.id}>{x.title}</option>)}</select><button onClick={() => setAutomation({ title: "", keywords: [], match_mode: "exact", form_id: content.forms[0]?.id, reply_text: "", public_replies: [], direct_enabled: true, comment_enabled: true, enabled: false })}>Нове</button></div>
            {automation && <div style={{ display: "grid", gap: 9 }}>
              <input style={box} value={automation.title || ""} onChange={(e) => setAutomation({ ...automation, title: e.target.value })} placeholder="Назва правила" />
              <input style={box} value={(automation.keywords || []).join(", ")} onChange={(e) => setAutomation({ ...automation, keywords: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} placeholder="Кодові слова через кому" />
              <select style={box} value={automation.match_mode || "exact"} onChange={(e) => setAutomation({ ...automation, match_mode: e.target.value })}><option value="exact">Точний збіг</option><option value="contains">Містить слово</option></select>
              <select style={box} value={automation.form_id || ""} onChange={(e) => setAutomation({ ...automation, form_id: Number(e.target.value) })}>{content.forms.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
              <label><input type="checkbox" checked={!!automation.comment_enabled} onChange={(e) => setAutomation({ ...automation, comment_enabled: e.target.checked })} /> Відповідати під коментарем і переводити в Direct</label>
              <textarea style={{ ...box, minHeight: 70 }} value={(automation.public_replies || []).join("\n")} onChange={(e) => setAutomation({ ...automation, public_replies: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })} placeholder="Варіанти публічної відповіді, кожен з нового рядка" />
              <label><input type="checkbox" checked={!!automation.direct_enabled} onChange={(e) => setAutomation({ ...automation, direct_enabled: e.target.checked })} /> Реагувати на кодове слово в Direct</label>
              <textarea style={{ ...box, minHeight: 110 }} value={automation.reply_text || ""} onChange={(e) => setAutomation({ ...automation, reply_text: e.target.value })} placeholder="Коротке повідомлення в Direct без посилання — адреса форми вже буде в кнопці." />
              <div className="muted" style={{ fontSize: 12 }}>Клієнт натисне «Отримати техкарту» і одразу відкриє форму. Посилання в текст додавати не потрібно.</div>
              <label><input type="checkbox" checked={!!automation.enabled} onChange={(e) => setAutomation({ ...automation, enabled: e.target.checked })} /> Правило активне</label>
              <div className="muted" style={{ fontSize: 12 }}>ChatPlace: {automation.chatplace_status || "ще не синхронізовано"}{automation.chatplace_automation_id ? ` · ${automation.chatplace_automation_id}` : ""}</div>
              {automation.chatplace_error && <div style={{ color: "#b42318", fontSize: 12 }}>{automation.chatplace_error}</div>}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><button className="button" disabled={!!busy} onClick={() => action({ action: "save_automation", ...automation })}>Зберегти правило</button>{automation.id && <button className="button" disabled={!!busy || !automation.enabled} onClick={() => action({ action: "sync_automation", id: automation.id })}>Синхронізувати з ChatPlace</button>}{automation.id && automation.chatplace_automation_id && <button disabled={!!busy} onClick={() => action({ action: "pause_automation", id: automation.id })}>Призупинити</button>}</div>
            </div>}
          </section>
        </div>
        <div className="note" style={{ marginTop: 16 }}>За 30 днів: кодове слово зафіксовано — <b>{content.recent?.captured_30d || 0}</b>, помилок — <b>{content.recent?.failed_30d || 0}</b>. Контакт і згода на подальші повідомлення зберігаються після відправлення форми.</div>
      </div>
    </div>
  );
}
