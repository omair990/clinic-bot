import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box, Card, CardContent, Grid, Chip, Button, Typography, Stack, IconButton, Tooltip,
  ToggleButton, ToggleButtonGroup, TextField, InputAdornment, alpha,
  Dialog, DialogContent, DialogActions,
} from "@mui/material";
import { useSearchParams } from "react-router-dom";
import ReportProblemIcon from "@mui/icons-material/ReportProblemOutlined";
import ErrorIcon from "@mui/icons-material/ErrorOutlineRounded";
import WarningIcon from "@mui/icons-material/WarningAmberRounded";
import InfoIcon from "@mui/icons-material/InfoOutlined";
import CheckCircleIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import DoneIcon from "@mui/icons-material/DoneRounded";
import SearchIcon from "@mui/icons-material/SearchOutlined";
import CloseIcon from "@mui/icons-material/CloseRounded";
import ScheduleIcon from "@mui/icons-material/ScheduleOutlined";
import PersonIcon from "@mui/icons-material/PersonOutline";
import NotesIcon from "@mui/icons-material/NotesOutlined";
import { apiPost, ApiError } from "../api";
import { useT } from "../i18n";
import {
  useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, dayLabel,
  TableSkeleton, QueryError, KpiCard, EmptyState, useToast,
} from "../lib";

// Per-level visual language — color, icon, and gradient for the detail header.
const LEVEL: Record<string, { color: "error" | "warning" | "info"; icon: React.ReactNode; grad: string }> = {
  error: { color: "error", icon: <ErrorIcon fontSize="small" />, grad: "linear-gradient(120deg,#b91c1c 0%,#ef4444 55%,#6366f1 100%)" },
  warning: { color: "warning", icon: <WarningIcon fontSize="small" />, grad: "linear-gradient(120deg,#b45309 0%,#f59e0b 55%,#6366f1 100%)" },
  info: { color: "info", icon: <InfoIcon fontSize="small" />, grad: "linear-gradient(120deg,#0369a1 0%,#38bdf8 55%,#6366f1 100%)" },
};
const lvl = (l?: string) => LEVEL[l || "info"] || LEVEL.info;

// Stable color per category for chips + the breakdown bar.
const CAT_COLOR: Record<string, string> = {
  whatsapp: "#22c55e", llm: "#6366f1", tool: "#f59e0b", agent: "#14b8a6",
  transcription: "#a78bfa", quota: "#ef4444", escalation: "#ec4899",
};
const catColor = (c?: string) => CAT_COLOR[c || ""] || "#64748b";

// Segmented bar of issue volume by category, with a wrapping legend.
function CategoryBar({ counts }: { counts: { cat: string; n: number }[] }) {
  const total = counts.reduce((s, x) => s + x.n, 0);
  return (
    <Box>
      <Box sx={{ display: "flex", gap: 0.5, height: 12, borderRadius: 6, overflow: "hidden",
        bgcolor: (t) => alpha(t.palette.text.primary, 0.06) }}>
        {total > 0 && counts.map((c) => (
          <Box key={c.cat} sx={{ flex: c.n, bgcolor: catColor(c.cat), transition: "flex .4s ease" }} />
        ))}
      </Box>
      <Stack direction="row" flexWrap="wrap" useFlexGap spacing={1.5} sx={{ mt: 1.75 }}>
        {counts.map((c) => (
          <Stack key={c.cat} direction="row" alignItems="center" spacing={0.75}>
            <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: catColor(c.cat) }} />
            <Typography variant="body2" sx={{ textTransform: "capitalize" }}>{c.cat}</Typography>
            <Typography variant="body2" fontWeight={800}>{c.n}</Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}

function IssueRow({ row, showClinic, clinicName, busy, onResolve, onOpen }: {
  row: any; showClinic: boolean; clinicName?: string; busy: boolean;
  onResolve: (id: number) => void; onOpen: () => void;
}) {
  const t = useT();
  const meta = lvl(row.level);
  return (
    <Box onClick={onOpen} sx={{
      display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.5, cursor: "pointer", position: "relative",
      borderBottom: (t) => `1px solid ${t.palette.divider}`, transition: "background .15s ease",
      opacity: row.resolved ? 0.62 : 1,
      "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
      "&::before": { content: '""', position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
        bgcolor: (t) => (t.palette as any)[meta.color].main, opacity: row.resolved ? 0.4 : 0.9 },
    }}>
      <Box sx={{ width: 34, height: 34, borderRadius: 2, flexShrink: 0, display: "grid", placeItems: "center",
        color: (t) => (t.palette as any)[meta.color].main, bgcolor: (t) => alpha((t.palette as any)[meta.color].main, 0.14) }}>
        {meta.icon}
      </Box>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography fontWeight={700} noWrap>{row.message}</Typography>
        <Stack direction="row" alignItems="center" spacing={0.75} sx={{ color: "text.secondary", minWidth: 0 }}>
          {row.detail && <Typography variant="body2" noWrap>{row.detail}</Typography>}
          {!row.detail && row.wa_user && <Typography variant="body2" noWrap>+{row.wa_user}</Typography>}
        </Stack>
      </Box>
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ flexShrink: 0 }}>
        {showClinic && clinicName && (
          <Chip size="small" variant="outlined" label={clinicName} sx={{ height: 22, display: { xs: "none", lg: "flex" } }} />)}
        <Chip size="small" label={row.category} sx={{ height: 22, fontWeight: 600, textTransform: "capitalize",
          color: catColor(row.category), bgcolor: (t) => alpha(catColor(row.category), 0.14),
          display: { xs: "none", sm: "flex" } }} />
        <Typography variant="caption" color="text.secondary" sx={{ display: { xs: "none", md: "block" }, whiteSpace: "nowrap" }}>
          {fmtDate(row.created_at)}
        </Typography>
        {row.resolved ? (
          <Chip size="small" color="success" variant="outlined" icon={<DoneIcon sx={{ fontSize: 15 }} />} label={t("issues.chipResolved")} sx={{ height: 24 }} />
        ) : (
          <Tooltip title={t("issues.tipMarkResolved")}><span>
            <IconButton size="small" color="success" disabled={busy}
              onClick={(e) => { e.stopPropagation(); onResolve(row.id); }}><CheckCircleIcon fontSize="small" /></IconButton>
          </span></Tooltip>
        )}
      </Stack>
    </Box>
  );
}

