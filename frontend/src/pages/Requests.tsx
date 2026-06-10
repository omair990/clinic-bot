import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box, Card, CardContent, Grid, Chip, Button, Typography, Stack, Avatar, Link,
  ToggleButton, ToggleButtonGroup, alpha, useTheme,
} from "@mui/material";
import MoveToInboxIcon from "@mui/icons-material/MoveToInboxOutlined";
import WhatsAppIcon from "@mui/icons-material/WhatsApp";
import CheckIcon from "@mui/icons-material/CheckRounded";
import HandshakeIcon from "@mui/icons-material/HandshakeOutlined";
import BlockIcon from "@mui/icons-material/BlockOutlined";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, TableSkeleton, QueryError, EmptyState, KpiCard, useToast, fmtDate, fmtTime } from "../lib";
import { useT } from "../i18n";

type Req = {
  id: number; name: string; phone: string; clinic_name?: string | null;
  message?: string | null; lang?: string | null; status: string; created_at: string;
};

const STATUS_COLOR: Record<string, "warning" | "info" | "success" | "default"> = {
  new: "warning", contacted: "info", converted: "success", rejected: "default",
};

export default function Requests() {
  const t = useT();
  const theme = useTheme();
  const toast = useToast();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<string>("");
  const q = useApiQuery<any>(["requests"], "/requests");

  const act = useMutation({
    mutationFn: (v: { id: number; status: string }) => apiPost(`/requests/${v.id}/status`, { status: v.status }),
    onSuccess: () => { toast.ok(t("requests.updated")); qc.invalidateQueries({ queryKey: ["requests"] }); },
    onError: (e) => toast.err(e instanceof ApiError ? e.message : t("requests.updateFailed")),
  });

  const rows: Req[] = q.data?.rows ?? [];
  const counts = q.data?.counts ?? {};
  const filtered = useMemo(
    () => (filter ? rows.filter((r) => r.status === filter) : rows),
    [rows, filter],
  );

  if (q.isLoading) return <><PageTitle title={t("requests.title")} subtitle={t("requests.subtitle")} /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;

  const statusLabel = (s: string) => t(`requests.status${s.charAt(0).toUpperCase()}${s.slice(1)}`);

  return (
    <>
      <PageTitle title={t("requests.title")} subtitle={t("requests.subtitle")}
        right={<Button variant="outlined" onClick={() => q.refetch()}>{t("requests.refresh")}</Button>} />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><KpiCard label={t("requests.kpiTotal")} value={counts.total ?? 0} icon={<MoveToInboxIcon fontSize="small" />} /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("requests.kpiNew")} value={counts.new ?? 0} icon={<MoveToInboxIcon fontSize="small" />} color="warning" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("requests.kpiContacted")} value={counts.contacted ?? 0} icon={<HandshakeIcon fontSize="small" />} color="info" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label={t("requests.kpiConverted")} value={counts.converted ?? 0} icon={<CheckIcon fontSize="small" />} color="success" /></Grid>
      </Grid>

      <ToggleButtonGroup size="small" value={filter} exclusive sx={{ mb: 2 }}
        onChange={(_e, v) => setFilter(v ?? "")}>
        <ToggleButton value="">{t("requests.all")}</ToggleButton>
        {(q.data?.statuses ?? []).map((s: string) => (
          <ToggleButton key={s} value={s}>{statusLabel(s)}</ToggleButton>
        ))}
      </ToggleButtonGroup>

      {filtered.length === 0 ? (
        <EmptyState text={t("requests.empty")} />
      ) : (
        <Stack spacing={1.5}>
          {filtered.map((r) => {
            const digits = (r.phone || "").replace(/[^\d]/g, "");
            return (
              <Card key={r.id}>
                <CardContent>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }} justifyContent="space-between">
                    <Stack direction="row" spacing={1.5} alignItems="center" sx={{ minWidth: 0 }}>
                      <Avatar sx={{ bgcolor: alpha(theme.palette.primary.main, 0.15), color: "primary.main", fontWeight: 800 }}>
                        {(r.name || "?").charAt(0)}
                      </Avatar>
                      <Box sx={{ minWidth: 0 }}>
                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                          <Typography fontWeight={800}>{r.name}</Typography>
                          <Chip size="small" label={statusLabel(r.status)} color={STATUS_COLOR[r.status] || "default"} />
                          {r.lang && <Chip size="small" variant="outlined" label={r.lang.toUpperCase()} />}
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                          {r.clinic_name ? `${r.clinic_name} · ` : ""}
                          <Link href={`https://wa.me/${digits}`} target="_blank" rel="noopener"
                            sx={{ display: "inline-flex", alignItems: "center", gap: 0.4 }}>
                            <WhatsAppIcon sx={{ fontSize: 15, color: "#22c55e" }} /> {r.phone}
                          </Link>
                        </Typography>
                        {r.message && <Typography variant="body2" sx={{ mt: 0.5 }}>{r.message}</Typography>}
                        <Typography variant="caption" color="text.secondary">
                          {t("requests.submitted")}: {fmtDate(r.created_at)} {fmtTime(r.created_at)}
                        </Typography>
                      </Box>
                    </Stack>
                    <Stack direction="row" spacing={1} flexShrink={0} flexWrap="wrap">
                      <Button size="small" variant="outlined" color="info" disabled={act.isPending || r.status === "contacted"}
                        startIcon={<HandshakeIcon />} onClick={() => act.mutate({ id: r.id, status: "contacted" })}>
                        {t("requests.markContacted")}
                      </Button>
                      <Button size="small" variant="outlined" color="success" disabled={act.isPending || r.status === "converted"}
                        startIcon={<CheckIcon />} onClick={() => act.mutate({ id: r.id, status: "converted" })}>
                        {t("requests.markConverted")}
                      </Button>
                      <Button size="small" variant="outlined" color="error" disabled={act.isPending || r.status === "rejected"}
                        startIcon={<BlockIcon />} onClick={() => act.mutate({ id: r.id, status: "rejected" })}>
                        {t("requests.markRejected")}
                      </Button>
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>
            );
          })}
        </Stack>
      )}
    </>
  );
}
