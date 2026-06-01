import { Card, CardContent, Grid, Typography, LinearProgress, Alert, Box, Stack } from "@mui/material";
import { useApiQuery, PageTitle, Loading, QueryError } from "../lib";

function Meter({ label, used, quota, on }: { label: string; used: number; quota: number | null; on: boolean }) {
  const p = quota ? Math.min(100, (used / quota) * 100) : 0;
  const over = !!quota && p >= 100;
  const near = !!quota && p >= 80 && !over;
  const color = over ? "error" : near ? "warning" : "success";
  return (
    <Card><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography fontWeight={700}>{label}</Typography>
        {!on ? <Typography variant="caption" color="text.secondary">disabled on your plan</Typography>
          : over ? <Typography variant="caption" color="error.main" fontWeight={700}>Limit reached</Typography>
          : near ? <Typography variant="caption" color="warning.main" fontWeight={700}>Approaching limit</Typography> : null}
      </Stack>
      {on ? (
        <Box sx={{ mt: 1 }}>
          <Typography variant="h4" fontWeight={700}>{used} <Typography component="span" variant="h6" color="text.secondary">/ {quota ?? "∞"}</Typography></Typography>
          <LinearProgress variant="determinate" value={quota ? p : 6} color={color as any} sx={{ height: 8, borderRadius: 4, mt: 1 }} />
          <Typography variant="caption" color="text.secondary">{quota ? `${Math.round(p)}% of monthly quota used` : "Unlimited on your plan"}</Typography>
        </Box>
      ) : <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Not included in your plan.</Typography>}
    </CardContent></Card>
  );
}

export default function Usage() {
  const q = useApiQuery<any>(["usage"], "/usage");
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const u = q.data.usage;
  if (!u) return <Typography color="text.secondary">No usage data yet.</Typography>;

  const tp = u.monthly_text_quota ? (u.text_count / u.monthly_text_quota) * 100 : 0;
  const vp = u.voice_enabled && u.monthly_voice_quota ? (u.voice_count / u.monthly_voice_quota) * 100 : 0;
  const warn = (u.monthly_text_quota && tp >= 80) || (u.voice_enabled && u.monthly_voice_quota && vp >= 80);
  const over = tp >= 100 || vp >= 100;

  return (
    <>
      <PageTitle title="Plan & usage" right={<Typography variant="body2" color="text.secondary">Period {q.data.period}</Typography>} />
      {warn && (
        <Alert severity={over ? "error" : "warning"} sx={{ mb: 2 }}>
          {over ? "You have reached a monthly quota. New messages may be blocked until the period resets or your plan is upgraded — please contact the clinic administrator."
                : "You are approaching your monthly quota. Consider upgrading your plan to avoid interruptions."}
        </Alert>
      )}
      <Typography variant="body2" color="text.secondary">Plan</Typography>
      <Typography variant="h6" sx={{ mb: 2 }}>{u.plan_name || "—"}</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}><Meter label="Text messages" used={u.text_count} quota={u.monthly_text_quota} on /></Grid>
        <Grid item xs={12} md={6}><Meter label="Voice notes" used={u.voice_count} quota={u.monthly_voice_quota} on={u.voice_enabled} /></Grid>
      </Grid>
    </>
  );
}
