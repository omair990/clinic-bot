import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Grid, Table, TableHead, TableRow, TableCell, TableBody, Chip, Button,
  Typography, LinearProgress, Box, Stack,
} from "@mui/material";
import { apiPost } from "../api";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, Loading, QueryError } from "../lib";

const riskColor: Record<string, any> = { low: "success", medium: "warning", high: "error" };

export default function NoShows() {
  const [clinic] = useClinic();
  const qc = useQueryClient();
  const q = useApiQuery<any>(["no-shows", clinic], `/no-shows?clinic=${clinic}`);
  const act = useMutation({
    mutationFn: (v: { id: number; action: string }) => apiPost(`/no-shows/${v.id}/action`, { action: v.action }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["no-shows"] }),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { rows = [], month_count, reasons = [], risk = {}, reason_labels = {}, is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const totalReasons = reasons.reduce((s: number, r: any) => s + r.n, 0) || 1;

  return (
    <>
      <PageTitle title="No-shows & recovery" right={<ClinicFilter meta={q.data} />} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={4}>
          <Card><CardContent>
            <Typography variant="h4" fontWeight={700}>{month_count}</Typography>
            <Typography variant="caption" color="text.secondary">No-shows this month</Typography>
          </CardContent></Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card><CardContent>
            <Typography variant="caption" color="text.secondary">Why patients missed</Typography>
            <Stack spacing={0.5} sx={{ mt: 1 }}>
              {reasons.map((r: any) => (
                <Box key={r.reason}>
                  <Stack direction="row" justifyContent="space-between"><Typography variant="caption">{reason_labels[r.reason] || r.reason || "—"}</Typography><Typography variant="caption">{r.n}</Typography></Stack>
                  <LinearProgress variant="determinate" value={(r.n / totalReasons) * 100} color="warning" sx={{ height: 5, borderRadius: 3 }} />
                </Box>
              ))}
              {reasons.length === 0 && <Typography variant="caption" color="text.secondary">No reasons recorded.</Typography>}
            </Stack>
          </CardContent></Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card><CardContent>
            <Typography variant="caption" color="text.secondary">Upcoming risk</Typography>
            <Stack direction="row" spacing={3} sx={{ mt: 1 }}>
              {[["Low", risk.low, "success.main"], ["Medium", risk.medium, "warning.main"], ["High", risk.high, "error.main"]].map(([l, v, c]: any) => (
                <Box key={l}><Typography variant="h6" sx={{ color: c }}>{v ?? 0}</Typography><Typography variant="caption" color="text.secondary">{l}</Typography></Box>
              ))}
            </Stack>
          </CardContent></Card>
        </Grid>
      </Grid>
      <Card>
        <Table size="small">
          <TableHead><TableRow>
            {showClinic && <TableCell>Clinic</TableCell>}
            <TableCell>Patient</TableCell><TableCell>Missed</TableCell><TableCell>Risk</TableCell>
            <TableCell>Stage</TableCell><TableCell>Outcome</TableCell><TableCell>Detected</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {rows.map((f: any) => (
              <TableRow key={f.id} hover>
                {showClinic && <TableCell><Typography variant="caption" color="text.secondary">{tenant_names[f.tenant_id] || "—"}</Typography></TableCell>}
                <TableCell>{f.patient_name || "—"}<Typography variant="caption" color="text.secondary" display="block">+{f.wa_user}</Typography></TableCell>
                <TableCell>{f.service || "—"}<Typography variant="caption" color="text.secondary" display="block">{f.doctor || ""} · {fmtDate(f.start_at)}</Typography></TableCell>
                <TableCell>{f.risk_band && <Chip size="small" color={riskColor[f.risk_band] || "default"} label={f.risk_band} />}</TableCell>
                <TableCell><Chip size="small" variant="outlined" label={(f.stage || "").replace("_", " ")} /></TableCell>
                <TableCell>{f.outcome || "—"}</TableCell>
                <TableCell><Typography variant="caption" color="text.secondary">{fmtDate(f.created_at)}</Typography></TableCell>
                <TableCell align="right">
                  {f.stage === "detected" && <Button size="small" onClick={() => act.mutate({ id: f.id, action: "send" })}>Send</Button>}
                  {["notified", "followed_up"].includes(f.stage) && <Button size="small" onClick={() => act.mutate({ id: f.id, action: "resend" })}>Resend</Button>}
                  {!["resolved", "inactive"].includes(f.stage) && <>
                    <Button size="small" color="inherit" onClick={() => act.mutate({ id: f.id, action: "resolve" })}>Resolve</Button>
                    <Button size="small" color="error" onClick={() => act.mutate({ id: f.id, action: "inactive" })}>Inactive</Button>
                  </>}
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && <TableRow><TableCell colSpan={showClinic ? 8 : 7} align="center" sx={{ py: 6, color: "text.secondary" }}>No no-shows recorded</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
