import { useEffect, useState } from "react";
import { api } from "./api";

/* 16.09.2026 (Олег): «Подяка від керівника» — не гроші, а видима вдячність. Співробітник бачить свої подяки;
   керівник може подякувати (кнопка з текстом «за що»). */
export function ThanksList({ userId }: { userId?: number }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.get<any>(`/api/gamification/thanks/?user=${userId || "me"}`).then(setD).catch(() => setD(null)); }, [userId]);
  if (!d || !(d.items || []).length) return null;
  return (
    <div className="panel" style={{ margin: "0 0 12px", borderLeft: "4px solid #16a34a" }}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>💚 Подяки від керівника</div>
      {d.items.slice(0, 5).map((x: any) => (
        <div key={x.id} style={{ fontSize: 13, padding: "4px 0", borderTop: "1px solid #f1f5f9" }}>
          <span className="muted" style={{ fontSize: 12 }}>{x.date}</span> — {x.text}{x.by ? <span className="muted" style={{ fontSize: 12 }}> · {x.by}</span> : null}
        </div>))}
    </div>
  );
}

export function ThankButton({ userId, name }: { userId: number; name: string }) {
  const [done, setDone] = useState(false);
  const give = () => {
    const text = prompt(`Подякувати: ${name}\nЗа що? (побачить у «Розвитку»)`, "Усі відправки в день оплати і без помилок");
    if (!text) return;
    api.post("/api/gamification/thanks/", { user: userId, text }).then(() => setDone(true)).catch((e: any) => alert(e?.response?.data?.detail || "Не вдалося"));
  };
  return <button type="button" className="btn btn-light" style={{ fontSize: 12, height: 28, padding: "0 10px" }} onClick={give}>{done ? "💚 Подякували" : "💚 Подякувати"}</button>;
}
