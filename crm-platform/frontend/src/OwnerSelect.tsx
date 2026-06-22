import { useEffect, useState } from "react";
import { api } from "./api";
import { Avatar } from "./ui";

/* Інлайн-вибір відповідального (менеджера). Використовується в картці сделки і клієнта. */
export default function OwnerSelect({ ownerId, ownerName, onSet }: { ownerId?: number | null; ownerName?: string; onSet: (id: number | null) => void }) {
  const [users, setUsers] = useState<any[]>([]);
  const [edit, setEdit] = useState(false);
  useEffect(() => {
    if (edit && users.length === 0) api.get<any>("/api/users/?page_size=300").then((d) => setUsers((d.results || d).filter((u: any) => u.is_active !== false)));
  }, [edit]);
  const nm = (u: any) => `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username;
  if (!edit) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
        <Avatar name={ownerName || "—"} />{ownerName || "Не призначено"}
        <span onClick={() => setEdit(true)} style={{ color: "#2563eb", cursor: "pointer", fontSize: 12, marginLeft: 6 }} title="Змінити відповідального">✏️ змінити</span>
      </div>
    );
  }
  return (
    <select autoFocus value={ownerId ?? ""} onChange={(e) => { onSet(e.target.value ? Number(e.target.value) : null); setEdit(false); }} onBlur={() => setEdit(false)}
      style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px" }}>
      <option value="">— не призначено —</option>
      {users.map((u) => <option key={u.id} value={u.id}>{nm(u)}</option>)}
    </select>
  );
}
