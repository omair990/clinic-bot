import { createTheme, alpha, Theme } from "@mui/material/styles";

export type Mode = "light" | "dark";
export type Dir = "ltr" | "rtl";

// Refined teal (primary) + indigo (secondary) on a slate canvas. Two cohesive palettes.
export function makeTheme(mode: Mode, dir: Dir = "ltr"): Theme {
  const dark = mode === "dark";
  const teal = "#14b8a6";
  const indigo = "#6366f1";
  return createTheme({
    direction: dir,
    palette: {
      mode,
      primary: { main: teal, light: "#5eead4", dark: "#0f766e" },
      secondary: { main: indigo, light: "#a5b4fc", dark: "#4338ca" },
      success: { main: "#10b981" },
      warning: { main: "#f59e0b" },
      error: { main: "#ef4444" },
      info: { main: "#38bdf8" },
      background: dark
        ? { default: "#0b1120", paper: "#111a2e" }
        : { default: "#f5f7fb", paper: "#ffffff" },
      text: dark
        ? { primary: "#e8edf6", secondary: "#94a3b8" }
        : { primary: "#0f172a", secondary: "#64748b" },
      divider: dark ? alpha("#94a3b8", 0.16) : alpha("#475569", 0.14),
    },
    shape: { borderRadius: 14 },
    typography: {
      fontFamily: `"Cairo", "Inter", "Segoe UI", "Tahoma", "Geeza Pro", "Noto Sans Arabic", system-ui, -apple-system, sans-serif`,
      h4: { fontWeight: 800, letterSpacing: -0.5 },
      h5: { fontWeight: 800, letterSpacing: -0.4 },
      h6: { fontWeight: 700 },
      subtitle2: { fontWeight: 700 },
      button: { textTransform: "none", fontWeight: 600 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundImage: dark
              ? "radial-gradient(1200px 600px at 100% -10%, rgba(99,102,241,.16), transparent), radial-gradient(1000px 500px at -10% 110%, rgba(20,184,166,.12), transparent)"
              : "radial-gradient(1200px 600px at 100% -10%, rgba(99,102,241,.08), transparent), radial-gradient(1000px 500px at -10% 110%, rgba(20,184,166,.08), transparent)",
            backgroundAttachment: "fixed",
          },
          "*::-webkit-scrollbar": { width: 10, height: 10 },
          "*::-webkit-scrollbar-thumb": {
            background: alpha("#94a3b8", 0.35), borderRadius: 8,
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            backgroundImage: "none",
            border: `1px solid ${dark ? alpha("#94a3b8", 0.12) : alpha("#475569", 0.1)}`,
            backdropFilter: "blur(6px)",
            backgroundColor: dark ? alpha("#111a2e", 0.7) : alpha("#ffffff", 0.85),
            boxShadow: dark
              ? "0 1px 0 rgba(255,255,255,.03) inset, 0 8px 24px -12px rgba(0,0,0,.6)"
              : "0 1px 2px rgba(15,23,42,.06), 0 8px 24px -16px rgba(15,23,42,.18)",
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: { root: { borderRadius: 10 } },
      },
      MuiAppBar: { styleOverrides: { root: { backgroundImage: "none", boxShadow: "none" } } },
      MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
      MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
    },
  });
}
