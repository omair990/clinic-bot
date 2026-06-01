import { Grid, Card, CardContent, Typography, Box, Chip, LinearProgress, Stack, Button, alpha } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { LineChart } from "@mui/x-charts/LineChart";
import ForumIcon from "@mui/icons-material/ForumOutlined";
import PeopleIcon from "@mui/icons-material/PeopleAltOutlined";
import EventIcon from "@mui/icons-material/EventAvailableOutlined";
import UpcomingIcon from "@mui/icons-material/UpcomingOutlined";
import WarningIcon from "@mui/icons-material/WarningAmberOutlined";
import EventBusyIcon from "@mui/icons-material/EventBusyOutlined";
import BusinessIcon from "@mui/icons-material/BusinessOutlined";
import CircleIcon from "@mui/icons-material/Circle";
import { useAuth } from "../auth";
import { useApiQuery, PageTitle, CardsSkeleton, QueryError, KpiCard } from "../lib";
import { useLive } from "../realtime";
import LiveActivityFeed from "../LiveActivityFeed";

function pct(used: number, quota: number | null) { return quota ? Math.min(100, (used / quota) * 100) : 0; }
function barColor(p: number) { return p >= 100 ? "error" : p >= 80 ? "warning" : "success"; }

function UsageBar({ label, used, quota, on }: { label: string; used: number; quota: number | null; on: boolean }) {
  if (!on) return <Typography variant="caption" color="text.secondary">{label}: off</Typography>;
  const p = pct(used, quota);
  return (
    <Box>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="caption" color={p >= 80 ? `${barColor(p)}.main` : "text.secondary"}>{used} / {quota ?? "∞"}</Typography>
      </Stack>
      <LinearProgress variant="determinate" value={quota ? p : 4} color={barColor(p) as any}
        sx={{ height: 6, borderRadius: 3, mt: 0.5 }} />
    </Box>
  );
}

// Premium gradient banner with a live-connection pill. Sets the tone for the whole page.
function Hero({ title, subtitle }: { title: string; subtitle: string }) {
  const { connected } = useLive();
  return (
    <Box sx={{
      position: "relative", overflow: "hidden", borderRadius: 4, mb: 3, px: { xs: 2.5, md: 4 }, py: { xs: 3, md: 3.5 },
      color: "#fff", background: "linear-gradient(120deg,#0f766e 0%,#14b8a6 45%,#6366f1 100%)",
      boxShadow: "0 16px 40px -18px rgba(20,184,166,.6)",
    }}>
      <Box sx={{ position: "absolute", right: -60, top: -60, width: 220, height: 220, borderRadius: "50%",
        background: alpha("#fff", 0.12) }} />
      <Box sx={{ position: "absolute", right: 80, bottom: -90, width: 200, height: 200, borderRadius: "50%",
        background: alpha("#fff", 0.08) }} />
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ position: "relative", gap: 2, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="h4" sx={{ color: "#fff" }}>{title}</Typography>
          <Typography sx={{ color: alpha("#fff", 0.85), mt: 0.5 }}>{subtitle}</Typography>
        </Box>
        <Chip
          icon={<CircleIcon sx={{ fontSize: "10px !important", color: `${connected ? "#86efac" : "#fca5a5"} !important` }} />}
          label={connected ? "Live · real-time" : "Reconnecting…"}
          sx={{ bgcolor: alpha("#fff", 0.16), color: "#fff", fontWeight: 700, backdropFilter: "blur(6px)" }} />
      </Stack>
    </Box>
  );
}

