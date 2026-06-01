import { useState } from "react";
import { Box, Card, CardContent, TextField, Button, Typography, Alert, Stack } from "@mui/material";
import { useAuth } from "../auth";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
    } catch {
      setError("Invalid credentials");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center", bgcolor: "#0f172a" }}>
      <Card sx={{ width: 380, p: 1 }}>
        <CardContent component="form" onSubmit={submit}>
          <Typography variant="h5" sx={{ mb: 0.5 }}>Clinic Console</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Sign in to continue
          </Typography>
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Username" size="small" fullWidth autoFocus
              helperText="Leave blank for platform admin"
              value={username} onChange={(e) => setUsername(e.target.value)}
            />
            <TextField
              label="Password" type="password" size="small" fullWidth
              value={password} onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" variant="contained" size="large" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
