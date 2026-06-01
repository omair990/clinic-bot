import { useState } from "react";
import {
  Box, Card, CardContent, TextField, Button, Typography, Alert, Stack, InputAdornment, IconButton,
} from "@mui/material";
import LocalHospitalIcon from "@mui/icons-material/LocalHospital";
import LightModeIcon from "@mui/icons-material/LightModeOutlined";
import DarkModeIcon from "@mui/icons-material/DarkModeOutlined";
import { useAuth } from "../auth";
import { useColorMode } from "../ColorMode";

export default function Login() {
  const { login } = useAuth();
  const { mode, toggle } = useColorMode();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); setBusy(true);
    try { await login(username, password); }
    catch { setError("Invalid credentials"); }
    finally { setBusy(false); }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center", p: 2, position: "relative",
      background: (t) => t.palette.mode === "dark"
        ? "radial-gradient(900px 500px at 20% 0%, rgba(20,184,166,.18), transparent), radial-gradient(900px 500px at 100% 100%, rgba(99,102,241,.18), transparent), #0b1120"
        : "radial-gradient(900px 500px at 20% 0%, rgba(20,184,166,.12), transparent), radial-gradient(900px 500px at 100% 100%, rgba(99,102,241,.12), transparent), #f5f7fb" }}>
      <IconButton onClick={toggle} sx={{ position: "absolute", top: 16, right: 16 }}>
        {mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}
      </IconButton>
      <Card sx={{ width: 400, maxWidth: "100%" }}>
        <CardContent component="form" onSubmit={submit} sx={{ p: 4 }}>
          <Stack alignItems="center" spacing={1.5} sx={{ mb: 3 }}>
            <Box sx={{ width: 56, height: 56, borderRadius: 3, display: "grid", placeItems: "center",
              background: "linear-gradient(135deg,#14b8a6,#6366f1)", color: "#fff" }}>
              <LocalHospitalIcon />
            </Box>
            <Typography variant="h5">Clinic Console</Typography>
            <Typography variant="body2" color="text.secondary">Sign in to your workspace</Typography>
          </Stack>
          <Stack spacing={2}>
            {error && <Alert severity="error" variant="outlined">{error}</Alert>}
            <TextField label="Username" size="small" fullWidth autoFocus
              helperText="Leave blank for platform admin"
              value={username} onChange={(e) => setUsername(e.target.value)} />
            <TextField label="Password" type="password" size="small" fullWidth
              value={password} onChange={(e) => setPassword(e.target.value)} />
            <Button type="submit" variant="contained" size="large" disabled={busy}
              sx={{ background: "linear-gradient(135deg,#14b8a6,#6366f1)", py: 1.2 }}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
