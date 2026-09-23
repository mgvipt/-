import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import ProductTechnicalFacts, {type Lang} from './ProductTechnicalFacts';

const labels: Record<string, string> = {
  packaging: 'Фасовка / відвантаження', finish: 'Фініш', washable: 'Догляд / миття',
  durability: 'Зносостійкість', application: 'Де використовувати',
  self_application: 'Самостійне нанесення', limitations: 'Обмеження',
  recommendation: 'Коли рекомендувати', search_terms: 'Пошукові назви',
  sample_size: 'Розмір зразка', tinting: 'Тонування',
};
const texts: Record<string, string> = {
  description: 'Додаткові відомості', shop_short_description: 'Коротке представлення',
  shop_full_description: 'Докладна стаття: застосування та нанесення', shop_effect: 'Ефект', shop_contents: 'Що входить у набір',
};

const ruLabels: Record<string, string> = {
  description: 'Дополнительные сведения', shop_short_description: 'Краткое представление', shop_full_description: 'Подробная статья: применение и нанесение', shop_effect: 'Эффект', shop_contents: 'Что входит в набор',
  packaging: 'Фасовка и отгрузка', finish: 'Финиш', washable: 'Уход и мытьё', durability: 'Износостойкость', application: 'Где применять', self_application: 'Самостоятельное нанесение', limitations: 'Ограничения', recommendation: 'Когда рекомендовать', search_terms: 'Поисковые названия', sample_size: 'Размер образца', tinting: 'Тонирование',
};

