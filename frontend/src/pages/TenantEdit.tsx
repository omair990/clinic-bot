import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Grid, TextField, Button, Typography, Alert, Stack, Divider, Box,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError } from "../lib";

export default function TenantEdit() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useApiQuery<any>(["tenant", id], `/tenants/${id}`);

  const [form, setForm] = useState<any>(null);
  const [staffPassword, setStaffPassword] = useState("");
  const [waToken, setWaToken] = useState("");
  const [confirmSlug, setConfirmSlug] = useState("");
  const [msg, setMsg] = useState<{ type: "success" | "error" | "warning"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (q.data) setForm(q.data); }, [q.data]);
  if (q.isLoading || !form) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await apiPost(`/tenants/${id}/edit`, {
        name: form.name, wa_phone_number_id: form.wa_phone_number_id,
        timezone: form.timezone, wa_access_token: waToken,
        staff_username: form.staff_username, staff_password: staffPassword,
        clinic_data: form.clinic_data,
      });
      qc.invalidateQueries({ queryKey: ["tenant", id] });
      setStaffPassword(""); setWaToken("");
      const warn = r.warnings?.length ? ` (warnings: ${r.warnings.join("; ")})` : "";
      setMsg({ type: r.warnings?.length ? "warning" : "success", text: "Saved." + warn });
    } catch (e) {
      setMsg({ type: "error", text: e instanceof ApiError ? e.message : "Save failed" });
    } finally { setBusy(false); }
  };

  const del = async () => {
    setBusy(true); setMsg(null);
    try {
      await apiPost(`/tenants/${id}/delete`, { confirm_slug: confirmSlug });
      qc.invalidateQueries({ queryKey: ["plans"] });
      nav("/plans");
    } catch (e) {
      setMsg({ type: "error", text: e instanceof ApiError ? e.message : "Delete failed" });
    } finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title={`Edit clinic · ${form.name}`}
        right={<Button startIcon={<ArrowBackIcon />} onClick={() => nav("/plans")}>Back</Button>} />
      {msg && <Alert severity={msg.type} sx={{ mb: 2 }}>{msg.text}</Alert>}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}><TextField fullWidth size="small" label="Name" value={form.name || ""} onChange={set("name")} /></Grid>
            <Grid item xs={12} md={6}><TextField fullWidth size="small" label="Slug" value={form.slug || ""} disabled helperText="Slug is immutable" /></Grid>
            <Grid item xs={12} md={6}><TextField fullWidth size="small" label="WhatsApp phone_number_id" value={form.wa_phone_number_id || ""} onChange={set("wa_phone_number_id")} /></Grid>
            <Grid item xs={12} md={6}><TextField fullWidth size="small" label="Timezone" value={form.timezone || ""} onChange={set("timezone")} /></Grid>
            <Grid item xs={12} md={6}><TextField fullWidth size="small" type="password" label="WhatsApp access token"
              placeholder={form.has_wa_access_token ? "•••• set — leave blank to keep" : "not set"}
              value={waToken} onChange={(e) => setWaToken(e.target.value)} /></Grid>
            <Grid item xs={12} md={3}><TextField fullWidth size="small" label="Staff username" value={form.staff_username || ""} onChange={set("staff_username")} /></Grid>
            <Grid item xs={12} md={3}><TextField fullWidth size="small" type="password" label="Staff password" placeholder="leave blank to keep" value={staffPassword} onChange={(e) => setStaffPassword(e.target.value)} /></Grid>
            <Grid item xs={12}>
              <TextField fullWidth multiline minRows={10} label="Clinic data (JSON)"
                value={form.clinic_data || ""} onChange={set("clinic_data")}
                InputProps={{ sx: { fontFamily: "monospace", fontSize: 13 } }} />
            </Grid>
          </Grid>
          <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
            <Button variant="contained" disabled={busy} onClick={save}>Save changes</Button>
            <Button onClick={() => nav(`/tenants/${id}/connector`)}>Configure connector</Button>
          </Stack>
        </CardContent>
      </Card>

      {!form.is_default && (
        <Card sx={{ borderColor: "error.main", borderWidth: 1, borderStyle: "solid" }}>
          <CardContent>
            <Typography color="error" fontWeight={700}>Danger zone</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Permanently delete this clinic and ALL its data. Type the slug <b>{form.slug}</b> to confirm.
            </Typography>
            <Stack direction="row" spacing={2}>
              <TextField size="small" label="Confirm slug" value={confirmSlug} onChange={(e) => setConfirmSlug(e.target.value)} />
              <Button color="error" variant="contained" disabled={busy || confirmSlug !== form.slug} onClick={del}>Delete clinic</Button>
            </Stack>
          </CardContent>
        </Card>
      )}
      {form.is_default && <Box sx={{ color: "text.secondary", fontSize: 13 }}>The default tenant cannot be deleted.</Box>}
    </>
  );
}
