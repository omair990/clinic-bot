/**
 * Bilingual (English / Arabic) layer for the console.
 *
 * - `useT()` returns a `t(key, vars?)` lookup into the merged locale dictionary
 *   (see ./locales). Keys are namespaced, e.g. t("appointments.title").
 * - Language is persisted in localStorage and drives `document.dir`/`lang` so the
 *   whole app flips to RTL for Arabic (MUI/emotion flipping is wired in ColorMode.tsx).
 * - Missing Arabic keys fall back to English, so a partially-translated screen never
 *   shows a raw key.
 */
import {
  createContext, useContext, useCallback, useEffect, useMemo, useState, ReactNode,
} from "react";
import { dict } from "./locales";

export type Lang = "en" | "ar";
const KEY = "clinic.lang";

export function initialLang(): Lang {
  const saved = localStorage.getItem(KEY);
  return saved === "ar" || saved === "en" ? saved : "en";
}

interface I18nCtx {
  lang: Lang;
  dir: "ltr" | "rtl";
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}
const Ctx = createContext<I18nCtx>(null as any);
export const useI18n = () => useContext(Ctx);
export const useT = () => useContext(Ctx).t;

function resolve(lang: Lang, key: string): string {
  const walk = (root: any) => {
    let cur = root;
    for (const p of key.split(".")) { cur = cur?.[p]; if (cur == null) return undefined; }
    return cur;
  };
  let val = walk(dict[lang]);
  if (val == null && lang !== "en") val = walk(dict.en);  // fall back to English
  return typeof val === "string" ? val : key;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const dir: "ltr" | "rtl" = lang === "ar" ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);

  const setLang = useCallback((l: Lang) => { localStorage.setItem(KEY, l); setLangState(l); }, []);
  const t = useCallback((key: string, vars?: Record<string, string | number>) => {
    let s = resolve(lang, key);
    if (vars) for (const k of Object.keys(vars)) s = s.split(`{${k}}`).join(String(vars[k]));
    return s;
  }, [lang]);

  const value = useMemo(() => ({ lang, dir, setLang, t }), [lang, dir, setLang, t]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
