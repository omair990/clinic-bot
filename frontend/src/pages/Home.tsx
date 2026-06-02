import { useMemo } from "react";
import { Grid, Card, CardContent, Typography, Box, Chip, Stack, Button, Avatar, Divider, alpha, Alert } from "@mui/material";
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
import StarIcon from "@mui/icons-material/StarRounded";
import TextsmsIcon from "@mui/icons-material/TextsmsOutlined";
import GraphicEqIcon from "@mui/icons-material/GraphicEqOutlined";
import ArrowIcon from "@mui/icons-material/ArrowForwardRounded";
import { useAuth } from "../auth";
import { useApiQuery, PageTitle, CardsSkeleton, QueryError, KpiCard } from "../lib";
import { useLive } from "../realtime";
import { useT } from "../i18n";
import LiveActivityFeed from "../LiveActivityFeed";

const fmt = (n: number | null | undefined) => (n == null ? "∞" : n.toLocaleString());
function avatarHue(s: string) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }

// Slim custom usage bar, colored by how close to the quota.
function UsageBar({ label, icon, used, quota, on }: {
  label: string; icon: React.ReactNode; used: number; quota: number | null; on: boolean;
}) {
  const t = useT();
  const unlimited = quota == null;
  const p = quota ? Math.min(100, (used / quota) * 100) : (unlimited ? 100 : 0);
  const over = on && !unlimited && p >= 100;
  const near = on && !unlimited && p >= 80 && !over;
  const color = !on ? "#94a3b8" : over ? "#ef4444" : near ? "#f59e0b" : "#14b8a6";
  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Stack direction="row" spacing={0.6} alignItems="center" sx={{ color: "text.secondary" }}>
          <Box sx={{ display: "grid", placeItems: "center", color }}>{icon}</Box>
          <Typography variant="caption" fontWeight={700}>{label}</Typography>
        </Stack>
        <Typography variant="caption" color={on ? "text.primary" : "text.secondary"} fontWeight={700}>
          {on ? `${fmt(used)} / ${fmt(quota)}` : t("home.off")}
        </Typography>
      </Stack>
      <Box sx={{ height: 7, borderRadius: 4, overflow: "hidden", bgcolor: (t) => alpha(t.palette.text.primary, 0.06) }}>
        <Box sx={{ width: `${on ? p : 0}%`, height: "100%", bgcolor: color, opacity: unlimited ? 0.5 : 1, transition: "width .4s ease" }} />
      </Box>
    </Box>
  );
}

