import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Select, MenuItem, Button, Typography, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, Grid, Alert, Stack, FormControlLabel, Switch, Box, Chip, Avatar,
  Divider, IconButton, Tooltip, alpha,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/EditOutlined";
import HubIcon from "@mui/icons-material/HubOutlined";
import BusinessIcon from "@mui/icons-material/BusinessOutlined";
import CheckCircleIcon from "@mui/icons-material/CheckCircleOutlined";
import PauseIcon from "@mui/icons-material/PauseCircleOutlined";
import LayersIcon from "@mui/icons-material/LayersOutlined";
import TextsmsIcon from "@mui/icons-material/TextsmsOutlined";
import GraphicEqIcon from "@mui/icons-material/GraphicEqOutlined";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError, useToast, KpiCard } from "../lib";

const statusColor: Record<string, any> = { active: "success", suspended: "warning", expired: "error" };
const fmt = (n: number | null | undefined) => (n == null ? "∞" : n.toLocaleString());
function avatarHue(s: string) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }

// Slim usage bar with a "used / quota" caption, colored by how close to the limit.
function UsageBar({ label, icon, used, quota, on }: {
  label: string; icon: React.ReactNode; used: number; quota: number | null; on: boolean;
}) {
  const unlimited = quota == null;
  const pct = quota ? Math.min(100, (used / quota) * 100) : (unlimited ? 100 : 0);
  const over = on && !unlimited && pct >= 100;
  const near = on && !unlimited && pct >= 80 && !over;
  const color = !on ? "#94a3b8" : over ? "#ef4444" : near ? "#f59e0b" : "#14b8a6";
  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ color: "text.secondary" }}>
          <Box sx={{ display: "grid", placeItems: "center", color }}>{icon}</Box>
          <Typography variant="caption" fontWeight={700}>{label}</Typography>
        </Stack>
        <Typography variant="caption" color={on ? "text.primary" : "text.secondary"} fontWeight={700}>
          {on ? `${fmt(used)} / ${fmt(quota)}` : "off"}
        </Typography>
      </Stack>
      <Box sx={{ height: 7, borderRadius: 4, overflow: "hidden", bgcolor: (t) => alpha(t.palette.text.primary, 0.06) }}>
        <Box sx={{ width: `${on ? (unlimited ? 100 : pct) : 0}%`, height: "100%", bgcolor: color,
          opacity: unlimited ? 0.5 : 1, transition: "width .4s ease" }} />
      </Box>
    </Box>
  );
}