export function ProductFacts({ id, canEdit, onSaved, lang = "uk" }: { lang?: Lang; id: number; canEdit: boolean; onSaved: () => void }) {
  const [data, setData] = useState<any>(null);
  const [draft, setDraft] = useState<any>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const t = (uk: string, ru: string) => lang === "ru" ? ru : uk;
  useEffect(() => {
    let current = true;
    generation.current += 1;
    setData(null); setDraft(null); setError('');
    api.get(`/api/products/${id}/facts/?lang=${lang}`).then(value => { if (current) setData(value); })
      .catch(() => { if (current) setError(t('Не вдалося завантажити характеристики. Оновіть картку.', 'Не удалось загрузить характеристики. Обновите карточку.')); });
    return () => { current = false; generation.current += 1; };
  }, [id, lang]);
  async function save() {
    if (!draft || busy) return;
    const requestGeneration = generation.current;
    setBusy(true); setError('');
    try {
      const payload: any = { updated_at: data.updated_at };
      Object.keys(texts).forEach(key => { if (draft[key] !== data[key]) payload[key] = draft[key] || ''; });
      const changedSpecs: any = {};
      Object.keys(draft.shop_specs || {}).forEach(key => { if (JSON.stringify(draft.shop_specs[key]) !== JSON.stringify(data.shop_specs[key])) changedSpecs[key] = draft.shop_specs[key]; });
      if (Object.keys(changedSpecs).length) payload.shop_specs = changedSpecs;
      const updated = await api.patch(`/api/products/${id}/facts/?lang=${lang}`, payload);
      if (generation.current !== requestGeneration) return;
      setData(updated); setDraft(null); onSaved();
    } catch (e: any) {
      if (generation.current !== requestGeneration) return;
      setError(e?.response?.status === 409 ? t('Картку вже змінили. Оновіть її перед збереженням.', 'Карточку уже изменили. Обновите её перед сохранением.') : (e?.response?.data?.detail || t('Не збережено. Перевірте витрату та оновіть картку, якщо її вже змінив колега.', 'Не сохранено. Проверьте расход и обновите карточку, если её уже изменил коллега.')));
    } finally { setBusy(false); }
  }
  const spec = (draft || data)?.shop_specs || {};
  const range = spec.consumption_range || {};
  function setSpec(key: string, value: any) {
    setDraft({ ...draft, shop_specs: { ...spec, [key]: value } });
  }
  return <section className="panel" style={{ margin: '12px 0', padding: 14 }}>
    <h4 style={{ margin: "0 0 8px" }}>{t("Матеріал: опис і застосування", "Материал: описание и применение")}</h4>
    {error && <p role="alert" style={{ color: '#b91c1c' }}>{error}</p>}
    {!data && !error && <p role="status">{t("Завантаження…", "Загрузка…")}</p>}
    {data && <>
      {!draft && <article aria-label={t("Повна стаття про матеріал", "Полная статья о материале")} style={{lineHeight:1.7}}>
        {lang === "ru" && data.fallback_fields?.some((field: string) => ["shop_full_description", "shop_short_description", "description"].includes(field)) && <p className="muted">Для части описания пока показан украинский текст.</p>}
        {data.shop_short_description && <p style={{whiteSpace:"pre-wrap"}}>{data.shop_short_description}</p>}
        {(data.shop_full_description || data.description || "").split(/\n\s*\n/).filter(Boolean).map((section: string, index: number) => {
          const lines = section.trim().split("\n");
          const title = lines[0].trim();
          const hasHeading = lines.length > 1 && title.length <= 110 && !/[.!?;]$/.test(title) && !/^[-•]/.test(title);
          const body = (hasHeading ? lines.slice(1) : lines).join("\n");
          return <section key={index} style={{marginTop:18}}>{hasHeading && <h5 style={{fontSize:15,lineHeight:1.45,margin:"0 0 8px"}}>{title}</h5>}<p style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere",margin:0}}>{body}</p></section>;
        })}
        {data.shop_full_description?.trim() && data.description?.trim() && ![data.shop_short_description?.trim(), data.shop_full_description?.trim()].includes(data.description.trim()) && <details style={{marginTop:14}}><summary style={{cursor:"pointer",fontWeight:600}}>{t("Додаткові відомості про матеріал", "Дополнительные сведения о материале")}</summary><p style={{whiteSpace:"pre-wrap"}}>{data.description}</p></details>}
      </article>}
      <h4 style={{margin:"20px 0 10px"}}>{t("Технічні характеристики", "Технические характеристики")}</h4>
      <ProductTechnicalFacts data={data.technical} lang={lang} />
      {canEdit && !draft && <button className="btn btn-light" onClick={() => setDraft(JSON.parse(JSON.stringify(data)))}>{t("Редагувати опис і характеристики", "Редактировать описание и характеристики")}</button>}
      {Object.entries(texts).map(([key, label]) => draft
        ? <label key={key} style={{ display: 'block', marginTop: 10 }}>{t(label, ruLabels[key] || label)}<textarea rows={3} style={{ width: '100%' }} value={draft[key] || ''} onChange={e => setDraft({ ...draft, [key]: e.target.value })} /></label>
        : !['description', 'shop_short_description', 'shop_full_description'].includes(key) && data[key] ? <p key={key} style={{ whiteSpace: 'pre-wrap' }}><b>{t(label, ruLabels[key] || label)}:</b> {data[key]}</p> : null)}
      {Object.entries(labels).map(([key, label]) => draft
        ? <label key={key} style={{ display: 'block', marginTop: 10 }}>{t(label, ruLabels[key] || label)}<textarea rows={2} style={{ width: '100%' }} value={spec[key] || ''} onChange={e => setSpec(key, e.target.value)} /></label>
        : spec[key] ? <p key={key} style={{ whiteSpace: 'pre-wrap' }}><b>{t(label, ruLabels[key] || label)}:</b> {spec[key]}</p> : null)}
      <p><b>{t("Діапазон витрати", "Диапазон расхода")}:</b> {range.min && range.max ? `${range.min}–${range.max} ${range.unit}` : t('Не вказано', 'Не указано')}</p>
      {range.source && <p className="muted" style={{ fontSize: 12 }}>{range.source === "Уточнено в картці CRM" ? t("Уточнено в картці CRM", "Уточнено в карточке CRM") : range.source}</p>}
      {draft && <fieldset><legend>{t("Витрата на 1 м²", "Расход на 1 м²")}</legend>
        {['min', 'max'].map((key, i) => <label key={key}>{i ? t(' Максимум ', ' Максимум ') : t('Мінімум ', 'Минимум ')}<input aria-label={i ? t('Максимальна витрата', 'Максимальный расход') : t('Мінімальна витрата', 'Минимальный расход')} type="number" step="0.0001" min="0" value={range[key] || ''} onChange={e => setSpec('consumption_range', { ...range, [key]: e.target.value, unit: range.unit || 'кг/м²', source: 'Уточнено в картці CRM' })} /></label>)}
        <select aria-label={t("Одиниця витрати", "Единица расхода")} value={range.unit || 'кг/м²'} onChange={e => setSpec('consumption_range', { ...range, unit: e.target.value, source: 'Уточнено в картці CRM' })}>{['кг/м²', 'л/м²', 'шт/м²', 'мл/м²'].map(unit => <option key={unit}>{unit}</option>)}</select>
        <button type="button" className="btn btn-light" onClick={() => setSpec('consumption_range', {})}>{t("Очистити діапазон", "Очистить диапазон")}</button>
      </fieldset>}
      {range.unit && range.unit !== data.unit + '/м²' && <p style={{ color: '#92400e' }}>{t("Витрата та одиниця продажу різні. Без перевіреного перерахунку ціну за м² не визначаємо.", "Расход и единица продажи различаются. Без проверенного пересчёта цену за м² не определяем.")}</p>}
      {draft && <div style={{ display: 'flex', gap: 8, marginTop: 10 }}><button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? t('Збереження…', 'Сохранение…') : t('Зберегти характеристики', 'Сохранить характеристики')}</button><button className="btn btn-light" disabled={busy} onClick={() => setDraft(null)}>{t("Скасувати", "Отмена")}</button></div>}
      <h4>{t("Фото зі спільної бібліотеки", "Фото из общей библиотеки")} · {data.media.length}</h4>
      {!data.media.length && <p className="muted">{t("Підтвердженого зв’язку фото з цим товаром поки немає.", "Подтверждённой связи фото с этим товаром пока нет.")}</p>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 10 }}>
        {data.media.map((item: any) => <a key={item.id} href={item.url} target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>
          {item.kind === 'video' ? <span>▶ {t("Відео", "Видео")}</span> : <img src={item.preview_url || item.url} alt={item.title} loading="lazy" style={{ width: '100%', height: 150, objectFit: 'contain' }} />}
          <span style={{ display: 'block' }}>{item.title}</span>
          <small>{item.color_code ? `${item.color_code} · ` : ""}{t("Спільна бібліотека", "Общая библиотека")}</small>
        </a>)}
      </div>
    </>}
  </section>;
}
