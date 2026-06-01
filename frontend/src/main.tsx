import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, CssBaseline } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { theme } from "./theme";
import { AuthProvider } from "./auth";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          {/* React console owns /admin (cut over from the legacy Jinja admin). */}
          <BrowserRouter basename="/admin">
            <App />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>
);
