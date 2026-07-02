/* Налаштування звуків: повідомлення + дзвінок. Можна завантажити свої файли — вони зʼявляються
   у списках вибору для ОБОХ (повідомлення і дзвінок). */
import { useState, useRef, useEffect } from "react";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
import {
  SOUNDS, CALL_SOUNDS, getMsgSound, setMsgSound, getCallSound, setCallSound,
  msgSoundOn, setMsgSoundOn, callSoundOn, setCallSoundOn, previewSel, stopPreview,
  getTeamSound, setTeamSound, teamSoundOn, setTeamSoundOn,
  getCustomSounds, addCustomSound, removeCustomSound,
} from "../sounds";

export default function SoundSettings() {
  const { t } = useLang();
  const [msg, setMsg] = useState(getMsgSound());
  const [call, setCall] = useState(getCallSound());
  const [msgOn, setMsgOnS] = useState(msgSoundOn());
  const [callOn, setCallOnS] = useState(callSoundOn());
  const [team, setTeam] = useState(getTeamSound());
  const [teamOn, setTeamOnS] = useState(teamSoundOn());
  const [customs, setCustoms] = useState(getCustomSounds());
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => () => stopPreview(), []); // зупинити прослуховування при виході зі сторінки

  const selStyle = { flex: 1, minWidth: 0, height: 34, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13, padding: "0 8px" } as const;

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 2 * 1024 * 1024) { alert(t("Файл слишком большой (макс 2 МБ)", "Файл завеликий (макс 2 МБ)")); return; }
    const r = new FileReader();
    r.onload = () => { addCustomSound(f.name, String(r.result)); setCustoms(getCustomSounds()); };
    r.readAsDataURL(f);
    e.target.value = "";
  };

  const delCustom = (id: string) => {
    removeCustomSound(id); const left = getCustomSounds(); setCustoms(left);
    if (msg === "custom:" + id) { setMsg("bloom"); setMsgSound("bloom"); }
    if (call === "custom:" + id) { setCall("iphone_marimba"); setCallSound("iphone_marimba"); }
    if (team === "custom:" + id) { setTeam("bloom"); setTeamSound("bloom"); }
  };

  const msgList = Object.entries(SOUNDS).map(([k, s]) => [k, s.label] as [string, string]);
  const callList = Object.entries(CALL_SOUNDS).map(([k, s]) => [k, s.label] as [string, string]);
  const sel = (value: string, onChange: (v: string) => void, builtin: [string, string][], disabled: boolean, isCall: boolean) => (
    <select value={value} disabled={disabled} onChange={(e) => { onChange(e.target.value); previewSel(e.target.value, isCall); }} style={selStyle}>
      <optgroup label={t("Встроенные", "Вбудовані")}>
        {builtin.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
      </optgroup>
      {customs.length > 0 && (
        <optgroup label={t("Мои файлы", "Мої файли")}>
          {customs.map((s) => <option key={s.id} value={"custom:" + s.id}>{s.name}</option>)}
        </optgroup>
      )}
    </select>
  );

  return (
    <div className="panel" style={{ margin: "0 0 12px", maxWidth: 400 }}>
      <div className="label" style={{ marginBottom: 10 }}><Icon n="bell" size={14} /> {t("Звуки уведомлений", "Звуки сповіщень")}</div>

      {/* повідомлення */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{t("Новое сообщение клиента", "Нове повідомлення клієнта")}</span>
        <span className={"toggle" + (msgOn ? " on" : "")} onClick={() => { const v = !msgOn; setMsgOnS(v); setMsgSoundOn(v); }} />
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {sel(msg, (v) => { setMsg(v); setMsgSound(v); }, msgList, !msgOn, false)}
        <button className="btn btn-light" onClick={() => previewSel(msg, false)}><Icon n="bell" size={14} /> {t("Прослушать", "Прослухати")}</button>
      </div>

      {/* повідомлення співробітника (командний чат) */}
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

      {/* завантаження файлів */}
      <input ref={fileRef} type="file" accept="audio/*" style={{ display: "none" }} onChange={onFile} />
      <button className="btn btn-light" style={{ width: "100%", justifyContent: "center" }} onClick={() => fileRef.current?.click()}>
        <Icon n="upload" size={14} /> {t("Загрузить свой звук (музыку)", "Завантажити свій звук (музику)")}
      </button>

      {customs.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 5 }}>{t("Мои загруженные звуки:", "Мої завантажені звуки:")}</div>
          {customs.map((s) => (
            <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 8px", background: "#f8fafc", border: "1px solid #eef2f7", borderRadius: 7, marginBottom: 5 }}>
              <Icon n="music" size={14} />
              <span style={{ flex: 1, fontSize: 12.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</span>
              <button className="btn btn-light" style={{ fontSize: 11 }} onClick={() => previewSel("custom:" + s.id, false)} title={t("Прослушать", "Прослухати")}><Icon n="bell" size={13} /></button>
              <button className="btn btn-light" style={{ fontSize: 11, color: "#dc2626" }} onClick={() => delCustom(s.id)} title={t("Удалить", "Видалити")}><Icon n="trash" size={13} /></button>
            </div>
          ))}
        </div>
      )}

      <div className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
        {t("Загруженные файлы появляются в списках выбора — и для сообщения, и для звонка. Звук работает на любой странице; хранится на этом устройстве.",
          "Завантажені файли зʼявляються у списках вибору — і для повідомлення, і для дзвінка. Звук працює на будь-якій сторінці; зберігається на цьому пристрої.")}
      </div>
    </div>
  );
}
