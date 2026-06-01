import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Chip, Button, Stack, ToggleButton, ToggleButtonGroup, Box } from "@mui/material";
import { GridColDef } from "@mui/x-data-grid";
import { useSearchParams } from "react-router-dom";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, TableSkeleton, QueryError, DataTable, useToast } from "../lib";

const statusColor: Record<string, any> = { confirmed: "success", completed: "info", cancelled: "default", no_show: "warning" };
const riskColor: Record<string, any> = { low: "success", medium: "warning", high: "error" };

export default function Appointments() {
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const qc = useQueryClient();
  const toast = useToast();
  const path = `/appointments?clinic=${clinic}${status ? `&status=${status}` : ""}`;
  const q = useApiQuery<any>(["appointments", clinic, status], path);
  const act = useMutation({
    mutationFn: (v: { id: number; status: string }) => apiPost(`/appointments/${v.id}/status`, { status: v.status }),
    onSuccess: (_d, v) => { toast.ok(`Marked ${v.status.replace("_", " ")}`); qc.invalidateQueries({ queryKey: ["appointments"] }); },
    onError: (e) => toast.err(e instanceof ApiError ? e.message : "Update failed"),
  });
  const setStatus = (s: string) => { const n = new URLSearchParams(params); if (s) n.set("status", s); else n.delete("status"); setParams(n); };

  if (q.isLoading) return <><PageTitle title="Appointments" /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { rows = [], is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;

  const cols: GridColDef[] = [
    ...(showClinic ? [{ field: "clinic", headerName: "Clinic", width: 140, valueGetter: (_v: any, r: any) => tenant_names[r.tenant_id] || "—" }] : []),
    { field: "patient_name", headerName: "Patient", width: 150, valueGetter: (v: any) => v || "—" },
    { field: "wa_user", headerName: "Phone", width: 140, valueGetter: (v: any) => `+${v}` },
    { field: "service", headerName: "Service", width: 150, valueGetter: (v: any) => v || "—" },
    { field: "doctor", headerName: "Doctor", width: 150, valueGetter: (v: any) => v || "—" },
    { field: "start_at", headerName: "When", width: 150, valueFormatter: (v: any) => fmtDate(v) },
    { field: "risk_band", headerName: "Risk", width: 110, renderCell: (p) => p.value
        ? <Chip size="small" color={riskColor[p.value] || "default"} label={`${p.value}${p.row.risk_score != null ? " " + p.row.risk_score : ""}`} variant="outlined" /> : null },
    { field: "status", headerName: "Status", width: 120, renderCell: (p) => <Chip size="small" color={statusColor[p.value] || "default"} label={p.value} /> },
    { field: "actions", headerName: "Actions", width: 230, sortable: false, filterable: false, renderCell: (p) => (
      <Box onClick={(e) => e.stopPropagation()}>
        {p.row.status !== "completed" && <Button size="small" onClick={() => act.mutate({ id: p.row.id, status: "completed" })}>Complete</Button>}
        {p.row.status !== "no_show" && <Button size="small" color="warning" onClick={() => act.mutate({ id: p.row.id, status: "no_show" })}>No-show</Button>}
        {p.row.status !== "cancelled" && <Button size="small" color="inherit" onClick={() => act.mutate({ id: p.row.id, status: "cancelled" })}>Cancel</Button>}
      </Box>) },
  ];

  return (
    <>
      <PageTitle title="Appointments" subtitle={`${rows.length} shown`} right={
        <Stack direction="row" spacing={1.5} alignItems="center">
          <ToggleButtonGroup size="small" exclusive value={status} onChange={(_e, v) => setStatus(v ?? "")}>
            <ToggleButton value="">All</ToggleButton>
            <ToggleButton value="confirmed">Confirmed</ToggleButton>
            <ToggleButton value="completed">Completed</ToggleButton>
            <ToggleButton value="cancelled">Cancelled</ToggleButton>
          </ToggleButtonGroup>
          <ClinicFilter meta={q.data} />
        </Stack>} />
      <DataTable rows={rows} columns={cols} loading={act.isPending} />
    </>
  );
}
