import { Card, CardContent, Grid, Typography, ToggleButton, ToggleButtonGroup, Stack, Box, Chip } from "@mui/material";
import { useSearchParams } from "react-router-dom";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, Loading, QueryError } from "../lib";

function Stat({ v, l }: { v: any; l: string }) {
  return <Card><CardContent><Typography variant="h5" fontWeight={700}>{v ?? 0}</Typography><Typography variant="caption" color="text.secondary">{l}</Typography></CardContent></Card>;
}

export default function Insights() {
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const period = params.get("period") || "day";
  const q = useApiQuery<any>(["insights", clinic, period], `/insights?clinic=${clinic}&period=${period}`);

  const setPeriod = (p: string) => {
    const next = new URLSearchParams(params); next.set("period", p); setParams(next);
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const r = q.data.report || {};
  const m = r.metrics || {};

  return (
    <>
      <PageTitle title="Business insights" right={<Stack direction="row" spacing={2} alignItems="center">
        <ClinicFilter meta={q.data} />
        <ToggleButtonGroup size="small" exclusive value={period} onChange={(_, v) => v && setPeriod(v)}>
          <ToggleButton value="day">Today</ToggleButton>
          <ToggleButton value="week">7 days</ToggleButton>
        </ToggleButtonGroup>
      </Stack>} />

      {r.narrative && (
        <Card sx={{ mb: 2 }}><CardContent>
          <Typography variant="overline" color="text.secondary">{r.label}</Typography>
          <Typography variant="body2">{r.narrative}</Typography>
        </CardContent></Card>
      )}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={2}><Stat v={m.messages} l="Messages" /></Grid>
        <Grid item xs={6} md={2}><Stat v={m.inbound} l="Inbound" /></Grid>
        <Grid item xs={6} md={2}><Stat v={m.users} l="Users" /></Grid>
        <Grid item xs={6} md={2}><Stat v={`${m.voice_share_pct ?? 0}%`} l="Voice share" /></Grid>
        <Grid item xs={6} md={2}><Stat v={m.no_shows} l="No-shows" /></Grid>
        <Grid item xs={6} md={2}><Stat v={(m.reviews?.avg_rating) ?? "—"} l="Avg rating" /></Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}><Card><CardContent>
          <Typography fontWeight={700} sx={{ mb: 1 }}>Top inquiries</Typography>
          <Stack spacing={0.5}>
            {(m.top_inquiries || []).map((t: any) => (
              <Stack key={t.intent} direction="row" justifyContent="space-between"><Typography variant="body2">{t.intent}</Typography><Chip size="small" label={t.n} /></Stack>
            ))}
            {(m.top_inquiries || []).length === 0 && <Typography variant="caption" color="text.secondary">No data</Typography>}
          </Stack>
        </CardContent></Card></Grid>
        <Grid item xs={12} md={6}><Card><CardContent>
          <Typography fontWeight={700} sx={{ mb: 1 }}>Top doctors</Typography>
          <Stack spacing={0.5}>
            {(m.top_doctors || []).map((t: any) => (
              <Stack key={t.doctor} direction="row" justifyContent="space-between"><Typography variant="body2">{t.doctor}</Typography><Chip size="small" label={t.n} /></Stack>
            ))}
            {(m.top_doctors || []).length === 0 && <Typography variant="caption" color="text.secondary">No data</Typography>}
          </Stack>
        </CardContent></Card></Grid>
        <Grid item xs={12} md={6}><Card><CardContent>
          <Typography fontWeight={700} sx={{ mb: 1 }}>Peak hours</Typography>
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            {(m.peak_hours || []).map((p: any) => <Chip key={p.hour} label={`${String(p.hour).padStart(2, "0")}:00 · ${p.n}`} />)}
            {(m.peak_hours || []).length === 0 && <Typography variant="caption" color="text.secondary">No data</Typography>}
          </Box>
        </CardContent></Card></Grid>
        <Grid item xs={12} md={6}><Card><CardContent>
          <Typography fontWeight={700} sx={{ mb: 1 }}>Sentiment</Typography>
          <Stack direction="row" spacing={3}>
            {Object.entries(m.sentiment || {}).map(([k, v]: any) => (
              <Box key={k}><Typography variant="h6">{v}</Typography><Typography variant="caption" color="text.secondary">{k}</Typography></Box>
            ))}
            {Object.keys(m.sentiment || {}).length === 0 && <Typography variant="caption" color="text.secondary">No data</Typography>}
          </Stack>
        </CardContent></Card></Grid>
      </Grid>
    </>
  );
}
