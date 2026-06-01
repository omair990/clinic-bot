import { useEffect, useState } from "react";
import { Card, CardContent, TextField, Button, Typography, Alert, Grid, Box, Chip, Stack } from "@mui/material";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError } from "../lib";

export default function Settings() {
  const q = useApiQuery<any>(["settings"], "/settings");
  const [values, setValues] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) {
      const init: Record<string, string> = {};
      Object.entries(q.data.editable).forEach(([k, v]: any) => (init[k] = v.value || ""));
      setValues(init);
    }
  }, [q.data]);
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;

  const editable = q.data.editable as Record<string, { label: string; group: string; value: string }>;
  const groups: Record<string, string[]> = {};
  Object.entries(editable).forEach(([k, v]) => { (groups[v.group] ||= []).push(k); });

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await apiPost("/settings", { values });
      setMsg({ type: "success", text: "Settings saved." });
      q.refetch();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof ApiError ? e.message : "Save failed" });
    } finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title="Settings" />
      {msg && <Alert severity={msg.type} sx={{ mb: 2 }}>{msg.text}</Alert>}
      {Object.entries(groups).map(([group, keys]) => (
        <Card key={group} sx={{ mb: 2 }}>
          <CardContent>
            <Typography fontWeight={700} sx={{ mb: 1.5 }}>{group}</Typography>
            <Grid container spacing={2}>
              {keys.map((k) => (
                <Grid item xs={12} md={6} key={k}>
                  <TextField fullWidth size="small" label={editable[k].label}
                    value={values[k] ?? ""} onChange={(e) => setValues({ ...values, [k]: e.target.value })} />
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      ))}
      <Button variant="contained" disabled={busy} onClick={save} sx={{ mb: 3 }}>Save settings</Button>

      {q.data.inventory && (
        <Card>
          <CardContent>
            <Typography fontWeight={700} sx={{ mb: 1 }}>Configuration status</Typography>
            <Stack spacing={0.5}>
              {Object.entries(q.data.inventory).map(([k, v]: any) => (
                <Box key={k} sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <Typography variant="body2">{k}</Typography>
                  <Chip size="small" label={String(typeof v === "object" ? (v.status ?? JSON.stringify(v)) : v)}
                    color={v === true || v === "ok" || v?.ok ? "success" : "default"} />
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}
    </>
  );
}
