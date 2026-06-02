import { createContext, useContext, useMemo, useState, ReactNode } from "react";
import { ThemeProvider, CssBaseline } from "@mui/material";
import createCache from "@emotion/cache";
import { CacheProvider } from "@emotion/react";
import { prefixer } from "stylis";
import rtlPlugin from "stylis-plugin-rtl";
import { makeTheme, Mode } from "./theme";
import { useI18n } from "./i18n";

const KEY = "clinic.colorMode";
const ColorModeCtx = createContext<{ mode: Mode; toggle: () => void }>({
  mode: "dark",
  toggle: () => {},
});
export const useColorMode = () => useContext(ColorModeCtx);

// One emotion cache per writing direction. The RTL cache runs stylis-plugin-rtl, which flips
// physical CSS (margins, paddings, left/right, transforms) in every styled/sx rule — so the
// whole MUI tree mirrors for Arabic with no per-component changes.
const ltrCache = createCache({ key: "mui", stylisPlugins: [prefixer] });
const rtlCache = createCache({ key: "muirtl", stylisPlugins: [prefixer, rtlPlugin] });

export function ColorModeProvider({ children }: { children: ReactNode }) {
  const { dir } = useI18n();
  const [mode, setMode] = useState<Mode>(
    () => (localStorage.getItem(KEY) as Mode) || "dark"   // default dark
  );
  const ctx = useMemo(
    () => ({
      mode,
      toggle: () =>
        setMode((m) => {
          const next: Mode = m === "dark" ? "light" : "dark";
          localStorage.setItem(KEY, next);
          return next;
        }),
    }),
    [mode]
  );
  const theme = useMemo(() => makeTheme(mode, dir), [mode, dir]);
  return (
    <ColorModeCtx.Provider value={ctx}>
      <CacheProvider value={dir === "rtl" ? rtlCache : ltrCache}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          {children}
        </ThemeProvider>
      </CacheProvider>
    </ColorModeCtx.Provider>
  );
}
