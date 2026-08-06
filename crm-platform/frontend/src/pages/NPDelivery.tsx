/* Доставка Нова Пошта — порт 1:1 з Cashflow (cashflow.html «Доставка НП»).
   Відправник · Отримувач · Пакування (місця+обʼєм) · Контроль оплати · Оцінка · ТТН.
   Дані в deal.np_data → синхронно для менеджера і складу. */
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

const PRESETS: any = {
  bucket10: { t: "Ведро 10л", l: 25, w: 25, h: 30, kg: 5 },
  bucket25: { t: "Ведро 25л", l: 32, w: 32, h: 38, kg: 12 },
  boxS: { t: "Коробка S", l: 20, w: 20, h: 15, kg: 1 },
  boxM: { t: "Коробка M", l: 30, w: 30, h: 25, kg: 3 },
  boxL: { t: "Коробка L", l: 40, w: 40, h: 35, kg: 6 },
  pallet60: { t: "Палета 60×80", l: 60, w: 80, h: 100, kg: 100 },
  pallet120: { t: "Палета 120×80", l: 120, w: 80, h: 100, kg: 200 },
};

/* автокомпліт міста/відділення/вулиці */
function Auto({ kind, value, onPick, onType, placeholder, disabled, settlementRef, cityName }: any) {
  const [q, setQ] = useState(value || "");
  const [list, setList] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const box = useRef<any>(null);
  const picked = useRef(false);   // щойно ВИБРАЛИ зі списку — не шукати повторно
  const focused = useRef(false);
  useEffect(() => { setQ(value || ""); }, [value]);
  // відділення/поштомати: одразу підвантажуємо ПОВНИЙ список по місту, щоб випадав без набору
  useEffect(() => {
    if (kind !== "warehouse" || !settlementRef) return;
    let ok = true;
    api.get<any[]>(`/api/deals/np_warehouses/?settlement_ref=${encodeURIComponent(settlementRef)}&q=`).then((r) => { if (ok) { setList(r || []); if (focused.current) setOpen(true); } }).catch(() => {});
    return () => { ok = false; };
  }, [settlementRef]);
  useEffect(() => {
    if (picked.current) { picked.current = false; return; }
    const minLen = kind === "warehouse" ? 1 : 2;
    if (!q || q.length < minLen) { if (kind !== "warehouse") setList([]); return; }
    const tm = setTimeout(() => {
      let url = "";
      if (kind === "warehouse") url = `/api/deals/np_warehouses/?settlement_ref=${encodeURIComponent(settlementRef || "")}&q=${encodeURIComponent(q)}`;
      else if (kind === "street") url = `/api/deals/np_streets/?settlement_ref=${encodeURIComponent(settlementRef || "")}&q=${encodeURIComponent(q)}&city=${encodeURIComponent(cityName || "")}`;
      else url = `/api/deals/np_cities/?q=${encodeURIComponent(q)}`;
      api.get<any[]>(url).then((r) => { setList(r || []); if (focused.current) setOpen(true); }).catch(() => {});
    }, 250);
    return () => clearTimeout(tm);
  }, [q]);
  useEffect(() => {
    const h = (e: any) => { if (box.current && !box.current.contains(e.target)) { setOpen(false); focused.current = false; } };
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h);
  }, []);
  const inp = { width: "100%", height: 38, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", boxSizing: "border-box" as const, fontSize: 13.5, background: disabled ? "#f1f5f9" : "#fff" };
  return (
    <div ref={box} style={{ position: "relative" }}>
      <input type="search" value={q} disabled={disabled} placeholder={placeholder} style={inp}
        onChange={(e) => { setQ(e.target.value); if (onType) onType(e.target.value); }} onFocus={() => { focused.current = true; if (list.length) { setOpen(true); } else if (kind === "warehouse" && settlementRef) { api.get<any[]>(`/api/deals/np_warehouses/?settlement_ref=${encodeURIComponent(settlementRef)}&q=${encodeURIComponent(q || "")}`).then((r) => { setList(r || []); setOpen(true); }).catch(() => {}); } }} />
      {open && list.length > 0 && <ul style={{ position: "absolute", zIndex: 40, top: 40, left: 0, right: 0, margin: 0, padding: 0, listStyle: "none", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, maxHeight: 220, overflowY: "auto", boxShadow: "0 10px 28px rgba(0,0,0,.14)" }}>
        {list.map((it, i) => <li key={i} onClick={() => { picked.current = true; onPick(it); setQ(it.name || it.desc || it.Present || ""); setOpen(false); }} style={{ padding: "8px 11px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f1f5f9" }}>
          {kind === "warehouse" ? (it.desc || it.name) : kind === "street" ? it.name : <>{it.name} <span style={{ color: "#94a3b8" }}>{it.area}</span></>}
        </li>)}
      </ul>}
    </div>
  );
}

