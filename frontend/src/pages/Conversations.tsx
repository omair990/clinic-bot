import { useNavigate } from "react-router-dom";
import { Chip, Typography } from "@mui/material";
import { GridColDef } from "@mui/x-data-grid";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, TableSkeleton, QueryError, DataTable } from "../lib";

const intentColor: Record<string, any> = {
  appointment: "success", emergency: "error", handover: "warning", complaint: "warning",
};

export default function Conversations() {
  const nav = useNavigate();
  const [clinic] = useClinic();
  const q = useApiQuery<any>(["conversations", clinic], `/conversations?clinic=${clinic}`);
  if (q.isLoading) return <><PageTitle title="Conversations" /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { rows = [], is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;

  const cols: GridColDef[] = [
    ...(showClinic ? [{ field: "clinic", headerName: "Clinic", width: 150,
      valueGetter: (_v: any, r: any) => tenant_names[r.tenant_id] || "—" }] : []),
    { field: "wa_user", headerName: "User", width: 150, valueGetter: (v: any) => `+${v}` },
    { field: "last_message", headerName: "Last message", flex: 1, minWidth: 240,
      renderCell: (p) => (
        <Typography variant="body2" noWrap>
          <span style={{ opacity: 0.5 }}>{p.row.last_direction === "in" ? "← " : "→ "}</span>{p.value}
        </Typography>) },
    { field: "last_intent", headerName: "Class", width: 130, sortable: false,
      renderCell: (p) => p.value ? <Chip size="small" label={p.value} color={intentColor[p.value] || "default"} variant="outlined" /> : null },
    { field: "lead_band", headerName: "Lead", width: 90,
      renderCell: (p) => p.value ? <Chip size="small" label={p.value} variant="outlined" /> : null },
    { field: "msg_count", headerName: "Msgs", width: 80, type: "number" },
    { field: "last_at", headerName: "Last activity", width: 150, valueFormatter: (v: any) => fmtDate(v) },
    { field: "needs_human", headerName: "Flag", width: 120, sortable: false,
      renderCell: (p) => p.value ? <Chip size="small" color="error" label="needs human" /> : null },
  ];

  return (
    <>
      <PageTitle title="Conversations" subtitle={`${rows.length} active`} right={<ClinicFilter meta={q.data} />} />
      <DataTable rows={rows} columns={cols} getRowId={(r) => r.wa_user}
        onRowClick={(r) => nav(`/conversations/${r.wa_user}`)} />
    </>
  );
}
