import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box, Card, Stack, Typography, Chip, Button, ToggleButton, ToggleButtonGroup, Avatar,
  Grid, IconButton, Tooltip, TextField, InputAdornment, alpha, Dialog, DialogContent, DialogActions,
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
import PersonIcon from "@mui/icons-material/PersonOutline";
import ScheduleIcon from "@mui/icons-material/ScheduleOutlined";
import NotesIcon from "@mui/icons-material/NotesOutlined";
import { apiPost, ApiError } from "../api";
import { useT } from "../i18n";
import {
  useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, fmtTime, dayLabel, displayName,
  initials, TableSkeleton, QueryError, KpiCard, EmptyState, useToast, ConfirmDialog,
} from "../lib";

const statusColor: Record<string, any> = { confirmed: "success", completed: "info", cancelled: "default", no_show: "warning" };
const riskColor: Record<string, any> = { low: "success", medium: "warning", high: "error" };

// Translation function shape from useT().
type TFn = (key: string, vars?: Record<string, string | number>) => string;
// Visible status label, translated; falls back to the prettified enum value.
const stShow = (t: TFn, s: string) => {
  const m: Record<string, string> = {
    confirmed: t("appointments.confirmed"),
    completed: t("appointments.completed"),
    cancelled: t("appointments.cancelled"),
    no_show: t("appointments.missed"),
  };
  return m[s] || s.replace("_", " ");
};

function avatarHue(s: string) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }

// Per-action confirmation copy — these reach the patient on WhatsApp, so we double-check.
// Built from `t` so the label/verb are translated; color/notifies are logic, not display.
const actionMeta = (t: TFn): Record<string, { label: string; color: any; verb: string; notifies: boolean }> => ({
  completed: { label: t("appointments.markCompleted"), color: "success", verb: t("appointments.verbCompleted"), notifies: true },
  no_show: { label: t("appointments.markMissed"), color: "warning", verb: t("appointments.verbMissed"), notifies: false },
  cancelled: { label: t("appointments.cancelAppointment"), color: "error", verb: t("appointments.verbCancelled"), notifies: true },
});

function ActionBtns({ row, busy, onAct, t }: { row: any; busy: boolean; onAct: (id: number, status: string) => void; t: TFn }) {
  return (
    <Stack direction="row" spacing={0.5} onClick={(e) => e.stopPropagation()}>
      {row.status !== "completed" && (
        <Tooltip title={t("appointments.markCompleted")}><span><IconButton size="small" color="success" disabled={busy}
          onClick={() => onAct(row.id, "completed")}><DoneIcon fontSize="small" /></IconButton></span></Tooltip>)}
      {row.status !== "no_show" && (
        <Tooltip title={t("appointments.markMissed")}><span><IconButton size="small" color="warning" disabled={busy}
          onClick={() => onAct(row.id, "no_show")}><EventBusyIcon fontSize="small" /></IconButton></span></Tooltip>)}
      {row.status !== "cancelled" && (
        <Tooltip title={t("common.cancel")}><span><IconButton size="small" color="error" disabled={busy}
          onClick={() => onAct(row.id, "cancelled")}><CloseIcon fontSize="small" /></IconButton></span></Tooltip>)}
    </Stack>
  );
}

function ApptRow({ row, showClinic, clinicName, busy, onAct, onOpen, t }: {
  row: any; showClinic: boolean; clinicName?: string; busy: boolean;
  onAct: (id: number, status: string) => void; onOpen: () => void; t: TFn;
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
        <Typography fontWeight={800} sx={{ lineHeight: 1.1 }}>{fmtTime(row.start_at)}</Typography>
      </Box>
      <Avatar sx={{ width: 42, height: 42, fontWeight: 700, fontSize: 14, flexShrink: 0,
        background: `linear-gradient(135deg, hsl(${hue} 70% 55%), hsl(${(hue + 40) % 360} 70% 45%))`, color: "#fff" }}>
        {initials(row.patient_name, row.wa_user)}
      </Avatar>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography fontWeight={700} noWrap>
          {displayName(row.patient_name, row.wa_user)}
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
            label={`${t(`enums.risk.${row.risk_band}`)}${row.risk_score != null ? " " + row.risk_score : ""}`}
            sx={{ height: 22, display: { xs: "none", md: "flex" } }} />)}
        <Chip size="small" color={sc} label={stShow(t, row.status)} sx={{ height: 22 }} />
        <Box sx={{ display: { xs: "none", sm: "block" } }}><ActionBtns row={row} busy={busy} onAct={onAct} t={t} /></Box>
      </Stack>
    </Box>
  );
}

