import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  MenuItem, Select, Stack, Typography, Box, Alert, Card, CardContent, Skeleton, Grid,
  alpha, useTheme, Dialog, DialogTitle, DialogContent, DialogActions,
} from "@mui/material";
import { DataGrid, GridColDef, GridToolbar } from "@mui/x-data-grid";
import { SparkLineChart } from "@mui/x-charts/SparkLineChart";
import { useSnackbar } from "notistack";
import { apiGet } from "./api";

export function useApiQuery<T = any>(key: any[], path: string) {
  return useQuery<T>({ queryKey: key, queryFn: () => apiGet<T>(path) });
}

export function useToast() {
  const { enqueueSnackbar } = useSnackbar();
  return {
    ok: (m: string) => enqueueSnackbar(m, { variant: "success" }),
    err: (m: string) => enqueueSnackbar(m, { variant: "error" }),
    info: (m: string) => enqueueSnackbar(m, { variant: "info" }),
  };
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export function PageTitle({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <Stack direction="row" alignItems="flex-start" justifyContent="space-between"
      sx={{ mb: 3, gap: 2, flexWrap: "wrap" }}>
      <Box>
        <Typography variant="h5">{title}</Typography>
        {subtitle && <Typography variant="body2" color="text.secondary">{subtitle}</Typography>}
      </Box>
      <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", flexWrap: "wrap" }}>{right}</Box>
    </Stack>
  );
}

export function useClinic(): [string, (v: string) => void] {
  const [params, setParams] = useSearchParams();
  const clinic = params.get("clinic") || "";
  const set = (v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set("clinic", v); else next.delete("clinic");
    setParams(next);
  };
  return [clinic, set];
}

interface Meta { is_super?: boolean; clinics?: { id: number; name: string }[]; selected_clinic?: number | null; }

export function ClinicFilter({ meta }: { meta?: Meta }) {
  const [clinic, setClinic] = useClinic();
  if (!meta?.is_super) return null;
  return (
    <Select size="small" value={clinic} displayEmpty
      onChange={(e) => setClinic(String(e.target.value))} sx={{ minWidth: 200 }}>
      <MenuItem value="">All clinics</MenuItem>
      {meta.clinics?.map((c) => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
    </Select>
  );
}

// --- loading / error -----------------------------------------------------------
export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <Card><CardContent>
      <Skeleton variant="text" width={180} height={32} sx={{ mb: 1 }} />
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} variant="rounded" height={40} sx={{ my: 0.8, opacity: 1 - i * 0.08 }} />
      ))}
    </CardContent></Card>
  );
}

export function CardsSkeleton({ count = 6 }: { count?: number }) {
  return (
    <Grid container spacing={2}>
      {Array.from({ length: count }).map((_, i) => (
        <Grid item xs={6} md={4} xl={2} key={i}>
          <Skeleton variant="rounded" height={104} />
        </Grid>
      ))}
    </Grid>
  );
}

export function Loading() {
  return (
    <Box>
      <Skeleton variant="rounded" height={120} sx={{ mb: 2 }} />
      <Skeleton variant="rounded" height={280} />
    </Box>
  );
}

export function QueryError({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : "Failed to load";
  return <Alert severity="error" variant="outlined" sx={{ my: 2 }}>{msg}</Alert>;
}

export interface DetailField { label: string; value: React.ReactNode; full?: boolean }

export function DetailDialog({ open, onClose, title, subtitle, fields, actions }: {
  open: boolean; onClose: () => void; title: React.ReactNode; subtitle?: React.ReactNode;
  fields: DetailField[]; actions?: React.ReactNode;
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ pb: subtitle ? 0.5 : 2 }}>
        {title}
        {subtitle && <Typography variant="body2" color="text.secondary">{subtitle}</Typography>}
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={1.5}>
          {fields.map((f, i) => f.full ? (
            <Box key={i}>
              <Typography variant="caption" color="text.secondary" fontWeight={600}>{f.label}</Typography>
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", mt: 0.3 }}>{f.value || "—"}</Typography>
            </Box>
          ) : (
            <Stack key={i} direction="row" spacing={2} alignItems="center">
              <Typography variant="body2" color="text.secondary" sx={{ minWidth: 130 }}>{f.label}</Typography>
              <Box sx={{ flex: 1, minWidth: 0 }}>{f.value ?? <span style={{ opacity: 0.5 }}>—</span>}</Box>
            </Stack>
          ))}
        </Stack>
      </DialogContent>
      {actions && <DialogActions sx={{ px: 3, py: 2 }}>{actions}</DialogActions>}
    </Dialog>
  );
}

