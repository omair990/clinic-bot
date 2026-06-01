import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, Grid, Chip, Button, Typography, Box, Stack } from "@mui/material";
import { GridColDef } from "@mui/x-data-grid";
import { BarChart } from "@mui/x-charts/BarChart";
import EventBusyIcon from "@mui/icons-material/EventBusyOutlined";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, TableSkeleton, QueryError, DataTable, KpiCard, useToast } from "../lib";

const riskColor: Record<string, any> = { low: "success", medium: "warning", high: "error" };

export default function NoShows() {
  const [clinic] = useClinic();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useApiQuery<any>(["no-shows", clinic], `/no-shows?clinic=${clinic}`);
  const act = useMutation({
    mutationFn: (v: { id: number; action: string }) => apiPost(`/no-shows/${v.id}/action`, { action: v.action }),
    onSuccess: (_d, v) => { toast.ok(`Done: ${v.action}`); qc.invalidateQueries({ queryKey: ["no-shows"] }); },
    onError: (e) => toast.err(e instanceof ApiError ? e.message : "Action failed"),
  });
  if (q.isLoading) return <><PageTitle title="No-shows & recovery" /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { rows = [], month_count, reasons = [], risk = {}, reason_labels = {}, is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;

  const cols: GridColDef[] = [
    ...(showClinic ? [{ field: "clinic", headerName: "Clinic", width: 140, valueGetter: (_v: any, r: any) => tenant_names[r.tenant_id] || "—" }] : []),
    { field: "patient_name", headerName: "Patient", width: 150, valueGetter: (v: any) => v || "—" },
    { field: "service", headerName: "Missed", flex: 1, minWidth: 180,
      valueGetter: (v: any, r: any) => `${v || "—"} · ${r.doctor || ""}` },
    { field: "start_at", headerName: "When", width: 150, valueFormatter: (v: any) => fmtDate(v) },
    { field: "risk_band", headerName: "Risk", width: 100, renderCell: (p) => p.value ? <Chip size="small" color={riskColor[p.value] || "default"} label={p.value} variant="outlined" /> : null },
    { field: "stage", headerName: "Stage", width: 120, renderCell: (p) => <Chip size="small" variant="outlined" label={(p.value || "").replace("_", " ")} /> },
    { field: "reason", headerName: "Reason", width: 130, valueGetter: (v: any) => v ? (reason_labels[v] || v) : "—" },
    { field: "actions", headerName: "Actions", width: 240, sortable: false, filterable: false, renderCell: (p) => (
      <Box onClick={(e) => e.stopPropagation()}>
        {p.row.stage === "detected" && <Button size="small" onClick={() => act.mutate({ id: p.row.id, action: "send" })}>Send</Button>}
        {["notified", "followed_up"].includes(p.row.stage) && <Button size="small" onClick={() => act.mutate({ id: p.row.id, action: "resend" })}>Resend</Button>}
        {!["resolved", "inactive"].includes(p.row.stage) && <>
          <Button size="small" color="inherit" onClick={() => act.mutate({ id: p.row.id, action: "resolve" })}>Resolve</Button>
          <Button size="small" color="error" onClick={() => act.mutate({ id: p.row.id, action: "inactive" })}>Inactive</Button>
        </>}
      </Box>) },
  ];

  const reasonData = reasons.map((r: any) => ({ label: reason_labels[r.reason] || r.reason || "—", n: r.n }));

  return (
    <>
      <PageTitle title="No-shows & recovery" right={<ClinicFilter meta={q.data} />} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={3}><KpiCard label="No-shows this month" value={month_count} icon={<EventBusyIcon fontSize="small" />} color="error" /></Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ height: "100%" }}><CardContent>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>Upcoming risk</Typography>
            <Stack direction="row" spacing={3} sx={{ mt: 1.5 }}>
              {[["Low", risk.low, "success.main"], ["Medium", risk.medium, "warning.main"], ["High", risk.high, "error.main"]].map(([l, v, c]: any) => (
                <Box key={l}><Typography variant="h5" sx={{ color: c }}>{v ?? 0}</Typography><Typography variant="caption" color="text.secondary">{l}</Typography></Box>
              ))}
            </Stack>
          </CardContent></Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ height: "100%" }}><CardContent sx={{ pb: 0 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>Why patients missed</Typography>
            {reasonData.length ? (
              <BarChart height={150} layout="horizontal"
                yAxis={[{ scaleType: "band", data: reasonData.map((r: any) => r.label) }]}
                series={[{ data: reasonData.map((r: any) => r.n), color: "#f59e0b" }]}
                margin={{ left: 90, right: 10, top: 10, bottom: 20 }} />
            ) : <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>No reasons recorded yet.</Typography>}
          </CardContent></Card>
        </Grid>
      </Grid>
      <DataTable rows={rows} columns={cols} loading={act.isPending} />
    </>
  );
}