// Premium appointment detail with a gradient identity header and icon'd fields.
function ApptDetail({ appt, showClinic, clinicName, onClose, onAct, onView, t }: {
  appt: any; showClinic: boolean; clinicName?: string; onClose: () => void;
  onAct: (id: number, status: string) => void; onView: () => void; t: TFn;
}) {
  const hue = avatarHue(appt.wa_user || "");
  const sc = statusColor[appt.status] || "primary";
  const Row = ({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) => (
    <Stack direction="row" spacing={1.5} alignItems="flex-start">
      <Box sx={{ color: "text.secondary", mt: 0.25 }}>{icon}</Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={700}>{label}</Typography>
        <Box sx={{ fontSize: 14 }}>{children}</Box>
      </Box>
    </Stack>
  );
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm"
      PaperProps={{ sx: { borderRadius: 3, overflow: "hidden" } }}>
      <Box sx={{ position: "relative", p: 2.5, color: "#fff",
        background: "linear-gradient(120deg,#0f766e 0%,#14b8a6 45%,#6366f1 100%)" }}>
        <IconButton onClick={onClose} sx={{ position: "absolute", top: 8, right: 8, color: alpha("#fff", 0.9) }}><CloseIcon /></IconButton>
        <Stack direction="row" spacing={2} alignItems="center">
          <Avatar sx={{ width: 56, height: 56, fontWeight: 800, bgcolor: alpha("#fff", 0.2), color: "#fff",
            border: `2px solid ${alpha("#fff", 0.5)}` }}>{initials(appt.patient_name, appt.wa_user)}</Avatar>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h6" sx={{ color: "#fff" }} noWrap>{displayName(appt.patient_name, appt.wa_user)}</Typography>
            <Typography variant="body2" sx={{ color: alpha("#fff", 0.85) }} noWrap>
              +{appt.wa_user}{showClinic && clinicName ? ` · ${clinicName}` : ""}
            </Typography>
          </Box>
          <Box sx={{ flex: 1 }} />
          <Chip label={stShow(t, appt.status)} sx={{ bgcolor: alpha("#fff", 0.22), color: "#fff", fontWeight: 700 }} />
        </Stack>
      </Box>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Row icon={<ScheduleIcon fontSize="small" />} label={t("appointments.when")}><b>{fmtDate(appt.start_at)}</b></Row>
          <Row icon={<MedicalServicesIcon fontSize="small" />} label={t("appointments.service")}>{appt.service || "—"}</Row>
          <Row icon={<PersonIcon fontSize="small" />} label={t("appointments.doctor")}>{appt.doctor || "—"}</Row>
          {appt.risk_band && (
            <Row icon={<WarningIcon fontSize="small" />} label={t("appointments.missedRisk")}>
              <Chip size="small" variant="outlined" color={riskColor[appt.risk_band] || "default"}
                label={`${t(`enums.risk.${appt.risk_band}`)}${appt.risk_score != null ? " · " + appt.risk_score : ""}`} />
            </Row>)}
          {appt.extra && Object.keys(appt.extra).length > 0 && (
            <Row icon={<NotesIcon fontSize="small" />} label={t("appointments.details")}>
              <Box sx={{ whiteSpace: "pre-wrap" }}>{Object.entries(appt.extra).map(([k, v]) => `${k}: ${v}`).join("\n")}</Box>
            </Row>)}
          {appt.notes && <Row icon={<NotesIcon fontSize="small" />} label={t("appointments.notes")}><Box sx={{ whiteSpace: "pre-wrap" }}>{appt.notes}</Box></Row>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onView}>{t("common.viewPatient")}</Button>
        <Box sx={{ flex: 1 }} />
        {appt.status !== "completed" && <Button color="success" onClick={() => onAct(appt.id, "completed")}>{t("appointments.complete")}</Button>}
        {appt.status !== "no_show" && <Button color="warning" onClick={() => onAct(appt.id, "no_show")}>{t("appointments.missed")}</Button>}
        {appt.status !== "cancelled" && <Button color="error" onClick={() => onAct(appt.id, "cancelled")}>{t("common.cancel")}</Button>}
      </DialogActions>
    </Dialog>
  );
}

