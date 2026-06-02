import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Card, CardContent, Grid, Chip, Rating, Typography, Button, Stack, Avatar, Divider,
  TextField, InputAdornment, ToggleButton, ToggleButtonGroup, IconButton, alpha,
  Dialog, DialogContent, DialogActions,
} from "@mui/material";
import StarIcon from "@mui/icons-material/StarRounded";
import SearchIcon from "@mui/icons-material/SearchOutlined";
import CheckIcon from "@mui/icons-material/TaskAltOutlined";
import PercentIcon from "@mui/icons-material/PercentOutlined";
import HourglassIcon from "@mui/icons-material/HourglassEmptyRounded";
import QuoteIcon from "@mui/icons-material/FormatQuoteRounded";
import CloseIcon from "@mui/icons-material/CloseRounded";
import MedicalServicesIcon from "@mui/icons-material/MedicalServicesOutlined";
import ScheduleIcon from "@mui/icons-material/ScheduleOutlined";
import {
  useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, displayName, initials,
  TableSkeleton, QueryError, KpiCard, EmptyState,
} from "../lib";
import { useT } from "../i18n";

const AMBER = "#f59e0b";
function avatarHue(s: string) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }
function ratingColor(r?: number): "success" | "warning" | "error" | "default" {
  if (!r) return "default";
  if (r >= 4) return "success";
  if (r === 3) return "warning";
  return "error";
}

// Star-by-star breakdown bar (5★ → 1★) computed from the received reviews.
function Distribution({ dist, total }: { dist: Record<number, number>; total: number }) {
  return (
    <Stack spacing={1.1}>
      {[5, 4, 3, 2, 1].map((star) => {
        const n = dist[star] || 0;
        const pct = total ? (n / total) * 100 : 0;
        return (
          <Stack key={star} direction="row" alignItems="center" spacing={1.25}>
            <Stack direction="row" alignItems="center" spacing={0.25} sx={{ width: 34, flexShrink: 0 }}>
              <Typography variant="body2" fontWeight={700}>{star}</Typography>
              <StarIcon sx={{ fontSize: 14, color: AMBER }} />
            </Stack>
            <Box sx={{ flex: 1, height: 9, borderRadius: 5, overflow: "hidden",
              bgcolor: (t) => alpha(t.palette.text.primary, 0.06) }}>
              <Box sx={{ width: `${pct}%`, height: "100%", borderRadius: 5, bgcolor: AMBER,
                transition: "width .4s ease" }} />
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ width: 26, textAlign: "right" }}>{n}</Typography>
          </Stack>
        );
      })}
    </Stack>
  );
}

