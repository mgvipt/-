// Тонкий клиент REST API с токеном из localStorage.
const TOKEN_KEY = "crm_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const tok = getToken();
  if (tok) headers["Authorization"] = `Token ${tok}`;
  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    setToken(null);
    window.location.reload();
  }
  if (!res.ok) {
    const txt = await res.text();
    const e: any = new Error(`${res.status} ${txt}`);
    e.status = res.status;
    try { e.data = JSON.parse(txt); } catch { /* не JSON */ }
    e.response = { status: res.status, data: e.data };
    throw e;
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function uploadFile<T>(url: string, file: File): Promise<T> {
  const headers: Record<string, string> = {};
  const tok = getToken();
  if (tok) headers["Authorization"] = `Token ${tok}`;
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(url, { method: "POST", headers, body: fd });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function uploadForm<T>(url: string, fd: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  const tok = getToken();
  if (tok) headers["Authorization"] = `Token ${tok}`;
  const res = await fetch(url, { method: "POST", headers, body: fd });
  if (!res.ok) { const e: any = new Error(`${res.status}`); try { e.response = { data: JSON.parse(await res.text()) }; } catch { /* ignore */ } throw e; }
  return res.json() as Promise<T>;
}

// Завантажує захищений файл і повертає blob-URL (для <img>/перегляду)
async function blobUrl(url: string): Promise<string> {
  const headers: Record<string, string> = {};
  const tok = getToken();
  if (tok) headers["Authorization"] = `Token ${tok}`;
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`${res.status}`);
  return URL.createObjectURL(await res.blob());
}

export const api = {
  get: <T>(u: string) => request<T>("GET", u),
  post: <T>(u: string, b?: unknown) => request<T>("POST", u, b),
  patch: <T>(u: string, b?: unknown) => request<T>("PATCH", u, b),
  put: <T>(u: string, b?: unknown) => request<T>("PUT", u, b),
  del: <T>(u: string) => request<T>("DELETE", u),
  upload: uploadFile,
  uploadForm,
  blobUrl,
};

export async function login(username: string, password: string): Promise<string> {
  const res = await fetch("/api/auth/token/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error("Неверный логин или пароль");
  const data = (await res.json()) as { token: string };
  setToken(data.token);
  return data.token;
}

// ---- типы ----
export interface Me {
  id: number; username: string; first_name: string; last_name: string;
  is_superuser: boolean; permissions: string[];
  permission_catalog: { code: string; label: string }[];
  theme: { bg?: string; accent?: string };
}
export interface Stage { id: number; name: string; color: string; order: number; is_won: boolean; is_lost: boolean; }
export interface Funnel { id: number; name: string; is_lead_funnel: boolean; order: number; stages: Stage[]; }
export interface Card {
  id: number; title: string; amount: string; source: string;
  stage: number; funnel: number; owner: number | null; owner_name?: string;
  contact_name?: string; is_seen?: boolean; contact?: number | null; contact_social_link?: string; contact_phone?: string;
}
export interface Paginated<T> { count: number; results: T[]; }

export interface Conversation {
  id: number; channel: number; channel_kind: string; channel_name: string;
  contact?: number; contact_name?: string; title: string; status: string; unread: number;
  needs_reply?: boolean;
  last_message_at: string | null; last_text: string;
  assigned_to: number | null; assigned_to_name: string;
  participants?: number[]; participant_names?: string[];
}
export interface ChatMessage {
  id: number; conversation: number; direction: "in" | "out";
  text: string; attachments: any[]; sender_name: string; created_at: string;
}
