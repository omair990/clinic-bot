import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box, Card, Stack, Typography, Chip, Button, ToggleButton, ToggleButtonGroup, Avatar,
  Grid, IconButton, Tooltip, TextField, InputAdornment, alpha,
} from "@mui/material";
import { useSearchParams, useNavigate } from "react-router-dom";
import SearchIcon from "@mui/icons-material/SearchOutlined";
import EventAvailableIcon from "@mui/icons-material/EventAvailableOutlined";
import CheckCircleIcon from "@mui/icons-material/CheckCircleOutlined";
import EventBusyIcon from "@mui/icons-material/EventBusyOutlined";
import WarningIcon from "@mui/icons-material/WarningAmberOutlined";
import DoneIcon from "@mui/icons-material/DoneRounded";
import CloseIcon from "@mui/icons-material/CloseRounded";
import MedicalServicesIcon from "@mui/icons-material/MedicalServicesOutlined";
import { apiPost, ApiError } from "../api";
import {
  useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, TableSkeleton, QueryError,
  KpiCard, EmptyState, useToast, DetailDialog,
} from "../lib";

const statusColor: Record<string, any> = { confirmed: "success", completed: "info", cancelled: "default", no_show: "warning" };
const riskColor: Record<string, any> = { low: "success", medium: "warning", high: "error" };

function avatarHue(s: string) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }
function initials(name: string | null, wa: string) { return name ? name.slice(0, 2).toUpperCase() : wa.slice(-2); }
function clock(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
function dayLabel(iso?: string | null) {
  if (!iso) return "Undated";
  const d = new Date(iso), now = new Date();
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = (day(d) - day(now)) / 86400000;
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  return d.toLocaleDateString(undefined, {
    weekday: "long", day: "2-digit", month: "short",
    year: d.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
  });
}

function ActionBtns({ row, busy, onAct, stop }: {
  row: any; busy: boolean; onAct: (id: number, status: string) => void; stop?: boolean;
}) {
  const wrap = (e: React.MouseEvent) => { if (stop) e.stopPropagation(); };
  return (
    <Stack direction="row" spacing={0.5} onClick={wrap}>
      {row.status !== "completed" && (
        <Tooltip title="Mark completed"><span><IconButton size="small" color="success" disabled={busy}
          onClick={() => onAct(row.id, "completed")}><DoneIcon fontSize="small" /></IconButton></span></Tooltip>)}
      {row.status !== "no_show" && (
        <Tooltip title="Mark no-show"><span><IconButton size="small" color="warning" disabled={busy}
          onClick={() => onAct(row.id, "no_show")}><EventBusyIcon fontSize="small" /></IconButton></span></Tooltip>)}
      {row.status !== "cancelled" && (
        <Tooltip title="Cancel"><span><IconButton size="small" color="error" disabled={busy}
          onClick={() => onAct(row.id, "cancelled")}><CloseIcon fontSize="small" /></IconButton></span></Tooltip>)}
    </Stack>
  );
}

function ApptRow({ row, showClinic, clinicName, busy, onAct, onOpen }: {
  row: any; showClinic: boolean; clinicName?: string; busy: boolean;
  onAct: (id: number, status: string) => void; onOpen: () => void;
}) {
  const hue = avatarHue(row.wa_user || "");
  const sc = statusColor[row.status] || "primary";
  return (
    <Box onClick={onOpen} sx={{
      display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.5, cursor: "pointer", position: "relative",
      borderBottom: (t) => `1px solid ${t.palette.divider}`, transition: "background .15s ease",
      "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
      "&::before": { content: '""', position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
        bgcolor: (t) => (t.palette as any)[sc]?.main || t.palette.primary.main, opacity: 0.85 },
    }}>
      <Box sx={{ width: 76, flexShrink: 0, textAlign: "center" }}>
        <Typography fontWeight={800} sx={{ lineHeight: 1.1 }}>{clock(row.start_at)}</Typography>
      </Box>
      <Avatar sx={{ width: 42, height: 42, fontWeight: 700, fontSize: 14, flexShrink: 0,
        background: `linear-gradient(135deg, hsl(${hue} 70% 55%), hsl(${(hue + 40) % 360} 70% 45%))`, color: "#fff" }}>
        {initials(row.patient_name, row.wa_user || "")}
      </Avatar>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography fontWeight={700} noWrap>
          {row.patient_name || `+${row.wa_user}`}
          {showClinic && clinicName && <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>· {clinicName}</Typography>}
        </Typography>
        <Stack direction="row" alignItems="center" spacing={0.6} sx={{ color: "text.secondary", minWidth: 0 }}>
          <MedicalServicesIcon sx={{ fontSize: 14, flexShrink: 0 }} />
          <Typography variant="body2" noWrap>{row.service || "—"}{row.doctor ? ` · ${row.doctor}` : ""}</Typography>
        </Stack>
      </Box>
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ flexShrink: 0 }}>
        {row.risk_band && row.status === "confirmed" && (
          <Chip size="small" variant="outlined" color={riskColor[row.risk_band] || "default"}
            label={`${row.risk_band}${row.risk_score != null ? " " + row.risk_score : ""}`}
            sx={{ height: 22, display: { xs: "none", md: "flex" } }} />)}
        <Chip size="small" color={sc} label={row.status.replace("_", " ")} sx={{ height: 22 }} />
        <Box sx={{ display: { xs: "none", sm: "block" } }}><ActionBtns row={row} busy={busy} onAct={onAct} stop /></Box>
      </Stack>
    </Box>
  );
}

