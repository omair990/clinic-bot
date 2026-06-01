import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Grid, Table, TableHead, TableRow, TableCell, TableBody, Select, MenuItem,
  Button, Typography,
} from "@mui/material";
import { apiPost } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError } from "../lib";

export default function Plans() {
  const qc = useQueryClient();
  const q = useApiQuery<any>(["plans"], "/plans");
  const setPlan = useMutation({
    mutationFn: (v: { id: number; plan_id: number }) => apiPost(`/tenants/${v.id}/plan`, { plan_id: v.plan_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plans"] }),
  });
  const setStatus = useMutation({
    mutationFn: (v: { id: number; status: string }) => apiPost(`/tenants/${v.id}/status`, { status: v.status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plans"] }),
  });

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { plans = [], tenants = [], period } = q.data;

  return (
    <>
      <PageTitle title="Plans & usage" right={<Typography variant="body2" color="text.secondary">Period {period}</Typography>} />
      <Card sx={{ mb: 3 }}>
        <CardContent><Typography fontWeight={700} sx={{ mb: 1 }}>Clinics</Typography></CardContent>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Clinic</TableCell><TableCell>Plan</TableCell><TableCell>Text usage</TableCell>
            <TableCell>Voice usage</TableCell><TableCell>Status</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {tenants.map((t: any) => (
              <TableRow key={t.id} hover>
                <TableCell>{t.name}<Typography variant="caption" color="text.secondary" display="block">{t.slug}</Typography></TableCell>
                <TableCell>
                  <Select size="small" value={plans.find((p: any) => p.name === t.plan_name)?.id ?? ""}
                    onChange={(e) => setPlan.mutate({ id: t.id, plan_id: Number(e.target.value) })}>
                    {plans.map((p: any) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
                  </Select>
                </TableCell>
                <TableCell>{t.text_count} / {t.monthly_text_quota ?? "∞"}</TableCell>
                <TableCell>{t.voice_enabled ? `${t.voice_count} / ${t.monthly_voice_quota ?? "∞"}` : "off"}</TableCell>
                <TableCell>
                  <Select size="small" value={t.status}
                    onChange={(e) => setStatus.mutate({ id: t.id, status: String(e.target.value) })}>
                    {["active", "suspended", "expired"].map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
                  </Select>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <Card>
        <CardContent><Typography fontWeight={700} sx={{ mb: 1 }}>Packages</Typography></CardContent>
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Name</TableCell><TableCell>Text/mo</TableCell><TableCell>Voice</TableCell>
            <TableCell>Trial</TableCell><TableCell>Price (SAR)</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {plans.map((p: any) => (
              <TableRow key={p.id}>
                <TableCell>{p.name}</TableCell>
                <TableCell>{p.monthly_text_quota ?? "∞"}</TableCell>
                <TableCell>{p.voice_enabled ? (p.monthly_voice_quota ?? "∞") : "off"}</TableCell>
                <TableCell>{p.is_trial ? `${p.trial_days}d` : "—"}</TableCell>
                <TableCell>{p.price_sar ?? "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
