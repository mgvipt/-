/* Публічна сторінка прийняття запрошення: співробітник ставить пароль → акаунт. */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "./api";
import { Icon } from "./Icon";

export default function InviteAccept() {
  const { token } = useParams();
  const nav = useNavigate();
  const [info, setInfo] = useState<any>(undefined);
  const [pwd, setPwd] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    api.get<any>(`/api/invite/${token}/`).then(setInfo).catch(() => setInfo({ valid: false }));
  }, [token]);

  async function accept() {
    setErr("");
    try {
      await api.post(`/api/invite/${token}/`, { password: pwd });
      setDone(true); setTimeout(() => nav("/login"), 2200);
    } catch (e: any) {
      const m = String(e?.message || "").match(/"detail"\s*:\s*"([^"]+)"/);
      setErr(m ? m[1] : "Помилка");
    }
  }

  const wrap: any = { minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f3efe9" };
  const card: any = { width: 360, background: "#fff", borderRadius: 16, boxShadow: "0 14px 44px rgba(0,0,0,.12)", padding: 26 };

  if (info === undefined) return <div className="spin">…</div>;
  if (!info.valid) return <div style={wrap}><div style={card}><h3>Запрошення недійсне або прострочене</h3><p className="muted">Зверніться до керівника за новим лінком.</p></div></div>;
  if (done) return <div style={wrap}><div style={card}><h3><Icon n="✅" size={18} /> Акаунт створено!</h3><p>Переходимо на вхід…</p></div></div>;

  return (
    <div style={wrap}>
      <div style={card}>
        <div style={{ fontWeight: 800, fontSize: 20, marginBottom: 4 }}>Wallcov CRM</div>
        <div className="muted" style={{ marginBottom: 16 }}>Запрошення в команду</div>
        {(info.first_name || info.last_name) && <div style={{ fontSize: 16, fontWeight: 600 }}>{info.first_name} {info.last_name}</div>}
        <div className="muted" style={{ fontSize: 13, marginBottom: 2 }}>{info.email}</div>
        {info.department && <div style={{ fontSize: 13, marginBottom: 14 }}>Відділ: <b>{info.department}</b></div>}
        <label className="label" style={{ display: "block", marginBottom: 4 }}>Придумайте пароль</label>
        <input type="password" value={pwd} onChange={(e) => setPwd(e.target.value)} onKeyDown={(e) => e.key === "Enter" && accept()}
          placeholder="мінімум 6 символів" style={{ width: "100%", height: 40, borderRadius: 9, border: "1px solid #cbd5e1", padding: "0 12px", fontSize: 14, marginBottom: 12 }} />
        {err && <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 10 }}>{err}</div>}
        <button className="btn btn-primary" style={{ width: "100%", height: 42 }} onClick={accept} disabled={pwd.length < 6}>Приєднатися до команди</button>
      </div>
    </div>
  );
}