export default function Appointments() {
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const status = params.get("status") || "";
  const qc = useQueryClient();
  const toast = useToast();
  const [sel, setSel] = useState<any | null>(null);
  const [search, setSearch] = useState("");
  const path = `/appointments?clinic=${clinic}${status ? `&status=${status}` : ""}`;
  const q = useApiQuery<any>(["appointments", clinic, status], path);
  const act = useMutation({
    mutationFn: (v: { id: number; status: string }) => apiPost(`/appointments/${v.id}/status`, { status: v.status }),
    onSuccess: (_d, v) => { toast.ok(`Marked ${v.status.replace("_", " ")}`); qc.invalidateQueries({ queryKey: ["appointments"] }); },
    onError: (e) => toast.err(e instanceof ApiError ? e.message : "Update failed"),
  });
  const setStatus = (s: string) => { const n = new URLSearchParams(params); if (s) n.set("status", s); else n.delete("status"); setParams(n); };
  const onAct = (id: number, s: string) => act.mutate({ id, status: s });

  const rows: any[] = q.data?.rows ?? [];
  // Agenda order: upcoming soonest-first, then past most-recent-first.
  const ordered = useMemo(() => {
    const sot = new Date().setHours(0, 0, 0, 0);
    const t = (r: any) => new Date(r.start_at).getTime();
    const up = rows.filter((r) => t(r) >= sot).sort((a, b) => t(a) - t(b));
    const past = rows.filter((r) => t(r) < sot).sort((a, b) => t(b) - t(a));
    return [...up, ...past];
  }, [rows]);
  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    if (!s) return ordered;
    return ordered.filter((r) =>
      `${r.patient_name || ""} ${r.wa_user} ${r.service || ""} ${r.doctor || ""}`.toLowerCase().includes(s));
  }, [ordered, search]);

  if (q.isLoading) return <><PageTitle title="Appointments" /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const now = Date.now();
  const upcoming = rows.filter((r) => r.status === "confirmed" && new Date(r.start_at).getTime() >= now).length;
  const completed = rows.filter((r) => r.status === "completed").length;
  const noShows = rows.filter((r) => r.status === "no_show").length;
  const atRisk = rows.filter((r) => r.risk_band === "high" && r.status === "confirmed" && new Date(r.start_at).getTime() >= now).length;

  return (
    <>
      <PageTitle title="Appointments" subtitle={`${rows.length} shown`} right={
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <ToggleButtonGroup size="small" exclusive value={status} onChange={(_e, v) => setStatus(v ?? "")}>
            <ToggleButton value="">All</ToggleButton>
            <ToggleButton value="confirmed">Confirmed</ToggleButton>
            <ToggleButton value="completed">Completed</ToggleButton>
            <ToggleButton value="cancelled">Cancelled</ToggleButton>
          </ToggleButtonGroup>
          <ClinicFilter meta={q.data} />
        </Stack>} />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><KpiCard label="Upcoming" value={upcoming} icon={<EventAvailableIcon fontSize="small" />} color="success" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Completed" value={completed} icon={<CheckCircleIcon fontSize="small" />} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="No-shows" value={noShows} icon={<EventBusyIcon fontSize="small" />} color="warning" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="At risk" value={atRisk} icon={<WarningIcon fontSize="small" />} color="error" /></Grid>
      </Grid>

      <Card sx={{ p: 0, overflow: "hidden" }}>
        <Box sx={{ px: 2, py: 1.5, borderBottom: (t) => `1px solid ${t.palette.divider}`,
          background: (t) => alpha(t.palette.primary.main, 0.04) }}>
          <TextField fullWidth size="small" placeholder="Search by patient, phone, service or doctor…"
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: (<InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>) }}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: 2.5 } }} />
        </Box>

        {filtered.length === 0 ? (
          <EmptyState text={search ? "No appointments match your search." : "No appointments."} />
        ) : (
          <Box sx={{ maxHeight: "calc(100vh - 380px)", minHeight: 260, overflow: "auto" }}>
            {filtered.map((r, i) => {
              const label = dayLabel(r.start_at);
              const showDay = i === 0 || dayLabel(filtered[i - 1].start_at) !== label;
              return (
                <Box key={r.id}>
                  {showDay && (
                    <Box sx={{ position: "sticky", top: 0, zIndex: 1, px: 2, py: 0.75,
                      bgcolor: (t) => alpha(t.palette.background.paper, 0.92), backdropFilter: "blur(6px)",
                      borderBottom: (t) => `1px solid ${t.palette.divider}` }}>
                      <Typography variant="caption" fontWeight={800} color="text.secondary"
                        sx={{ textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</Typography>
                    </Box>
                  )}
                  <ApptRow row={r} showClinic={showClinic} clinicName={tenant_names[r.tenant_id]}
                    busy={act.isPending} onAct={onAct} onOpen={() => setSel(r)} />
                </Box>
              );
            })}
          </Box>
        )}
      </Card>

      <DetailDialog open={!!sel} onClose={() => setSel(null)} title="Appointment"
        subtitle={sel ? `#${sel.id}` : ""}
        fields={sel ? [
          { label: "Patient", value: `${sel.patient_name || "—"} · +${sel.wa_user}` },
          { label: "Service", value: sel.service || "—" },
          { label: "Doctor", value: sel.doctor || "—" },
          { label: "When", value: fmtDate(sel.start_at) },
          { label: "Status", value: <Chip size="small" color={statusColor[sel.status] || "default"} label={sel.status} /> },
          { label: "Risk", value: sel.risk_band ? <Chip size="small" variant="outlined" color={riskColor[sel.risk_band] || "default"} label={`${sel.risk_band}${sel.risk_score != null ? " " + sel.risk_score : ""}`} /> : "—" },
          ...(sel.extra && Object.keys(sel.extra).length
            ? [{ label: "Details", value: Object.entries(sel.extra).map(([k, v]) => `${k}: ${v}`).join("\n"), full: true }] : []),
          ...(sel.notes ? [{ label: "Notes", value: sel.notes, full: true }] : []),
        ] : []}
        actions={sel && <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", width: "100%" }} alignItems="center">
          <Button onClick={() => nav(`/patients/${sel.wa_user}`)}>View patient</Button>
          <Box sx={{ flex: 1 }} />
          {sel.status !== "completed" && <Button onClick={() => { act.mutate({ id: sel.id, status: "completed" }); setSel(null); }}>Complete</Button>}
          {sel.status !== "no_show" && <Button color="warning" onClick={() => { act.mutate({ id: sel.id, status: "no_show" }); setSel(null); }}>No-show</Button>}
          {sel.status !== "cancelled" && <Button color="error" onClick={() => { act.mutate({ id: sel.id, status: "cancelled" }); setSel(null); }}>Cancel</Button>}
        </Stack>} />
    </>
  );
}