function ClinicCard({ t, plans, onPlan, onStatus, onEdit, onConnector }: {
  t: any; plans: any[]; onPlan: (id: number, planId: number) => void;
  onStatus: (id: number, status: string) => void; onEdit: () => void; onConnector: () => void;
}) {
  const hue = avatarHue(t.slug || t.name || "");
  const sc = statusColor[t.status] || "default";
  return (
    <Card sx={{ height: "100%", display: "flex", flexDirection: "column", position: "relative", overflow: "hidden",
      "&::before": { content: '""', position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
        bgcolor: (th) => (th.palette as any)[sc]?.main || th.palette.primary.main, opacity: 0.85 } }}>
      <CardContent sx={{ flex: 1, display: "flex", flexDirection: "column", gap: 1.5 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Avatar sx={{ width: 42, height: 42, fontWeight: 800, fontSize: 15, flexShrink: 0,
            background: `linear-gradient(135deg, hsl(${hue} 70% 55%), hsl(${(hue + 40) % 360} 70% 45%))`, color: "#fff" }}>
            {(t.name || t.slug || "?").slice(0, 2).toUpperCase()}
          </Avatar>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography fontWeight={700} noWrap>{t.name}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap display="block">{t.slug}</Typography>
          </Box>
          <Chip size="small" color={sc} variant="outlined" label={t.status} sx={{ textTransform: "capitalize" }} />
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center">
          <Select size="small" fullWidth value={plans.find((p: any) => p.name === t.plan_name)?.id ?? ""}
            onChange={(e) => onPlan(t.id, Number(e.target.value))}>
            {plans.map((p: any) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
          </Select>
          <Select size="small" value={t.status} onChange={(e) => onStatus(t.id, String(e.target.value))} sx={{ minWidth: 124 }}>
            {["active", "suspended", "expired"].map((s) => <MenuItem key={s} value={s} sx={{ textTransform: "capitalize" }}>{s}</MenuItem>)}
          </Select>
        </Stack>

        <Stack spacing={1.25} sx={{ mt: 0.5 }}>
          <UsageBar label="Text" icon={<TextsmsIcon sx={{ fontSize: 15 }} />} used={t.text_count} quota={t.monthly_text_quota} on />
          <UsageBar label="Voice" icon={<GraphicEqIcon sx={{ fontSize: 15 }} />} used={t.voice_count} quota={t.monthly_voice_quota} on={t.voice_enabled} />
        </Stack>

        <Divider sx={{ mt: "auto" }} />
        <Stack direction="row" alignItems="center" spacing={1}>
          <Chip size="small" variant="outlined" label={t.connector_type} sx={{ textTransform: "capitalize" }} />
          <Box sx={{ flex: 1 }} />
          <Tooltip title="Edit clinic"><IconButton size="small" onClick={onEdit}><EditIcon fontSize="small" /></IconButton></Tooltip>
          <Tooltip title="Connector"><IconButton size="small" onClick={onConnector}><HubIcon fontSize="small" /></IconButton></Tooltip>
        </Stack>
      </CardContent>
    </Card>
  );
}

function PackageCard({ p, onEdit }: { p: any; onEdit: () => void }) {
  const accent = p.is_trial ? "#a78bfa" : "#6366f1";
  return (
    <Card sx={{ height: "100%", display: "flex", flexDirection: "column", position: "relative", overflow: "hidden",
      "&::before": { content: '""', position: "absolute", inset: 0, pointerEvents: "none",
        background: `radial-gradient(120% 80% at 100% 0%, ${alpha(accent, 0.14)}, transparent 55%)` } }}>
      <CardContent sx={{ flex: 1, display: "flex", flexDirection: "column", gap: 1, position: "relative" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="h6" fontWeight={800}>{p.name}</Typography>
          {p.is_trial && <Chip size="small" label={`Trial · ${p.trial_days ?? 0}d`} sx={{ bgcolor: alpha(accent, 0.16), color: accent, fontWeight: 700 }} />}
        </Stack>
        <Stack direction="row" alignItems="baseline" spacing={0.5}>
          <Typography variant="h4" fontWeight={800}>{p.price_sar != null ? p.price_sar : "—"}</Typography>
          <Typography variant="body2" color="text.secondary">{p.price_sar != null ? "SAR / mo" : ""}</Typography>
        </Stack>
        <Divider sx={{ my: 0.5 }} />
        <Stack spacing={0.75}>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextsmsIcon sx={{ fontSize: 16, color: "#14b8a6" }} />
            <Typography variant="body2"><b>{fmt(p.monthly_text_quota)}</b> text / mo</Typography>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center">
            <GraphicEqIcon sx={{ fontSize: 16, color: p.voice_enabled ? "#6366f1" : "#94a3b8" }} />
            <Typography variant="body2" color={p.voice_enabled ? "text.primary" : "text.secondary"}>
              {p.voice_enabled ? <><b>{fmt(p.monthly_voice_quota)}</b> voice / mo</> : "Voice off"}
            </Typography>
          </Stack>
        </Stack>
        <Box sx={{ flex: 1 }} />
        <Button size="small" startIcon={<EditIcon fontSize="small" />} onClick={onEdit} sx={{ alignSelf: "flex-start", mt: 1 }}>Edit</Button>
      </CardContent>
    </Card>
  );
}

export default function Plans() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const [addOpen, setAddOpen] = useState(false);
  const [pkg, setPkg] = useState<any | null>(null);   // null = closed, {} = new, {…} = edit
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
  const active = tenants.filter((t: any) => t.status === "active").length;
  const inactive = tenants.length - active;

  return (
    <>
      <PageTitle title="Plans & usage" subtitle="Clinics, plans and monthly usage" right={
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Chip variant="outlined" label={`Period ${period}`} />
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>Add clinic</Button>
        </Stack>} />
      <AddClinicDialog open={addOpen} onClose={() => setAddOpen(false)} plans={plans}
        onCreated={() => qc.invalidateQueries({ queryKey: ["plans"] })} />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><KpiCard label="Clinics" value={tenants.length} icon={<BusinessIcon fontSize="small" />} color="primary" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Active" value={active} icon={<CheckCircleIcon fontSize="small" />} color="success" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Suspended / expired" value={inactive} icon={<PauseIcon fontSize="small" />} color="warning" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Packages" value={plans.length} icon={<LayersIcon fontSize="small" />} color="secondary" /></Grid>
      </Grid>

      <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1.5 }}>Clinics</Typography>
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {tenants.map((t: any) => (
          <Grid item xs={12} sm={6} lg={4} key={t.id}>
            <ClinicCard t={t} plans={plans}
              onPlan={(id, planId) => setPlan.mutate({ id, plan_id: planId })}
              onStatus={(id, status) => setStatus.mutate({ id, status })}
              onEdit={() => nav(`/tenants/${t.id}`)} onConnector={() => nav(`/tenants/${t.id}/connector`)} />
          </Grid>
        ))}
      </Grid>

      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
        <Typography variant="subtitle2" fontWeight={800}>Packages</Typography>
        <Button size="small" startIcon={<AddIcon />} onClick={() => setPkg({})}>New package</Button>
      </Stack>
      <Grid container spacing={2}>
        {plans.map((p: any) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={p.id}>
            <PackageCard p={p} onEdit={() => setPkg(p)} />
          </Grid>
        ))}
      </Grid>

      <PackageDialog pkg={pkg} onClose={() => setPkg(null)}
        onSaved={() => { toast.ok("Package saved"); qc.invalidateQueries({ queryKey: ["plans"] }); }} />
    </>
  );
}

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
      <DialogTitle sx={{ fontWeight: 800 }}>Add clinic</DialogTitle>
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
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit">Cancel</Button>
        <Button variant="contained" disabled={busy} onClick={create}>Create clinic</Button>
      </DialogActions>
    </Dialog>
  );
}

