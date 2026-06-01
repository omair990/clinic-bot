import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { apiGet, apiPost } from "./api";
import { setDisplayTz } from "./tz";

export interface Principal {
  role: "super" | "clinic";
  tenant_id: number | null;
  tenant_name: string | null;
  timezone?: string | null;
}

interface AuthState {
  me: Principal | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthCtx = createContext<AuthState>(null as any);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Principal | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<Principal>("/me")
      .then((p) => { setDisplayTz(p.timezone); setMe(p); })
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const p = await apiPost<Principal>("/login", { username, password });
    setDisplayTz(p.timezone);
    setMe(p);
  };
  const logout = async () => {
    await apiPost("/logout");
    setDisplayTz(undefined);
    setMe(null);
  };

  return <AuthCtx.Provider value={{ me, loading, login, logout }}>{children}</AuthCtx.Provider>;
}