export default function Appointments() {
  const t = useT();
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const status = params.get("status") || "";
  const qc = useQueryClient();
  const toast = useToast();
  const [sel, setSel] = useState<any | null>(null);
  const [confirm, setConfirm] = useState<{ id: number; status: string; name: string } | null>(null);
  const [search, setSearch] = useState("");
  const path = `/appointments?clinic=${clinic}${status ? `&status=${status}` : ""}`;
  const q = useApiQuery<any>(["appointments", clinic, status], path);
  const act = useMutation({
    mutationFn: (v: { id: number; status: string }) => apiPost(`/appointments/${v.id}/status`, { status: v.status }),
    onSuccess: (_d, v) => { toast.ok(`Marked ${v.status.replace("_", " ")}`); qc.invalidateQueries({ queryKey: ["appointments"] }); },
    onError: (e) => toast.err(e instanceof ApiError ? e.message : "Update failed"),
  });
  const setStatus = (s: string) => { const n = new URLSearchParams(params); if (s) n.set("status", s); else n.delete("status"); setParams(n); };

  const rows: any[] = q.data?.rows ?? [];
  const byId = (id: number) => rows.find((r) => r.id === id);
  // Every status change is patient-visible, so route it through a confirm step.
  const requestAct = (id: number, s: string) => {
    setConfirm({ id, status: s, name: displayName(byId(id)?.patient_name, byId(id)?.wa_user) });
  };
  const doConfirm = () => { if (confirm) act.mutate({ id: confirm.id, status: confirm.status }); setConfirm(null); setSel(null); };

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

  if (q.isLoading) return <><PageTitle title={t("appointments.title")} /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const now = Date.now();
  const upcoming = rows.filter((r) => r.status === "confirmed" && new Date(r.start_at).getTime() >= now).length;
  const completed = rows.filter((r) => r.status === "completed").length;
  const noShows = rows.filter((r) => r.status === "no_show").length;
  const atRisk = rows.filter((r) => r.risk_band === "high" && r.status === "confirmed" && new Date(r.start_at).getTime() >= now).length;
  const cm = confirm ? actionMeta(t)[confirm.status] : null;

  return (
    <>
      <PageTitle title={t("appointments.title")} subtitle={t("appointments.subtitle", { n: rows.length })} right={
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <ToggleButtonGroup size="small" exclusive value={status} onChange={(_e, v) => setStatus(v ?? "")}>
            <ToggleButton value="">{t("appointments.filterAll")}</ToggleButton>
            <ToggleButton value="confirmed">{t("appointments.filterConfirmed")}</ToggleButton>
            <ToggleButton value="completed">{t("appointments.filterCompleted")}</ToggleButton>
            <ToggleButton value="cancelled">{t("appointments.filterCancelled")}</ToggleButton>
          </ToggleButtonGroup>
          <ClinicFilter meta={q.data} />
        </Stack>} />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><KpiCard label={t("appointments.kpiUpcoming")} value={upcoming} icon={<EventAvailableIcon fontSize="small" />} color="success" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("appointments.kpiCompleted")} value={completed} icon={<CheckCircleIcon fontSize="small" />} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("appointments.kpiMissed")} value={noShows} icon={<EventBusyIcon fontSize="small" />} color="warning" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("appointments.kpiAtRisk")} value={atRisk} icon={<WarningIcon fontSize="small" />} color="error" /></Grid>
      </Grid>

      <Card sx={{ p: 0, overflow: "hidden" }}>
        <Box sx={{ px: 2, py: 1.5, borderBottom: (t) => `1px solid ${t.palette.divider}`,
          background: (t) => alpha(t.palette.primary.main, 0.04) }}>
          <TextField fullWidth size="small" placeholder={t("appointments.searchPlaceholder")}
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: (<InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>) }}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: 2.5 } }} />
        </Box>

        {filtered.length === 0 ? (
          <EmptyState text={search ? t("appointments.emptyNoMatch") : t("appointments.emptyNone")} />
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
                    busy={act.isPending} onAct={requestAct} onOpen={() => setSel(r)} t={t} />
                </Box>
              );
            })}
          </Box>
        )}
      </Card>

      {sel && <ApptDetail appt={sel} showClinic={showClinic} clinicName={tenant_names[sel.tenant_id]}
        onClose={() => setSel(null)} onAct={requestAct} onView={() => nav(`/patients/${sel.wa_user}`)} t={t} />}

      <ConfirmDialog open={!!confirm}
        title={t("appointments.confirmTitle")}
        confirmLabel={cm?.label} confirmColor={cm?.color}
        message={confirm ? (
          <>{t("appointments.confirmMessage", { name: confirm.name, verb: cm?.verb ?? "" })}{cm?.notifies ? t("appointments.confirmNotify") : ""}</>
        ) : ""}
        onConfirm={doConfirm} onClose={() => setConfirm(null)} />
    </>
  );
}
