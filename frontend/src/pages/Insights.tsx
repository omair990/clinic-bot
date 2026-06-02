import {
  Card, CardContent, Grid, Typography, ToggleButton, ToggleButtonGroup, Stack, Box, Chip, alpha,
} from "@mui/material";
import { BarChart } from "@mui/x-charts/BarChart";
import { PieChart } from "@mui/x-charts/PieChart";
import { useSearchParams } from "react-router-dom";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesomeOutlined";
import ForumIcon from "@mui/icons-material/ForumOutlined";
import PeopleIcon from "@mui/icons-material/PeopleAltOutlined";
import EventAvailableIcon from "@mui/icons-material/EventAvailableOutlined";
import TrendingUpIcon from "@mui/icons-material/TrendingUpOutlined";
import GraphicEqIcon from "@mui/icons-material/GraphicEqOutlined";
import EventBusyIcon from "@mui/icons-material/EventBusyOutlined";
import QuestionAnswerIcon from "@mui/icons-material/QuestionAnswerOutlined";
import MedicalServicesIcon from "@mui/icons-material/MedicalServicesOutlined";
import ScheduleIcon from "@mui/icons-material/ScheduleOutlined";
import MoodIcon from "@mui/icons-material/SentimentSatisfiedAltOutlined";
import LocalFireIcon from "@mui/icons-material/LocalFireDepartmentOutlined";
import StarIcon from "@mui/icons-material/StarRounded";
import StarBorderIcon from "@mui/icons-material/StarBorderRounded";
import FilterFunnelIcon from "@mui/icons-material/FilterAltOutlined";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, TableSkeleton, QueryError, KpiCard } from "../lib";

// Brand palette — keeps every chart and accent on the same teal→indigo→amber language.
const C = {
  teal: "#14b8a6", indigo: "#6366f1", amber: "#f59e0b", red: "#ef4444",
  sky: "#38bdf8", violet: "#a78bfa", green: "#10b981", pink: "#ec4899",
};
const BAR_PIE = [C.teal, C.indigo, C.amber, C.sky, C.violet, C.pink];

const titleCase = (s: string) => (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

// --- reusable polished panel (icon + title + caption header) -------------------------------
function Panel({ icon, title, caption, accent, children }: {
  icon: React.ReactNode; title: string; caption?: string; accent: string; children: React.ReactNode;
}) {
  return (
    <Card sx={{ height: "100%", position: "relative", overflow: "hidden",
      "&::before": { content: '""', position: "absolute", inset: 0, pointerEvents: "none",
        background: `radial-gradient(120% 90% at 100% 0%, ${alpha(accent, 0.1)}, transparent 55%)` } }}>
      <CardContent sx={{ position: "relative" }}>
        <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 1.5 }}>
          <Box sx={{ width: 34, height: 34, borderRadius: 2, display: "grid", placeItems: "center",
            color: accent, bgcolor: alpha(accent, 0.14), flexShrink: 0 }}>{icon}</Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" fontWeight={800} noWrap>{title}</Typography>
            {caption && <Typography variant="caption" color="text.secondary" noWrap>{caption}</Typography>}
          </Box>
        </Stack>
        {children}
      </CardContent>
    </Card>
  );
}

function Empty({ h = 160 }: { h?: number }) {
  return (
    <Box sx={{ height: h, display: "grid", placeItems: "center", color: "text.secondary" }}>
      <Typography variant="caption">No data for this period</Typography>
    </Box>
  );
}

// Segmented bar with a labelled legend (used for the lead mix).
function SegBar({ segments }: { segments: { label: string; n: number; color: string }[] }) {
  const total = segments.reduce((s, x) => s + x.n, 0);
  return (
    <Box>
      <Box sx={{ display: "flex", gap: 0.5, height: 14, borderRadius: 7, overflow: "hidden",
        bgcolor: (t) => alpha(t.palette.text.primary, 0.06) }}>
        {total > 0 && segments.map((s) => s.n > 0 && (
          <Box key={s.label} sx={{ flex: s.n, bgcolor: s.color, transition: "flex .4s ease" }} />
        ))}
      </Box>
      <Stack spacing={1} sx={{ mt: 1.75 }}>
        {segments.map((s) => (
          <Stack key={s.label} direction="row" alignItems="center" spacing={1}>
            <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: s.color, flexShrink: 0 }} />
            <Typography variant="body2" sx={{ flex: 1 }}>{s.label}</Typography>
            <Typography variant="body2" fontWeight={800}>{s.n}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ width: 40, textAlign: "right" }}>
              {total ? Math.round((s.n / total) * 100) : 0}%
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}

