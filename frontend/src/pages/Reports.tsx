import { useMemo, useState } from "react";
import {
  Box, Card, CardContent, Grid, Stack, Typography, TextField, Button, Chip, Divider,
  ToggleButton, ToggleButtonGroup, alpha,
} from "@mui/material";
import EventIcon from "@mui/icons-material/EventAvailableOutlined";
import CheckIcon from "@mui/icons-material/TaskAltOutlined";
import EventBusyIcon from "@mui/icons-material/EventBusyOutlined";
import PaymentsIcon from "@mui/icons-material/PaymentsOutlined";
import GroupIcon from "@mui/icons-material/GroupOutlined";
import PercentIcon from "@mui/icons-material/PercentOutlined";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdfOutlined";
import DownloadIcon from "@mui/icons-material/FileDownloadOutlined";
import StarIcon from "@mui/icons-material/StarRounded";
import { GridColDef } from "@mui/x-data-grid";
import {
  useApiQuery, PageTitle, ClinicFilter, useClinic, KpiCard, DataTable, TableSkeleton,
  QueryError, EmptyState, fmtDate,
} from "../lib";
import { useT } from "../i18n";
import { useAuth } from "../auth";

type TFn = (key: string, vars?: Record<string, string | number>) => string;

// --- date helpers (local YYYY-MM-DD, no timezone surprises) ---------------------
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function daysAgo(n: number) { const d = new Date(); d.setDate(d.getDate() - n); return iso(d); }
function monthStart() { const d = new Date(); return iso(new Date(d.getFullYear(), d.getMonth(), 1)); }
const today = () => iso(new Date());

const PRESETS = [
  { key: "last7", from: () => daysAgo(6), to: today },
  { key: "last30", from: () => daysAgo(29), to: today },
  { key: "last90", from: () => daysAgo(89), to: today },
  { key: "thisMonth", from: monthStart, to: today },
];

