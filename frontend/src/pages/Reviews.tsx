import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Grid, Chip, Rating, Typography, Button } from "@mui/material";
import { GridColDef } from "@mui/x-data-grid";
import StarIcon from "@mui/icons-material/StarRounded";
import CheckIcon from "@mui/icons-material/TaskAltOutlined";
import PercentIcon from "@mui/icons-material/PercentOutlined";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, TableSkeleton, QueryError, DataTable, KpiCard, DetailDialog } from "../lib";

export default function Reviews() {
  const nav = useNavigate();
  const [clinic] = useClinic();
  const [sel, setSel] = useState<any | null>(null);
  const q = useApiQuery<any>(["reviews", clinic], `/reviews?clinic=${clinic}`);
  if (q.isLoading) return <><PageTitle title="Patient reviews" /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { rows = [], stats = {}, is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const rate = stats.requested ? Math.floor((stats.responded / stats.requested) * 100) : 0;

  const cols: GridColDef[] = [
    ...(showClinic ? [{ field: "clinic", headerName: "Clinic", width: 140, valueGetter: (_v: any, r: any) => tenant_names[r.tenant_id] || "—" }] : []),
    { field: "patient_name", headerName: "Patient", width: 150, valueGetter: (v: any) => v || "—" },
    { field: "service", headerName: "Visit", width: 160, valueGetter: (v: any, r: any) => `${v || "—"}${r.doctor ? " · " + r.doctor : ""}` },
    { field: "rating", headerName: "Rating", width: 150, renderCell: (p) => p.value ? <Rating value={p.value} readOnly size="small" /> : "—" },
    { field: "comment", headerName: "Comment", flex: 1, minWidth: 200, valueGetter: (v: any) => v || "" },
    { field: "stage", headerName: "Status", width: 120, renderCell: (p) => <Chip size="small" color={p.value === "done" ? "success" : "warning"} variant="outlined" label={p.value === "done" ? "received" : "awaiting"} /> },
    { field: "responded_at", headerName: "When", width: 150, valueGetter: (v: any, r: any) => v || r.created_at, valueFormatter: (v: any) => fmtDate(v) },
  ];

  return (
    <>
      <PageTitle title="Patient reviews" right={<ClinicFilter meta={q.data} />} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={4}><KpiCard label="Average rating" color="warning" icon={<StarIcon fontSize="small" />}
          value={<>{stats.avg_rating != null ? stats.avg_rating : "—"} <Typography component="span" variant="h6" color="warning.main">★</Typography></>} /></Grid>
        <Grid item xs={12} md={4}><KpiCard label="Reviews received" value={stats.responded ?? 0} color="success" icon={<CheckIcon fontSize="small" />} /></Grid>
        <Grid item xs={12} md={4}><KpiCard label={`Response rate (${stats.responded ?? 0}/${stats.requested ?? 0})`} value={`${rate}%`} color="info" icon={<PercentIcon fontSize="small" />} /></Grid>
      </Grid>
      <DataTable rows={rows} columns={cols} onRowClick={setSel} />

      <DetailDialog open={!!sel} onClose={() => setSel(null)} title="Review"
        subtitle={sel ? fmtDate(sel.responded_at || sel.created_at) : ""}
        fields={sel ? [
          { label: "Patient", value: `${sel.patient_name || "—"} · +${sel.wa_user}` },
          { label: "Visit", value: `${sel.service || "—"}${sel.doctor ? " · " + sel.doctor : ""}` },
          { label: "Rating", value: sel.rating ? <Rating value={sel.rating} readOnly size="small" /> : "—" },
          { label: "Status", value: <Chip size="small" color={sel.stage === "done" ? "success" : "warning"} variant="outlined" label={sel.stage === "done" ? "received" : "awaiting"} /> },
          { label: "Comment", value: sel.comment || "—", full: true },
        ] : []}
        actions={<>
          <Button onClick={() => setSel(null)}>Close</Button>
          {sel && <Button variant="contained" onClick={() => nav(`/patients/${sel.wa_user}`)}>View patient</Button>}
        </>} />
    </>
  );
}
