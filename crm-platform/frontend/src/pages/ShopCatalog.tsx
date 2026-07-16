import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../Icon";
import { useLang } from "../i18n";
import ShopCatalogImport from "./ShopCatalogImport";

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
  category_path: string[];
  variants_count: number;
  expected_variants: number;
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

type MirrorProduct = ShopVariant & {
  price: string; unit: string; category: number | null; category_name: string;
  shop_enabled: boolean; shop_category_path: string[]; shop_parent_name: string; shop_slug: string;
  shop_short_description: string; shop_full_description: string; shop_effect: string; shop_beginner: boolean;
  shop_group_key: string; shop_variant_type: string; shop_variant_order: number; shop_variant_name: string;
  shop_has_board: boolean | null; shop_is_tinted: boolean | null; shop_contents: string;
  shop_specs: Record<string, unknown>;
  shop_status: string; shop_remote_url: string; shop_validation_errors: string[];
  images: { id: number; url: string; is_approved: boolean; is_primary: boolean; alt_text: string }[];
};

const pathText = (path?: string[]) => (path || []).join(" → ");
const parsePath = (value: string) => value.split(/\s*(?:→|>|\/)\s*/).map((part) => part.trim()).filter(Boolean);

const statusStyle: Record<string, { bg: string; color: string }> = {
  published: { bg: "#dcfce7", color: "#166534" },
  ready: { bg: "#dbeafe", color: "#1d4ed8" },
  draft: { bg: "#f1f5f9", color: "#475569" },
  error: { bg: "#fee2e2", color: "#b91c1c" },
};

