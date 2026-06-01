import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { MenuItem, Select, Stack, Typography, Box, CircularProgress, Alert } from "@mui/material";
import { apiGet } from "./api";

export function useApiQuery<T = any>(key: any[], path: string) {
  return useQuery<T>({ queryKey: key, queryFn: () => apiGet<T>(path) });
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export function PageTitle({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
      <Typography variant="h5">{title}</Typography>
      {right}
    </Stack>
  );
}

export function useClinic(): [string, (v: string) => void] {
  const [params, setParams] = useSearchParams();
  const clinic = params.get("clinic") || "";
  const set = (v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set("clinic", v);
    else next.delete("clinic");
    setParams(next);
  };
  return [clinic, set];
}

interface Meta {
  is_super?: boolean;
  clinics?: { id: number; name: string }[];
  selected_clinic?: number | null;
}

export function ClinicFilter({ meta }: { meta?: Meta }) {
  const [clinic, setClinic] = useClinic();
  if (!meta?.is_super) return null;
  return (
    <Select
      size="small"
      value={clinic}
      displayEmpty
      onChange={(e) => setClinic(String(e.target.value))}
      sx={{ minWidth: 200, bgcolor: "#fff" }}
    >
      <MenuItem value="">All clinics</MenuItem>
      {meta.clinics?.map((c) => (
        <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>
      ))}
    </Select>
  );
}

export function Loading() {
  return (
    <Box sx={{ display: "grid", placeItems: "center", py: 8 }}>
      <CircularProgress />
    </Box>
  );
}

export function QueryError({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : "Failed to load";
  return <Alert severity="error" sx={{ my: 2 }}>{msg}</Alert>;
}
