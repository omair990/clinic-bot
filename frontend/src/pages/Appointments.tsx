import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, Table, TableHead, TableRow, TableCell, TableBody, Chip, Button, Stack, ToggleButton,
  ToggleButtonGroup, Typography,
} from "@mui/material";
import { useSearchParams } from "react-router-dom";
import { apiPost } from "../api";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, Loading, QueryError } from "../lib";

const statusColor: Record<string, any> = {
  confirmed: "success", completed: "info", cancelled: "default", no_show: "warning",
};
const riskColor: Record<string, any> = { low: "success", medium: "warning", high: "error" };

export default function Appointments() {
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const qc = useQueryClient();
  const path = `/appointments?clinic=${clinic}${status ? `&status=${status}` : ""}`;
  const q = useApiQuery<any>(["appointments", clinic, status], path);
  const act = useMutation({
    mutationFn: (v: { id: number; status: string }) => apiPost(`/appointments/${v.id}/status`, { status: v.status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["appointments"] }),
  });

  const setStatus = (s: string) => {
    const next = new URLSearchParams(params);
    if (s) next.set("status", s); else next.delete("status");
    setParams(next);
  };

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { rows = [], is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const span = showClinic ? 9 : 8;

  return (
    <>
      <PageTitle title="Appointments" right={<ClinicFilter meta={q.data} />} />
      <Stack direction="row" spacing={2} sx={{ mb: 2 }} alignItems="center">
        <ToggleButtonGroup size="small" exclusive value={status} onChange={(_, v) => setStatus(v ?? "")}>
          <ToggleButton value="">All</ToggleButton>
          <ToggleButton value="confirmed">Confirmed</ToggleButton>
          <ToggleButton value="completed">Completed</ToggleButton>
          <ToggleButton value="cancelled">Cancelled</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <Card>
        <Table size="small">
          <TableHead>
            <TableRow>
              {showClinic && <TableCell>Clinic</TableCell>}
              <TableCell>Patient</TableCell>
              <TableCell>Service</TableCell>
              <TableCell>Doctor</TableCell>
              <TableCell>When</TableCell>
              <TableCell>Risk</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((a: any) => (
              <TableRow key={a.id} hover>
                {showClinic && <TableCell><Typography variant="caption" color="text.secondary">{tenant_names[a.tenant_id] || "—"}</Typography></TableCell>}
                <TableCell>{a.patient_name || "—"}<Typography variant="caption" color="text.secondary" display="block">+{a.wa_user}</Typography></TableCell>
                <TableCell>{a.service || "—"}</TableCell>
                <TableCell>{a.doctor || "—"}</TableCell>
                <TableCell>{fmtDate(a.start_at)}</TableCell>
                <TableCell>{a.risk_band && <Chip size="small" color={riskColor[a.risk_band] || "default"} label={`${a.risk_band}${a.risk_score != null ? " " + a.risk_score : ""}`} />}</TableCell>
                <TableCell><Chip size="small" color={statusColor[a.status] || "default"} label={a.status} /></TableCell>
                <TableCell align="right">
                  {a.status !== "completed" && <Button size="small" onClick={() => act.mutate({ id: a.id, status: "completed" })}>Complete</Button>}
                  {a.status !== "no_show" && <Button size="small" color="warning" onClick={() => act.mutate({ id: a.id, status: "no_show" })}>No-show</Button>}
                  {a.status !== "cancelled" && <Button size="small" color="inherit" onClick={() => act.mutate({ id: a.id, status: "cancelled" })}>Cancel</Button>}
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && <TableRow><TableCell colSpan={span} align="center" sx={{ py: 6, color: "text.secondary" }}>No appointments</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
