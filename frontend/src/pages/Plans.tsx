import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Table, TableHead, TableRow, TableCell, TableBody, Select, MenuItem,
  Button, Typography, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Grid, Alert,
  Stack,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError, useToast } from "../lib";

function AddClinicDialog({ open, onClose, plans, onCreated }: any) {
  const [f, setF] = useState<any>({ timezone: "Asia/Riyadh", plan_id: plans[0]?.id });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const create = async () => {
    setBusy(true); setErr(null);
    try { await apiPost("/tenants", f); onCreated(); onClose(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Create failed"); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Add clinic</DialogTitle>
      <DialogContent>
        {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
        <Grid container spacing={2} sx={{ mt: 0 }}>
          <Grid item xs={12} md={6}><TextField fullWidth size="small" label="Name" onChange={set("name")} /></Grid>
          <Grid item xs={12} md={6}><TextField fullWidth size="small" label="Slug (unique)" onChange={set("slug")} /></Grid>
          <Grid item xs={12} md={6}><TextField fullWidth size="small" label="WhatsApp phone_number_id" onChange={set("wa_phone_number_id")} /></Grid>
          <Grid item xs={12} md={6}><TextField fullWidth size="small" label="Timezone" value={f.timezone} onChange={set("timezone")} /></Grid>
          <Grid item xs={12} md={6}>
            <Select fullWidth size="small" value={f.plan_id ?? ""} onChange={set("plan_id")}>
              {plans.map((p: any) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
            </Select>
          </Grid>
          <Grid item xs={12} md={6}><TextField fullWidth size="small" label="WhatsApp token (optional)" onChange={set("wa_access_token")} /></Grid>
          <Grid item xs={12} md={6}><TextField fullWidth size="small" label="Staff username (optional)" onChange={set("staff_username")} /></Grid>
          <Grid item xs={12} md={6}><TextField fullWidth size="small" type="password" label="Staff password (optional)" onChange={set("staff_password")} /></Grid>
          <Grid item xs={12}><TextField fullWidth multiline minRows={4} label="Clinic data JSON (optional)" onChange={set("clinic_data")} InputProps={{ sx: { fontFamily: "monospace", fontSize: 13 } }} /></Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={busy} onClick={create}>Create clinic</Button>
      </DialogActions>
    </Dialog>
  );
}

export default function Plans() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const [addOpen, setAddOpen] = useState(false);
  const q = useApiQuery<any>(["plans"], "/plans");
  const setPlan = useMutation({
    mutationFn: (v: { id: number; plan_id: number }) => apiPost(`/tenants/${v.id}/plan`, { plan_id: v.plan_id }),
    onSuccess: () => { toast.ok("Plan updated"); qc.invalidateQueries({ queryKey: ["plans"] }); },
  });
  const setStatus = useMutation({
    mutationFn: (v: { id: number; status: string }) => apiPost(`/tenants/${v.id}/status`, { status: v.status }),
    onSuccess: () => { toast.ok("Status updated"); qc.invalidateQueries({ queryKey: ["plans"] }); },
  });

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { plans = [], tenants = [], period } = q.data;

  return (
    <>
      <PageTitle title="Plans & usage" right={
        <Stack direction="row" spacing={2} alignItems="center">
          <Typography variant="body2" color="text.secondary">Period {period}</Typography>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>Add clinic</Button>
        </Stack>} />
      <AddClinicDialog open={addOpen} onClose={() => setAddOpen(false)} plans={plans}
        onCreated={() => qc.invalidateQueries({ queryKey: ["plans"] })} />
      <Card sx={{ mb: 3 }}>
        <CardContent><Typography fontWeight={700} sx={{ mb: 1 }}>Clinics</Typography></CardContent>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Clinic</TableCell><TableCell>Plan</TableCell><TableCell>Text usage</TableCell>
            <TableCell>Voice usage</TableCell><TableCell>Status</TableCell><TableCell align="right">Manage</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {tenants.map((t: any) => (
              <TableRow key={t.id} hover>
                <TableCell>{t.name}<Typography variant="caption" color="text.secondary" display="block">{t.slug}</Typography></TableCell>
                <TableCell>
                  <Select size="small" value={plans.find((p: any) => p.name === t.plan_name)?.id ?? ""}
                    onChange={(e) => setPlan.mutate({ id: t.id, plan_id: Number(e.target.value) })}>
                    {plans.map((p: any) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
                  </Select>
                </TableCell>
                <TableCell>{t.text_count} / {t.monthly_text_quota ?? "∞"}</TableCell>
                <TableCell>{t.voice_enabled ? `${t.voice_count} / ${t.monthly_voice_quota ?? "∞"}` : "off"}</TableCell>
                <TableCell>
                  <Select size="small" value={t.status}
                    onChange={(e) => setStatus.mutate({ id: t.id, status: String(e.target.value) })}>
                    {["active", "suspended", "expired"].map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
                  </Select>
                </TableCell>
                <TableCell align="right">
                  <Button size="small" onClick={() => nav(`/tenants/${t.id}`)}>Edit</Button>
                  <Button size="small" onClick={() => nav(`/tenants/${t.id}/connector`)}>Connector</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <Card>
        <CardContent><Typography fontWeight={700} sx={{ mb: 1 }}>Packages</Typography></CardContent>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Name</TableCell><TableCell>Text/mo</TableCell><TableCell>Voice</TableCell>
            <TableCell>Trial</TableCell><TableCell>Price (SAR)</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {plans.map((p: any) => (
              <TableRow key={p.id}>
                <TableCell>{p.name}</TableCell>
                <TableCell>{p.monthly_text_quota ?? "∞"}</TableCell>
                <TableCell>{p.voice_enabled ? (p.monthly_voice_quota ?? "∞") : "off"}</TableCell>
                <TableCell>{p.is_trial ? `${p.trial_days}d` : "—"}</TableCell>
                <TableCell>{p.price_sar ?? "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
