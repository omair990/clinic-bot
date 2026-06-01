import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SnackbarProvider } from "notistack";
import { ColorModeProvider } from "./ColorMode";
import { AuthProvider } from "./auth";
import { LiveProvider } from "./realtime";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
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
  </React.StrictMode>
);