// Two-step conversion funnel: patients who messaged → patients who booked.
function Conversion({ messaged, booked, pct }: { messaged: number; booked: number; pct: number }) {
  const max = Math.max(messaged, 1);
  const steps = [
    { label: "Messaged", n: messaged, color: C.indigo },
    { label: "Booked", n: booked, color: C.teal },
  ];
  return (
    <Box>
      <Stack direction="row" alignItems="baseline" spacing={1}>
        <Typography variant="h3" fontWeight={800} sx={{ color: C.teal }}>{pct}%</Typography>
        <Typography variant="body2" color="text.secondary">message → booking</Typography>
      </Stack>
      <Stack spacing={1.5} sx={{ mt: 2 }}>
        {steps.map((s) => (
          <Box key={s.label}>
            <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
              <Typography variant="caption" color="text.secondary" fontWeight={700}>{s.label}</Typography>
              <Typography variant="caption" fontWeight={800}>{s.n}</Typography>
            </Stack>
            <Box sx={{ height: 10, borderRadius: 5, overflow: "hidden",
              bgcolor: (t) => alpha(t.palette.text.primary, 0.06) }}>
              <Box sx={{ width: `${(s.n / max) * 100}%`, height: "100%", bgcolor: s.color,
                borderRadius: 5, transition: "width .4s ease" }} />
            </Box>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

function Stars({ value }: { value: number }) {
  const rounded = Math.round(value);
  return (
    <Stack direction="row" spacing={0.1}>
      {[1, 2, 3, 4, 5].map((i) => i <= rounded
        ? <StarIcon key={i} sx={{ fontSize: 22, color: C.amber }} />
        : <StarBorderIcon key={i} sx={{ fontSize: 22, color: C.amber }} />)}
    </Stack>
  );
}

const SHARED_BAR_SX = {
  "& .MuiChartsAxis-line, & .MuiChartsAxis-tick": { display: "none" },
} as const;

export default function Insights() {
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const period = params.get("period") || "day";
  const q = useApiQuery<any>(["insights", clinic, period], `/insights?clinic=${clinic}&period=${period}`);
  const setPeriod = (p: string) => { const n = new URLSearchParams(params); n.set("period", p); setParams(n); };

  if (q.isLoading) return <><PageTitle title="Business insights" /><TableSkeleton rows={4} /></>;
  if (q.error) return <QueryError error={q.error} />;
  const r = q.data.report || {}; const m = r.metrics || {};
  const conv = m.conversion || { users_messaged: 0, users_booked: 0, conversion_pct: 0 };
  const reviews = m.reviews || {};
  const inquiries = (m.top_inquiries || []).map((t: any) => ({ label: titleCase(t.intent), n: t.n }));
  const doctors = (m.top_doctors || []).map((t: any) => ({ label: t.doctor, n: t.n }));
  const peaks = (m.peak_hours || []).map((p: any) => ({ label: `${String(p.hour).padStart(2, "0")}:00`, n: p.n }));

  const sentOrder: [string, string, string][] = [
    ["positive", "Positive", C.green], ["neutral", "Neutral", C.sky], ["negative", "Negative", C.red],
  ];
  const sentiment = sentOrder
    .map(([k, label, color], i) => ({ id: i, value: m.sentiment?.[k] || 0, label, color }))
    .filter((s) => s.value > 0);
  const sentTotal = sentiment.reduce((s, x) => s + x.value, 0);

  const leadSegments = [
    { label: "Hot", n: m.lead_mix?.hot || 0, color: C.red },
    { label: "Warm", n: m.lead_mix?.warm || 0, color: C.amber },
    { label: "Cold", n: m.lead_mix?.cold || 0, color: C.sky },
  ];
  const hasLeads = leadSegments.some((s) => s.n > 0);

  return (
    <>
      <PageTitle title="Business insights" subtitle={r.label} right={
        <Stack direction="row" spacing={1.5} alignItems="center">
          <ClinicFilter meta={q.data} />
          <ToggleButtonGroup size="small" exclusive value={period} onChange={(_e, v) => v && setPeriod(v)}>
            <ToggleButton value="day">Today</ToggleButton>
            <ToggleButton value="week">7 days</ToggleButton>
          </ToggleButtonGroup>
        </Stack>} />

      {r.narrative && (
        <Card sx={{ mb: 2, position: "relative", overflow: "hidden", color: "#fff",
          background: "linear-gradient(120deg,#0f766e 0%,#14b8a6 45%,#6366f1 100%)" }}>
          <CardContent sx={{ p: { xs: 2.5, md: 3 } }}>
            <Stack direction="row" spacing={2} alignItems="flex-start">
              <Box sx={{ width: 46, height: 46, borderRadius: 2.5, display: "grid", placeItems: "center",
                bgcolor: alpha("#fff", 0.18), border: `1px solid ${alpha("#fff", 0.35)}`, flexShrink: 0 }}>
                <AutoAwesomeIcon />
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
                  <Typography variant="subtitle2" fontWeight={800} sx={{ letterSpacing: 0.6 }}>AI BUSINESS INSIGHT</Typography>
                  <Chip size="small" label={r.narrative_source === "ai" ? "AI-generated" : "Auto-summary"}
                    sx={{ height: 20, bgcolor: alpha("#fff", 0.22), color: "#fff", fontWeight: 700 }} />
                </Stack>
                <Typography variant="body1" sx={{ lineHeight: 1.65, color: alpha("#fff", 0.96) }}>{r.narrative}</Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      )}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} sm={4} md={2}><KpiCard label="Inbound messages" value={m.inbound ?? 0} icon={<ForumIcon fontSize="small" />} color="primary" /></Grid>
        <Grid item xs={6} sm={4} md={2}><KpiCard label="Patients" value={m.users ?? 0} icon={<PeopleIcon fontSize="small" />} color="secondary" /></Grid>
        <Grid item xs={6} sm={4} md={2}><KpiCard label="Bookings" value={conv.users_booked ?? 0} icon={<EventAvailableIcon fontSize="small" />} color="success" /></Grid>
        <Grid item xs={6} sm={4} md={2}><KpiCard label="Conversion" value={`${conv.conversion_pct ?? 0}%`} icon={<TrendingUpIcon fontSize="small" />} color="info" /></Grid>
        <Grid item xs={6} sm={4} md={2}><KpiCard label="Voice share" value={`${m.voice_share_pct ?? 0}%`} icon={<GraphicEqIcon fontSize="small" />} color="warning" /></Grid>
        <Grid item xs={6} sm={4} md={2}><KpiCard label="Missed visits" value={m.no_shows ?? 0} icon={<EventBusyIcon fontSize="small" />} color="error" /></Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={4}>
          <Panel icon={<FilterFunnelIcon fontSize="small" />} title="Conversion funnel"
            caption="Patients who messaged vs. booked" accent={C.teal}>
            <Conversion messaged={conv.users_messaged ?? 0} booked={conv.users_booked ?? 0} pct={conv.conversion_pct ?? 0} />
          </Panel>
        </Grid>
        <Grid item xs={12} md={4}>
          <Panel icon={<LocalFireIcon fontSize="small" />} title="Lead mix" caption="Intent quality across conversations" accent={C.red}>
            {hasLeads ? <SegBar segments={leadSegments} /> : <Empty h={140} />}
          </Panel>
        </Grid>
        <Grid item xs={12} md={4}>
          <Panel icon={<MoodIcon fontSize="small" />} title="Sentiment" caption="Conversation mood — negative = at-risk" accent={C.green}>
            {sentiment.length ? (
              <Box sx={{ position: "relative" }}>
                <PieChart height={180}
                  series={[{ data: sentiment, innerRadius: 58, outerRadius: 84, paddingAngle: 2, cornerRadius: 5 }]}
                  colors={sentiment.map((s) => s.color)} margin={{ top: 6, bottom: 6 }}
                  slotProps={{ legend: { hidden: true } }} />
                <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", pointerEvents: "none" }}>
                  <Box sx={{ textAlign: "center" }}>
                    <Typography variant="h5" fontWeight={800} sx={{ lineHeight: 1 }}>{sentTotal}</Typography>
                    <Typography variant="caption" color="text.secondary">chats</Typography>
                  </Box>
                </Box>
                <Stack direction="row" spacing={2} justifyContent="center" sx={{ mt: 1 }}>
                  {sentiment.map((s) => (
                    <Stack key={s.label} direction="row" spacing={0.6} alignItems="center">
                      <Box sx={{ width: 9, height: 9, borderRadius: "50%", bgcolor: s.color }} />
                      <Typography variant="caption" color="text.secondary">{s.label} {s.value}</Typography>
                    </Stack>
                  ))}
                </Stack>
              </Box>
            ) : <Empty h={180} />}
          </Panel>
        </Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <Panel icon={<QuestionAnswerIcon fontSize="small" />} title="Top inquiries" caption="What patients ask about most" accent={C.teal}>
            {inquiries.length ? <BarChart height={240} layout="horizontal"
              yAxis={[{ scaleType: "band", data: inquiries.map((i: any) => i.label) }]}
              series={[{ data: inquiries.map((i: any) => i.n), color: C.teal }]}
              borderRadius={6} margin={{ left: 100, right: 12, top: 6, bottom: 24 }} sx={SHARED_BAR_SX} /> : <Empty />}
          </Panel>
        </Grid>
        <Grid item xs={12} md={6}>
          <Panel icon={<MedicalServicesIcon fontSize="small" />} title="Top doctors" caption="Most-requested practitioners" accent={C.indigo}>
            {doctors.length ? <BarChart height={240} layout="horizontal"
              yAxis={[{ scaleType: "band", data: doctors.map((d: any) => d.label) }]}
              series={[{ data: doctors.map((d: any) => d.n), color: C.indigo }]}
              borderRadius={6} margin={{ left: 120, right: 12, top: 6, bottom: 24 }} sx={SHARED_BAR_SX} /> : <Empty />}
          </Panel>
        </Grid>
        <Grid item xs={12} md={8}>
          <Panel icon={<ScheduleIcon fontSize="small" />} title="Peak contact hours" caption="When patients reach out" accent={C.sky}>
            {peaks.length ? <BarChart height={220} xAxis={[{ scaleType: "band", data: peaks.map((p: any) => p.label) }]}
              series={[{ data: peaks.map((p: any) => p.n), color: C.sky }]}
              borderRadius={6} margin={{ left: 32, right: 12, top: 6, bottom: 24 }} sx={SHARED_BAR_SX} /> : <Empty h={220} />}
          </Panel>
        </Grid>
        <Grid item xs={12} md={4}>
          <Panel icon={<StarIcon fontSize="small" />} title="Reviews" caption="Patient feedback collected" accent={C.amber}>
            {reviews.avg_rating != null ? (
              <Stack spacing={1.5} sx={{ pt: 1 }}>
                <Stack direction="row" alignItems="baseline" spacing={1}>
                  <Typography variant="h3" fontWeight={800}>{Number(reviews.avg_rating).toFixed(1)}</Typography>
                  <Typography variant="body2" color="text.secondary">/ 5</Typography>
                </Stack>
                <Stars value={Number(reviews.avg_rating)} />
                <Stack direction="row" spacing={3} sx={{ pt: 1 }}>
                  <Box><Typography variant="h6" fontWeight={800}>{reviews.responded ?? 0}</Typography>
                    <Typography variant="caption" color="text.secondary">responded</Typography></Box>
                  <Box><Typography variant="h6" fontWeight={800}>{reviews.requested ?? 0}</Typography>
                    <Typography variant="caption" color="text.secondary">requested</Typography></Box>
                </Stack>
              </Stack>
            ) : <Empty h={180} />}
          </Panel>
        </Grid>
      </Grid>
    </>
  );
}
