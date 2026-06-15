import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, Card, Funnel } from "../api";
import { Avatar } from "../ui";

export default function DealCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const [deal, setDeal] = useState<Card | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);

  useEffect(() => {
    api.get<Card>(`/api/deals/${id}/`).then(async (d) => {
      setDeal(d);
      const f = await api.get<Funnel>(`/api/funnels/${d.funnel}/`);
      setFunnel(f);
    });
  }, [id]);

  if (!deal) return <div className="spin">Загрузка сделки…</div>;
  const curStageOrder = funnel?.stages.find((s) => s.id === deal.stage)?.order ?? 0;

  return (
    <div className="scroll fade">
      <div className="dealhead">
        <button className="back" onClick={() => nav("/deals")}>←</button>
        <b style={{ fontSize: 16 }}>{deal.title}</b>
        <span className="muted">{funnel?.name}</span>
        <div className="spacer" />
        <button className="btn btn-primary">Пропозиція ▾</button>
      </div>

      {funnel && (
        <div className="stagebar">
          {funnel.stages.map((s) => (
            <div key={s.id} className="stage"
              style={{ background: s.order <= curStageOrder ? "var(--brand)" : "#cbd5e1" }}>
              {s.name}
            </div>
          ))}
        </div>
      )}

      <div className="grid2">
        <div>
          <div className="panel">
            <div className="label">Клієнт</div>
            <div style={{ fontWeight: 600 }}>{deal.contact_name || "—"}</div>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button className="btn" style={{ flex: 1, background: "#ecfdf5", color: "#047857" }}>📞 Позвонить</button>
              <button className="btn" style={{ flex: 1, background: "#eff6ff", color: "#1d4ed8" }}>💬 Чат</button>
            </div>
          </div>
          <div className="panel">
            <div className="label">Відповідальний</div>
            <div className="owner" style={{ fontSize: 13 }}>
              <Avatar name={deal.owner_name || "—"} />{deal.owner_name || "—"}
            </div>
          </div>
          <div className="panel">
            <div className="label">Сума</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              {Number(deal.amount).toLocaleString("ru")} <span className="muted" style={{ fontSize: 14 }}>грн.</span>
            </div>
            <button className="btn btn-primary" style={{ width: "100%", height: 36, marginTop: 10 }}>Прийняти оплату</button>
          </div>
        </div>
        <div>
          <div className="panel">
            <div className="label">Лента событий</div>
            <div className="muted" style={{ fontSize: 13 }}>
              Здесь появятся звонки с записью, сообщения из мессенджеров и бизнес-процессы — подключаются на этапах «Чаты» и «Телефония».
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
