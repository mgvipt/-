import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../Icon";
import { useLang } from "../i18n";

type ShopVariant = {
  id: number;
  sku: string;
  name: string;
  price: string;
  variant_order: number;
  variant_name: string;
  enabled: boolean;
  status: string;
  approved_photo: boolean;
  image_url: string;
  errors: string[];
};

type ShopGroup = {
  key: string;
  name: string;
  slug: string;
  status: "published" | "ready" | "draft" | "error";
  remote_url: string;
  variants_count: number;
  enabled_count: number;
  approved_photos: number;
  updated_at: string;
  errors: string[];
  variants: ShopVariant[];
};

type ShopDashboard = {
  summary: {
    products: number;
    groups: number;
    published_groups: number;
    draft_groups: number;
    enabled_products: number;
    missing_photo: number;
    problem_products: number;
    pending_events: number;
    failed_events: number;
  };
  groups: ShopGroup[];
  generated_at: string;
};

type Filter = "all" | "published" | "draft" | "problems";

const statusStyle: Record<string, { bg: string; color: string }> = {
  published: { bg: "#dcfce7", color: "#166534" },
  ready: { bg: "#dbeafe", color: "#1d4ed8" },
  draft: { bg: "#f1f5f9", color: "#475569" },
  error: { bg: "#fee2e2", color: "#b91c1c" },
};

