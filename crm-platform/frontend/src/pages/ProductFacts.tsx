import { useEffect, useState } from 'react';
import { api } from '../api';

const labels: Record<string, string> = {
  packaging: 'Фасовка / відвантаження', finish: 'Фініш', washable: 'Догляд / миття',
  durability: 'Зносостійкість', application: 'Де використовувати',
  self_application: 'Самостійне нанесення', limitations: 'Обмеження',
  recommendation: 'Коли рекомендувати', search_terms: 'Пошукові назви',
  sample_size: 'Розмір зразка', tinting: 'Тонування',
};
const texts: Record<string, string> = {
  description: 'Опис', shop_short_description: 'Короткий опис',
  shop_full_description: 'Повний опис', shop_effect: 'Ефект', shop_contents: 'Що входить у набір',
};

export function ProductFacts({ id, canEdit, onSaved }: { id: number; canEdit: boolean; onSaved: () => void }) {
  const [data, setData] = useState<any>(null);
  const [draft, setDraft] = useState<any>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let current = true;
    setData(null); setDraft(null); setError('');
    api.get(`/api/products/${id}/facts/`).then(value => { if (current) setData(value); })
      .catch(() => { if (current) setError('Не вдалося завантажити характеристики. Оновіть картку.'); });
    return () => { current = false; };
  }, [id]);
  async function save() {
    if (!draft || busy) return;
    setBusy(true); setError('');
    try {
      const payload: any = { updated_at: data.updated_at, shop_specs: draft.shop_specs };
      Object.keys(texts).forEach(key => { payload[key] = draft[key] || ''; });
      const updated = await api.patch(`/api/products/${id}/facts/`, payload);
      setData(updated); setDraft(null); onSaved();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не збережено. Перевірте витрату та оновіть картку, якщо її вже змінив колега.');
    } finally { setBusy(false); }
  }
  const spec = (draft || data)?.shop_specs || {};
  const range = spec.consumption_range || {};
  function setSpec(key: string, value: any) {
    setDraft({ ...draft, shop_specs: { ...spec, [key]: value } });
  }
  return <section className="panel" style={{ margin: '12px 0', padding: 14 }}>
    <h4 style={{ margin: '0 0 8px' }}>Характеристики для команди та ШІ</h4>
    <p className="muted" style={{ fontSize: 12 }}>Ціни й описи беруться з цієї картки. Фото відкриваються зі спільної бібліотеки.</p>
    {error && <p role="alert" style={{ color: '#b91c1c' }}>{error}</p>}
    {!data && !error && <p>Завантаження…</p>}
    {data && <>
      {canEdit && !draft && <button className="btn btn-light" onClick={() => setDraft(JSON.parse(JSON.stringify(data)))}>Редагувати характеристики</button>}
      {Object.entries(texts).map(([key, label]) => draft
        ? <label key={key} style={{ display: 'block', marginTop: 10 }}>{label}<textarea rows={3} style={{ width: '100%' }} value={draft[key] || ''} onChange={e => setDraft({ ...draft, [key]: e.target.value })} /></label>
        : key !== 'description' && data[key] ? <p key={key} style={{ whiteSpace: 'pre-wrap' }}><b>{label}:</b> {data[key]}</p> : null)}
      {Object.entries(labels).map(([key, label]) => draft
        ? <label key={key} style={{ display: 'block', marginTop: 10 }}>{label}<textarea rows={2} style={{ width: '100%' }} value={spec[key] || ''} onChange={e => setSpec(key, e.target.value)} /></label>
        : spec[key] ? <p key={key} style={{ whiteSpace: 'pre-wrap' }}><b>{label}:</b> {spec[key]}</p> : null)}
      <p><b>Діапазон витрати:</b> {range.min && range.max ? `${range.min}–${range.max} ${range.unit}` : 'Не вказано'}</p>
      {range.source && <p className="muted" style={{ fontSize: 12 }}>{range.source}</p>}
      {draft && <fieldset><legend>Витрата на 1 м²</legend>
        {['min', 'max'].map((key, i) => <label key={key}>{i ? ' Максимум ' : 'Мінімум '}<input aria-label={i ? 'Максимальна витрата' : 'Мінімальна витрата'} type="number" step="0.0001" min="0" value={range[key] || ''} onChange={e => setSpec('consumption_range', { ...range, [key]: e.target.value, unit: range.unit || 'кг/м²', source: 'Уточнено в картці CRM' })} /></label>)}
        <select aria-label="Одиниця витрати" value={range.unit || 'кг/м²'} onChange={e => setSpec('consumption_range', { ...range, unit: e.target.value, source: 'Уточнено в картці CRM' })}>{['кг/м²', 'л/м²', 'шт/м²', 'мл/м²'].map(unit => <option key={unit}>{unit}</option>)}</select>
        <button type="button" className="btn btn-light" onClick={() => setSpec('consumption_range', {})}>Очистити діапазон</button>
      </fieldset>}
      {range.unit && range.unit !== data.unit + '/м²' && <p style={{ color: '#92400e' }}>Витрата та одиниця продажу різні. Без перевіреного перерахунку ціну за м² не визначаємо.</p>}
      {draft && <div style={{ display: 'flex', gap: 8, marginTop: 10 }}><button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? 'Збереження…' : 'Зберегти характеристики'}</button><button className="btn btn-light" disabled={busy} onClick={() => setDraft(null)}>Скасувати</button></div>}
      <h4>Фото зі спільної бібліотеки · {data.media.length}</h4>
      {!data.media.length && <p className="muted">Підтвердженого зв’язку фото з цим товаром поки немає.</p>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 10 }}>
        {data.media.map((item: any) => <a key={item.id} href={item.url} target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>
          {item.kind === 'video' ? <span>▶ Відео</span> : <img src={item.preview_url || item.url} alt={item.title} loading="lazy" style={{ width: '100%', height: 150, objectFit: 'contain' }} />}
          <span style={{ display: 'block' }}>{item.title}</span>
          <small>{item.color_code} · Спільна бібліотека</small>
        </a>)}
      </div>
    </>}
  </section>;
}