export default function ShopCatalog() {
  const { t } = useLang();
  const { can } = useAuth();
  const canEdit = can("warehouse.edit");
  const [data, setData] = useState<ShopDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [editor, setEditor] = useState<MirrorProduct | null>(null);
  const [form, setForm] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const imageRef = useRef<HTMLInputElement>(null);

  async function openEditor(id: number) {
    const product = await api.get<MirrorProduct>(`/api/products/${id}/`);
    setEditor(product);
    setForm({ ...product, shop_category_path: product.shop_category_path?.length ? product.shop_category_path : (product.category === 59 ? ["Пробники"] : []) });
  }

  async function refreshEditor() {
    if (!editor) return;
    const product = await api.get<MirrorProduct>(`/api/products/${editor.id}/`);
    setEditor(product); setForm({ ...product, shop_category_path: product.shop_category_path?.length ? product.shop_category_path : (product.category === 59 ? ["Пробники"] : []) });
  }

  async function saveEditor() {
    if (!editor || !form) return;
    setSaving(true);
    try {
      const product = await api.patch<MirrorProduct>(`/api/products/${editor.id}/`, {
        name: form.name, sku: form.sku, price: Number(form.price) || 0, unit: form.unit,
        shop_enabled: form.shop_enabled, shop_category_path: form.shop_category_path,
        shop_parent_name: form.shop_parent_name, shop_slug: form.shop_slug,
        shop_short_description: form.shop_short_description, shop_full_description: form.shop_full_description,
        shop_effect: form.shop_effect, shop_beginner: form.shop_beginner,
        shop_group_key: form.shop_group_key, shop_variant_type: form.shop_variant_type,
        shop_variant_order: Number(form.shop_variant_order) || 0, shop_variant_name: form.shop_variant_name,
        shop_has_board: form.shop_has_board, shop_is_tinted: form.shop_is_tinted, shop_contents: form.shop_contents,
        shop_specs: form.shop_specs || {},
      });
      setEditor(product); setForm({ ...product, shop_category_path: product.shop_category_path?.length ? product.shop_category_path : (product.category === 59 ? ["Пробники"] : []) });
      await load(true);
    } finally { setSaving(false); }
  }

  async function uploadImage(file?: File) {
    if (!editor || !file) return;
    await api.upload(`/api/products/${editor.id}/shop-images/`, file);
    await refreshEditor();
  }

  async function patchImage(id: number, body: any) {
    if (!editor) return;
    await api.patch(`/api/products/${editor.id}/shop-images/${id}/`, body);
    await refreshEditor();
  }

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
          <a className="btn btn-light" href="https://wallcovdec.com.ua/" target="_blank" rel="noreferrer"><Icon n="eye" /> {t("Открыть сайт", "Відкрити сайт")}</a>
          <button className="btn btn-primary" onClick={() => load()} disabled={loading}><Icon n="refresh" /> {t("Обновить", "Оновити")}</button>
        </div>
      </div>

      {error && <div style={{ marginTop: 18, padding: 14, borderRadius: 12, background: "#fee2e2", color: "#b91c1c" }}>{error}</div>}

      <ShopCatalogImport canEdit={canEdit} onApplied={() => load(true)} />

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
                    <b style={{ color: group.variants_count === group.expected_variants ? "#15803d" : "#b91c1c" }}>{group.variants_count}/{group.expected_variants}</b>
                    <div style={{ fontSize: 12, color: "#64748b", marginTop: 3 }}>{group.enabled_count} {t("разрешено", "дозволено")}</div>
                  </td>
                  <td style={{ padding: "14px 10px" }}><b style={{ color: group.approved_photos === group.variants_count && group.variants_count > 0 ? "#15803d" : "#d97706" }}>{group.approved_photos}/{group.variants_count}</b></td>
                  <td style={{ padding: "14px 10px" }}><span style={{ display: "inline-flex", padding: "6px 9px", borderRadius: 999, background: style.bg, color: style.color, fontWeight: 750, fontSize: 12 }}>{statusLabel(group.status)}</span></td>
                  <td style={{ padding: "14px 10px", maxWidth: 360 }}>
                    {group.errors.length === 0 ? <span style={{ color: "#15803d", fontSize: 13 }}>✓ {t("Карточка заполнена", "Картку заповнено")}</span> :
                      <div style={{ color: "#b45309", fontSize: 12.5 }}>{group.errors.slice(0, 2).join(" · ")}{group.errors.length > 2 ? ` · +${group.errors.length - 2}` : ""}</div>}
                  </td>
                  <td style={{ padding: "14px 16px", textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="btn btn-light" onClick={() => first && openEditor(first.id)}><Icon n="pencil" /> {t("Открыть карточку", "Відкрити картку")}</button>
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

      {editor && form && <div onClick={() => setEditor(null)} style={{position:'fixed',inset:0,zIndex:80,background:'rgba(15,23,42,.45)',display:'flex',justifyContent:'flex-end'}}>
        <div onClick={e=>e.stopPropagation()} style={{width:'min(700px,96vw)',height:'100%',overflow:'auto',background:'#fff',padding:'20px 22px',color:'#0f172a'}}>
          <div style={{display:'flex',justifyContent:'space-between',gap:12,alignItems:'flex-start'}}><div><h2 style={{margin:0}}>{form.name}</h2><div className="muted" style={{fontSize:12,marginTop:4}}>{t('Зеркальная карточка той же номенклатуры','Дзеркальна картка тієї самої номенклатури')} #{editor.id}</div></div><button className="btn btn-light" onClick={()=>setEditor(null)}>✕</button></div>
          <div style={{margin:'16px 0',padding:12,borderRadius:10,background:form.shop_enabled?'#dcfce7':'#f1f5f9'}}><label><input disabled={!canEdit} type="checkbox" checked={!!form.shop_enabled} onChange={e=>setForm({...form,shop_enabled:e.target.checked,...(e.target.checked&&form.shop_variant_type!=='sample'?{shop_group_key:form.shop_group_key||`product-${editor.id}`,shop_slug:form.shop_slug||`product-${editor.id}`,shop_parent_name:form.shop_parent_name||form.name,shop_variant_order:form.shop_variant_order||1,shop_variant_name:form.shop_variant_name||t('Основной товар','Основний товар')}:{})})}/> <b>{t('Отображать в интернет-магазине','Показувати в інтернет-магазині')}</b></label><small style={{display:'block',marginTop:4,color:'#64748b'}}>{t('Включайте только после заполнения карточки и утверждения фото. Сайт обновится автоматически.','Вмикайте лише після заповнення картки й затвердження фото. Сайт оновиться автоматично.')}</small></div>
          <div style={{padding:13,border:'1px solid #bfdbfe',borderRadius:10,background:'#eff6ff',marginBottom:15}}><b>{t('Как заполнить карточку','Як заповнити картку')}</b><ol style={{margin:'7px 0 0',paddingLeft:20,fontSize:13,color:'#475569'}}><li>{t('Проверьте цену и выберите тип карточки.','Перевірте ціну й оберіть тип картки.')}</li><li>{t('Укажите категорию и понятное название для покупателя.','Вкажіть категорію та зрозумілу назву для покупця.')}</li><li>{t('Добавьте короткое описание и фотографии, затем утвердите фото.','Додайте короткий опис і фотографії, потім затвердьте фото.')}</li><li>{t('Нажмите «Сохранить». Группа товара и служебный URL для обычного товара создаются сами.','Натисніть «Зберегти». Група товару й службовий URL для звичайного товару створюються самі.')}</li></ol></div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:11}}>
            <label className="muted" style={{fontSize:12}}>{t('Название в номенклатуре','Назва в номенклатурі')}<input disabled={!canEdit} value={form.name||''} onChange={e=>setForm({...form,name:e.target.value})} style={{width:'100%',height:36}}/><small>{t('Внутреннее название товара в CRM.','Внутрішня назва товару в CRM.')}</small></label>
            <label className="muted" style={{fontSize:12}}>SKU<input disabled={!canEdit} value={form.sku||''} onChange={e=>setForm({...form,sku:e.target.value})} style={{width:'100%',height:36}}/><small>{t('Артикул номенклатуры. Обычно уже заполнен.','Артикул номенклатури. Зазвичай уже заповнений.')}</small></label>
            <label className="muted" style={{fontSize:12}}>{t('Цена','Ціна')}<input disabled={!canEdit} type="number" value={form.price||0} onChange={e=>setForm({...form,price:e.target.value})} style={{width:'100%',height:36}}/><small>{t('Цена этой позиции или упаковки из номенклатуры.','Ціна цієї позиції або упаковки з номенклатури.')}</small></label>
            <label className="muted" style={{fontSize:12}}>{t('Тип карточки','Тип картки')}<select disabled={!canEdit} value={form.shop_variant_type||'product'} onChange={e=>setForm({...form,shop_variant_type:e.target.value,shop_variant_order:e.target.value==='sample'?form.shop_variant_order:1,shop_variant_name:e.target.value==='sample'?form.shop_variant_name:t('Основной товар','Основний товар')})} style={{width:'100%',height:36}}><option value="product">{t('Обычный товар','Звичайний товар')}</option><option value="sample">{t('Пробник — 4 комплектации','Пробник — 4 комплектації')}</option></select></label>
            <label className="muted" style={{fontSize:12,gridColumn:'1 / -1'}}>{t('Категория → подкатегория → следующий уровень','Категорія → підкатегорія → наступний рівень')}<input disabled={!canEdit} value={pathText(form.shop_category_path)} onChange={e=>setForm({...form,shop_category_path:parsePath(e.target.value)})} placeholder={t('Пробники или Декоративные покрытия → Шёлк','Пробники або Декоративні покриття → Шовк')} style={{width:'100%',height:36}}/><small>{t('Глубина не ограничена — разделяйте уровни стрелкой →','Глибина не обмежена — розділяйте рівні стрілкою →')}</small></label>
            <label className="muted" style={{fontSize:12}}>{t('Название для покупателя','Назва для покупця')}<input disabled={!canEdit} value={form.shop_parent_name||''} onChange={e=>setForm({...form,shop_parent_name:e.target.value})} placeholder={t('Например: Velvet Luna — тихий бархат','Наприклад: Velvet Luna — тихий оксамит')} style={{width:'100%',height:36}}/><small>{t('Это название увидит покупатель на сайте.','Цю назву побачить покупець на сайті.')}</small></label>
            <label className="muted" style={{fontSize:12}}>URL<input disabled={!canEdit} value={form.shop_slug||''} onChange={e=>setForm({...form,shop_slug:e.target.value})} placeholder={t('Заполнится автоматически','Заповниться автоматично')} style={{width:'100%',height:36}}/><small>{t('Адрес страницы. Для обычного товара создаётся автоматически.','Адреса сторінки. Для звичайного товару створюється автоматично.')}</small></label>
            <label className="muted" style={{fontSize:12}}>{t('Группа товара','Група товару')}<input disabled value={form.shop_group_key||''} placeholder={t('Создаётся автоматически','Створюється автоматично')} style={{width:'100%',height:36,background:'#f8fafc'}}/><small>{t('Служебная связь: обычный товар — одна карточка; у пробника объединяет 4 комплектации. Вручную не заполняется.','Службовий зв’язок: звичайний товар — одна картка; у пробника об’єднує 4 комплектації. Вручну не заповнюється.')}</small></label>
            <label className="muted" style={{fontSize:12}}>{t('Эффект','Ефект')}<input disabled={!canEdit} value={form.shop_effect||''} onChange={e=>setForm({...form,shop_effect:e.target.value})} placeholder={t('Шёлк, бетон, камень…','Шовк, бетон, камінь…')} style={{width:'100%',height:36}}/><small>{t('Коротко: какой результат получает покупатель.','Коротко: який результат отримує покупець.')}</small></label>
            {form.shop_variant_type==='sample'&&<><label className="muted" style={{fontSize:12}}>{t('Название комплектации','Назва комплектації')}<input disabled={!canEdit} value={form.shop_variant_name||''} onChange={e=>setForm({...form,shop_variant_name:e.target.value})} style={{width:'100%',height:36}}/></label><label className="muted" style={{fontSize:12}}>{t('Порядок 1–4','Порядок 1–4')}<input disabled={!canEdit} type="number" min="1" max="4" value={form.shop_variant_order||0} onChange={e=>setForm({...form,shop_variant_order:e.target.value})} style={{width:'100%',height:36}}/></label></>}
            <label className="muted" style={{fontSize:12,gridColumn:'1 / -1'}}>{t('Короткое описание','Короткий опис')}<textarea disabled={!canEdit} rows={2} value={form.shop_short_description||''} onChange={e=>setForm({...form,shop_short_description:e.target.value})} style={{width:'100%'}}/></label>
            <label className="muted" style={{fontSize:12,gridColumn:'1 / -1'}}>{t('Полное описание','Повний опис')}<textarea disabled={!canEdit} rows={4} value={form.shop_full_description||''} onChange={e=>setForm({...form,shop_full_description:e.target.value})} style={{width:'100%'}}/></label>
          </div>
          {form.shop_specs?.source_columns && <div style={{marginTop:16,padding:14,border:'1px solid #e2e8f0',borderRadius:10}}><b>{t('Характеристики из таблицы','Характеристики з таблиці')}</b><div className="muted" style={{fontSize:12,marginTop:3}}>{t('Эти данные хранятся в этой же карточке CRM и передаются на сайт','Ці дані зберігаються у цій самій картці CRM і передаються на сайт')}</div><div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(230px,1fr))',gap:9,marginTop:11}}>{Object.entries(form.shop_specs.source_columns as Record<string,unknown>).map(([key,value])=><label key={key} className="muted" style={{fontSize:12}}>{key}<textarea disabled={!canEdit} rows={String(value??'').length>70?3:1} value={String(value??'')} onChange={e=>setForm({...form,shop_specs:{...form.shop_specs,source_columns:{...form.shop_specs.source_columns,[key]:e.target.value}}})} style={{width:'100%'}}/></label>)}</div></div>}
          <div style={{marginTop:18}}><div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><b>📷 {t('Фотографии','Фотографії')}</b>{canEdit&&<><input ref={imageRef} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{uploadImage(e.target.files?.[0]);e.target.value='';}}/><button className="btn btn-light" onClick={()=>imageRef.current?.click()}>{t('Добавить фото','Додати фото')}</button></>}</div><div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8,marginTop:9}}>{(editor.images||[]).map(image=><div key={image.id} style={{border:'1px solid #e2e8f0',padding:6,borderRadius:8}}><img src={image.url} alt="" style={{width:'100%',height:110,objectFit:'cover',borderRadius:6}}/><button disabled={!canEdit} className="btn btn-light" style={{marginTop:5,width:'100%'}} onClick={()=>patchImage(image.id,{is_approved:!image.is_approved})}>{image.is_approved?'✅ '+t('Утверждено','Затверджено'):t('Утвердить','Затвердити')}</button></div>)}</div></div>
          <div style={{marginTop:18,padding:12,borderRadius:9,background:(editor.shop_validation_errors||[]).length?'#fff7ed':'#ecfdf5'}}>{(editor.shop_validation_errors||[]).length?<><b style={{color:'#b45309'}}>{t('Нужно заполнить','Потрібно заповнити')}:</b><ul>{editor.shop_validation_errors.map((problem)=><li key={problem}>{problem}</li>)}</ul></>:<b style={{color:'#15803d'}}>✓ {t('Карточка готова','Картка готова')}</b>}</div>
          <div style={{display:'flex',justifyContent:'space-between',gap:8,marginTop:18}}><div><a className="btn btn-light" href={`/warehouse?product=${editor.id}`}>{t('Открыть в номенклатуре','Відкрити в номенклатурі')}</a><small style={{display:'block',color:'#64748b',marginTop:4}}>{t('Открывает эту же позицию в полном каталоге CRM.','Відкриває цю саму позицію у повному каталозі CRM.')}</small></div>{canEdit&&<div style={{textAlign:'right'}}><button className="btn btn-primary" disabled={saving} onClick={saveEditor}>{saving?t('Сохраняю…','Зберігаю…'):t('Сохранить','Зберегти')}</button><small style={{display:'block',color:'#64748b',marginTop:4}}>{t('Сохраняет карточку; при включённом показе отправляет изменения на сайт.','Зберігає картку; коли показ увімкнено, надсилає зміни на сайт.')}</small></div>}</div>
        </div>
      </div>}
    </div>
  );
}