export default function ShopCatalog() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [data, setData] = useState<ShopDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  async function load(silent = false) {
    if (!silent) setLoading(true);
    try {
      setData(await api.get<ShopDashboard>("/api/products/shop-dashboard/"));
      setError("");
    } catch {
      setError(t("Не удалось загрузить данные магазина", "Не вдалося завантажити дані магазину"));
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(true), 30000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const groups = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.groups || []).filter((group) => {
      const matchesSearch = !q || group.name.toLowerCase().includes(q) ||
        group.variants.some((variant) => `${variant.sku} ${variant.name}`.toLowerCase().includes(q));
      const matchesFilter = filter === "all" ||
        (filter === "published" && group.status === "published") ||
        (filter === "draft" && group.status !== "published") ||
        (filter === "problems" && group.errors.length > 0);
      return matchesSearch && matchesFilter;
    });
  }, [data, filter, search]);

  const statusLabel = (status: string) => ({
    published: t("Опубликован", "Опубліковано"),
    ready: t("Готов к публикации", "Готово до публікації"),
    draft: t("Черновик", "Чернетка"),
    error: t("Ошибка", "Помилка"),
  }[status] || status);

  const metricCards = data ? [
    [t("Групп товаров", "Груп товарів"), data.summary.groups, "bag", "#2563eb"],
    [t("Опубликовано", "Опубліковано"), data.summary.published_groups, "check", "#16a34a"],
    [t("Черновиков", "Чернеток"), data.summary.draft_groups, "file", "#64748b"],
    [t("Без фото", "Без фото"), data.summary.missing_photo, "image", "#d97706"],
    [t("С проблемами", "З проблемами"), data.summary.problem_products, "warn", "#dc2626"],
    [t("В очереди", "У черзі"), data.summary.pending_events, "refresh", "#7c3aed"],
    [t("Ошибки передачи", "Помилки передачі"), data.summary.failed_events, "zap", "#be123c"],
  ] as const : [];

  return (
    <div style={{ padding: "22px 26px 50px", maxWidth: 1560, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 18, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 27, fontWeight: 850, color: "var(--card-text, #0f172a)" }}>{t("Интернет-магазин", "Інтернет-магазин")}</div>
          <div style={{ color: "var(--card-text-2, #64748b)", marginTop: 5, maxWidth: 760 }}>
            {t("Единая админ-панель товаров сайта. Цены и SKU берутся из номенклатуры CRM, сайт обновляется в фоне.", "Єдина адмін-панель товарів сайту. Ціни та SKU беруться з номенклатури CRM, сайт оновлюється у фоні.")}
          </div>
        </div>
        <div style={{ display: "flex", gap: 9 }}>
          <a className="btn btn-light" href="https://wallcov.com.ua/new/" target="_blank" rel="noreferrer"><Icon n="eye" /> {t("Открыть сайт", "Відкрити сайт")}</a>
          <button className="btn btn-primary" onClick={() => load()} disabled={loading}><Icon n="refresh" /> {t("Обновить", "Оновити")}</button>
        </div>
      </div>

      {error && <div style={{ marginTop: 18, padding: 14, borderRadius: 12, background: "#fee2e2", color: "#b91c1c" }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(155px,1fr))", gap: 12, marginTop: 22 }}>
        {metricCards.map(([label, value, icon, color]) => (
          <div key={label} className="panel" style={{ padding: "17px 18px", margin: 0, minHeight: 92 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", color: "var(--card-text-2, #64748b)", fontSize: 12, fontWeight: 700 }}><span>{label}</span><Icon n={icon} size={18} style={{ color }} /></div>
            <div style={{ fontSize: 30, fontWeight: 850, color, marginTop: 8 }}>{value}</div>
          </div>
        ))}
      </div>

      <div className="panel" style={{ margin: "18px 0 0", padding: 14, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 330px" }}>
          <Icon n="search" size={17} style={{ position: "absolute", left: 12, top: 11, color: "#94a3b8" }} />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("Поиск по названию или SKU", "Пошук за назвою або SKU")} style={{ width: "100%", height: 40, paddingLeft: 38 }} />
        </div>
        {(["all", "published", "draft", "problems"] as Filter[]).map((key) => (
          <button key={key} className={filter === key ? "btn btn-primary" : "btn btn-light"} onClick={() => setFilter(key)}>
            {{ all: t("Все", "Усі"), published: t("Опубликованные", "Опубліковані"), draft: t("Черновики", "Чернетки"), problems: t("Нужно заполнить", "Потрібно заповнити") }[key]}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", margin: "15px 2px 8px", color: "var(--card-text-2, #64748b)", fontSize: 13 }}>
        <span>{t("Показано групп", "Показано груп")}: <b>{groups.length}</b></span>
        <span>{data?.generated_at ? `${t("Обновлено", "Оновлено")}: ${new Date(data.generated_at).toLocaleTimeString()}` : ""}</span>
      </div>

      <div className="panel" style={{ margin: 0, padding: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 980 }}>
          <thead>
            <tr style={{ background: "rgba(148,163,184,.09)", textAlign: "left", color: "var(--card-text-2, #64748b)", fontSize: 12 }}>
              <th style={{ padding: "13px 16px" }}>{t("Товар на сайте", "Товар на сайті")}</th>
              <th style={{ padding: "13px 10px" }}>{t("Комплектации", "Комплектації")}</th>
              <th style={{ padding: "13px 10px" }}>{t("Фото", "Фото")}</th>
              <th style={{ padding: "13px 10px" }}>{t("Статус", "Статус")}</th>
              <th style={{ padding: "13px 10px" }}>{t("Что заполнить", "Що заповнити")}</th>
              <th style={{ padding: "13px 16px", textAlign: "right" }}>{t("Действия", "Дії")}</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => {
              const style = statusStyle[group.status] || statusStyle.draft;
              const first = group.variants[0];
              return (
                <tr key={group.key} style={{ borderTop: "1px solid rgba(148,163,184,.20)" }}>
                  <td style={{ padding: "14px 16px", minWidth: 290 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <div style={{ width: 52, height: 52, borderRadius: 10, overflow: "hidden", background: "#eef2f7", display: "grid", placeItems: "center", flexShrink: 0 }}>
                        {first?.image_url ? <img src={first.image_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : <Icon n="image" size={22} style={{ color: "#94a3b8" }} />}
                      </div>
                      <div><div style={{ fontWeight: 780, color: "var(--card-text, #0f172a)" }}>{group.name}</div><div style={{ fontSize: 12, color: "#94a3b8", marginTop: 3 }}>{group.slug || group.key}</div></div>
                    </div>
                  </td>
                  <td style={{ padding: "14px 10px" }}>
                    <b style={{ color: group.variants_count === 4 ? "#15803d" : "#b91c1c" }}>{group.variants_count}/4</b>
                    <div style={{ fontSize: 12, color: "#64748b", marginTop: 3 }}>{group.enabled_count} {t("разрешено", "дозволено")}</div>
                  </td>
                  <td style={{ padding: "14px 10px" }}><b style={{ color: group.approved_photos === group.variants_count && group.variants_count > 0 ? "#15803d" : "#d97706" }}>{group.approved_photos}/{group.variants_count}</b></td>
                  <td style={{ padding: "14px 10px" }}><span style={{ display: "inline-flex", padding: "6px 9px", borderRadius: 999, background: style.bg, color: style.color, fontWeight: 750, fontSize: 12 }}>{statusLabel(group.status)}</span></td>
                  <td style={{ padding: "14px 10px", maxWidth: 360 }}>
                    {group.errors.length === 0 ? <span style={{ color: "#15803d", fontSize: 13 }}>✓ {t("Карточка заполнена", "Картку заповнено")}</span> :
                      <div style={{ color: "#b45309", fontSize: 12.5 }}>{group.errors.slice(0, 2).join(" · ")}{group.errors.length > 2 ? ` · +${group.errors.length - 2}` : ""}</div>}
                  </td>
                  <td style={{ padding: "14px 16px", textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="btn btn-light" onClick={() => first && navigate(`/warehouse?product=${first.id}`)}><Icon n="pencil" /> {t("Редактировать", "Редагувати")}</button>
                    {group.remote_url && <a className="btn btn-light" href={group.remote_url} target="_blank" rel="noreferrer" style={{ marginLeft: 6 }}><Icon n="eye" /></a>}
                  </td>
                </tr>
              );
            })}
            {!loading && groups.length === 0 && <tr><td colSpan={6} style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>{t("Ничего не найдено", "Нічого не знайдено")}</td></tr>}
            {loading && <tr><td colSpan={6} style={{ padding: 40, textAlign: "center", color: "#64748b" }}>{t("Загрузка…", "Завантаження…")}</td></tr>}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 14, color: "var(--card-text-2, #64748b)", fontSize: 12.5 }}>
        {t("Изменения товара отправляются на сайт автоматически. Покупатель открывает каталог из локальной базы магазина — скорость CRM на сайт не влияет.", "Зміни товару надсилаються на сайт автоматично. Покупець відкриває каталог з локальної бази магазину — швидкість CRM на сайт не впливає.")}
      </div>
    </div>
  );
}
