import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Box, Card, CardContent, Grid, Chip, Button, Typography, Stack, Avatar, IconButton, Tooltip,
  TextField, InputAdornment, alpha, Dialog, DialogContent, DialogActions,
} from "@mui/material";
import { BarChart } from "@mui/x-charts/BarChart";
import EventBusyIcon from "@mui/icons-material/EventBusyOutlined";
import SearchIcon from "@mui/icons-material/SearchOutlined";
import SendIcon from "@mui/icons-material/SendOutlined";
import ReplayIcon from "@mui/icons-material/ReplayRounded";
import CheckIcon from "@mui/icons-material/CheckRounded";
import BlockIcon from "@mui/icons-material/BlockOutlined";
import SpaIcon from "@mui/icons-material/SpaOutlined";
import OutboxIcon from "@mui/icons-material/OutboxOutlined";
import AutorenewIcon from "@mui/icons-material/AutorenewOutlined";
import CloseIcon from "@mui/icons-material/CloseRounded";
import MedicalServicesIcon from "@mui/icons-material/MedicalServicesOutlined";
import ScheduleIcon from "@mui/icons-material/ScheduleOutlined";
import WarningIcon from "@mui/icons-material/WarningAmberOutlined";
import { apiPost, ApiError } from "../api";
import {
  useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, fmtTime, dayLabel, displayName,
  initials, TableSkeleton, QueryError, KpiCard, EmptyState, useToast,
} from "../lib";

const riskColor: Record<string, any> = { low: "success", medium: "warning", high: "error" };
const ACTIVE_STAGES = ["detected", "notified", "followed_up"];

function avatarHue(s: string) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }
function stageLabel(s?: string) { return (s || "").replace(/_/g, " "); }

function ActionBtns({ row, busy, onAct }: { row: any; busy: boolean; onAct: (id: number, action: string) => void }) {
  return (
    <Stack direction="row" spacing={0.5} onClick={(e) => e.stopPropagation()}>
      {row.stage === "detected" && (
        <Tooltip title="Send recovery message"><span><IconButton size="small" color="primary" disabled={busy}
          onClick={() => onAct(row.id, "send")}><SendIcon fontSize="small" /></IconButton></span></Tooltip>)}
      {["notified", "followed_up"].includes(row.stage) && (
        <Tooltip title="Resend"><span><IconButton size="small" color="primary" disabled={busy}
          onClick={() => onAct(row.id, "resend")}><ReplayIcon fontSize="small" /></IconButton></span></Tooltip>)}
      {!["resolved", "inactive"].includes(row.stage) && <>
        <Tooltip title="Mark resolved"><span><IconButton size="small" color="success" disabled={busy}
          onClick={() => onAct(row.id, "resolve")}><CheckIcon fontSize="small" /></IconButton></span></Tooltip>
        <Tooltip title="Mark inactive"><span><IconButton size="small" color="error" disabled={busy}
          onClick={() => onAct(row.id, "inactive")}><BlockIcon fontSize="small" /></IconButton></span></Tooltip>
      </>}
    </Stack>
  );
}

function MissedRow({ row, showClinic, clinicName, reasonLabels, busy, onAct, onOpen }: {
  row: any; showClinic: boolean; clinicName?: string; reasonLabels: Record<string, string>;
  busy: boolean; onAct: (id: number, action: string) => void; onOpen: () => void;
}) {
  const hue = avatarHue(row.wa_user || "");
  const accent = riskColor[row.risk_band] || "warning";
  return (
    <Box onClick={onOpen} sx={{
      display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.5, cursor: "pointer", position: "relative",
      borderBottom: (t) => `1px solid ${t.palette.divider}`, transition: "background .15s ease",
      "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
      "&::before": { content: '""', position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
        bgcolor: (t) => (t.palette as any)[accent]?.main || t.palette.warning.main, opacity: 0.85 },
    }}>
      <Box sx={{ width: 64, flexShrink: 0, textAlign: "center" }}>
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
          <Typography variant="body2" noWrap>
            {row.service || "—"}{row.doctor ? ` · ${row.doctor}` : ""}
            {row.reason ? ` · ${reasonLabels[row.reason] || row.reason}` : ""}
          </Typography>
        </Stack>
      </Box>
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ flexShrink: 0 }}>
        {row.risk_band && <Chip size="small" variant="outlined" color={riskColor[row.risk_band] || "default"}
          label={row.risk_band} sx={{ height: 22, display: { xs: "none", md: "flex" } }} />}
        <Chip size="small" variant="outlined" label={stageLabel(row.stage)} sx={{ height: 22 }} />
        <Box sx={{ display: { xs: "none", sm: "block" } }}><ActionBtns row={row} busy={busy} onAct={onAct} /></Box>
      </Stack>
    </Box>
  );
}

