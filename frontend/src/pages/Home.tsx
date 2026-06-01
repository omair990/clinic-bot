import { Grid, Card, CardContent, Typography, Box, Chip, LinearProgress, Stack, Button } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useApiQuery, PageTitle, Loading, QueryError } from "../lib";

function pct(used: number, quota: number | null) {
  return quota ? Math.min(100, (used / quota) * 100) : 0;
}
function barColor(p: number) {
  return p >= 100 ? "error" : p >= 80 ? "warning" : "success";
}

function UsageBar({ label, used, quota, on }: { label: string; used: number; quota: number | null; on: boolean }) {
  if (!on) return <Typography variant="caption" color="text.secondary">{label}: off</Typography>;
  const p = pct(used, quota);
  return (
    <Box>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="caption" color={p >= 80 ? (barColor(p) + ".main") : "text.secondary"}>
          {used} / {quota ?? "∞"}
        </Typography>
      </Stack>
      <LinearProgress variant="determinate" value={quota ? p : 4} color={barColor(p) as any}
        sx={{ height: 6, borderRadius: 3, mt: 0.5 }} />
    </Box>
  );
}

function Metric({ value, label }: { value: any; label: string }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="h4" sx={{ fontWeight: 700 }}>{value}</Typography>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
      </CardContent>
    </Card>
  );
}

function Overview() {
  const nav = useNavigate();
  const q = useApiQuery<{ clinics: any[] }>(["overview"], "/overview");
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const clinics = q.data?.clinics ?? [];
  return (
    <>
      <PageTitle title="Clinics overview" right={<Typography variant="body2" color="text.secondary">{clinics.length} clinic(s)</Typography>} />
      <Grid container spacing={2}>
        {clinics.map((c) => (
          <Grid item xs={12} md={6} xl={4} key={c.id}>
            <Card>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                  <Box>
                    <Typography fontWeight={700}>{c.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{c.slug} · {c.plan_name || "no plan"}</Typography>
                  </Box>
                  <Chip size="small" label={c.status}
                    color={c.status === "active" ? "success" : c.status === "suspended" ? "error" : "default"} />
                </Stack>
                <Grid container spacing={1} sx={{ my: 1 }}>
                  {[
                    { v: c.open_issues, l: "Issues", to: `/issues?clinic=${c.id}` },
                    { v: c.reviews_avg != null ? c.reviews_avg.toFixed(1) : "—", l: `★ (${c.reviews_count})`, to: `/reviews?clinic=${c.id}` },
                    { v: c.no_shows_month, l: "No-shows", to: `/no-shows?clinic=${c.id}` },
                    { v: c.upcoming_appts, l: "Upcoming", to: `/appointments?clinic=${c.id}` },
                  ].map((m, i) => (
                    <Grid item xs={3} key={i}>
                      <Box onClick={() => nav(m.to)} sx={{ cursor: "pointer", textAlign: "center", p: 1, borderRadius: 1, "&:hover": { bgcolor: "#f8fafc" } }}>
                        <Typography fontWeight={700}>{m.v}</Typography>
                        <Typography variant="caption" color="text.secondary">{m.l}</Typography>
                      </Box>
                    </Grid>
                  ))}
                </Grid>
                <Stack spacing={1}>
                  <UsageBar label="Text" used={c.text_count} quota={c.monthly_text_quota} on />
                  <UsageBar label="Voice" used={c.voice_count} quota={c.monthly_voice_quota} on={c.voice_enabled} />
                </Stack>
                <Stack direction="row" spacing={2} sx={{ mt: 1.5, pt: 1.5, borderTop: "1px solid #f1f5f9" }}>
                  <Button size="small" onClick={() => nav(`/conversations?clinic=${c.id}`)}>Conversations</Button>
                  <Button size="small" onClick={() => nav(`/insights?clinic=${c.id}`)}>Insights</Button>
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
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const s = q.data?.stats ?? {};
  const cards = [
    { v: s.messages, l: "Messages" },
    { v: s.users, l: "Users" },
    { v: s.appointments, l: "Appointments" },
    { v: s.upcoming_appointments, l: "Upcoming" },
    { v: s.needs_human_users, l: "Need human" },
    { v: q.data?.no_shows_month, l: "No-shows (month)" },
  ];
  return (
    <>
      <PageTitle title="Dashboard" />
      <Grid container spacing={2}>
        {cards.map((c, i) => (
          <Grid item xs={6} md={2} key={i}><Metric value={c.v ?? 0} label={c.l} /></Grid>
        ))}
      </Grid>
    </>
  );
}

export default function Home() {
  const { me } = useAuth();
  return me?.role === "super" ? <Overview /> : <Dashboard />;
}
