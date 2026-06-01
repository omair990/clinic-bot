import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Grid, TextField, Button, Typography, Alert, Stack, Box,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SettingsInputComponentIcon from "@mui/icons-material/SettingsInputComponent";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError, useToast } from "../lib";
import ClinicDataEditor, { ClinicData } from "../ClinicDataEditor";

export default function TenantEdit() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useApiQuery<any>(["tenant", id], `/tenants/${id}`);

  const [form, setForm] = useState<any>(null);
  const [cd, setCd] = useState<ClinicData>({});
  const [staffPassword, setStaffPassword] = useState("");
  const [waToken, setWaToken] = useState("");
  const [confirmSlug, setConfirmSlug] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (q.data) { setForm(q.data); setCd(q.data.clinic_data_obj || {}); } }, [q.data]);
  if (q.isLoading || !form) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });

  const save = async () => {
    setBusy(true); setErrors([]);
    try {
      const r = await apiPost(`/tenants/${id}/edit`, {
        name: form.name, wa_phone_number_id: form.wa_phone_number_id, timezone: form.timezone,
        wa_access_token: waToken, staff_username: form.staff_username, staff_password: staffPassword,
        clinic_data: JSON.stringify(cd),
      });
      qc.invalidateQueries({ queryKey: ["tenant", id] });
      setStaffPassword(""); setWaToken("");
      toast.ok(r.warnings?.length ? `Saved (${r.warnings.length} warning(s))` : "Clinic saved");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Save failed";
      // Server returns "Clinic data invalid — a; b; c" — split into a checklist.
      if (msg.includes("invalid —")) setErrors(msg.split("—")[1].split(";").map((s) => s.trim()).filter(Boolean));
      toast.err(msg.length > 90 ? "Please fix the highlighted clinic-data errors" : msg);
    } finally { setBusy(false); }
  };

  const del = async () => {
    setBusy(true);
    try {
      await apiPost(`/tenants/${id}/delete`, { confirm_slug: confirmSlug });
      qc.invalidateQueries({ queryKey: ["plans"] });
      toast.ok("Clinic deleted");
      nav("/plans");
    } catch (e) { toast.err(e instanceof ApiError ? e.message : "Delete failed"); }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title={`Manage clinic · ${form.name}`} right={
        <Stack direction="row" spacing={1}>
          <Button startIcon={<SettingsInputComponentIcon />} onClick={() => nav(`/tenants/${id}/connector`)}>Connector</Button>
          <Button startIcon={<ArrowBackIcon />} onClick={() => nav("/plans")}>Back</Button>
        </Stack>} />

      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Account & WhatsApp</Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} md={4}><TextField fullWidth size="small" label="Name" value={form.name || ""} onChange={set("name")} /></Grid>
            <Grid item xs={12} md={4}><TextField fullWidth size="small" label="Slug" value={form.slug || ""} disabled helperText="Immutable" /></Grid>
            <Grid item xs={12} md={4}><TextField fullWidth size="small" label="Timezone" value={form.timezone || ""} onChange={set("timezone")} /></Grid>
            <Grid item xs={12} md={4}><TextField fullWidth size="small" label="WhatsApp phone_number_id" value={form.wa_phone_number_id || ""} onChange={set("wa_phone_number_id")} /></Grid>
            <Grid item xs={12} md={4}><TextField fullWidth size="small" type="password" label="WhatsApp access token"
              placeholder={form.has_wa_access_token ? "•••• set — blank keeps" : "not set"} value={waToken} onChange={(e) => setWaToken(e.target.value)} /></Grid>
            <Grid item xs={6} md={2}><TextField fullWidth size="small" label="Staff username" value={form.staff_username || ""} onChange={set("staff_username")} /></Grid>
            <Grid item xs={6} md={2}><TextField fullWidth size="small" type="password" label="Staff password" placeholder="blank keeps" value={staffPassword} onChange={(e) => setStaffPassword(e.target.value)} /></Grid>
          </Grid>
        </CardContent>
      </Card>

      <Typography variant="subtitle2" sx={{ mb: 1 }}>Clinic data</Typography>
      {errors.length > 0 && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography variant="body2" fontWeight={700}>Fix these before saving:</Typography>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </Alert>
      )}
      <ClinicDataEditor value={cd} onChange={setCd} />

      <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
        <Button variant="contained" disabled={busy} onClick={save}>Save clinic</Button>
      </Stack>

      {!form.is_default && (
        <Card sx={{ mt: 4, borderColor: "error.main", borderWidth: 1, borderStyle: "solid" }}>
          <CardContent>
            <Typography color="error" fontWeight={700}>Danger zone</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Permanently delete this clinic and all its data. Type the slug <b>{form.slug}</b> to confirm.
            </Typography>
            <Stack direction="row" spacing={2}>
              <TextField size="small" label="Confirm slug" value={confirmSlug} onChange={(e) => setConfirmSlug(e.target.value)} />
              <Button color="error" variant="contained" disabled={busy || confirmSlug !== form.slug} onClick={del}>Delete clinic</Button>
            </Stack>
          </CardContent>
        </Card>
      )}
      {form.is_default && <Box sx={{ mt: 3, color: "text.secondary", fontSize: 13 }}>The default tenant cannot be deleted.</Box>}
    </>
  );
}