function MissedDetail({ row, showClinic, clinicName, reasonLabels, onClose, onAct, onView }: {
  row: any; showClinic: boolean; clinicName?: string; reasonLabels: Record<string, string>;
  onClose: () => void; onAct: (id: number, action: string) => void; onView: () => void;
}) {
  const hue = avatarHue(row.wa_user || "");
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
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" PaperProps={{ sx: { borderRadius: 3, overflow: "hidden" } }}>
      <Box sx={{ position: "relative", p: 2.5, color: "#fff",
        background: "linear-gradient(120deg,#b45309 0%,#f59e0b 55%,#6366f1 100%)" }}>
        <IconButton onClick={onClose} sx={{ position: "absolute", top: 8, right: 8, color: alpha("#fff", 0.9) }}><CloseIcon /></IconButton>
        <Stack direction="row" spacing={2} alignItems="center">
          <Avatar sx={{ width: 56, height: 56, fontWeight: 800, bgcolor: alpha("#fff", 0.2), color: "#fff",
            border: `2px solid ${alpha("#fff", 0.5)}` }}>{initials(row.patient_name, row.wa_user)}</Avatar>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h6" sx={{ color: "#fff" }} noWrap>{displayName(row.patient_name, row.wa_user)}</Typography>
            <Typography variant="body2" sx={{ color: alpha("#fff", 0.85) }} noWrap>
              +{row.wa_user}{showClinic && clinicName ? ` · ${clinicName}` : ""}
            </Typography>
          </Box>
          <Box sx={{ flex: 1 }} />
          <Chip label={stageLabel(row.stage)} sx={{ bgcolor: alpha("#fff", 0.22), color: "#fff", fontWeight: 700 }} />
        </Stack>
      </Box>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Row icon={<ScheduleIcon fontSize="small" />} label="Missed appointment">
            <b>{fmtDate(row.start_at)}</b>
          </Row>
          <Row icon={<MedicalServicesIcon fontSize="small" />} label="Service">{row.service || "—"}{row.doctor ? ` · ${row.doctor}` : ""}</Row>
          {row.risk_band && (
            <Row icon={<WarningIcon fontSize="small" />} label="Missed-visit risk">
              <Chip size="small" variant="outlined" color={riskColor[row.risk_band] || "default"} label={row.risk_band} />
            </Row>)}
          <Row icon={<SpaIcon fontSize="small" />} label="Reason">{row.reason ? (reasonLabels[row.reason] || row.reason) : "—"}</Row>
          <Row icon={<AutorenewIcon fontSize="small" />} label="Outcome">{row.outcome || "—"}</Row>
          <Row icon={<OutboxIcon fontSize="small" />} label="Detected">{fmtDate(row.created_at)}</Row>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onView}>View patient</Button>
        <Box sx={{ flex: 1 }} />
        {row.stage === "detected" && <Button variant="contained" onClick={() => onAct(row.id, "send")}>Send</Button>}
        {["notified", "followed_up"].includes(row.stage) && <Button onClick={() => onAct(row.id, "resend")}>Resend</Button>}
        {!["resolved", "inactive"].includes(row.stage) && <>
          <Button color="success" onClick={() => onAct(row.id, "resolve")}>Resolve</Button>
          <Button color="error" onClick={() => onAct(row.id, "inactive")}>Inactive</Button>
        </>}
      </DialogActions>
    </Dialog>
  );
}