function IssueDetail({ row, showClinic, clinicName, busy, onClose, onResolve }: {
  row: any; showClinic: boolean; clinicName?: string; busy: boolean;
  onClose: () => void; onResolve: () => void;
}) {
  const t = useT();
  const meta = lvl(row.level);
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
      <Box sx={{ position: "relative", p: 2.5, color: "#fff", background: meta.grad }}>
        <IconButton onClick={onClose} sx={{ position: "absolute", top: 8, right: 8, color: alpha("#fff", 0.9) }}><CloseIcon /></IconButton>
        <Stack direction="row" spacing={2} alignItems="center">
          <Box sx={{ width: 52, height: 52, borderRadius: 2.5, display: "grid", placeItems: "center", flexShrink: 0,
            bgcolor: alpha("#fff", 0.2), border: `2px solid ${alpha("#fff", 0.5)}` }}>{meta.icon}</Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="overline" sx={{ color: alpha("#fff", 0.85), letterSpacing: 1 }}>{row.level} · {row.category}</Typography>
            <Typography variant="h6" sx={{ color: "#fff", lineHeight: 1.25 }}>{row.message}</Typography>
          </Box>
          <Box sx={{ flex: 1 }} />
          <Chip label={row.resolved ? t("issues.chipResolved") : t("issues.chipOpen")}
            sx={{ bgcolor: alpha("#fff", 0.22), color: "#fff", fontWeight: 700, flexShrink: 0 }} />
        </Stack>
      </Box>
      <DialogContent dividers>
        <Stack spacing={2}>
          {showClinic && <Row icon={<PersonIcon fontSize="small" />} label={t("issues.detailClinic")}>{clinicName || "—"}</Row>}
          <Row icon={<ScheduleIcon fontSize="small" />} label={t("issues.detailWhen")}><b>{fmtDate(row.created_at)}</b></Row>
          {row.wa_user && <Row icon={<PersonIcon fontSize="small" />} label={t("issues.detailPatient")}>+{row.wa_user}</Row>}
          <Row icon={<NotesIcon fontSize="small" />} label={t("issues.detailDetail")}>
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}
              color={row.detail ? "text.primary" : "text.disabled"}>{row.detail || t("issues.noDetail")}</Typography>
          </Row>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} color="inherit">{t("common.close")}</Button>
        <Box sx={{ flex: 1 }} />
        {!row.resolved && <Button variant="contained" color="success" disabled={busy} onClick={onResolve}>{t("issues.markResolved")}</Button>}
      </DialogActions>
    </Dialog>
  );
}

const LEVEL_FILTERS = [
  { value: "", labelKey: "issues.filterAll" },
  { value: "error", labelKey: "issues.filterErrors" },
  { value: "warning", labelKey: "issues.filterWarnings" },
  { value: "info", labelKey: "issues.filterInfo" },
];

