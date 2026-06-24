import { useState } from "react";
import { login } from "../api";
import { useAuth } from "../auth";
import { useLang } from "../i18n";

export default function Login() {
  const { refresh } = useAuth();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const { t } = useLang();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try { await login(u, p); await refresh(); }
    catch (ex: any) { setErr(ex.message ?? t("Ошибка входа","Помилка входу")); }
    finally { setBusy(false); }
  }

  return (
    <div className="login-wrap">
      <form className="login-box" onSubmit={submit}>
        <h2>Wallcov</h2>
        <div className="muted" style={{ fontSize: 13 }}>{t("Вход в систему","Вхід у систему")}</div>
        <input placeholder={t("Логин","Логін")} value={u} onChange={(e) => setU(e.target.value)} autoFocus />
        <input placeholder={t("Пароль","Пароль")} type="password" value={p} onChange={(e) => setP(e.target.value)} />
        {err && <div className="err">{err}</div>}
        <button className="btn btn-primary" disabled={busy}>{busy ? t("Вход…","Вхід…") : t("Войти","Увійти")}</button>
        <div className="muted" style={{ fontSize: 11, marginTop: 12 }}>
          {t("Демо: kirill / demo12345 (менеджер), head / demo12345 (руководитель)","Демо: kirill / demo12345 (менеджер), head / demo12345 (керівник)")}
        </div>
      </form>
    </div>
  );
}
