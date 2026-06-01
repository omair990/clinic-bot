import { Grid, Card, CardContent, Typography, Box, Chip, LinearProgress, Stack, Button, alpha } from "@mui/material";
import { useNavigate } from "react-router-dom";
import ForumIcon from "@mui/icons-material/ForumOutlined";
import PeopleIcon from "@mui/icons-material/PeopleAltOutlined";
import EventIcon from "@mui/icons-material/EventAvailableOutlined";
import UpcomingIcon from "@mui/icons-material/UpcomingOutlined";
import WarningIcon from "@mui/icons-material/WarningAmberOutlined";
import EventBusyIcon from "@mui/icons-material/EventBusyOutlined";
import BusinessIcon from "@mui/icons-material/BusinessOutlined";
import { useAuth } from "../auth";
import { useApiQuery, PageTitle, CardsSkeleton, QueryError, KpiCard } from "../lib";

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
      <PageTitle title="Clinics overview" subtitle={`${clinics.length} clinic${clinics.length === 1 ? "" : "s"} · last 14 days`} />
      <Grid container spacing={2} sx={{ mb: 1 }}>
        <Grid item xs={6} md={3}><KpiCard label="Clinics" value={clinics.length} icon={<BusinessIcon fontSize="small" />} color="secondary" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Open issues" value={sum("open_issues")} icon={<WarningIcon fontSize="small" />} color="error" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Upcoming appts" value={sum("upcoming_appts")} icon={<UpcomingIcon fontSize="small" />} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Inbound (14d)" value={spark ? spark.reduce((a, b) => a + b, 0) : "…"} icon={<ForumIcon fontSize="small" />} color="primary" spark={spark} /></Grid>
      </Grid>

      <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 2, mb: 1 }}>Clinics</Typography>
      <Grid container spacing={2}>
        {clinics.map((c) => (
          <Grid item xs={12} md={6} xl={4} key={c.id}>
            <Card sx={{ height: "100%" }}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                  <Box>
                    <Typography fontWeight={800}>{c.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{c.slug} · {c.plan_name || "no plan"}</Typography>
                  </Box>
                  <Chip size="small" label={c.status}
                    color={c.status === "active" ? "success" : c.status === "suspended" ? "error" : "default"} variant="outlined" />
                </Stack>
                <Grid container spacing={1} sx={{ my: 1 }}>
                  {[
                    { v: c.open_issues, l: "Issues", to: `/issues?clinic=${c.id}`, c: c.open_issues ? "error" : "text.primary" },
                    { v: c.reviews_avg != null ? c.reviews_avg.toFixed(1) : "—", l: `★ (${c.reviews_count})`, to: `/reviews?clinic=${c.id}`, c: "warning.main" },
                    { v: c.no_shows_month, l: "No-shows", to: `/no-shows?clinic=${c.id}`, c: "text.primary" },
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
                  <Button size="small" onClick={() => nav(`/conversations?clinic=${c.id}`)}>Conversations</Button>
                  <Button size="small" onClick={() => nav(`/insights?clinic=${c.id}`)}>Insights</Button>
                  <Button size="small" color="inherit" onClick={() => nav(`/tenants/${c.id}`)}>Settings</Button>
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
    { l: "No-shows (mo)", v: q.data?.no_shows_month, icon: <EventBusyIcon fontSize="small" />, c: "error" },
  ];
  return (
    <>
      <PageTitle title="Dashboard" subtitle="Last 14 days of activity" />
      <Grid container spacing={2}>
        {cards.map((c, i) => (
          <Grid item xs={6} md={4} xl={2} key={i}>
            <KpiCard label={c.l} value={c.v ?? 0} icon={c.icon} color={c.c as any} spark={c.spark} />
          </Grid>
        ))}
      </Grid>
    </>
  );
}

export default function Home() {
  const { me } = useAuth();
  return me?.role === "super" ? <Overview /> : <Dashboard />;
}