function ReviewCard({ row, showClinic, clinicName, onOpen }: {
  row: any; showClinic: boolean; clinicName?: string; onOpen: () => void;
}) {
  const t = useT();
  const hue = avatarHue(row.wa_user || "");
  const awaiting = row.stage !== "done" || !row.rating;
  const accent = ratingColor(row.rating);
  return (
    <Card onClick={onOpen} sx={{
      height: "100%", display: "flex", flexDirection: "column", cursor: "pointer", position: "relative",
      overflow: "hidden", transition: "transform .18s ease, box-shadow .18s ease",
      opacity: awaiting ? 0.92 : 1,
      "&:hover": { transform: "translateY(-3px)", boxShadow: (t) => t.shadows[8] },
      "&::before": { content: '""', position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
        bgcolor: (t) => awaiting ? t.palette.divider : ((t.palette as any)[accent]?.main || AMBER), opacity: 0.9 },
    }}>
      <CardContent sx={{ flex: 1, display: "flex", flexDirection: "column", gap: 1.25 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Avatar sx={{ width: 40, height: 40, fontWeight: 700, fontSize: 14, flexShrink: 0,
            background: `linear-gradient(135deg, hsl(${hue} 70% 55%), hsl(${(hue + 40) % 360} 70% 45%))`, color: "#fff" }}>
            {initials(row.patient_name, row.wa_user)}
          </Avatar>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography fontWeight={700} noWrap>{displayName(row.patient_name, row.wa_user)}</Typography>
            <Stack direction="row" alignItems="center" spacing={0.6} sx={{ color: "text.secondary", minWidth: 0 }}>
              <MedicalServicesIcon sx={{ fontSize: 14, flexShrink: 0 }} />
              <Typography variant="caption" noWrap>
                {row.service || "—"}{row.doctor ? ` · ${row.doctor}` : ""}
                {showClinic && clinicName ? ` · ${clinicName}` : ""}
              </Typography>
            </Stack>
          </Box>
        </Stack>

        {awaiting ? (
          <Chip size="small" variant="outlined" color="warning" icon={<HourglassIcon sx={{ fontSize: 15 }} />}
            label={t("reviews.awaitingResponse")} sx={{ alignSelf: "flex-start", height: 24 }} />
        ) : (
          <Rating value={row.rating} readOnly size="small" />
        )}

        <Box sx={{ flex: 1, position: "relative", pl: 2.5 }}>
          <QuoteIcon sx={{ position: "absolute", left: -2, top: -4, fontSize: 22,
            color: (t) => alpha(t.palette.text.primary, 0.18) }} />
          <Typography variant="body2" color={row.comment ? "text.primary" : "text.disabled"}
            sx={{ fontStyle: row.comment ? "italic" : "normal",
              display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
            {row.comment || (awaiting ? t("reviews.noResponseYet") : t("reviews.noCommentLeft"))}
          </Typography>
        </Box>

        <Divider sx={{ mt: "auto" }} />
        <Typography variant="caption" color="text.secondary">{fmtDate(row.responded_at || row.created_at)}</Typography>
      </CardContent>
    </Card>
  );
}

function ReviewDetail({ row, showClinic, clinicName, onClose, onView }: {
  row: any; showClinic: boolean; clinicName?: string; onClose: () => void; onView: () => void;
}) {
  const t = useT();
  const awaiting = row.stage !== "done" || !row.rating;
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
          {!awaiting && <Rating value={row.rating} readOnly sx={{ "& .MuiRating-iconEmpty": { color: alpha("#fff", 0.45) } }} />}
        </Stack>
      </Box>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Row icon={<MedicalServicesIcon fontSize="small" />} label={t("reviews.visit")}>{row.service || "—"}{row.doctor ? ` · ${row.doctor}` : ""}</Row>
          <Row icon={<StarIcon fontSize="small" />} label={t("reviews.rating")}>
            {awaiting ? <Chip size="small" variant="outlined" color="warning" label={t("reviews.awaitingResponse")} />
              : <Rating value={row.rating} readOnly size="small" />}
          </Row>
          <Row icon={<QuoteIcon fontSize="small" />} label={t("reviews.comment")}>
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontStyle: row.comment ? "italic" : "normal" }}
              color={row.comment ? "text.primary" : "text.disabled"}>{row.comment || "—"}</Typography>
          </Row>
          <Row icon={<ScheduleIcon fontSize="small" />} label={awaiting ? t("reviews.requested") : t("reviews.responded")}>
            {fmtDate(row.responded_at || row.created_at)}
          </Row>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} color="inherit">{t("common.close")}</Button>
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" onClick={onView}>{t("common.viewPatient")}</Button>
      </DialogActions>
    </Dialog>
  );
}

const FILTERS = [
  { value: "", key: "filterAll" },
  { value: "received", key: "filterReceived" },
  { value: "awaiting", key: "filterAwaiting" },
];