function Grid({ children }: any) {
  return <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 460 }}>{children}</div>;
}

export default function NPDelivery({ deal, onReload, flash, readOnly, defaultWeight, codReadOnly }: any) {
  const { t } = useLang();
  const D = deal.np_data && Object.keys(deal.np_data).length ? deal.np_data : {};
  const [snd, setSnd] = useState<any>(D.sender || { pickup: "warehouse", city: "", city_ref: "", wh: "", wh_ref: "", street: "", house: "", flat: "" });
  const [rec, setRec] = useState<any>(D.recipient || {
    service: "WarehouseWarehouse", city: "", city_name: "", area: "", region: "", settlement_ref: "", city_ref: "",
    wh: "", wh_number: "", street: "", street_ref: "", house: "", flat: "",
    name: (deal as any).contact_name || "", phone: (deal as any).contact_phone || "",
  });
  const [par, setPar] = useState<any>(D.parcel || { descr: "Декоративне покриття", declared: String(Math.round(Number(deal.amount) || 100)), payer: "Recipient", method: "Cash" });
  const [cargo, setCargo] = useState(D.cargo_type || "Parcel");
  const [seats, setSeats] = useState<any[]>(D.seats && D.seats.length ? D.seats : [{ l: 30, w: 30, h: 30, kg: Number(defaultWeight) || 5 }]);
  const [pack, setPack] = useState<any>(D.pack || { ref: "", saturday: false, return_docs: false });
  const [note, setNote] = useState(D.note || "");
  const [items, setItems] = useState(D.cargo_details || (deal.items || []).map((i: any) => `${i.product_name || i.product} · ${i.quantity} шт`).join("\n"));
  const _payType = String((deal as any).pay_type || "").toLowerCase();
  const _remain = Math.max(0, Math.round((Number(deal.amount) || 0) - (Number((deal as any).paid) || 0)));
  const _wantsCod = _payType === "prepay_np" || /наклад|cod|післяпл|послеопл|післяоплат|np_cod/.test(_payType);
  // Авто «Контроль оплати»: якщо тип оплати = наложка/передоплата-НП і є залишок —
  // одразу вмикаємо і підставляємо залишок (щоб менеджер не забув). Склад це не знімає.
  const [bw, setBw] = useState<any>(D.backward || ((_wantsCod && _remain > 0) ? { on: true, amount: String(_remain) } : { on: false, amount: "" }));
  const [date, setDate] = useState((deal as any).np_delivery_date || "");
  const [timeInterval, setTimeInterval] = useState(D.time_interval || "");
  const [packlist, setPacklist] = useState<any[]>([]);
  const [price, setPrice] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const ttn = deal.ttn;

  useEffect(() => { api.get<any[]>("/api/deals/np_packlist/").then(setPacklist).catch(() => {}); }, []);

  const totW = seats.reduce((s, x) => s + (Number(x.kg) || 0), 0);
  const totV = seats.reduce((s, x) => s + (Number(x.l) * Number(x.w) * Number(x.h) || 0), 0);
  const volM3 = totV / 1_000_000;
  const volW = totV / 4000;
  const chargeW = Math.max(totW, volW);

  const setSeat = (i: number, k: string, v: any) => setSeats((p) => p.map((s, j) => j === i ? { ...s, [k]: v } : s));
  const addSeat = () => setSeats((p) => [...p, { l: 30, w: 30, h: 30, kg: 5 }]);
  const delSeat = (i: number) => setSeats((p) => p.length > 1 ? p.filter((_, j) => j !== i) : p);
  const applyPreset = (key: string) => { const pr = PRESETS[key]; setSeats((p) => [...p, { l: pr.l, w: pr.w, h: pr.h, kg: pr.kg }]); };

  const collect = () => ({ sender: snd, recipient: rec, parcel: par, cargo_type: cargo, seats, pack, note, cargo_details: items, backward: bw, time_interval: timeInterval });

  const save = (silent?: boolean) => {
    setBusy("save");
    return api.post(`/api/deals/${deal.id}/np_save/`, { np_data: collect(), delivery_date: date || null })
      .then(() => { if (!silent) flash && flash(t("✓ Сохранено", "✓ Збережено")); })
      .catch(() => flash && flash(t("Ошибка сохранения", "Помилка збереження"))).finally(() => setBusy(""));
  };
  const estimate = () => {
    setBusy("est");
    const props: any = { CityRecipient: rec.city_ref || "", Weight: String(chargeW || totW || 1), ServiceType: rec.service, Cost: par.declared, CargoType: cargo, SeatsAmount: String(seats.length) };
    if (bw.on) props.RedeliveryCalculate = { CargoType: "Money", Amount: bw.amount || par.declared };
    if (pack.ref) { props.PackCount = "1"; props.PackRef = pack.ref; }
    api.post<any>(`/api/deals/${deal.id}/np_estimate/`, { props }).then(setPrice).catch(() => flash && flash(t("Не удалось оценить", "Не вдалося оцінити"))).finally(() => setBusy(""));
  };
  const createTTN = () => {
    if (!rec.name || !rec.phone || !rec.city_name || (rec.service !== "WarehouseDoors" && !rec.wh_number)) { flash && flash(t("Заполни: имя, телефон, город, отделение", "Заповни: імʼя, телефон, місто, відділення")); return; }
    if (rec.service === "WarehouseDoors" && (!rec.street || !rec.house)) { flash && flash(t("Адресная доставка: заполни улицу и дом", "Адресна доставка: заповни вулицю і будинок")); return; }
    setBusy("ttn");
    save(true);
    api.post<any>(`/api/deals/${deal.id}/create_ttn/`, {
      recipient_name: rec.name, recipient_phone: rec.phone, recipient_city_name: rec.city_name, recipient_area: rec.area, recipient_region: rec.region,
      warehouse_number: rec.wh_number, street: rec.street, street_ref: rec.street_ref, house: rec.house, flat: rec.flat,
      weight: String(chargeW || totW || 1), seats: String(seats.length), cost: par.declared, service_type: rec.service,
      cargo_type: cargo, description: par.descr, cargo_details: items, additional: note, pack_ref: pack.ref, time_interval: timeInterval,
      saturday: pack.saturday, return_docs: pack.return_docs, payer: par.payer, payment_method: par.method,
      cod_amount: bw.on ? (bw.amount || par.declared) : 0, delivery_date: date,
    }).then((r) => { flash && flash(t(`✓ ТТН ${r.ttn} создана`, `✓ ТТН ${r.ttn} створена`)); onReload && onReload(); })
      .catch((e: any) => flash && flash(t("Ошибка НП: ", "Помилка НП: ") + (e?.response?.data?.detail || ""))).finally(() => setBusy(""));
  };

  const printTTN = async (fmt: string) => {
    try { const u = await api.blobUrl(`/api/deals/${deal.id}/np_print/?fmt=${fmt}`); window.open(u, "_blank"); }
    catch { flash && flash(t("Не удалось напечатать", "Не вдалося надрукувати")); }
  };
  const recreateTTN = () => {
    if (!confirm(t("Удалить текущую ТТН и создать новую? Оплата и чек остаются.", "Видалити поточну ТТН і створити нову? Оплата і чек лишаються."))) return;
    setBusy("re");
    api.post(`/api/deals/${deal.id}/np_recreate/`, {}).then(() => { flash && flash(t("ТТН удалена — заполни заново", "ТТН видалено — заповни заново")); onReload && onReload(); }).catch(() => flash && flash(t("Ошибка", "Помилка"))).finally(() => setBusy(""));
  };
  const cancelTTN = () => {
    if (!confirm(t("ПОЛНАЯ отмена: удалить ТТН + откат стадии. Деньги вернёшь клиенту вручную. Продолжить?", "ПОВНЕ скасування: видалити ТТН + відкат стадії. Гроші повернеш клієнту вручну. Продовжити?"))) return;
    setBusy("cancel");
    api.post(`/api/deals/${deal.id}/np_cancel/`, {}).then(() => { flash && flash(t("Заказ отменён — нужен возврат средств вручную", "Замовлення скасовано — потрібне повернення коштів вручну")); onReload && onReload(); }).catch(() => flash && flash(t("Ошибка", "Помилка"))).finally(() => setBusy(""));
  };

  /* стилі */
  const lbl = { fontSize: 11.5, color: "#475569", fontWeight: 600, marginBottom: 3, display: "block" } as const;
  const inp = { width: "100%", height: 38, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", boxSizing: "border-box" as const, fontSize: 13.5 };
  const zone = (bg: string, bd: string) => ({ background: bg, border: "1px solid " + bd, borderRadius: 12, padding: 14, marginBottom: 14 });
  const Card = ({ checked, onClick, icon, title, desc, color }: any) => (
    <button type="button" disabled={readOnly} onClick={onClick} style={{ flex: "0 1 auto", maxWidth: 200, textAlign: "left", padding: "7px 11px", borderRadius: 9, border: "2px solid " + (checked ? color : "#e2e8f0"), background: checked ? "#fff" : "#fafafa", cursor: "pointer", boxShadow: checked ? `0 0 0 2px ${color}22` : "none" }}>
      <div style={{ fontSize: 15 }}><Icon n={icon} size={18} /></div>
      <div style={{ fontWeight: 700, fontSize: 13, color: checked ? color : "#334155" }}>{title}</div>
      <div style={{ fontSize: 10.5, color: "#94a3b8", lineHeight: 1.2 }}>{desc}</div>
    </button>
  );

  return (
    <div className="panel" style={{ margin: 0 }}>
      <h3 style={{ margin: "0 0 4px", fontSize: 17, display: "flex", alignItems: "center", gap: 6 }}><Icon n="package" size={18} /> {t("Создать ТТН Нова Пошта", "Створити ТТН Нова Пошта")} {ttn && <span style={{ fontSize: 13, color: "#16a34a" }}>· {ttn}</span>}</h3>
      <p style={{ margin: "0 0 14px", fontSize: 12.5, color: "#64748b" }}>{t("Заполни данные — сервер сам вызовет НП и запишет ТТН в сделку.", "Заповни дані — сервер сам викличе НП і запише ТТН в угоду.")}</p>

      {ttn ? (
        <div style={zone("#f0fdf4", "#bbf7d0")}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <Icon n="package" size={18} />
            <b style={{ fontSize: 14 }}>{t("Активная ТТН", "Активна ТТН")}:</b>
            <span style={{ fontFamily: "monospace", fontSize: 15, fontWeight: 700, color: "#166534" }}>{ttn}</span>
          </div>
          <div style={{ fontSize: 11.5, color: "#475569", fontWeight: 600, marginBottom: 5 }}><Icon n="printer" size={13} /> {t("Печать:", "Друк:")}</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
            <button className="btn btn-light" onClick={() => printTTN("A4")} style={{ display: "flex", alignItems: "center", gap: 5 }}><Icon n="file" size={14} /> A4 {t("накладная", "накладна")}</button>
            <button className="btn btn-light" onClick={() => printTTN("m100")} style={{ display: "flex", alignItems: "center", gap: 5 }}><Icon n="printer" size={14} /> 100×100 {t("мм", "мм")}</button>
            <button className="btn btn-light" onClick={() => printTTN("m85")} style={{ display: "flex", alignItems: "center", gap: 5 }}><Icon n="printer" size={14} /> 85×85 {t("мм", "мм")}</button>
            <button className="btn btn-light" onClick={() => printTTN("zebra")} style={{ display: "flex", alignItems: "center", gap: 5 }}><Icon n="truck" size={14} /> Zebra {t("термо", "термо")}</button>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={recreateTTN} disabled={!!busy} style={{ flex: 1, minWidth: 150, background: "#f97316", color: "#fff", border: "none", borderRadius: 9, padding: "9px 12px", cursor: "pointer", fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}><Icon n="refresh" size={15} /> {busy === "re" ? "…" : t("Пересоздать", "Перестворити")}</button>
            <button onClick={cancelTTN} disabled={!!busy} style={{ flex: 1, minWidth: 150, background: "#dc2626", color: "#fff", border: "none", borderRadius: 9, padding: "9px 12px", cursor: "pointer", fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}><Icon n="x" size={15} /> {busy === "cancel" ? "…" : t("Отменить заказ", "Скасувати замовлення")}</button>
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 8, lineHeight: 1.5 }}>
            <b>{t("Пересоздать", "Перестворити")}</b> — {t("удалить ТТН (ошибка в адресе/отделении). Оплата, чек и сделка остаются.", "видалити лише ТТН (помилка в адресі/відділенні). Оплата, чек і угода лишаються.")}<br />
            <b style={{ color: "#dc2626" }}>{t("Отменить заказ", "Скасувати замовлення")}</b> — {t("удалить ТТН + откат стадии. Деньги вернуть клиенту вручную (безопасность).", "видалити ТТН + відкат стадії. Гроші повернути клієнту вручну (безпека).")}
          </div>
        </div>
      ) : null}

      {/* ── ВІДПРАВНИК (teal) ── */}
      <div style={zone("#f0fdfa", "#99f6e4")}>
        <div style={{ fontWeight: 700, fontSize: 13.5, color: "#0f766e", marginBottom: 10 }}>📤 {t("Отправитель", "Відправник")} <span style={{ fontWeight: 400, color: "#5eead4", fontSize: 11 }}>({t("наша сторона", "наша сторона")})</span></div>
        <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
          <Card checked={snd.pickup === "warehouse"} onClick={() => setSnd({ ...snd, pickup: "warehouse" })} icon="🏤" title={t("Отделение", "Відділення")} desc={t("заносим в НП сами", "заносимо до НП самі")} color="#0d9488" />
          <Card checked={snd.pickup === "address"} onClick={() => setSnd({ ...snd, pickup: "address" })} icon="🚚" title={t("С адреса", "З адреси")} desc={t("курьер заберёт", "курʼєр забере")} color="#0d9488" />
        </div>
        {snd.pickup === "warehouse" ? <Grid>
          <div><label style={lbl}>{t("Город-отправитель", "Місто-відправник")}</label><Auto kind="city" value={snd.city} disabled={readOnly} placeholder="Кременчук, Київ…" onPick={(c: any) => setSnd({ ...snd, city: c.name, city_ref: c.city_ref || c.settlement_ref || c.ref, settlement_ref: c.settlement_ref || c.ref, wh: "", wh_ref: "" })} /></div>
          <div><label style={lbl}>{t("Отделение-отправитель", "Відділення-відправник")}</label><Auto kind="warehouse" value={snd.wh} disabled={readOnly || !snd.city_ref} settlementRef={snd.city_ref} placeholder={t("сначала город", "спершу місто")} onPick={(w: any) => setSnd({ ...snd, wh: w.desc || w.name, wh_ref: w.ref })} /></div>
        </Grid> : <Grid>
          <div><label style={lbl}>{t("Город-отправитель", "Місто-відправник")}</label><Auto kind="city" value={snd.city} disabled={readOnly} onPick={(c: any) => setSnd({ ...snd, city: c.name, city_ref: c.city_ref || c.settlement_ref || c.ref, settlement_ref: c.settlement_ref || c.ref })} /></div>
          <div><label style={lbl}>{t("Улица", "Вулиця")}</label><Auto kind="street" value={snd.street} disabled={readOnly || !(snd.city_ref || snd.city)} settlementRef={snd.settlement_ref || snd.city_ref} cityName={snd.city} onPick={(s: any) => setSnd({ ...snd, street: s.name, street_ref: s.ref })} onType={(v: string) => setSnd({ ...snd, street: v, street_ref: "" })} /></div>
          <div><label style={lbl}>{t("Дом", "Будинок")}</label><input value={snd.house} disabled={readOnly} onChange={(e) => setSnd({ ...snd, house: e.target.value })} style={inp} placeholder="12А" /></div>
          <div><label style={lbl}>{t("Кв./офис", "Кв./офіс")}</label><input value={snd.flat} disabled={readOnly} onChange={(e) => setSnd({ ...snd, flat: e.target.value })} style={inp} /></div>
        </Grid>}
      </div>

      {/* ── ОТРИМУВАЧ (orange) ── */}
      <div style={zone("#fff7ed", "#fed7aa")}>
        <div style={{ fontWeight: 700, fontSize: 13.5, color: "#9a3412", marginBottom: 10 }}>📥 {t("Получатель", "Отримувач")} <span style={{ fontWeight: 400, color: "#fb923c", fontSize: 11 }}>({t("куда доставить клиенту", "куди доставити клієнту")})</span></div>
        <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
          <Card checked={rec.service === "WarehouseWarehouse"} onClick={() => setRec({ ...rec, service: "WarehouseWarehouse" })} icon="🏤" title={t("Отделение", "Відділення")} desc={t("частый выбор", "найчастіший вибір")} color="#C67D5F" />
          <Card checked={rec.service === "WarehousePostomat"} onClick={() => setRec({ ...rec, service: "WarehousePostomat" })} icon="📮" title={t("Почтомат", "Поштомат")} desc={t("до 30 кг, 24/7", "до 30 кг, 24/7")} color="#C67D5F" />
          <Card checked={rec.service === "WarehouseDoors"} onClick={() => setRec({ ...rec, service: "WarehouseDoors" })} icon="🏠" title={t("Адрес", "Адреса")} desc={t("курьер домой", "курʼєр додому")} color="#C67D5F" />
        </div>
        <Grid>
          <div><label style={lbl}>{t("Город получателя", "Місто отримувача")}</label><Auto kind="city" value={rec.city} disabled={readOnly} placeholder="Кременчук, Київ, Львів…" onPick={(c: any) => setRec({ ...rec, city: c.name, city_name: c.name, area: c.area || "", region: c.region || "", settlement_ref: c.settlement_ref || c.ref, city_ref: c.city_ref || c.settlement_ref || c.ref, wh: "", wh_number: "", street: "", street_ref: "" })} /></div>
          {rec.service !== "WarehouseDoors" ? <div><label style={lbl}>{rec.service === "WarehousePostomat" ? t("Почтомат", "Поштомат") : t("Отделение", "Відділення")}</label><Auto kind="warehouse" value={rec.wh} disabled={readOnly || !(rec.city_ref || rec.settlement_ref)} settlementRef={rec.city_ref || rec.settlement_ref} placeholder={t("сначала город", "спершу місто")} onPick={(w: any) => setRec({ ...rec, wh: w.desc || w.name, wh_number: w.number })} /></div>
            : <>
              <div><label style={lbl}>{t("Улица", "Вулиця")}</label><Auto kind="street" value={rec.street} disabled={readOnly || !(rec.settlement_ref || rec.city_name || rec.city)} settlementRef={rec.settlement_ref} cityName={rec.city_name || rec.city} onPick={(s: any) => setRec({ ...rec, street: s.name, street_ref: s.ref })} onType={(v: string) => setRec({ ...rec, street: v, street_ref: "" })} /></div>
              <div><label style={lbl}>{t("Дом", "Будинок")}</label><input value={rec.house} disabled={readOnly} onChange={(e) => setRec({ ...rec, house: e.target.value })} style={inp} placeholder="12А" /></div>
              <div><label style={lbl}>{t("Квартира", "Квартира")}</label><input value={rec.flat} disabled={readOnly} onChange={(e) => setRec({ ...rec, flat: e.target.value })} style={inp} /></div>
              <div><label style={lbl}>📅 {t("Дата доставки курьером", "Дата доставки курʼєром")}</label><input type="date" value={date} disabled={readOnly} onChange={(e) => setDate(e.target.value)} style={inp} /></div>
              <div><label style={lbl}>🕒 {t("Время (интервал НП)", "Час (інтервал НП)")}</label><select value={timeInterval} disabled={readOnly} onChange={(e) => setTimeInterval(e.target.value)} style={inp}><option value="">{t("любое", "будь-який")}</option><option value="9:00-12:00">9:00–12:00</option><option value="12:00-15:00">12:00–15:00</option><option value="15:00-18:00">15:00–18:00</option><option value="18:00-21:00">18:00–21:00</option></select></div>
            </>}
          <div><label style={lbl}>{t("ФИО получателя", "ПІБ отримувача")}</label><input value={rec.name} disabled={readOnly} onChange={(e) => setRec({ ...rec, name: e.target.value })} style={inp} placeholder="Кріжевські Олег Леонідович" /></div>
          <div><label style={lbl}>{t("Телефон", "Телефон")}</label><input value={rec.phone} disabled={readOnly} onChange={(e) => setRec({ ...rec, phone: e.target.value })} style={inp} placeholder="0671234567" /></div>
          <div><label style={lbl}>{t("Описание вложения", "Опис вкладення")}</label><input value={par.descr} disabled={readOnly} onChange={(e) => setPar({ ...par, descr: e.target.value })} style={inp} /></div>
          <div><label style={lbl}>{t("Оценочная стоимость, ₴", "Оголошена вартість, ₴")}</label><input type="number" value={par.declared} disabled={readOnly} onChange={(e) => setPar({ ...par, declared: e.target.value })} style={inp} /></div>
          <div><label style={lbl}>{t("Плательщик доставки", "Платник доставки")}</label><select value={par.payer} disabled={readOnly} onChange={(e) => setPar({ ...par, payer: e.target.value })} style={inp}><option value="Recipient">{t("Получатель", "Отримувач")}</option><option value="Sender">{t("Отправитель", "Відправник")}</option></select></div>
          <div><label style={lbl}>{t("Метод оплаты", "Спосіб оплати")}</label><select value={par.method} disabled={readOnly} onChange={(e) => setPar({ ...par, method: e.target.value })} style={inp}><option value="Cash">{t("Наличные", "Готівка")}</option><option value="NonCash">{t("Безнал", "Безготівково")}</option></select></div>
        </Grid>
      </div>

      {/* ── ПАКУВАННЯ (blue) ── */}
      <div style={zone("#eff6ff", "#bfdbfe")}>
        <div style={{ fontWeight: 700, fontSize: 13.5, color: "#1e40af", marginBottom: 4 }}>📦 {t("Упаковка — для склада", "Пакування — для складу")}</div>
        <div style={{ fontSize: 11, color: "#60a5fa", marginBottom: 10 }}>{t("тип груза · места · упаковка НП · регламент", "тип вантажу · місця · пакування НП · регламент")}</div>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <Card checked={cargo === "Parcel"} onClick={() => setCargo("Parcel")} icon="📦" title={t("Посылка", "Посилка")} desc={t("коробка до 30 кг", "коробка до 30 кг")} color="#2563eb" />
          <Card checked={cargo === "Cargo"} onClick={() => setCargo("Cargo")} icon="🛢️" title={t("Груз", "Вантаж")} desc={t("вёдра, жидкости · грузовое отд.", "відра, рідини · вантажне відд.")} color="#2563eb" />
          <Card checked={cargo === "Pallet"} onClick={() => setCargo("Pallet")} icon="🟫" title={t("Палета", "Палета")} desc="60×80 / 120×80" color="#2563eb" />
        </div>

        {/* Місця */}
        <div style={{ background: "#fff", borderRadius: 10, padding: 12, border: "1px solid #dbeafe" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
            <b style={{ fontSize: 13 }}>📐 {t("Места посылки", "Місця посилки")}</b>
            {!readOnly && <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>{Object.keys(PRESETS).map((k) => <button key={k} type="button" onClick={() => applyPreset(k)} style={{ fontSize: 11, padding: "4px 8px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#f8fafc", cursor: "pointer" }}>{PRESETS[k].t}</button>)}</div>}
          </div>
          {seats.map((s, i) => <div key={i} style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: "#94a3b8", width: 18 }}>#{i + 1}</span>
            {["l", "w", "h"].map((dim) => <div key={dim} style={{ flex: 1 }}><div style={{ fontSize: 9, color: "#94a3b8" }}>{({ l: "Д", w: "Ш", h: "В" } as any)[dim]} {t("см", "см")}</div><input type="number" value={s[dim]} disabled={readOnly} onChange={(e) => setSeat(i, dim, e.target.value)} style={{ ...inp, height: 32 }} /></div>)}
            <div style={{ flex: 1.2 }}><div style={{ fontSize: 9, color: "#94a3b8" }}>{t("вес кг", "вага кг")}</div><input type="number" value={s.kg} disabled={readOnly} onChange={(e) => setSeat(i, "kg", e.target.value)} style={{ ...inp, height: 32 }} /></div>
            {!readOnly && seats.length > 1 && <button type="button" onClick={() => delSeat(i)} style={{ border: "none", background: "none", color: "#ef4444", cursor: "pointer", fontSize: 16 }}>×</button>}
          </div>)}
          {!readOnly && <button type="button" onClick={addSeat} style={{ marginTop: 4, fontSize: 12, padding: "5px 10px", borderRadius: 7, border: "1px dashed #93c5fd", background: "#eff6ff", color: "#2563eb", cursor: "pointer" }}>+ {t("Добавить место", "Додати місце")}</button>}
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 8, fontSize: 12, color: "#475569", borderTop: "1px solid #f1f5f9", paddingTop: 8 }}>
            <span><b>{t("Мест:", "Місць:")}</b> {seats.length}</span>
            <span><b>{t("Вес:", "Вага:")}</b> {totW.toFixed(2)} кг</span>
            <span><b>{t("Объём:", "Обʼєм:")}</b> {volM3.toFixed(4)} м³</span>
            <span><b>{t("Объёмный вес:", "Обʼємна вага:")}</b> {volW.toFixed(2)} кг <small style={{ color: "#94a3b8" }}>(Д×Ш×В÷4000)</small></span>
          </div>
        </div>

        {/* Упаковка НП + опції */}
        <div style={{ marginTop: 12, display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ flex: "1 1 240px" }}><label style={lbl}>{t("Упаковка от НП", "Пакування від НП")} <small style={{ color: "#94a3b8" }}>({t("опц. — иначе своя", "опц. — інакше своя")})</small></label>
            <select value={pack.ref} disabled={readOnly} onChange={(e) => setPack({ ...pack, ref: e.target.value })} style={inp}><option value="">— {t("Своє пакування (0 ₴)", "Своє пакування (0 ₴)")} —</option>{packlist.map((p) => <option key={p.ref} value={p.ref}>{p.descr}</option>)}</select></div>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5 }}><input type="checkbox" checked={!!pack.saturday} disabled={readOnly} onChange={(e) => setPack({ ...pack, saturday: e.target.checked })} /> 📅 {t("Суббота-доставка", "Доставка в суботу")}</label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5 }}><input type="checkbox" checked={!!pack.return_docs} disabled={readOnly} onChange={(e) => setPack({ ...pack, return_docs: e.target.checked })} /> 📄 {t("Возвратные документы", "Зворотні документи")}</label>
        </div>

        <details style={{ marginTop: 10, fontSize: 12.5 }}>
          <summary style={{ cursor: "pointer", fontWeight: 600, color: "#1e40af" }}>📋 {t("Инструкция упаковки для склада", "Інструкція пакування для складу")} <small style={{ color: "#94a3b8" }}>({t("регламент НП", "регламент НП")})</small></summary>
          <div style={{ padding: "8px 0", color: "#475569", lineHeight: 1.5 }}>
            <b>🛢️ {t("Вёдра/канистры с жидкостью:", "Відра/каністри з рідиною:")}</b> {t("гофрокартон верх+низ · 3 слоя стрейча · маркировка «ВЕРХ» с 2 сторон · скотч крест-накрест если крышка не закручивается. Принимают только грузовые отделения НП.", "гофрокартон верх+низ · 3 шари стрейчу · маркування «ВЕРХ» з 2 сторін · скотч хрест-навхрест якщо кришка не закручується. Приймають тільки вантажні відділення НП.")}<br />
            <b>🍶 {t("Бутылки/стекло:", "Пляшки/скло:")}</b> {t("3 слоя пузырчатой плёнки · 5-слойная коробка · бумагой заполнить пустоты · «ХРУПКОЕ»+«ВЕРХ».", "3 шари бульбашкової плівки · 5-шарова коробка · папером заповнити порожнини · «КРИХКЕ»+«ВЕРХ».")}<br />
            <b style={{ color: "#dc2626" }}>❌ {t("Запрещено:", "Заборонено:")}</b> {t("краска в металле · аэрозоли · автомасла без ограничения тары · жидкости без заводской этикетки.", "фарба в металі · аерозолі · авто-мастила без обмеження тари · рідини без заводської етикетки.")}
          </div>
        </details>

        <Grid>
          <div style={{ marginTop: 10 }}><label style={lbl}>{t("Примечание для НП", "Примітка для НП")} <small style={{ color: "#94a3b8" }}>({t("служебная, клиент НЕ видит", "службова, клієнт НЕ бачить")})</small></label><textarea rows={2} value={note} disabled={readOnly} onChange={(e) => setNote(e.target.value)} style={{ ...inp, height: "auto", padding: 8 }} placeholder={t("Напр.: ЖИДКОСТЬ. ВЕРХ. Не кантовать.", "Напр.: РІДИНА. ВЕРХ. Не кантувати.")} /></div>
          <div style={{ marginTop: 10 }}><label style={lbl}>{t("Перечень товаров", "Перелік товарів")} <small style={{ color: "#94a3b8" }}>({t("строка = товар, для накладной", "рядок = товар, для накладної")})</small></label><textarea rows={2} value={items} disabled={readOnly} onChange={(e) => setItems(e.target.value)} style={{ ...inp, height: "auto", padding: 8 }} /></div>
        </Grid>
      </div>

      {/* ── Контроль оплати ── */}
      <div style={{ ...zone("#fefce8", "#fde68a"), padding: 12 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 600 }}><input type="checkbox" checked={!!bw.on} disabled={readOnly || codReadOnly} onChange={(e) => setBw({ ...bw, on: e.target.checked })} style={{ width: 16, height: 16 }} /> 💰 {t("Контроль оплаты", "Контроль оплати")} — {t("НП удержит сумму при получении и переведёт нам", "НП утримає суму при отриманні і переведе нам")}{codReadOnly ? <span style={{ fontWeight: 500, color: "#92400e", fontSize: 11.5 }}> · 🔒 {t("только менеджер", "тільки менеджер")}</span> : null}</label>
        {bw.on && <div style={{ marginTop: 8, maxWidth: 260 }}><label style={lbl}>{t("Сумма контроля, ₴", "Сума контролю, ₴")}</label><input type="number" value={bw.amount} disabled={readOnly || codReadOnly} onChange={(e) => setBw({ ...bw, amount: e.target.value })} style={inp} placeholder={par.declared} /></div>}
      </div>

      {/* ── Дата + ціна ── */}
      <Grid>
        {rec.service !== "WarehouseDoors" && <div><label style={lbl}>📅 {t("Желаемая дата доставки", "Бажана дата доставки")}</label><input type="date" value={date} disabled={readOnly} onChange={(e) => setDate(e.target.value)} style={inp} /></div>}
        <div style={{ background: "#f8fafc", borderRadius: 10, padding: "10px 14px", display: "flex", alignItems: "center" }}>
          <div><div style={{ fontSize: 11, color: "#64748b" }}>📊 {t("Ориентир НП:", "Орієнтир НП:")}</div><div style={{ fontSize: 18, fontWeight: 800, color: "#0f766e" }}>{price ? `${price.Cost || "—"} ₴` : "—"}</div>{price && (price.CostRedelivery || price.CostPack) ? <div style={{ fontSize: 11, color: "#94a3b8" }}>{price.CostPack ? `+${price.CostPack} упак ` : ""}{price.CostRedelivery ? `+${price.CostRedelivery} контр.` : ""}</div> : null}</div>
        </div>
      </Grid>

      {!readOnly && <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
        <button className="btn btn-light" onClick={estimate} disabled={!!busy || !rec.city_ref}>{busy === "est" ? "…" : "🧮 " + t("Оценить стоимость", "Оцінити вартість")}</button>
        <div style={{ flex: 1 }} />
        <button className="btn" onClick={() => save()} disabled={!!busy} style={{ background: "#eff6ff", color: "#2563eb" }}>{busy === "save" ? "…" : "💾 " + t("Сохранить получателя", "Зберегти отримувача")}</button>
        <button className="btn btn-primary" onClick={createTTN} disabled={!!busy || !!ttn} style={{ background: ttn ? "#cbd5e1" : undefined }}>{busy === "ttn" ? t("⏳ Создаю ТТН, подождите…", "⏳ Створюю ТТН, зачекайте…") : ttn ? t("ТТН создана", "ТТН створена") : t("🚀 Создать ТТН", "🚀 Створити ТТН")}</button>
      </div>}
    </div>
  );
}