export default function Issues() {
  const t = useT();
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const show = params.get("show") || "open";
  const qc = useQueryClient();
  const toast = useToast();
  const [sel, setSel] = useState<any | null>(null);
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("");
  const q = useApiQuery<any>(["logs", clinic, show], `/logs?clinic=${clinic}&show=${show}`);
  const resolve = useMutation({
    mutationFn: (id: number) => apiPost(`/logs/${id}/resolve`),
    onSuccess: () => { toast.ok(t("issues.resolved")); qc.invalidateQueries({ queryKey: ["logs"] }); },
    onError: (e) => toast.err(e instanceof ApiError ? e.message : t("issues.failed")),
  });
  const setShow = (s: string) => { const n = new URLSearchParams(params); n.set("show", s); setParams(n); };

  const events: any[] = q.data?.events ?? [];
  const tenant_names: Record<string, string> = q.data?.tenant_names ?? {};
  const catCounts = useMemo(() => {
    const m = new Map<string, number>();
    events.forEach((e) => m.set(e.category, (m.get(e.category) || 0) + 1));
    return [...m.entries()].map(([cat, n]) => ({ cat, n })).sort((a, b) => b.n - a.n);
  }, [events]);
  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return events.filter((e) => {
      if (level && e.level !== level) return false;
      if (!s) return true;
      return `${e.message || ""} ${e.detail || ""} ${e.category || ""} ${e.wa_user || ""} ${tenant_names[e.tenant_id] || ""}`.toLowerCase().includes(s);
    });
  }, [events, search, level, tenant_names]);

  if (q.isLoading) return <><PageTitle title={t("issues.title")} /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { open_count, is_super, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const errors = events.filter((e) => e.level === "error").length;
  const warnings = events.filter((e) => e.level === "warning").length;
  const infos = events.filter((e) => e.level === "info").length;

  const doResolve = (id: number) => resolve.mutate(id);

  return (
    <>
      <PageTitle title={t("issues.title")} subtitle={t("issues.subtitle")} right={
        <Stack direction="row" spacing={1.5} alignItems="center">
          <ClinicFilter meta={q.data} />
          <ToggleButtonGroup size="small" exclusive value={show} onChange={(_e, v) => v && setShow(v)}>
            <ToggleButton value="open">{t("issues.showOpen", { n: open_count })}</ToggleButton>
            <ToggleButton value="resolved">{t("issues.showResolved")}</ToggleButton>
            <ToggleButton value="all">{t("issues.showAll")}</ToggleButton>
          </ToggleButtonGroup>
        </Stack>} />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><KpiCard label={t("issues.kpiOpen")} value={open_count ?? 0} icon={<ReportProblemIcon fontSize="small" />} color="error" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("issues.kpiErrors")} value={errors} icon={<ErrorIcon fontSize="small" />} color="error" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("issues.kpiWarnings")} value={warnings} icon={<WarningIcon fontSize="small" />} color="warning" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("issues.kpiInfo")} value={infos} icon={<InfoIcon fontSize="small" />} color="info" /></Grid>
      </Grid>

      {catCounts.length > 0 && (
        <Card sx={{ mb: 2 }}><CardContent>
          <Typography variant="caption" color="text.secondary" fontWeight={700}>{t("issues.byCategory")}</Typography>
          <Box sx={{ mt: 1.5 }}><CategoryBar counts={catCounts} /></Box>
        </CardContent></Card>
      )}

      <Card sx={{ p: 0, overflow: "hidden" }}>
        <Box sx={{ px: 2, py: 1.5, borderBottom: (t) => `1px solid ${t.palette.divider}`,
          background: (t) => alpha(t.palette.primary.main, 0.04) }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ md: "center" }}>
            <TextField fullWidth size="small" placeholder={t("issues.searchPlaceholder")}
              value={search} onChange={(e) => setSearch(e.target.value)}
              InputProps={{ startAdornment: (<InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>) }}
              sx={{ "& .MuiOutlinedInput-root": { borderRadius: 2.5 } }} />
            <ToggleButtonGroup size="small" exclusive value={level} onChange={(_e, v) => setLevel(v ?? "")} sx={{ flexShrink: 0 }}>
              {LEVEL_FILTERS.map((f) => <ToggleButton key={f.value} value={f.value}>{t(f.labelKey)}</ToggleButton>)}
            </ToggleButtonGroup>
          </Stack>
        </Box>

        {filtered.length === 0 ? (
          (search || level) ? (
            <EmptyState text={t("issues.emptyFiltered")} />
          ) : (
            <Box sx={{ textAlign: "center", py: 8, color: "text.secondary" }}>
              <CheckCircleIcon sx={{ fontSize: 48, color: "success.main", opacity: 0.85 }} />
              <Typography variant="h6" sx={{ mt: 1 }}>{t("issues.allClear")}</Typography>
              <Typography variant="body2">{show === "open" ? t("issues.emptyNoneOpen") : t("issues.emptyNone")}</Typography>
            </Box>
          )
        ) : (
          <Box sx={{ maxHeight: "calc(100vh - 420px)", minHeight: 240, overflow: "auto" }}>
            {filtered.map((r, i) => {
              const label = dayLabel(r.created_at);
              const showDay = i === 0 || dayLabel(filtered[i - 1].created_at) !== label;
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
                  <IssueRow row={r} showClinic={showClinic} clinicName={tenant_names[r.tenant_id]}
                    busy={resolve.isPending} onResolve={doResolve} onOpen={() => setSel(r)} />
                </Box>
              );
            })}
          </Box>
        )}
      </Card>

      {sel && <IssueDetail row={sel} showClinic={showClinic} clinicName={tenant_names[sel.tenant_id]}
        busy={resolve.isPending} onClose={() => setSel(null)}
        onResolve={() => { resolve.mutate(sel.id); setSel(null); }} />}
    </>
  );
}
