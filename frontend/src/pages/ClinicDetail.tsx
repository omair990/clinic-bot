import { useParams, useNavigate } from "react-router-dom";
import {
  Card, CardContent, Grid, Typography, Box, Chip, Stack, Button, LinearProgress, Table,
  TableHead, TableRow, TableCell, TableBody, Rating, Divider,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SettingsIcon from "@mui/icons-material/SettingsOutlined";
import SettingsInputComponentIcon from "@mui/icons-material/SettingsInputComponent";
import { useApiQuery, PageTitle, Loading, QueryError, KpiCard, fmtDate, EmptyState } from "../lib";

const statusColor: Record<string, any> = { confirmed: "success", completed: "info", cancelled: "default", no_show: "warning" };

function pct(u: number, q: number | null) { return q ? Math.min(100, (u / q) * 100) : 0; }
function barColor(p: number) { return p >= 100 ? "error" : p >= 80 ? "warning" : "success"; }

function UsageBar({ label, used, quota, on }: { label: string; used: number; quota: number | null; on: boolean }) {
  if (!on) return <Typography variant="caption" color="text.secondary">{label}: off</Typography>;
  const p = pct(used, quota);
  return (
    <Box sx={{ mb: 1 }}>
      <Stack direction="row" justifyContent="space-between"><Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="caption">{used} / {quota ?? "∞"}</Typography></Stack>
      <LinearProgress variant="determinate" value={quota ? p : 4} color={barColor(p) as any} sx={{ height: 6, borderRadius: 3, mt: 0.5 }} />
    </Box>
  );
}

export default function ClinicDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const q = useApiQuery<any>(["clinic", id], `/clinics/${id}`);
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { clinic: c, stats: s, trends, review_stats: rv, recent_appointments = [], recent_reviews = [] } = q.data;

  return (
    <>
      <PageTitle title={c.name} subtitle={`${c.slug} · ${c.plan_name || "no plan"}`} right={
        <Stack direction="row" spacing={1}>
          <Chip label={c.status} color={c.status === "active" ? "success" : c.status === "suspended" ? "error" : "default"} variant="outlined" />
          <Button startIcon={<SettingsInputComponentIcon />} onClick={() => nav(`/tenants/${id}/connector`)}>Connector</Button>
          <Button startIcon={<SettingsIcon />} variant="contained" onClick={() => nav(`/tenants/${id}`)}>Manage</Button>
          <Button startIcon={<ArrowBackIcon />} onClick={() => nav("/")}>Back</Button>
        </Stack>} />

      <Grid container spacing={2} sx={{ mb: 1 }}>
        <Grid item xs={6} md={3}><KpiCard label="Messages" value={s.messages ?? 0} color="primary" spark={trends} /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Appointments" value={s.appointments ?? 0} color="success" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Upcoming" value={s.upcoming_appointments ?? 0} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Open issues" value={c.open_issues ?? 0} color="error" /></Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: "100%" }}><CardContent>
            <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Usage · {c.plan_name || "no plan"}</Typography>
            <UsageBar label="Text" used={c.text_count} quota={c.monthly_text_quota} on />
            <UsageBar label="Voice" used={c.voice_count} quota={c.monthly_voice_quota} on={c.voice_enabled} />
            <Divider sx={{ my: 1.5 }} />
            <Stack direction="row" spacing={3}>
              <Box><Typography variant="h6" color="warning.main">{rv?.avg_rating ?? "—"} ★</Typography><Typography variant="caption" color="text.secondary">Avg rating</Typography></Box>
              <Box><Typography variant="h6">{c.no_shows_month ?? 0}</Typography><Typography variant="caption" color="text.secondary">Missed visits (mo)</Typography></Box>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: "wrap" }}>
              <Button size="small" onClick={() => nav(`/conversations?clinic=${id}`)}>Conversations</Button>
              <Button size="small" onClick={() => nav(`/insights?clinic=${id}`)}>Insights</Button>
              <Button size="small" onClick={() => nav(`/no-shows?clinic=${id}`)}>Missed visits</Button>
            </Stack>
          </CardContent></Card>
        </Grid>

        <Grid item xs={12} md={8}>
          <Card sx={{ mb: 2 }}>
            <CardContent sx={{ pb: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Typography variant="subtitle2">Recent appointments</Typography>
              <Button size="small" onClick={() => nav(`/appointments?clinic=${id}`)}>View all</Button>
            </CardContent>
            {recent_appointments.length ? (
              <Table size="small">
                <TableHead><TableRow><TableCell>Patient</TableCell><TableCell>Service</TableCell><TableCell>When</TableCell><TableCell>Status</TableCell></TableRow></TableHead>
                <TableBody>{recent_appointments.map((a: any) => (
                  <TableRow key={a.id} hover sx={{ cursor: "pointer" }} onClick={() => nav(`/patients/${a.wa_user}`)}>
                    <TableCell>{a.patient_name || `+${a.wa_user}`}</TableCell>
                    <TableCell>{a.service || "—"}</TableCell>
                    <TableCell>{fmtDate(a.start_at)}</TableCell>
                    <TableCell><Chip size="small" color={statusColor[a.status] || "default"} label={a.status} /></TableCell>
                  </TableRow>))}</TableBody>
              </Table>
            ) : <EmptyState text="No appointments yet." />}
          </Card>
          <Card>
            <CardContent sx={{ pb: 0 }}><Typography variant="subtitle2">Recent reviews</Typography></CardContent>
            {recent_reviews.length ? (
              <Table size="small">
                <TableHead><TableRow><TableCell>Rating</TableCell><TableCell>Comment</TableCell><TableCell>When</TableCell></TableRow></TableHead>
                <TableBody>{recent_reviews.map((r: any) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.rating ? <Rating value={r.rating} readOnly size="small" /> : "—"}</TableCell>
                    <TableCell>{r.comment || "—"}</TableCell>
                    <TableCell>{fmtDate(r.responded_at || r.created_at)}</TableCell>
                  </TableRow>))}</TableBody>
              </Table>
            ) : <EmptyState text="No reviews yet." />}
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