function TrendChart({ data }: { data?: number[] }) {
  const series = data ?? [];
  const total = series.reduce((a, b) => a + b, 0);
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline">
          <Box>
            <Typography fontWeight={800}>Inbound messages</Typography>
            <Typography variant="caption" color="text.secondary">Last 14 days</Typography>
          </Box>
          <Typography variant="h5" color="primary.main">{total.toLocaleString()}</Typography>
        </Stack>
        <Box sx={{ height: 260, mt: 1 }}>
          {series.length > 1 ? (
            <LineChart
              height={260}
              series={[{ data: series, area: true, showMark: false, curve: "natural", color: "#14b8a6", label: "Messages" }]}
              xAxis={[{ data: series.map((_, i) => i - series.length + 1), valueFormatter: (v) => v === 0 ? "today" : `${v}d` }]}
              margin={{ left: 36, right: 12, top: 12, bottom: 24 }}
              slotProps={{ legend: { hidden: true } }}
              sx={{ "& .MuiAreaElement-root": { fillOpacity: 0.18 } }}
            />
          ) : (
            <Box sx={{ height: "100%", display: "grid", placeItems: "center", color: "text.secondary" }}>
              <Typography variant="body2">No trend data yet</Typography>
            </Box>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}

function Overview() {
  const nav = useNavigate();
  const q = useApiQuery<{ clinics: any[] }>(["overview"], "/overview");
  const trends = useApiQuery<{ daily_messages: number[] }>(["trends"], "/trends");
  if (q.isLoading) return <><PageTitle title="Clinics overview" /><CardsSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const clinics = q.data?.clinics ?? [];
  const sum = (k: string) => clinics.reduce((a, c) => a + (c[k] || 0), 0);
  const spark = trends.data?.daily_messages;

  return (
    <>
      <Hero title="Platform overview"
        subtitle={`${clinics.length} clinic${clinics.length === 1 ? "" : "s"} · last 14 days of activity`} />
      <Grid container spacing={2} sx={{ mb: 1 }}>
        <Grid item xs={6} md={3}><KpiCard label="Clinics" value={clinics.length} icon={<BusinessIcon fontSize="small" />} color="secondary" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Open issues" value={sum("open_issues")} icon={<WarningIcon fontSize="small" />} color="error" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Upcoming appts" value={sum("upcoming_appts")} icon={<UpcomingIcon fontSize="small" />} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Inbound (14d)" value={spark ? spark.reduce((a, b) => a + b, 0) : 0} icon={<ForumIcon fontSize="small" />} color="primary" spark={spark} /></Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mt: 0.5 }}>
        <Grid item xs={12} lg={7}><TrendChart data={spark} /></Grid>
        <Grid item xs={12} lg={5}><LiveActivityFeed /></Grid>
      </Grid>

      <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 3, mb: 1 }}>Clinics</Typography>
      <Grid container spacing={2}>
        {clinics.map((c) => (
          <Grid item xs={12} md={6} xl={4} key={c.id}>
            <Card sx={{ height: "100%" }}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                  <Box onClick={() => nav(`/clinics/${c.id}`)} sx={{ cursor: "pointer", "&:hover .cn": { color: "primary.main" } }}>
                    <Typography className="cn" fontWeight={800}>{c.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{c.slug} · {c.plan_name || "no plan"}</Typography>
                  </Box>
                  <Chip size="small" label={c.status}
                    color={c.status === "active" ? "success" : c.status === "suspended" ? "error" : "default"} variant="outlined" />
                </Stack>
                <Grid container spacing={1} sx={{ my: 1 }}>
                  {[
                    { v: c.open_issues, l: "Issues", to: `/issues?clinic=${c.id}`, c: c.open_issues ? "error" : "text.primary" },
                    { v: c.reviews_avg != null ? c.reviews_avg.toFixed(1) : "—", l: `★ (${c.reviews_count})`, to: `/reviews?clinic=${c.id}`, c: "warning.main" },
                    { v: c.no_shows_month, l: "Missed", to: `/no-shows?clinic=${c.id}`, c: "text.primary" },
                    { v: c.upcoming_appts, l: "Upcoming", to: `/appointments?clinic=${c.id}`, c: "text.primary" },
                  ].map((m, i) => (
                    <Grid item xs={3} key={i}>
                      <Box onClick={() => nav(m.to)} sx={{ cursor: "pointer", textAlign: "center", p: 1, borderRadius: 2,
                        "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.08) } }}>
                        <Typography fontWeight={800} sx={{ color: m.c }}>{m.v}</Typography>
                        <Typography variant="caption" color="text.secondary">{m.l}</Typography>
                      </Box>
                    </Grid>
                  ))}
                </Grid>
                <Stack spacing={1}>
                  <UsageBar label="Text" used={c.text_count} quota={c.monthly_text_quota} on />
                  <UsageBar label="Voice" used={c.voice_count} quota={c.monthly_voice_quota} on={c.voice_enabled} />
                </Stack>
                <Stack direction="row" spacing={1} sx={{ mt: 1.5, pt: 1.5, borderTop: (t) => `1px solid ${t.palette.divider}` }}>
                  <Button size="small" variant="outlined" onClick={() => nav(`/clinics/${c.id}`)}>Open profile</Button>
                  <Button size="small" onClick={() => nav(`/insights?clinic=${c.id}`)}>Insights</Button>
                  <Button size="small" color="inherit" onClick={() => nav(`/tenants/${c.id}`)}>Manage</Button>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </>
  );
}

function Dashboard() {
  const { me } = useAuth();
  const q = useApiQuery<any>(["dashboard"], "/dashboard");
  const trends = useApiQuery<{ daily_messages: number[] }>(["trends"], "/trends");
  if (q.isLoading) return <><PageTitle title="Dashboard" /><CardsSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const s = q.data?.stats ?? {};
  const spark = trends.data?.daily_messages;
  const cards = [
    { l: "Messages", v: s.messages, icon: <ForumIcon fontSize="small" />, c: "primary", spark },
    { l: "Users", v: s.users, icon: <PeopleIcon fontSize="small" />, c: "secondary" },
    { l: "Appointments", v: s.appointments, icon: <EventIcon fontSize="small" />, c: "success" },
    { l: "Upcoming", v: s.upcoming_appointments, icon: <UpcomingIcon fontSize="small" />, c: "info" },
    { l: "Need human", v: s.needs_human_users, icon: <WarningIcon fontSize="small" />, c: "warning" },
    { l: "Missed visits (mo)", v: q.data?.no_shows_month, icon: <EventBusyIcon fontSize="small" />, c: "error" },
  ];
  return (
    <>
      <Hero title={me?.tenant_name ? `Welcome, ${me.tenant_name}` : "Dashboard"}
        subtitle="Your clinic at a glance · last 14 days" />
      <Grid container spacing={2}>
        {cards.map((c, i) => (
          <Grid item xs={6} md={4} xl={2} key={i}>
            <KpiCard label={c.l} value={c.v ?? 0} icon={c.icon} color={c.c as any} spark={c.spark} />
          </Grid>
        ))}
      </Grid>
      <Grid container spacing={2} sx={{ mt: 0.5 }}>
        <Grid item xs={12} lg={7}><TrendChart data={spark} /></Grid>
        <Grid item xs={12} lg={5}><LiveActivityFeed /></Grid>
      </Grid>
    </>
  );
}

export default function Home() {
  const { me } = useAuth();
  return me?.role === "super" ? <Overview /> : <Dashboard />;
}
