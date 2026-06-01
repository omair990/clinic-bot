import { createTheme } from "@mui/material/styles";

// A clean, professional console theme — teal/emerald primary on a soft slate canvas.
export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#0f766e", light: "#14b8a6", dark: "#0b5650" },
    secondary: { main: "#2563eb" },
    background: { default: "#f1f5f9", paper: "#ffffff" },
    success: { main: "#059669" },
    warning: { main: "#d97706" },
    error: { main: "#dc2626" },
    text: { primary: "#0f172a", secondary: "#64748b" },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: `"Inter", "Segoe UI", system-ui, -apple-system, sans-serif`,
    h5: { fontWeight: 700 },
    h6: { fontWeight: 700 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiCard: { styleOverrides: { root: { boxShadow: "0 1px 3px rgba(15,23,42,.08)" } } },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiAppBar: { styleOverrides: { root: { boxShadow: "none" } } },
  },
});
