import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SnackbarProvider } from "notistack";
import { I18nProvider, initialLang } from "./i18n";
import { ColorModeProvider } from "./ColorMode";
import { AuthProvider } from "./auth";
import { LiveProvider } from "./realtime";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

// Set direction/lang before first paint so the cold render is already RTL for Arabic.
const lang = initialLang();
document.documentElement.lang = lang;
document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <ColorModeProvider>
        <SnackbarProvider
          maxSnack={3}
          anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
          autoHideDuration={3500}
        >
          <QueryClientProvider client={queryClient}>
            <AuthProvider>
              <LiveProvider>
                {/* React console owns /admin (cut over from the legacy Jinja admin). */}
                <BrowserRouter basename="/admin">
                  <App />
                </BrowserRouter>
              </LiveProvider>
            </AuthProvider>
          </QueryClientProvider>
        </SnackbarProvider>
      </ColorModeProvider>
    </I18nProvider>
  </React.StrictMode>
);
