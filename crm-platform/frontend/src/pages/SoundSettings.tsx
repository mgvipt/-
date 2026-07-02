/* Налаштування звуків: повідомлення клієнта + повідомлення співробітника + дзвінок.
   Завантажені звуки — СПІЛЬНІ (на сервері): усі можуть обирати; завантажувати/видаляти —
   лише з правом settings.sounds.upload. Однакові файли не дублюються (дедуп по вмісту). */
import { useState, useRef, useEffect } from "react";
import { useLang } from "../i18n";
import { useAuth } from "../auth";
import { Icon } from "../Icon";
import {
  SOUNDS, CALL_SOUNDS, getMsgSound, setMsgSound, getCallSound, setCallSound,
  msgSoundOn, setMsgSoundOn, callSoundOn, setCallSoundOn, previewSel, stopPreview,
  getTeamSound, setTeamSound, teamSoundOn, setTeamSoundOn,
  getLibrary, loadSoundLibrary, uploadSound, deleteSound,
} from "../sounds";

export default function SoundSettings() {
  const { t } = useLang();
  const { can } = useAuth();
  const canUpload = can("settings.sounds.upload") || can("roles.manage");
  const [msg, setMsg] = useState(getMsgSound());
  const [call, setCall] = useState(getCallSound());
  const [team, setTeam] = useState(getTeamSound());
  const [msgOn, setMsgOnS] = useState(msgSoundOn());
  const [callOn, setCallOnS] = useState(callSoundOn());
  const [teamOn, setTeamOnS] = useState(teamSoundOn());
  const [customs, setCustoms] = useState(getLibrary());
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => { loadSoundLibrary().then(() => setCustoms(getLibrary())); }, []);
  useEffect(() => () => stopPreview(), []); // зупинити прослуховування при виході

  const selStyle = { flex: 1, minWidth: 0, height: 34, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13, padding: "0 8px" } as const;

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 3 * 1024 * 1024) { alert(t("Файл слишком большой (макс 3 МБ)", "Файл завеликий (макс 3 МБ)")); return; }
    setBusy(true);
    const r = new FileReader();
    r.onload = async () => {
      try {
        const res = await uploadSound(f.name, String(r.result));
        setCustoms(getLibrary());
        if (res.dedup) alert(t("Такой звук уже есть на сервере — используем существующий, без дубля.", "Такий звук уже є на сервері — використовуємо наявний, без дубля."));
      } catch (err) {
        alert(String(err).includes("403") ? t("Нет права загружать звуки", "Немає права завантажувати звуки") : t("Не удалось загрузить", "Не вдалося завантажити"));
      } finally { setBusy(false); }
    };
    r.readAsDataURL(f);
    e.target.value = "";
  };

  const delCustom = async (id: number) => {
    if (!confirm(t("Удалить звук из общей библиотеки? Он пропадёт у всех.", "Видалити звук зі спільної бібліотеки? Він зникне у всіх."))) return;
    try { await deleteSound(id); } catch { alert(t("Не удалось удалить (нужно право)", "Не вдалося видалити (потрібне право)")); return; }
    setCustoms(getLibrary());
    if (msg === "custom:" + id) { setMsg("real_notify"); setMsgSound("real_notify"); }
    if (call === "custom:" + id) { setCall("real_pizzi"); setCallSound("real_pizzi"); }
    if (team === "custom:" + id) { setTeam("real_confirm"); setTeamSound("real_confirm"); }
  };

  const msgList = Object.entries(SOUNDS).map(([k, s]) => [k, s.label] as [string, string]);
  const callList = Object.entries(CALL_SOUNDS).map(([k, s]) => [k, s.label] as [string, string]);
  const sel = (value: string, onChange: (v: string) => void, builtin: [string, string][], disabled: boolean, isCall: boolean) => (
    <select value={value} disabled={disabled} onChange={(e) => { onChange(e.target.value); previewSel(e.target.value, isCall); }} style={selStyle}>
      <optgroup label={t("Встроенные", "Вбудовані")}>
        {builtin.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
      </optgroup>
      {customs.length > 0 && (
        <optgroup label={t("Загруженные (общие)", "Завантажені (спільні)")}>
          {customs.map((s) => <option key={s.id} value={"custom:" + s.id}>{s.name}</option>)}
        </optgroup>
      )}
    </select>
  );

  return (
    <div className="panel" style={{ margin: "0 0 12px", maxWidth: 400 }}>
      <div className="label" style={{ marginBottom: 10 }}><Icon n="bell" size={14} /> {t("Звуки уведомлений", "Звуки сповіщень")}</div>

      {/* повідомлення клієнта */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{t("Новое сообщение клиента", "Нове повідомлення клієнта")}</span>
        <span className={"toggle" + (msgOn ? " on" : "")} onClick={() => { const v = !msgOn; setMsgOnS(v); setMsgSoundOn(v); }} />
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {sel(msg, (v) => { setMsg(v); setMsgSound(v); }, msgList, !msgOn, false)}
        <button className="btn btn-light" onClick={() => previewSel(msg, false)}><Icon n="bell" size={14} /> {t("Прослушать", "Прослухати")}</button>
      </div>

      {/* повідомлення співробітника */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{t("Сообщение от сотрудника", "Повідомлення від співробітника")}</span>
        <span className={"toggle" + (teamOn ? " on" : "")} onClick={() => { const v = !teamOn; setTeamOnS(v); setTeamSoundOn(v); }} />
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {sel(team, (v) => { setTeam(v); setTeamSound(v); }, msgList, !teamOn, false)}
        <button className="btn btn-light" onClick={() => previewSel(team, false)}><Icon n="bell" size={14} /> {t("Прослушать", "Прослухати")}</button>
      </div>

      {/* дзвінок */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{t("Входящий звонок", "Вхідний дзвінок")}</span>
        <span className={"toggle" + (callOn ? " on" : "")} onClick={() => { const v = !callOn; setCallOnS(v); setCallSoundOn(v); }} />
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {sel(call, (v) => { setCall(v); setCallSound(v); }, callList, !callOn, true)}
        <button className="btn btn-light" onClick={() => previewSel(call, true)}><Icon n="bell" size={14} /> {t("Прослушать", "Прослухати")}</button>
      </div>

      {/* завантаження — лише з правом; вибирати можуть усі */}
      {canUpload ? (
        <>
          <input ref={fileRef} type="file" accept="audio/*" style={{ display: "none" }} onChange={onFile} />
          <button className="btn btn-light" style={{ width: "100%", justifyContent: "center" }} disabled={busy} onClick={() => fileRef.current?.click()}>
            <Icon n="upload" size={14} /> {busy ? t("Загрузка…", "Завантаження…") : t("Загрузить свой звук (в общую библиотеку)", "Завантажити свій звук (у спільну бібліотеку)")}
          </button>
        </>
      ) : (
        <div className="muted" style={{ fontSize: 11.5 }}>
          {t("Загружать новые звуки может сотрудник с правом «Загрузка звуков». Выбрать из общих можно любой.",
            "Завантажувати нові звуки може співробітник з правом «Завантаження звуків». Обрати зі спільних можна будь-який.")}
        </div>
      )}

      {customs.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 5 }}>{t("Общая библиотека звуков:", "Спільна бібліотека звуків:")}</div>
          {customs.map((s) => (
            <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 8px", background: "#f8fafc", border: "1px solid #eef2f7", borderRadius: 7, marginBottom: 5 }}>
              <Icon n="music" size={14} />
              <span style={{ flex: 1, fontSize: 12.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}{s.by ? " · " + s.by : ""}</span>
              <button className="btn btn-light" style={{ fontSize: 11 }} onClick={() => previewSel("custom:" + s.id, false)} title={t("Прослушать", "Прослухати")}><Icon n="bell" size={13} /></button>
              {canUpload && <button className="btn btn-light" style={{ fontSize: 11, color: "#dc2626" }} onClick={() => delCustom(s.id)} title={t("Удалить", "Видалити")}><Icon n="trash" size={13} /></button>}
            </div>
          ))}
        </div>
      )}

      <div className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
        {t("Загруженные звуки общие — их видят и могут выбрать все сотрудники. Одинаковые файлы не дублируются. Выбор звука хранится на этом устройстве.",
          "Завантажені звуки спільні — їх бачать і можуть обрати всі співробітники. Однакові файли не дублюються. Вибір звука зберігається на цьому пристрої.")}
      </div>
    </div>
  );
}