const apptStatus = (t: TFn, s: string) => t(`enums.appt.${s}`, {}) || s;
const money = (v: number | null | undefined, ccy: string) =>
  v == null ? "" : `${ccy} ${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

// --- CSV ------------------------------------------------------------------------
function csvCell(v: unknown): string {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
function downloadCsv(name: string, rows: (string | number | null | undefined)[][]) {
  const body = rows.map((r) => r.map(csvCell).join(",")).join("\n");
  const blob = new Blob(["﻿" + body], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// --- PDF via a styled print window (zero deps; user saves as PDF) ----------------
function escapeHtml(s: unknown): string {
  return String(s ?? "").replace(/[&<>"]/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
}
function printReport(html: string) {
  const w = window.open("", "_blank", "width=900,height=700");
  if (!w) return;
  w.document.write(html);
  w.document.close();
  w.focus();
  // Give the new document a tick to lay out before invoking the print dialog.
  setTimeout(() => w.print(), 350);
}

export default function Reports() {
  const t = useT();
  const { me } = useAuth();
  const [clinic] = useClinic();
  const [from, setFrom] = useState(daysAgo(29));
  const [to, setTo] = useState(today());

  const q = useApiQuery<any>(["reports", clinic, from, to],
    `/reports?clinic=${clinic}&from=${from}&to=${to}`);

  const data = q.data;
  const rep = data?.report;
  const isSuper = data?.is_super;
  const tenantNames: Record<string, string> = data?.tenant_names ?? {};
  const showClinic = isSuper && !data?.selected_clinic;
  const clinicLabel = data?.selected_clinic
    ? (tenantNames[String(data.selected_clinic)] || "")
    : (isSuper ? t("reports.allClinics") : (me?.tenant_name || ""));

  const activePreset = useMemo(
    () => PRESETS.find((p) => p.from() === from && p.to() === to)?.key ?? "",
    [from, to]);
  const applyPreset = (key: string) => {
    const p = PRESETS.find((x) => x.key === key);
    if (p) { setFrom(p.from()); setTo(p.to()); }
  };

  const apptCols: GridColDef[] = [
    { field: "start_at", headerName: t("reports.colDate"), flex: 1.1, minWidth: 150,
      valueFormatter: (v) => fmtDate(v as string) },
    { field: "patient_name", headerName: t("reports.colPatient"), flex: 1, minWidth: 130,
      valueGetter: (_v, r) => r.patient_name || r.wa_user },
    { field: "doctor", headerName: t("reports.colDoctor"), flex: 1, minWidth: 110 },
    { field: "service", headerName: t("reports.colService"), flex: 1, minWidth: 120 },
    ...(showClinic ? [{ field: "tenant_id", headerName: t("reports.colClinic"), flex: 1,
      minWidth: 120, valueGetter: (_v: any, r: any) => tenantNames[String(r.tenant_id)] || r.tenant_id } as GridColDef] : []),
    { field: "status", headerName: t("reports.colStatus"), width: 120,
      valueFormatter: (v) => apptStatus(t, v as string) },
    { field: "price", headerName: t("reports.colPrice"), width: 120, type: "number",
      valueFormatter: (v) => (v == null ? "" : money(v as number, rep?.summary?.currency || "SAR")) },
  ];

  function exportCsv() {
    if (!rep) return;
    const s = rep.summary;
    const ccy = s.currency;
    const rows: (string | number | null | undefined)[][] = [
      [t("reports.reportTitle"), clinicLabel],
      [t("reports.period"), `${from} → ${to}`],
      [],
      [t("reports.kpiAppointments"), s.appointments],
      [t("reports.kpiCompleted"), s.completed],
      [t("reports.kpiNoShows"), s.no_shows],
      [t("reports.kpiCancelled"), s.cancelled],
      [t("reports.kpiCompletionRate"), `${s.completion_rate}%`],
      [t("reports.kpiPatients"), s.unique_patients],
      [t("reports.kpiConversion"), `${s.conversion_pct}%`],
      [t("reports.kpiRevenue"), money(s.est_revenue, ccy)],
      [],
      [t("reports.secAppointments")],
      [t("reports.colDate"), t("reports.colPatient"), t("reports.colDoctor"),
        t("reports.colService"), t("reports.colStatus"), t("reports.colPrice")],
      ...rep.appointments.map((a: any) => [
        fmtDate(a.start_at), a.patient_name || a.wa_user, a.doctor, a.service,
        apptStatus(t, a.status), a.price ?? ""]),
    ];
    downloadCsv(`report_${from}_${to}.csv`, rows);
  }

  function exportPdf() {
    if (!rep) return;
    const s = rep.summary;
    const ccy = s.currency;
    const kpis: [string, string | number][] = [
      [t("reports.kpiAppointments"), s.appointments],
      [t("reports.kpiCompleted"), s.completed],
      [t("reports.kpiNoShows"), s.no_shows],
      [t("reports.kpiCancelled"), s.cancelled],
      [t("reports.kpiCompletionRate"), `${s.completion_rate}%`],
      [t("reports.kpiNoShowRate"), `${s.no_show_rate}%`],
      [t("reports.kpiPatients"), s.unique_patients],
      [t("reports.kpiConversion"), `${s.conversion_pct}%`],
      [t("reports.kpiInbound"), s.inbound],
      [t("reports.kpiRevenue"), money(s.est_revenue, ccy)],
    ];
    const apptRowsHtml = rep.appointments.slice(0, 500).map((a: any) => `
      <tr><td>${escapeHtml(fmtDate(a.start_at))}</td><td>${escapeHtml(a.patient_name || a.wa_user)}</td>
      <td>${escapeHtml(a.doctor || "")}</td><td>${escapeHtml(a.service || "")}</td>
      <td>${escapeHtml(apptStatus(t, a.status))}</td>
      <td style="text-align:right">${a.price != null ? escapeHtml(money(a.price, ccy)) : ""}</td></tr>`).join("");
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(t("reports.reportTitle"))}</title>
      <style>
        *{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;box-sizing:border-box}
        body{margin:32px;color:#0f172a}
        h1{font-size:22px;margin:0 0 2px} .sub{color:#64748b;font-size:13px;margin-bottom:18px}
        .brand{display:inline-block;width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,#14b8a6,#6366f1);vertical-align:middle;margin-right:10px}
        .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:18px 0 8px}
        .kpi{border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px}
        .kpi .l{color:#64748b;font-size:11px} .kpi .v{font-size:20px;font-weight:700;margin-top:2px}
        h2{font-size:15px;margin:22px 0 8px;border-bottom:2px solid #14b8a6;padding-bottom:4px}
        table{width:100%;border-collapse:collapse;font-size:12px}
        th{text-align:left;color:#475569;border-bottom:1px solid #cbd5e1;padding:6px 8px}
        td{border-bottom:1px solid #eef2f7;padding:6px 8px}
        .note{color:#94a3b8;font-size:11px;margin-top:14px}
        @media print{body{margin:14px}.kpi{break-inside:avoid}tr{break-inside:avoid}}
      </style></head><body>
      <div><span class="brand"></span><h1 style="display:inline-block">${escapeHtml(t("reports.reportTitle"))}</h1></div>
      <div class="sub">${escapeHtml(clinicLabel)} · ${escapeHtml(t("reports.period"))}: ${escapeHtml(from)} → ${escapeHtml(to)}
        · ${escapeHtml(t("reports.generated"))}: ${escapeHtml(fmtDate(new Date().toISOString()))}</div>
      <div class="kpis">${kpis.map(([l, v]) => `<div class="kpi"><div class="l">${escapeHtml(l)}</div><div class="v">${escapeHtml(v)}</div></div>`).join("")}</div>
      <div class="note">${escapeHtml(t("reports.revenueNote"))}</div>
      <h2>${escapeHtml(t("reports.secAppointments"))}</h2>
      <table><thead><tr>
        <th>${escapeHtml(t("reports.colDate"))}</th><th>${escapeHtml(t("reports.colPatient"))}</th>
        <th>${escapeHtml(t("reports.colDoctor"))}</th><th>${escapeHtml(t("reports.colService"))}</th>
        <th>${escapeHtml(t("reports.colStatus"))}</th><th style="text-align:right">${escapeHtml(t("reports.colPrice"))}</th>
      </tr></thead><tbody>${apptRowsHtml || `<tr><td colspan="6" style="color:#94a3b8">${escapeHtml(t("reports.emptyAppointments"))}</td></tr>`}</tbody></table>
      </body></html>`;
    printReport(html);
  }

  if (q.isLoading) return <><PageTitle title={t("reports.title")} /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;

  const s = rep.summary;
  const ccy = s.currency;
  const reviews = rep.reviews;

  const dateField = (label: string, value: string, onChange: (v: string) => void) => (
    <TextField type="date" size="small" label={label} value={value}
      onChange={(e) => onChange(e.target.value)} InputLabelProps={{ shrink: true }}
      sx={{ width: 160 }} />
  );

  return (
    <>
      <PageTitle title={t("reports.title")} subtitle={t("reports.subtitle")}
        right={<ClinicFilter meta={data} />} />

      {/* Controls: presets + date range + exports */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction={{ xs: "column", lg: "row" }} spacing={2} alignItems={{ lg: "center" }}
            justifyContent="space-between">
            <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
              {dateField(t("reports.from"), from, setFrom)}
              {dateField(t("reports.to"), to, setTo)}
              <ToggleButtonGroup size="small" exclusive value={activePreset}
                onChange={(_e, v) => v && applyPreset(v)}>
                {PRESETS.map((p) => (
                  <ToggleButton key={p.key} value={p.key}>{t(`reports.${p.key}`)}</ToggleButton>
                ))}
              </ToggleButtonGroup>
            </Stack>
            <Stack direction="row" spacing={1.5}>
              <Button variant="outlined" startIcon={<DownloadIcon />} onClick={exportCsv}>
                {t("reports.exportCsv")}</Button>
              <Button variant="contained" startIcon={<PictureAsPdfIcon />} onClick={exportPdf}>
                {t("reports.exportPdf")}</Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      {/* KPI summary */}
      <Grid container spacing={2} sx={{ mb: 1 }}>
        {([
          [t("reports.kpiAppointments"), s.appointments, <EventIcon fontSize="small" />, "primary"],
          [t("reports.kpiCompleted"), `${s.completed} · ${s.completion_rate}%`, <CheckIcon fontSize="small" />, "success"],
          [t("reports.kpiNoShows"), `${s.no_shows} · ${s.no_show_rate}%`, <EventBusyIcon fontSize="small" />, "warning"],
          [t("reports.kpiPatients"), s.unique_patients, <GroupIcon fontSize="small" />, "info"],
          [t("reports.kpiConversion"), `${s.conversion_pct}%`, <PercentIcon fontSize="small" />, "secondary"],
          [t("reports.kpiRevenue"), money(s.est_revenue, ccy), <PaymentsIcon fontSize="small" />, "success"],
        ] as const).map(([label, value, icon, color], i) => (
          <Grid item xs={6} md={4} lg={2} key={i}>
            <KpiCard label={label} value={value} icon={icon} color={color as any} />
          </Grid>
        ))}
      </Grid>

      {/* Reviews summary band */}
      <Card sx={{ my: 2 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap" useFlexGap>
            <StarIcon sx={{ color: "#f59e0b" }} />
            <Typography fontWeight={700}>{t("reports.secReviews")}</Typography>
            <Box sx={{ flex: 1 }} />
            {reviews.stats.requested > 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t("reports.reviewsSummary", {
                  n: reviews.stats.requested, responded: reviews.stats.responded,
                  avg: reviews.stats.avg_rating ?? "—",
                })}
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary">{t("reports.noReviews")}</Typography>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Appointments detail (DataGrid toolbar also offers its own CSV export) */}
      <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
        {t("reports.secAppointments")}
      </Typography>
      {rep.appointments.length === 0
        ? <Card><EmptyState text={t("reports.emptyAppointments")} /></Card>
        : <DataTable rows={rep.appointments} columns={apptCols} density="compact" />}
    </>
  );
}
