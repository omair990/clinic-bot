import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Chip, Button, Typography, ToggleButton, ToggleButtonGroup, Stack, Box } from "@mui/material";
import { GridColDef } from "@mui/x-data-grid";
import { useSearchParams } from "react-router-dom";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, TableSkeleton, QueryError, DataTable, useToast } from "../lib";

const levelColor: Record<string, any> = { error: "error", warning: "warning", info: "default" };

export default function Issues() {
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const show = params.get("show") || "open";
  const qc = useQueryClient();
  const toast = useToast();
  const q = useApiQuery<any>(["logs", clinic, show], `/logs?clinic=${clinic}&show=${show}`);
  const resolve = useMutation({
    mutationFn: (id: number) => apiPost(`/logs/${id}/resolve`),
    onSuccess: () => { toast.ok("Issue resolved"); qc.invalidateQueries({ queryKey: ["logs"] }); },
    onError: (e) => toast.err(e instanceof ApiError ? e.message : "Failed"),
  });
  const setShow = (s: string) => { const n = new URLSearchParams(params); n.set("show", s); setParams(n); };

  if (q.isLoading) return <><PageTitle title="Issues" /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { events = [], open_count, is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;

  const cols: GridColDef[] = [
    ...(showClinic ? [{ field: "clinic", headerName: "Clinic", width: 140, valueGetter: (_v: any, r: any) => tenant_names[r.tenant_id] || "—" }] : []),
    { field: "created_at", headerName: "When", width: 150, valueFormatter: (v: any) => fmtDate(v) },
    { field: "level", headerName: "Level", width: 110, renderCell: (p) => <Chip size="small" color={levelColor[p.value] || "default"} label={p.value} variant="outlined" /> },
    { field: "category", headerName: "Category", width: 130 },
    { field: "message", headerName: "Issue", flex: 1, minWidth: 240, renderCell: (p) => (
      <Box sx={{ py: 0.5 }}>
        <Typography variant="body2" noWrap>{p.value}</Typography>
        {p.row.detail && <Typography variant="caption" color="text.secondary" noWrap display="block">{p.row.detail}</Typography>}
      </Box>) },
    { field: "actions", headerName: "", width: 110, sortable: false, filterable: false, renderCell: (p) => (
      p.row.resolved
        ? <Typography variant="caption" color="success.main">resolved</Typography>
        : <Button size="small" variant="contained" onClick={(e) => { e.stopPropagation(); resolve.mutate(p.row.id); }}>Resolve</Button>) },
  ];

  return (
    <>
      <PageTitle title="Issues" right={
        <Stack direction="row" spacing={1.5} alignItems="center">
          <ClinicFilter meta={q.data} />
          <ToggleButtonGroup size="small" exclusive value={show} onChange={(_e, v) => v && setShow(v)}>
            <ToggleButton value="open">Open ({open_count})</ToggleButton>
            <ToggleButton value="resolved">Resolved</ToggleButton>
            <ToggleButton value="all">All</ToggleButton>
          </ToggleButtonGroup>
        </Stack>} />
      <DataTable rows={events} columns={cols} loading={resolve.isPending} />
    </>
  );
}
