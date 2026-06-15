// Заглушка для модулей следующих этапов (чаты, телефония, склад, финансы…).
export default function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <div className="pad fade">
      <div className="panel" style={{ maxWidth: 640 }}>
        <h2 style={{ marginTop: 0 }}>{title}</h2>
        <p className="muted" style={{ fontSize: 14, lineHeight: 1.5 }}>{note}</p>
        <p className="muted" style={{ fontSize: 13 }}>
          Дизайн этого экрана уже есть в превью (<code>crm-platform/preview.html</code>).
          Боевая версия подключается на соответствующем этапе.
        </p>
      </div>
    </div>
  );
}