export default function NoShows() {
  const nav = useNavigate();
  const [clinic] = useClinic();
  const qc = useQueryClient();
  const toast = useToast();
  const [sel, setSel] = useState<any | null>(null);
  const [search, setSearch] = useState("");
  const q = useApiQuery<any>(["no-shows", clinic], `/no-shows?clinic=${clinic}`);
  const act = useMutation({
    mutationFn: (v: { id: number; action: string }) => apiPost(`/no-shows/${v.id}/action`, { action: v.action }),
    onSuccess: (_d, v) => { toast.ok(`Done: ${v.action}`); qc.invalidateQueries({ queryKey: ["no-shows"] }); },
    onError: (e) => toast.err(e instanceof ApiError ? e.message : "Action failed"),
  });
  const onAct = (id: number, action: string) => { act.mutate({ id, action }); setSel(null); };

  const rows: any[] = q.data?.rows ?? [];
  const reasonLabels: Record<string, string> = q.data?.reason_labels ?? {};
  const ordered = useMemo(() => {
    const t = (r: any) => new Date(r.start_at).getTime();
    return [...rows].sort((a, b) => t(b) - t(a)); // most recent misses first
  }, [rows]);
  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    if (!s) return ordered;
    return ordered.filter((r) =>
      `${r.patient_name || ""} ${r.wa_user} ${r.service || ""} ${r.doctor || ""} ${reasonLabels[r.reason] || r.reason || ""}`.toLowerCase().includes(s));
  }, [ordered, search, reasonLabels]);

  if (q.isLoading) return <><PageTitle title="Missed Visits" /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { month_count, reasons = [], risk = {}, is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const needsOutreach = rows.filter((r) => r.stage === "detected").length;
  const inRecovery = rows.filter((r) => ["notified", "followed_up"].includes(r.stage)).length;
  const recovered = rows.filter((r) => r.stage === "resolved").length;
  const reasonData = reasons.map((r: any) => ({ label: reasonLabels[r.reason] || r.reason || "—", n: r.n }));

  return (
    <>
      <PageTitle title="Missed Visits" subtitle="Detection & recovery outreach" right={<ClinicFilter meta={q.data} />} />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><KpiCard label="Missed this month" value={month_count ?? 0} icon={<EventBusyIcon fontSize="small" />} color="error" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Needs outreach" value={needsOutreach} icon={<SendIcon fontSize="small" />} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="In recovery" value={inRecovery} icon={<AutorenewIcon fontSize="small" />} color="warning" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Recovered" value={recovered} icon={<CheckIcon fontSize="small" />} color="success" /></Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={5}>
          <Card sx={{ height: "100%" }}><CardContent>
            <Typography variant="caption" color="text.secondary" fontWeight={700}>Upcoming missed-visit risk</Typography>
            <Stack direction="row" spacing={3} sx={{ mt: 1.5 }}>
              {[["Low", risk.low, "success.main"], ["Medium", risk.medium, "warning.main"], ["High", risk.high, "error.main"]].map(([l, v, c]: any) => (
                <Box key={l}><Typography variant="h5" sx={{ color: c }}>{v ?? 0}</Typography><Typography variant="caption" color="text.secondary">{l}</Typography></Box>
              ))}
            </Stack>
          </CardContent></Card>
        </Grid>
        <Grid item xs={12} md={7}>
          <Card sx={{ height: "100%" }}><CardContent sx={{ pb: 0 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={700}>Why patients missed</Typography>
            {reasonData.length ? (
              <BarChart height={150} layout="horizontal"
                yAxis={[{ scaleType: "band", data: reasonData.map((r: any) => r.label) }]}
                series={[{ data: reasonData.map((r: any) => r.n), color: "#f59e0b" }]}
                margin={{ left: 90, right: 10, top: 10, bottom: 20 }} />
            ) : <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>No reasons recorded yet.</Typography>}
          </CardContent></Card>
        </Grid>
      </Grid>

      <Card sx={{ p: 0, overflow: "hidden" }}>
        <Box sx={{ px: 2, py: 1.5, borderBottom: (t) => `1px solid ${t.palette.divider}`,
          background: (t) => alpha(t.palette.primary.main, 0.04) }}>
          <TextField fullWidth size="small" placeholder="Search by patient, phone, service, doctor or reason…"
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: (<InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>) }}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: 2.5 } }} />
        </Box>
        {filtered.length === 0 ? (
          <EmptyState text={search ? "No missed visits match your search." : "No missed visits — nice."} />
        ) : (
          <Box sx={{ maxHeight: "calc(100vh - 470px)", minHeight: 240, overflow: "auto" }}>
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
                        sx={{ textTransform: "uppercase", letterSpacing: 0.5 }}>Missed · {label}</Typography>
                    </Box>
                  )}
                  <MissedRow row={r} showClinic={showClinic} clinicName={tenant_names[r.tenant_id]}
                    reasonLabels={reasonLabels} busy={act.isPending} onAct={onAct} onOpen={() => setSel(r)} />
                </Box>
              );
            })}
          </Box>
        )}
      </Card>

      {sel && <MissedDetail row={sel} showClinic={showClinic} clinicName={tenant_names[sel.tenant_id]}
        reasonLabels={reasonLabels} onClose={() => setSel(null)} onAct={onAct}
        onView={() => nav(`/patients/${sel.wa_user}`)} />}
    </>
  );
}
