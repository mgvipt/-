import { useState } from "react";
import { login } from "../api";
import { useAuth } from "../auth";

export default function Login() {
  const { refresh } = useAuth();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try { await login(u, p); await refresh(); }
    catch (ex: any) { setErr(ex.message ?? "Ошибка входа"); }
    finally { setBusy(false); }
  }

  return (
    <div className="login-wrap">
      <form className="login-box" onSubmit={submit}>
        <h2>Wallcov</h2>
        <div className="muted" style={{ fontSize: 13 }}>Вход в систему</div>
        <input placeholder="Логин" value={u} onChange={(e) => setU(e.target.value)} autoFocus />
        <input placeholder="Пароль" type="password" value={p} onChange={(e) => setP(e.target.value)} />
        {err && <div className="err">{err}</div>}
        <button className="btn btn-primary" disabled={busy}>{busy ? "Вход…" : "Войти"}</button>
        <div className="muted" style={{ fontSize: 11, marginTop: 12 }}>
          Демо: kirill / demo12345 (менеджер), head / demo12345 (руководитель)
        </div>
      </form>
    </div>
  );
}