function PackageDialog({ pkg, onClose, onSaved }: { pkg: any | null; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<any>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setF(pkg || {}); }, [pkg]);
  if (pkg === null) return null;
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    try {
      await apiPost("/plans", {
        name: f.name, monthly_text_quota: f.monthly_text_quota, monthly_voice_quota: f.monthly_voice_quota,
        voice_enabled: !!f.voice_enabled, is_trial: !!f.is_trial, trial_days: f.trial_days, price_sar: f.price_sar,
      });
      onSaved(); onClose();
    } finally { setBusy(false); }
  };
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle sx={{ fontWeight: 800 }}>{pkg?.id ? "Edit package" : "New package"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField size="small" label="Name (existing name = edit)" value={f.name || ""} onChange={set("name")} disabled={!!pkg?.id} />
          <TextField size="small" type="number" label="Monthly text quota (blank = unlimited)" value={f.monthly_text_quota ?? ""} onChange={set("monthly_text_quota")} />
          <FormControlLabel control={<Switch checked={!!f.voice_enabled} onChange={(e) => setF({ ...f, voice_enabled: e.target.checked })} />} label="Voice enabled" />
          <TextField size="small" type="number" label="Monthly voice quota (blank = unlimited)" value={f.monthly_voice_quota ?? ""} onChange={set("monthly_voice_quota")} disabled={!f.voice_enabled} />
          <FormControlLabel control={<Switch checked={!!f.is_trial} onChange={(e) => setF({ ...f, is_trial: e.target.checked })} />} label="Trial plan" />
          <TextField size="small" type="number" label="Trial days" value={f.trial_days ?? ""} onChange={set("trial_days")} disabled={!f.is_trial} />
          <TextField size="small" type="number" label="Price (SAR)" value={f.price_sar ?? ""} onChange={set("price_sar")} />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit">Cancel</Button>
        <Button variant="contained" disabled={busy || !f.name} onClick={save}>Save package</Button>
      </DialogActions>
    </Dialog>
  );
}
