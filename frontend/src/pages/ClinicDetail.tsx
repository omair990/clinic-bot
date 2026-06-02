import { useParams, useNavigate } from "react-router-dom";
import {
  Card, CardContent, Grid, Typography, Box, Chip, Stack, Button, LinearProgress, Table,
  TableHead, TableRow, TableCell, TableBody, Rating, Divider,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SettingsIcon from "@mui/icons-material/SettingsOutlined";
import SettingsInputComponentIcon from "@mui/icons-material/SettingsInputComponent";
import { useApiQuery, PageTitle, Loading, QueryError, KpiCard, fmtDate, EmptyState } from "../lib";
import { useT } from "../i18n";

const statusColor: Record<string, any> = { confirmed: "success", completed: "info", cancelled: "default", no_show: "warning" };

function pct(u: number, q: number | null) { return q ? Math.min(100, (u / q) * 100) : 0; }
function barColor(p: number) { return p >= 100 ? "error" : p >= 80 ? "warning" : "success"; }

function UsageBar({ label, used, quota, on }: { label: string; used: number; quota: number | null; on: boolean }) {
  const t = useT();
  if (!on) return <Typography variant="caption" color="text.secondary">{t("clinicDetail.off", { label })}</Typography>;
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
  const t = useT();
  const q = useApiQuery<any>(["clinic", id], `/clinics/${id}`);
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { clinic: c, stats: s, trends, review_stats: rv, recent_appointments = [], recent_reviews = [] } = q.data;

  return (
    <>
      <PageTitle title={c.name} subtitle={`${c.slug} · ${c.plan_name || t("clinicDetail.noPlan")}`} right={
        <Stack direction="row" spacing={1}>
          <Chip label={t(`enums.status.${c.status}`)} color={c.status === "active" ? "success" : c.status === "suspended" ? "error" : "default"} variant="outlined" />
          <Button startIcon={<SettingsInputComponentIcon />} onClick={() => nav(`/tenants/${id}/connector`)}>{t("clinicDetail.connector")}</Button>
          <Button startIcon={<SettingsIcon />} variant="contained" onClick={() => nav(`/tenants/${id}`)}>{t("clinicDetail.manage")}</Button>
          <Button startIcon={<ArrowBackIcon />} onClick={() => nav("/")}>{t("clinicDetail.back")}</Button>
        </Stack>} />

      <Grid container spacing={2} sx={{ mb: 1 }}>
        <Grid item xs={6} md={3}><KpiCard label={t("clinicDetail.messages")} value={s.messages ?? 0} color="primary" spark={trends} /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("clinicDetail.appointments")} value={s.appointments ?? 0} color="success" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("clinicDetail.upcoming")} value={s.upcoming_appointments ?? 0} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("clinicDetail.openIssues")} value={c.open_issues ?? 0} color="error" /></Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: "100%" }}><CardContent>
            <Typography variant="subtitle2" sx={{ mb: 1.5 }}>{t("clinicDetail.usage", { plan: c.plan_name || t("clinicDetail.noPlan") })}</Typography>
            <UsageBar label={t("clinicDetail.text")} used={c.text_count} quota={c.monthly_text_quota} on />
            <UsageBar label={t("clinicDetail.voice")} used={c.voice_count} quota={c.monthly_voice_quota} on={c.voice_enabled} />
            <Divider sx={{ my: 1.5 }} />
            <Stack direction="row" spacing={3}>
              <Box><Typography variant="h6" color="warning.main">{rv?.avg_rating ?? "—"} ★</Typography><Typography variant="caption" color="text.secondary">{t("clinicDetail.avgRating")}</Typography></Box>
              <Box><Typography variant="h6">{c.no_shows_month ?? 0}</Typography><Typography variant="caption" color="text.secondary">{t("clinicDetail.missedVisitsMo")}</Typography></Box>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: "wrap" }}>
              <Button size="small" onClick={() => nav(`/conversations?clinic=${id}`)}>{t("clinicDetail.conversations")}</Button>
              <Button size="small" onClick={() => nav(`/insights?clinic=${id}`)}>{t("clinicDetail.insights")}</Button>
              <Button size="small" onClick={() => nav(`/no-shows?clinic=${id}`)}>{t("clinicDetail.missedVisits")}</Button>
            </Stack>
          </CardContent></Card>
        </Grid>

        <Grid item xs={12} md={8}>
          <Card sx={{ mb: 2 }}>
            <CardContent sx={{ pb: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Typography variant="subtitle2">{t("clinicDetail.recentAppointments")}</Typography>
              <Button size="small" onClick={() => nav(`/appointments?clinic=${id}`)}>{t("clinicDetail.viewAll")}</Button>
            </CardContent>
            {recent_appointments.length ? (
              <Table size="small">
                <TableHead><TableRow><TableCell>{t("clinicDetail.patient")}</TableCell><TableCell>{t("clinicDetail.service")}</TableCell><TableCell>{t("clinicDetail.when")}</TableCell><TableCell>{t("clinicDetail.status")}</TableCell></TableRow></TableHead>
                <TableBody>{recent_appointments.map((a: any) => (
                  <TableRow key={a.id} hover sx={{ cursor: "pointer" }} onClick={() => nav(`/patients/${a.wa_user}`)}>
                    <TableCell>{a.patient_name || `+${a.wa_user}`}</TableCell>
                    <TableCell>{a.service || t("clinicDetail.dash")}</TableCell>
                    <TableCell>{fmtDate(a.start_at)}</TableCell>
                    <TableCell><Chip size="small" color={statusColor[a.status] || "default"} label={t(`enums.appt.${a.status}`)} /></TableCell>
                  </TableRow>))}</TableBody>
              </Table>
            ) : <EmptyState text={t("clinicDetail.noAppointments")} />}
          </Card>
          <Card>
            <CardContent sx={{ pb: 0 }}><Typography variant="subtitle2">{t("clinicDetail.recentReviews")}</Typography></CardContent>
            {recent_reviews.length ? (
              <Table size="small">
                <TableHead><TableRow><TableCell>{t("clinicDetail.rating")}</TableCell><TableCell>{t("clinicDetail.comment")}</TableCell><TableCell>{t("clinicDetail.when")}</TableCell></TableRow></TableHead>
                <TableBody>{recent_reviews.map((r: any) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.rating ? <Rating value={r.rating} readOnly size="small" /> : t("clinicDetail.dash")}</TableCell>
                    <TableCell>{r.comment || t("clinicDetail.dash")}</TableCell>
                    <TableCell>{fmtDate(r.responded_at || r.created_at)}</TableCell>
                  </TableRow>))}</TableBody>
              </Table>
            ) : <EmptyState text={t("clinicDetail.noReviews")} />}
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
