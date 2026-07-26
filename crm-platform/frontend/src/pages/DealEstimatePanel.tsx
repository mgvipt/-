import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

interface Estimate {
  id: number; name: string; contact_name: string; deal_id: number | null; project_uuid: string | null;
  status: string; version: number; can_edit: boolean;
  measurement: any; lines: any[]; totals: any; updated_at: string;
}

const fmt = (value: any, digits = 2) => Number(value || 0).toLocaleString("ru", { maximumFractionDigits: digits });

export default function DealEstimatePanel({ dealId }: { dealId: number }) {
  const { t } = useLang();
  const [rows, setRows] = useState<Estimate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");

  function load() {
    setLoading(true); setError("");
    api.get<Estimate[]>(`/api/estimates/?deal_id=${dealId}`)
      .then(setRows)
      .catch((e: any) => setError(e?.response?.data?.detail || t("Не удалось загрузить смету", "Не вдалося завантажити кошторис")))
      .finally(() => setLoading(false));
  }
  useEffect(load, [dealId]);

  async function status(row: Estimate, value: string) {
    if (!row.can_edit) return;
    setActionError("");
    try {
      const updated = await api.patch<Estimate>(`/api/estimates/${row.id}/`, { status: value });
      setRows((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || t("Не удалось изменить статус сметы", "Не вдалося змінити статус кошторису"));
    }
  }

  if (loading) return <div className="panel muted">{t("Загрузка сметы…", "Завантаження кошторису…")}</div>;
  if (error) return <div className="note" style={{ color: "#b91c1c" }}>{error}</div>;
  if (!rows.length) return (
    <div className="panel" style={{ textAlign: "center", padding: 32 }}>
      <div style={{ fontSize: 40 }}>📐</div>
      <h3>{t("Смета ещё не отправлена", "Кошторис ще не надіслано")}</h3>
      <div className="muted">{t("После кнопки «Отправить смету» в Wallcov Замер здесь появятся комнаты, площади, откосы и позиции.",
        "Після кнопки «Надіслати кошторис» у Wallcov Замір тут зʼявляться кімнати, площі, укоси та позиції.")}</div>
    </div>
  );

  return <div style={{ display: "grid", gap: 14 }}>
    {actionError && <div className="note" style={{ color: "#b91c1c", margin: 0 }}>{actionError}</div>}
    {rows.map((row) => {
      const measurement = row.measurement || {};
      const rooms = Array.isArray(measurement.rooms) ? measurement.rooms : [];
      const totals = measurement.totals || row.totals?.measurement || {};
      return <div className="panel" key={row.id} style={{ margin: 0 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div>
            <h3 style={{ margin: "0 0 3px" }}>{row.name}</h3>
            <div className="muted" style={{ fontSize: 12 }}>
              ID {row.id} · v{row.version} · {new Date(row.updated_at).toLocaleString("ru")}
            </div>
          </div>
          <div className="spacer" />
          <select value={row.status} disabled={!row.can_edit}
            title={row.can_edit ? "" : t("Только ответственный может менять статус", "Лише відповідальний може змінювати статус")}
            onChange={(e) => status(row, e.target.value)}
            style={{ height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px" }}>
            <option value="draft">{t("Черновик", "Чернетка")}</option>
            <option value="sent">{t("Отправлена", "Надіслано")}</option>
            <option value="accepted">{t("Согласована", "Погоджено")}</option>
            <option value="archived">{t("Архив", "Архів")}</option>
          </select>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(145px,1fr))", gap: 8, marginTop: 14 }}>
          {[
            [t("Стены", "Стіни"), `${fmt(totals.net_m2)} м²`],
            [t("Пол", "Підлога"), `${fmt(totals.floor_m2)} м²`],
            [t("Потолок", "Стеля"), `${fmt(totals.ceiling_m2)} м²`],
            [t("Откосы · работа", "Укоси · робота"), `${fmt(totals.reveals_linear_m)} м.п.`],
            [t("Откосы · материал", "Укоси · матеріал"), `${fmt(totals.reveals_area_m2)} м²`],
          ].map(([label, value]) => <div key={label} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 9, padding: 10 }}>
            <div className="muted" style={{ fontSize: 11 }}>{label}</div><b>{value}</b>
          </div>)}
        </div>

        {rooms.length > 0 && <div style={{ marginTop: 14 }}>
          <b>{t("Комнаты", "Кімнати")}</b>
          <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
            {rooms.map((room: any, index: number) => <div key={room.name || index} style={{ display: "flex", gap: 10, flexWrap: "wrap", padding: "8px 10px", borderRadius: 8, background: "#f8fafc" }}>
              <b>{room.name || `${t("Комната", "Кімната")} ${index + 1}`}</b>
              <span>{t("стены", "стіни")} {fmt(room.net_m2)} м²</span>
              <span>{t("пол", "підлога")} {fmt(room.floor_m2)} м²</span>
              <span>{t("потолок", "стеля")} {fmt(room.ceiling_m2)} м²</span>
              <span>{t("откосы", "укоси")} {fmt(room.reveals_linear_m)} м.п. / {fmt(room.reveals_area_m2)} м²</span>
            </div>)}
          </div>
        </div>}

        <div style={{ marginTop: 14 }}>
          <b>{t("Позиции", "Позиції")}</b>
          <div style={{ overflowX: "auto", marginTop: 6 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead><tr style={{ textAlign: "left", borderBottom: "1px solid #cbd5e1" }}>
                <th style={{ padding: 7 }}>{t("Тип", "Тип")}</th><th>{t("Наименование", "Найменування")}</th>
                <th>{t("Количество", "Кількість")}</th><th style={{ textAlign: "right" }}>{t("Сумма", "Сума")}</th>
              </tr></thead>
              <tbody>{(row.lines || []).map((line: any, index: number) => <tr key={index} style={{ borderBottom: "1px solid #eef2f7" }}>
                <td style={{ padding: 7 }}>{line.role || "—"}</td><td>{line.title || "—"}</td>
                <td>{fmt(line.quantity)} {line.unit || ""}</td><td style={{ textAlign: "right" }}>{fmt(line.cost, 0)} ₴</td>
              </tr>)}</tbody>
            </table>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "baseline", gap: 12, marginTop: 14, paddingTop: 12, borderTop: "2px solid #e2e8f0" }}>
          <span className="muted">{t("Итого", "Разом")}</span>
          <b style={{ fontSize: 24 }}>{fmt(row.totals?.total, 0)} ₴</b>
        </div>
      </div>;
    })}
  </div>;
}
