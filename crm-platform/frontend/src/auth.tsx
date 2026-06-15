import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, getToken, setToken, Me } from "./api";

interface AuthCtx {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => void;
  can: (code: string) => boolean;
}
const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    if (!getToken()) { setMe(null); setLoading(false); return; }
    try { setMe(await api.get<Me>("/api/me/")); }
    catch { setMe(null); }
    finally { setLoading(false); }
  }
  useEffect(() => { refresh(); }, []);

  function logout() { setToken(null); setMe(null); }

  function can(code: string) {
    if (!me) return false;
    return me.is_superuser || me.permissions.includes(code);
  }

  return <Ctx.Provider value={{ me, loading, refresh, logout, can }}>{children}</Ctx.Provider>;
}