export default function Reviews() {
  const t = useT();
  const nav = useNavigate();
  const [clinic] = useClinic();
  const [sel, setSel] = useState<any | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const q = useApiQuery<any>(["reviews", clinic], `/reviews?clinic=${clinic}`);

  const rows: any[] = q.data?.rows ?? [];
  const dist = useMemo(() => {
    const d: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
    rows.forEach((r) => { if (r.rating) d[r.rating] = (d[r.rating] || 0) + 1; });
    return d;
  }, [rows]);
  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return rows.filter((r) => {
      const done = r.stage === "done" && r.rating;
      if (filter === "received" && !done) return false;
      if (filter === "awaiting" && done) return false;
      if (!s) return true;
      return `${r.patient_name || ""} ${r.wa_user} ${r.service || ""} ${r.doctor || ""} ${r.comment || ""}`.toLowerCase().includes(s);
    });
  }, [rows, search, filter]);

  if (q.isLoading) return <><PageTitle title={t("reviews.title")} /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { stats = {}, is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const rate = stats.requested ? Math.floor((stats.responded / stats.requested) * 100) : 0;
  const awaiting = Math.max(0, (stats.requested ?? 0) - (stats.responded ?? 0));
  const avg = stats.avg_rating;

  return (
    <>
      <PageTitle title={t("reviews.title")} subtitle={t("reviews.subtitle")} right={<ClinicFilter meta={q.data} />} />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: "100%", position: "relative", overflow: "hidden",
            "&::before": { content: '""', position: "absolute", inset: 0, pointerEvents: "none",
              background: `radial-gradient(120% 90% at 100% 0%, ${alpha(AMBER, 0.16)}, transparent 55%)` } }}>
            <CardContent sx={{ position: "relative", textAlign: "center", py: 3 }}>
              <Typography variant="caption" color="text.secondary" fontWeight={700}>{t("reviews.overallRating")}</Typography>
              <Typography variant="h2" fontWeight={800} sx={{ mt: 0.5, lineHeight: 1 }}>
                {avg != null ? avg : "—"}
              </Typography>
              <Box sx={{ display: "flex", justifyContent: "center", mt: 1 }}>
                <Rating value={avg ?? 0} precision={0.1} readOnly />
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {t("reviews.basedOn", { n: stats.responded ?? 0 })}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={5}>
          <Card sx={{ height: "100%" }}><CardContent>
            <Typography variant="caption" color="text.secondary" fontWeight={700}>{t("reviews.ratingDistribution")}</Typography>
            <Box sx={{ mt: 2 }}>
              {(stats.responded ?? 0) > 0
                ? <Distribution dist={dist} total={stats.responded ?? 0} />
                : <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>{t("reviews.noReviewsYet")}</Typography>}
            </Box>
          </CardContent></Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Stack spacing={2} sx={{ height: "100%" }}>
            <KpiCard label={t("reviews.kpiReceived")} value={stats.responded ?? 0} color="success" icon={<CheckIcon fontSize="small" />} />
            <KpiCard label={t("reviews.kpiAwaiting")} value={awaiting} color="warning" icon={<HourglassIcon fontSize="small" />} />
            <KpiCard label={t("reviews.kpiResponseRate", { n: stats.responded ?? 0, m: stats.requested ?? 0 })} value={`${rate}%`} color="info" icon={<PercentIcon fontSize="small" />} />
          </Stack>
        </Grid>
      </Grid>

      <Card sx={{ p: 0, overflow: "hidden" }}>
        <Box sx={{ px: 2, py: 1.5, borderBottom: (t) => `1px solid ${t.palette.divider}`,
          background: (t) => alpha(t.palette.primary.main, 0.04) }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ md: "center" }}>
            <TextField fullWidth size="small" placeholder={t("reviews.searchPlaceholder")}
              value={search} onChange={(e) => setSearch(e.target.value)}
              InputProps={{ startAdornment: (<InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>) }}
              sx={{ "& .MuiOutlinedInput-root": { borderRadius: 2.5 } }} />
            <ToggleButtonGroup size="small" exclusive value={filter} onChange={(_e, v) => setFilter(v ?? "")}
              sx={{ flexShrink: 0 }}>
              {FILTERS.map((f) => <ToggleButton key={f.value} value={f.value}>{t(`reviews.${f.key}`)}</ToggleButton>)}
            </ToggleButtonGroup>
          </Stack>
        </Box>

        <Box sx={{ p: 2 }}>
          {filtered.length === 0 ? (
            <EmptyState text={search || filter ? t("reviews.emptyNoMatch") : t("reviews.emptyNone")} />
          ) : (
            <Grid container spacing={2}>
              {filtered.map((r) => (
                <Grid item xs={12} sm={6} lg={4} key={r.id}>
                  <ReviewCard row={r} showClinic={showClinic} clinicName={tenant_names[r.tenant_id]} onOpen={() => setSel(r)} />
                </Grid>
              ))}
            </Grid>
          )}
        </Box>
      </Card>

      {sel && <ReviewDetail row={sel} showClinic={showClinic} clinicName={tenant_names[sel.tenant_id]}
        onClose={() => setSel(null)} onView={() => nav(`/patients/${sel.wa_user}`)} />}
    </>
  );
}
