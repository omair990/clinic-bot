import { createContext, useContext, useMemo, useState, ReactNode } from "react";
import { ThemeProvider, CssBaseline } from "@mui/material";
import { makeTheme, Mode } from "./theme";

const KEY = "clinic.colorMode";
const ColorModeCtx = createContext<{ mode: Mode; toggle: () => void }>({
  mode: "dark",
  toggle: () => {},
});
export const useColorMode = () => useContext(ColorModeCtx);

export function ColorModeProvider({ children }: { children: ReactNode }) {
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
  const theme = useMemo(() => makeTheme(mode), [mode]);
  return (
    <ColorModeCtx.Provider value={ctx}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ColorModeCtx.Provider>
  );
}