// Premium gradient banner with a live-connection pill + optional glassy stat strip.
function Hero({ title, subtitle, stats }: { title: string; subtitle: string; stats?: { label: string; value: React.ReactNode }[] }) {
  const t = useT();
  const { connected } = useLive();
  return (
    <Box sx={{
      position: "relative", overflow: "hidden", borderRadius: 4, mb: 3, px: { xs: 2.5, md: 4 }, py: { xs: 3, md: 3.5 },
      color: "#fff", background: "linear-gradient(120deg,#0f766e 0%,#14b8a6 45%,#6366f1 100%)",
      boxShadow: "0 16px 40px -18px rgba(20,184,166,.6)",
    }}>
      <Box sx={{ position: "absolute", right: -60, top: -60, width: 220, height: 220, borderRadius: "50%", background: alpha("#fff", 0.12) }} />
      <Box sx={{ position: "absolute", right: 80, bottom: -90, width: 200, height: 200, borderRadius: "50%", background: alpha("#fff", 0.08) }} />
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ position: "relative", gap: 2, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="h4" sx={{ color: "#fff" }}>{title}</Typography>
          <Typography sx={{ color: alpha("#fff", 0.85), mt: 0.5 }}>{subtitle}</Typography>
        </Box>
        <Chip
          icon={<CircleIcon sx={{ fontSize: "10px !important", color: `${connected ? "#86efac" : "#fca5a5"} !important` }} />}
          label={connected ? t("home.liveRealtime") : t("common.reconnecting")}
          sx={{ bgcolor: alpha("#fff", 0.16), color: "#fff", fontWeight: 700, backdropFilter: "blur(6px)" }} />
      </Stack>
      {stats && stats.length > 0 && (
        <Stack direction="row" spacing={1.5} useFlexGap sx={{ position: "relative", mt: 2.5, flexWrap: "wrap" }}>
          {stats.map((s) => (
            <Box key={s.label} sx={{ px: 2, py: 1, borderRadius: 2.5, minWidth: 96,
              bgcolor: alpha("#fff", 0.14), border: `1px solid ${alpha("#fff", 0.22)}`, backdropFilter: "blur(6px)" }}>
              <Typography variant="h6" fontWeight={800} sx={{ color: "#fff", lineHeight: 1.1 }}>{s.value}</Typography>
              <Typography variant="caption" sx={{ color: alpha("#fff", 0.85) }}>{s.label}</Typography>
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  );
}

function TrendChart({ data }: { data?: number[] }) {
  const t = useT();
  const series = data ?? [];
  const total = series.reduce((a, b) => a + b, 0);
  const avg = series.length ? Math.round(total / series.length) : 0;
  const peak = series.length ? Math.max(...series) : 0;
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography fontWeight={800}>{t("home.inboundMessages")}</Typography>
            <Typography variant="caption" color="text.secondary">{t("home.last14Days")}</Typography>
          </Box>
          <Stack direction="row" spacing={2.5}>
            {[["Total", t("home.total"), total], ["Avg/day", t("home.avgDay"), avg], ["Peak", t("home.peak"), peak]].map(([l, label, v]: any) => (
              <Box key={l} sx={{ textAlign: "right" }}>
                <Typography variant="h6" fontWeight={800} color={l === "Total" ? "primary.main" : "text.primary"}>{v.toLocaleString()}</Typography>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
              </Box>
            ))}
          </Stack>
        </Stack>
        <Box sx={{ height: 256, mt: 1 }}>
          {series.length > 1 ? (
            <LineChart
              height={256}
              series={[{ data: series, area: true, showMark: false, curve: "natural", color: "#14b8a6", label: "Messages" }]}
              xAxis={[{ data: series.map((_, i) => i - series.length + 1), valueFormatter: (v) => v === 0 ? "today" : `${v}d` }]}
              margin={{ left: 36, right: 12, top: 12, bottom: 24 }}
              slotProps={{ legend: { hidden: true } }}
              sx={{ "& .MuiAreaElement-root": { fillOpacity: 0.2 }, "& .MuiLineElement-root": { strokeWidth: 2.5 } }}
            />
          ) : (
            <Box sx={{ height: "100%", display: "grid", placeItems: "center", color: "text.secondary" }}>
              <Typography variant="body2">{t("home.noTrendData")}</Typography>
            </Box>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}

function ClinicCard({ c, nav }: { c: any; nav: (to: string) => void }) {
  const t = useT();
  const hue = avatarHue(c.slug || c.name || "");
  const sc = c.status === "active" ? "success" : c.status === "suspended" ? "error" : "default";
  const tiles = [
    { v: c.open_issues, l: t("home.issues"), icon: <WarningIcon sx={{ fontSize: 16 }} />, color: c.open_issues ? "#ef4444" : undefined, to: `/issues?clinic=${c.id}` },
    { v: c.reviews_avg != null ? c.reviews_avg.toFixed(1) : "—", l: t("home.reviews", { n: c.reviews_count }), icon: <StarIcon sx={{ fontSize: 16 }} />, color: "#f59e0b", to: `/reviews?clinic=${c.id}` },
    { v: c.no_shows_month, l: t("home.missed"), icon: <EventBusyIcon sx={{ fontSize: 16 }} />, to: `/no-shows?clinic=${c.id}` },
    { v: c.upcoming_appts, l: t("home.upcoming"), icon: <UpcomingIcon sx={{ fontSize: 16 }} />, to: `/appointments?clinic=${c.id}` },
  ];
  return (
    <Card sx={{ height: "100%", display: "flex", flexDirection: "column", position: "relative", overflow: "hidden",
      transition: "transform .18s ease, box-shadow .18s ease",
      "&:hover": { transform: "translateY(-3px)", boxShadow: (t) => t.shadows[8] },
      "&::before": { content: '""', position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
        bgcolor: (t) => (t.palette as any)[sc]?.main || t.palette.primary.main, opacity: 0.85 } }}>
      <CardContent sx={{ flex: 1, display: "flex", flexDirection: "column", gap: 1.5 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Avatar onClick={() => nav(`/clinics/${c.id}`)} sx={{ width: 44, height: 44, fontWeight: 800, fontSize: 15, flexShrink: 0, cursor: "pointer",
            background: `linear-gradient(135deg, hsl(${hue} 70% 55%), hsl(${(hue + 40) % 360} 70% 45%))`, color: "#fff" }}>
            {(c.name || c.slug || "?").slice(0, 2).toUpperCase()}
          </Avatar>
          <Box onClick={() => nav(`/clinics/${c.id}`)} sx={{ minWidth: 0, flex: 1, cursor: "pointer", "&:hover .cn": { color: "primary.main" } }}>
            <Typography className="cn" fontWeight={700} noWrap>{c.name}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap display="block">{c.slug} · {c.plan_name || t("home.noPlan")}</Typography>
          </Box>
          <Chip size="small" variant="outlined" color={sc as any} label={t(`enums.status.${c.status}`)} />
        </Stack>

        <Grid container spacing={1}>
          {tiles.map((m, i) => (
            <Grid item xs={3} key={i}>
              <Box onClick={() => nav(m.to)} sx={{ cursor: "pointer", textAlign: "center", py: 1, borderRadius: 2,
                transition: "background .15s ease", "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.08) } }}>
                <Box sx={{ color: m.color || "text.secondary", display: "grid", placeItems: "center", mb: 0.25 }}>{m.icon}</Box>
                <Typography fontWeight={800} sx={{ color: m.color || "text.primary", lineHeight: 1.1 }}>{m.v}</Typography>
                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block" }}>{m.l}</Typography>
              </Box>
            </Grid>
          ))}
        </Grid>

        <Stack spacing={1.25}>
          <UsageBar label={t("home.text")} icon={<TextsmsIcon sx={{ fontSize: 15 }} />} used={c.text_count} quota={c.monthly_text_quota} on />
          <UsageBar label={t("home.voice")} icon={<GraphicEqIcon sx={{ fontSize: 15 }} />} used={c.voice_count} quota={c.monthly_voice_quota} on={c.voice_enabled} />
        </Stack>

        <Divider sx={{ mt: "auto" }} />
        <Stack direction="row" spacing={1} alignItems="center">
          <Button size="small" variant="outlined" onClick={() => nav(`/clinics/${c.id}`)}>{t("home.openProfile")}</Button>
          <Button size="small" onClick={() => nav(`/insights?clinic=${c.id}`)}>{t("home.insights")}</Button>
          <Box sx={{ flex: 1 }} />
          <Button size="small" color="inherit" endIcon={<ArrowIcon sx={{ fontSize: 16 }} />} onClick={() => nav(`/tenants/${c.id}`)}>{t("home.manage")}</Button>
        </Stack>
      </CardContent>
    </Card>
  );
}

function Overview() {
  const t = useT();
  const nav = useNavigate();
  const q = useApiQuery<{ clinics: any[] }>(["overview"], "/overview");
  const trends = useApiQuery<{ daily_messages: number[] }>(["trends"], "/trends");
  // Clinics needing attention (open issues, then suspended/expired) float to the top.
  const clinics = useMemo(() => {
    const list = q.data?.clinics ?? [];
    return [...list].sort((a, b) => (b.open_issues || 0) - (a.open_issues || 0)
      || (a.status === "active" ? 1 : 0) - (b.status === "active" ? 1 : 0));
  }, [q.data]);

  if (q.isLoading) return <><PageTitle title={t("home.clinicsOverview")} /><CardsSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const sum = (k: string) => clinics.reduce((a, c) => a + (c[k] || 0), 0);
  const spark = trends.data?.daily_messages;
  const active = clinics.filter((c) => c.status === "active").length;

  return (
    <>
      <Hero title={t("home.platformOverview")}
        subtitle={t("home.overviewSubtitle", { n: clinics.length, s: clinics.length === 1 ? "" : "s" })}
        stats={[
          { label: t("home.clinics"), value: clinics.length },
          { label: t("home.active"), value: active },
          { label: t("home.openIssues"), value: sum("open_issues") },
          { label: t("home.upcomingAppts"), value: sum("upcoming_appts") },
        ]} />

      <Grid container spacing={2} sx={{ mb: 1 }}>
        <Grid item xs={6} md={3}><KpiCard label={t("home.clinics")} value={clinics.length} icon={<BusinessIcon fontSize="small" />} color="secondary" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("home.openIssues")} value={sum("open_issues")} icon={<WarningIcon fontSize="small" />} color="error" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("home.upcomingAppts")} value={sum("upcoming_appts")} icon={<UpcomingIcon fontSize="small" />} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("home.inbound14d")} value={spark ? spark.reduce((a, b) => a + b, 0) : 0} icon={<ForumIcon fontSize="small" />} color="primary" spark={spark} /></Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mt: 0.5 }}>
        <Grid item xs={12} lg={7}><TrendChart data={spark} /></Grid>
        <Grid item xs={12} lg={5}><LiveActivityFeed /></Grid>
      </Grid>

      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 3, mb: 1.5 }}>
        <Typography variant="subtitle2" fontWeight={800}>{t("home.clinicsHeader")}</Typography>
        <Typography variant="caption" color="text.secondary">{t("home.clinicsTotalActive", { n: clinics.length, m: active })}</Typography>
      </Stack>
      <Grid container spacing={2}>
        {clinics.map((c) => (
          <Grid item xs={12} md={6} xl={4} key={c.id}><ClinicCard c={c} nav={nav} /></Grid>
        ))}
      </Grid>
    </>
  );
}

function Dashboard() {
  const t = useT();
  const { me } = useAuth();
  const q = useApiQuery<any>(["dashboard"], "/dashboard");
  const trends = useApiQuery<{ daily_messages: number[] }>(["trends"], "/trends");
  if (q.isLoading) return <><PageTitle title={t("home.dashboard")} /><CardsSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const s = q.data?.stats ?? {};
  const spark = trends.data?.daily_messages;
  const cards = [
    { l: t("home.messages"), v: s.messages, icon: <ForumIcon fontSize="small" />, c: "primary", spark },
    { l: t("home.users"), v: s.users, icon: <PeopleIcon fontSize="small" />, c: "secondary" },
    { l: t("home.appointments"), v: s.appointments, icon: <EventIcon fontSize="small" />, c: "success" },
    { l: t("home.upcoming"), v: s.upcoming_appointments, icon: <UpcomingIcon fontSize="small" />, c: "info" },
    { l: t("home.needHuman"), v: s.needs_human_users, icon: <WarningIcon fontSize="small" />, c: "warning" },
    { l: t("home.missedVisitsMo"), v: q.data?.no_shows_month, icon: <EventBusyIcon fontSize="small" />, c: "error" },
  ];
  return (
    <>
      <Hero title={me?.tenant_name ? t("home.welcome", { name: me.tenant_name }) : t("home.dashboard")}
        subtitle={t("home.dashboardSubtitle")}
        stats={[
          { label: t("home.appointments"), value: (s.appointments ?? 0).toLocaleString() },
          { label: t("home.upcoming"), value: (s.upcoming_appointments ?? 0).toLocaleString() },
          { label: t("home.needHuman"), value: (s.needs_human_users ?? 0).toLocaleString() },
        ]} />

      {q.data?.wa_send_failing && (
        <Alert severity="error" variant="outlined" sx={{ mb: 2 }}>
          {t("home.waSendFailing")}
        </Alert>
      )}

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
