/* Двомовність CRM (українська / російська). Перемикання у Налаштуваннях.
 * Використання у компонентах:  const { t } = useLang();  t("по-русски", "українською") */
import { createContext, useContext, useState, ReactNode } from "react";

export type Lang = "uk" | "ru";

interface Ctx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (ru: string, uk: string) => string;
}

const LangCtx = createContext<Ctx>({ lang: "uk", setLang: () => {}, t: (ru) => ru });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => ((localStorage.getItem("crm_lang") as Lang) || "uk"));
  const setLang = (l: Lang) => {
    localStorage.setItem("crm_lang", l);
    document.documentElement.lang = l;
    setLangState(l);
  };
  const t = (ru: string, uk: string) => (lang === "uk" ? uk : ru);
  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>;
}

export function useLang() { return useContext(LangCtx); }
export function useT() { return useContext(LangCtx).t; }
