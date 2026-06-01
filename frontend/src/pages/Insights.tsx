import { Card, CardContent, Grid, Typography, ToggleButton, ToggleButtonGroup, Stack, Box } from "@mui/material";
import { BarChart } from "@mui/x-charts/BarChart";
import { PieChart } from "@mui/x-charts/PieChart";
import { useSearchParams } from "react-router-dom";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, TableSkeleton, QueryError, KpiCard } from "../lib";

const PIE = ["#14b8a6", "#6366f1", "#f59e0b", "#ef4444", "#38bdf8", "#a78bfa"];

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return <Card sx={{ height: "100%" }}><CardContent>
    <Typography variant="subtitle2" sx={{ mb: 1 }}>{title}</Typography>{children}
  </CardContent></Card>;
}

export default function Insights() {
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const period = params.get("period") || "day";
  const q = useApiQuery<any>(["insights", clinic, period], `/insights?clinic=${clinic}&period=${period}`);
  const setPeriod = (p: string) => { const n = new URLSearchParams(params); n.set("period", p); setParams(n); };

  if (q.isLoading) return <><PageTitle title="Business insights" /><TableSkeleton rows={4} /></>;
  if (q.error) return <QueryError error={q.error} />;
  const r = q.data.report || {}; const m = r.metrics || {};
  const inquiries = (m.top_inquiries || []).map((t: any) => ({ label: t.intent, n: t.n }));
  const doctors = (m.top_doctors || []).map((t: any) => ({ label: t.doctor, n: t.n }));
  const peaks = (m.peak_hours || []).map((p: any) => ({ label: `${String(p.hour).padStart(2, "0")}:00`, n: p.n }));
  const sentiment = Object.entries(m.sentiment || {}).map(([k, v]: any, i) => ({ id: i, value: v, label: k }));
  const leads = Object.entries(m.lead_mix || {}).map(([k, v]: any, i) => ({ id: i, value: v, label: k }));

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
        <Card sx={{ mb: 2 }}><CardContent>
          <Typography variant="body2" color="text.secondary">{r.narrative}</Typography>
        </CardContent></Card>
      )}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><KpiCard label="Messages" value={m.messages ?? 0} color="primary" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Users" value={m.users ?? 0} color="secondary" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Voice share" value={`${m.voice_share_pct ?? 0}%`} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Missed visits" value={m.no_shows ?? 0} color="error" /></Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}><ChartCard title="Top inquiries">
          {inquiries.length ? <BarChart height={220} layout="horizontal"
            yAxis={[{ scaleType: "band", data: inquiries.map((i: any) => i.label) }]}
            series={[{ data: inquiries.map((i: any) => i.n), color: "#14b8a6" }]}
            margin={{ left: 90, right: 10 }} /> : <Empty />}
        </ChartCard></Grid>
        <Grid item xs={12} md={6}><ChartCard title="Top doctors">
          {doctors.length ? <BarChart height={220} layout="horizontal"
            yAxis={[{ scaleType: "band", data: doctors.map((d: any) => d.label) }]}
            series={[{ data: doctors.map((d: any) => d.n), color: "#6366f1" }]}
            margin={{ left: 110, right: 10 }} /> : <Empty />}
        </ChartCard></Grid>
        <Grid item xs={12} md={4}><ChartCard title="Peak hours">
          {peaks.length ? <BarChart height={200} xAxis={[{ scaleType: "band", data: peaks.map((p: any) => p.label) }]}
            series={[{ data: peaks.map((p: any) => p.n), color: "#38bdf8" }]} margin={{ left: 30, right: 10 }} /> : <Empty />}
        </ChartCard></Grid>
        <Grid item xs={12} md={4}><ChartCard title="Sentiment">
          {sentiment.length ? <PieChart height={200} series={[{ data: sentiment, innerRadius: 40, paddingAngle: 2, cornerRadius: 4 }]} colors={PIE} /> : <Empty />}
        </ChartCard></Grid>
        <Grid item xs={12} md={4}><ChartCard title="Lead mix">
          {leads.length ? <PieChart height={200} series={[{ data: leads, innerRadius: 40, paddingAngle: 2, cornerRadius: 4 }]} colors={PIE} /> : <Empty />}
        </ChartCard></Grid>
      </Grid>
    </>
  );
}

function Empty() {
  return <Box sx={{ py: 4, textAlign: "center", color: "text.secondary" }}><Typography variant="caption">No data for this period</Typography></Box>;
}
