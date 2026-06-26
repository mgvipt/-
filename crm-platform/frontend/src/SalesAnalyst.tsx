import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";

const DIM_LABELS: Record<string, [string, string]> = {
  "вступ": ["Вступление", "Вступ"],
  "виявлення_потреби": ["Выявление потребности", "Виявлення потреби"],
  "презентація_цінності": ["Презентация ценности", "Презентація цінності"],
  "робота_з_запереченнями": ["Работа с возражениями", "Робота з запереченнями"],
  "заклик_до_дії": ["Призыв к действию", "Заклик до дії"],
  "тон_емпатія": ["Тон / эмпатия", "Тон / емпатія"],
};

function barColor(v: number) { return v >= 70 ? "#1D9E75" : v >= 40 ? "#EF9F27" : "#E24B4A"; }
function scoreColor(v: number) { return v >= 70 ? "#0F6E56" : v >= 40 ? "#854F0B" : "#A32D2D"; }
function scoreBg(v: number) { return v >= 70 ? "#E1F5EE" : v >= 40 ? "#FAEEDA" : "#FCEBEB"; }

export function SalesAnalystPanel({ kind, id, onInsert }: { kind: "deals" | "leads"; id: string | number; onInsert?: (t: string) => void }) {
  const { t } = useLang();
  const [a, setA] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => { api.get<any>(`/api/${kind}/${id}/sales_analysis/`).then(setA).catch(() => {}); }, [kind, id]);
  async function refresh() { setLoading(true); try { setA(await api.post<any>(`/api/${kind}/${id}/sales_analysis/`, {})); } catch { /* */ } setLoading(false); }

  const score = a?.overall ?? null;
  return (
    <div style={{ background: "#fff", border: "0.5px solid #e2e8f0", borderRadius: 12, padding: "12px 14px", marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <Icon n="🧠" size={16} />
        <b style={{ fontSize: 13.5 }}>{t("Аналитик продаж — коуч", "Аналітик продажів — коуч")}</b>
        <button className="btn" style={{ marginLeft: "auto", padding: "3px 10px", fontSize: 12 }} onClick={refresh} disabled={loading}>
          {loading ? "…" : (a && !a.empty ? t("🎓 Обновить оценку качества", "🎓 Оновити оцінку якості") : t("🎓 Оценить качество диалога", "🎓 Оцінити якість діалогу"))}
        </button>
      </div>

      {!a && <div className="muted" style={{ fontSize: 12.5 }}>{t("Загрузка…", "Завантаження…")}</div>}
      {a?.empty && <div className="muted" style={{ fontSize: 12.5 }}>{a.why_not_selling || t("Нет диалога для разбора", "Немає діалогу для розбору")}</div>}

      {a && !a.empty && score != null && (<>
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 10 }}>
          <div style={{ width: 60, height: 60, borderRadius: "50%", background: scoreBg(score), display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <span style={{ fontSize: 19, fontWeight: 600, color: scoreColor(score) }}>{score}</span>
            <span style={{ fontSize: 9, color: scoreColor(score) }}>{t("качество", "якість")}</span>
          </div>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
            {Object.entries(a.scores || {}).map(([k, v]: any) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
                <span style={{ width: 118, color: "#64748b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{(DIM_LABELS[k] ? t(DIM_LABELS[k][0], DIM_LABELS[k][1]) : k)}</span>
                <div style={{ flex: 1, height: 5, background: "#eef2f6", borderRadius: 5 }}><div style={{ width: `${v}%`, height: 5, background: barColor(v), borderRadius: 5 }} /></div>
              </div>
            ))}
          </div>
        </div>

        {a.strengths && <div style={{ background: "#E1F5EE", borderRadius: 8, padding: "8px 10px", marginBottom: 7 }}>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "#0F6E56", marginBottom: 2 }}><Icon n="✅" size={14} /> {t("Что хорошо", "Що добре")}</div>
          <div style={{ fontSize: 12, color: "#04342C", lineHeight: 1.5 }}>{a.strengths}</div></div>}

        {a.why_not_selling && <div style={{ background: "#FCEBEB", borderRadius: 8, padding: "8px 10px", marginBottom: 7 }}>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "#A32D2D", marginBottom: 2 }}><Icon n="⚠️" size={14} /> {t("Почему не ведёт к продаже", "Чому не веде до продажу")}</div>
          <div style={{ fontSize: 12, color: "#791F1F", lineHeight: 1.5 }}>{a.why_not_selling}</div></div>}

        {a.recommended_reply && <div style={{ background: "#E6F1FB", borderRadius: 8, padding: "8px 10px", marginBottom: 7 }}>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "#185FA5", marginBottom: 2 }}><Icon n="💬" size={14} /> {t("Как лучше ответить", "Як краще відповісти")}</div>
          <div style={{ fontSize: 12, color: "#042C53", lineHeight: 1.5, marginBottom: 6 }}>{a.recommended_reply}</div>
          <button className="btn" style={{ padding: "3px 10px", fontSize: 11.5 }} onClick={() => { if (onInsert) onInsert(a.recommended_reply); else { navigator.clipboard?.writeText(a.recommended_reply); } }}>
            {onInsert ? t("↳ Вставить в ответ", "↳ Вставити у відповідь") : t("Скопировать", "Скопіювати")}
          </button></div>}

        {a.coaching && <div style={{ background: "#EEEDFE", borderRadius: 8, padding: "8px 10px" }}>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "#534AB7", marginBottom: 2 }}><Icon n="🎓" size={14} /> {t("Мини-урок", "Міні-урок")}</div>
          <div style={{ fontSize: 12, color: "#26215C", lineHeight: 1.5 }}>{a.coaching}</div></div>}

        {a.created_at && <div className="muted" style={{ fontSize: 10, marginTop: 7, textAlign: "right" }}>{t("разбор от", "розбір від")} {new Date(a.created_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</div>}
      </>)}
    </div>
  );
}