export function EmptyState({ text }: { text: string }) {
  return (
    <Box sx={{ textAlign: "center", py: 8, color: "text.secondary" }}>
      <Typography variant="body2">{text}</Typography>
    </Box>
  );
}

// --- animated counter ----------------------------------------------------------
// Eases a number toward its latest value so live KPI updates feel alive rather than jump.
export function AnimatedNumber({ value }: { value: number }) {
  const [display, setDisplay] = useState(value);
  const prev = useRef(value);
  useEffect(() => {
    const from = prev.current, to = value;
    prev.current = value;
    if (from === to) { setDisplay(to); return; }
    const dur = 650, start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(Math.round(from + (to - from) * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <>{display.toLocaleString()}</>;
}

// --- KPI card + sparkline ------------------------------------------------------
export function KpiCard({ label, value, icon, color = "primary", spark }: {
  label: string; value: React.ReactNode; icon?: React.ReactNode;
  color?: "primary" | "secondary" | "success" | "warning" | "error" | "info";
  spark?: number[];
}) {
  const t = useTheme();
  const c = (t.palette as any)[color].main as string;
  return (
    <Card sx={{
      height: "100%", position: "relative", overflow: "hidden",
      transition: "transform .18s ease, box-shadow .18s ease",
      "&:hover": { transform: "translateY(-2px)", boxShadow: (th) => th.shadows[6] },
      "&::before": {
        content: '""', position: "absolute", inset: 0, pointerEvents: "none",
        background: `radial-gradient(120% 100% at 100% 0%, ${alpha(c, 0.14)}, transparent 60%)`,
      },
    }}>
      <CardContent sx={{ position: "relative" }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>{label}</Typography>
          {icon && (
            <Box sx={{ width: 30, height: 30, borderRadius: 2, display: "grid", placeItems: "center",
              color: c, bgcolor: alpha(c, 0.14) }}>{icon}</Box>
          )}
        </Stack>
        <Typography variant="h4" sx={{ mt: 0.5 }}>
          {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
        </Typography>
        {spark && spark.length > 1 && (
          <Box sx={{ mt: 0.5, height: 32 }}>
            <SparkLineChart data={spark} height={32} curve="natural" area
              colors={[c]} showTooltip={false} />
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

// --- styled DataGrid wrapper ---------------------------------------------------
export function DataTable({ rows, columns, getRowId, loading, density = "standard", onRowClick }: {
  rows: any[]; columns: GridColDef[]; getRowId?: (r: any) => any;
  loading?: boolean; density?: "compact" | "standard" | "comfortable";
  onRowClick?: (row: any) => void;
}) {
  // Controlled pagination + autoHeight so "Rows per page" reliably re-renders and the grid
  // grows to fit the selected page (no fixed-height clipping / inner scroll surprises).
  const [paginationModel, setPaginationModel] = useState({ pageSize: 10, page: 0 });
  return (
    <Card sx={{ p: 0, overflow: "hidden" }}>
      <DataGrid
        autoHeight
        rows={rows} columns={columns} getRowId={getRowId} loading={loading}
        density={density}
        paginationModel={paginationModel}
        onPaginationModelChange={setPaginationModel}
        pageSizeOptions={[10, 25, 50, 100]}
        slots={{ toolbar: GridToolbar }}
        slotProps={{ toolbar: { showQuickFilter: true, csvOptions: { allColumns: true } } }}
        disableRowSelectionOnClick
        onRowClick={onRowClick ? (p) => onRowClick(p.row) : undefined}
        sx={{
          border: 0,
          "& .MuiDataGrid-columnHeaders": { bgcolor: (t) => alpha(t.palette.text.primary, 0.04) },
          "& .MuiDataGrid-cell:focus, & .MuiDataGrid-cell:focus-within": { outline: "none" },
          "& .MuiDataGrid-row:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
          ...(onRowClick ? { "& .MuiDataGrid-row": { cursor: "pointer" } } : {}),
        }}
      />
    </Card>
  );
}
