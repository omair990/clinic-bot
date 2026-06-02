import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Card, CardContent, TextField, Button, Typography, Stack, MenuItem, Select, Box, Chip,
  IconButton, Table, TableBody, TableRow, TableCell, FormControl, InputLabel, Grid, Divider,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError, useToast } from "../lib";
import { useT } from "../i18n";

const TYPE_VALUES = ["native", "google_calendar", "cliniko", "custom_erp", "fhir"] as const;
const typeLabelKey: Record<string, string> = {
  native: "connector.typeNative",
  google_calendar: "connector.typeGoogleCalendar",
  cliniko: "connector.typeCliniko",
  custom_erp: "connector.typeCustomErp",
  fhir: "connector.typeFhir",
};

function MapEditor({ label, value, onChange, kHead, vHead }: {
  label: string; value: Record<string, string>; onChange: (o: Record<string, string>) => void;
  kHead?: string; vHead?: string;
}) {
  const t = useT();
  const kh = kHead ?? t("connector.keyHead");
  const vh = vHead ?? t("connector.valueHead");
  const rows = Object.entries(value || {});
  const setRow = (i: number, k: string, val: string) => {
    const next: Record<string, string> = {};
    rows.forEach(([rk, rv], j) => { const key = j === i ? k : rk; next[key] = j === i ? val : rv; });
    onChange(next);
  };
  const del = (i: number) => onChange(Object.fromEntries(rows.filter((_, j) => j !== i)));
  const add = () => onChange({ ...value, "": "" });
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" fontWeight={600}>{label}</Typography>
      <Table size="small"><TableBody>
        {rows.map(([k, val], i) => (
          <TableRow key={i}>
            <TableCell sx={{ pl: 0 }}><TextField size="small" variant="standard" placeholder={kh} value={k} onChange={(e) => setRow(i, e.target.value, val)} /></TableCell>
            <TableCell><TextField size="small" variant="standard" placeholder={vh} value={val} onChange={(e) => setRow(i, k, e.target.value)} fullWidth /></TableCell>
            <TableCell width={40}><IconButton size="small" onClick={() => del(i)}><DeleteIcon fontSize="small" /></IconButton></TableCell>
          </TableRow>
        ))}
      </TableBody></Table>
      <Button size="small" startIcon={<AddIcon />} onClick={add}>{t("connector.add")}</Button>
    </Box>
  );
}

export default function Connector() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const t = useT();
  const q = useApiQuery<any>(["connector", id], `/tenants/${id}/connector`);
  const [type, setType] = useState("native");
  const [cfg, setCfg] = useState<any>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) {
      const c = q.data.config || {};
      setType(c.type || "native");
      setCfg(c);
    }
  }, [q.data]);
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;

  const secretsSet: string[] = q.data?.secrets_set || [];
  const f = (k: string) => cfg[k] ?? "";
  const set = (k: string, val: any) => setCfg({ ...cfg, [k]: val });
  const auth = cfg.auth || {};
  const setAuth = (p: any) => setCfg({ ...cfg, auth: { ...auth, ...p } });
  const secretPlaceholder = (name: string) => (secretsSet.includes(name) ? t("connector.secretSetPlaceholder") : "");

  const build = () => (type === "native" ? null : { ...cfg, type });

  const run = async (test: boolean) => {
    setBusy(true);
    try {
      const r = await apiPost(`/tenants/${id}/connector`, { config: build(), test });
      if (test) {
        const ok = r.result?.ok;
        ok ? toast.ok(t("connector.connectionOk")) : toast.err(t("connector.testFailed", { detail: r.result?.detail || "" }));
      } else { toast.ok(t("connector.connectorSaved")); q.refetch(); }
    } catch (e) { toast.err(e instanceof ApiError ? e.message : t("connector.failed")); }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title={t("connector.title", { name: q.data?.name || "" })}
        right={<Button startIcon={<ArrowBackIcon />} onClick={() => nav(`/tenants/${id}`)}>{t("connector.back")}</Button>} />
      <Card>
        <CardContent>
          <Stack spacing={2.5}>
            <FormControl size="small" sx={{ maxWidth: 320 }}>
              <InputLabel>{t("connector.appointmentBackend")}</InputLabel>
              <Select label={t("connector.appointmentBackend")} value={type} onChange={(e) => setType(String(e.target.value))}>
                {TYPE_VALUES.map((v) => <MenuItem key={v} value={v}>{t(typeLabelKey[v])}</MenuItem>)}
              </Select>
            </FormControl>

            {type === "native" && (
              <Typography variant="body2" color="text.secondary">
                {t("connector.nativeNote")}
              </Typography>
            )}

            {type === "cliniko" && (
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}><TextField fullWidth size="small" type="password" label={t("connector.apiKey")}
                  placeholder={secretPlaceholder("api_key")} value={f("api_key")} onChange={(e) => set("api_key", e.target.value)} /></Grid>
                <Grid item xs={12} md={6}><TextField fullWidth size="small" label={t("connector.businessId")} value={f("business_id")} onChange={(e) => set("business_id", e.target.value)} /></Grid>
                <Grid item xs={12} md={6}><TextField fullWidth size="small" label={t("connector.userAgent")} value={f("user_agent")} onChange={(e) => set("user_agent", e.target.value)} /></Grid>
                <Grid item xs={12} md={6}><MapEditor label={t("connector.practitioners")} value={cfg.practitioners || {}} onChange={(o) => set("practitioners", o)} kHead={t("connector.doctor")} vHead={t("connector.practitionerId")} /></Grid>
                <Grid item xs={12} md={6}><MapEditor label={t("connector.appointmentTypes")} value={cfg.appointment_types || {}} onChange={(o) => set("appointment_types", o)} kHead={t("connector.service")} vHead={t("connector.typeId")} /></Grid>
              </Grid>
            )}

            {type === "google_calendar" && (
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}><TextField fullWidth size="small" type="password" label={t("connector.refreshToken")}
                  placeholder={secretPlaceholder("refresh_token")} value={f("refresh_token")} onChange={(e) => set("refresh_token", e.target.value)} /></Grid>
                <Grid item xs={12} md={3}><TextField fullWidth size="small" label={t("connector.timezone")} value={f("timezone")} onChange={(e) => set("timezone", e.target.value)} /></Grid>
                <Grid item xs={12} md={3}><TextField fullWidth size="small" label={t("connector.defaultCalendar")} value={f("default_calendar")} onChange={(e) => set("default_calendar", e.target.value)} /></Grid>
                <Grid item xs={12}><MapEditor label={t("connector.calendars")} value={cfg.calendars || {}} onChange={(o) => set("calendars", o)} kHead={t("connector.doctor")} vHead={t("connector.calendarId")} /></Grid>
              </Grid>
            )}

            {(type === "custom_erp" || type === "fhir") && (
              <Grid container spacing={2}>
                <Grid item xs={12} md={8}><TextField fullWidth size="small" label={t("connector.baseUrl")} value={f("base_url")} onChange={(e) => set("base_url", e.target.value)} /></Grid>
                {type === "fhir" && <Grid item xs={12} md={4}><TextField fullWidth size="small" label={t("connector.bookingStatus")} placeholder={t("connector.bookingStatusPlaceholder")} value={f("booking_status")} onChange={(e) => set("booking_status", e.target.value)} /></Grid>}
                <Grid item xs={12} md={4}>
                  <FormControl size="small" fullWidth>
                    <InputLabel>{t("connector.authType")}</InputLabel>
                    <Select label={t("connector.authType")} value={auth.type || "none"} onChange={(e) => setAuth({ type: e.target.value })}>
                      <MenuItem value="none">{t("connector.authNone")}</MenuItem>
                      <MenuItem value="bearer">{t("connector.authBearer")}</MenuItem>
                      {type === "custom_erp" && <MenuItem value="header">{t("connector.authHeader")}</MenuItem>}
                      {type === "fhir" && <MenuItem value="client_credentials">{t("connector.authClientCredentials")}</MenuItem>}
                    </Select>
                  </FormControl>
                </Grid>
                {auth.type === "bearer" && <Grid item xs={12} md={8}><TextField fullWidth size="small" type="password" label={t("connector.token")} placeholder={secretPlaceholder("auth.token")} value={auth.token || ""} onChange={(e) => setAuth({ token: e.target.value })} /></Grid>}
                {auth.type === "header" && <>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" label={t("connector.headerName")} value={auth.name || ""} onChange={(e) => setAuth({ name: e.target.value })} /></Grid>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" type="password" label={t("connector.headerValue")} placeholder={secretPlaceholder("auth.value")} value={auth.value || ""} onChange={(e) => setAuth({ value: e.target.value })} /></Grid>
                </>}
                {auth.type === "client_credentials" && <>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" label={t("connector.tokenUrl")} value={auth.token_url || ""} onChange={(e) => setAuth({ token_url: e.target.value })} /></Grid>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" label={t("connector.clientId")} value={auth.client_id || ""} onChange={(e) => setAuth({ client_id: e.target.value })} /></Grid>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" type="password" label={t("connector.clientSecret")} placeholder={secretPlaceholder("auth.client_secret")} value={auth.client_secret || ""} onChange={(e) => setAuth({ client_secret: e.target.value })} /></Grid>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" label={t("connector.scope")} value={auth.scope || ""} onChange={(e) => setAuth({ scope: e.target.value })} /></Grid>
                </>}
                {type === "fhir" && <>
                  <Grid item xs={12} md={6}><MapEditor label={t("connector.schedules")} value={cfg.schedules || {}} onChange={(o) => set("schedules", o)} kHead={t("connector.doctor")} vHead={t("connector.scheduleId")} /></Grid>
                  <Grid item xs={12} md={6}><MapEditor label={t("connector.practitioners")} value={cfg.practitioners || {}} onChange={(o) => set("practitioners", o)} kHead={t("connector.doctor")} vHead={t("connector.practitionerId")} /></Grid>
                </>}
              </Grid>
            )}

            {type !== "native" && (
              <>
                <Divider />
                <TextField size="small" type="password" label={t("connector.webhookSecret")} sx={{ maxWidth: 320 }}
                  placeholder={secretPlaceholder("webhook_secret")} value={f("webhook_secret")} onChange={(e) => set("webhook_secret", e.target.value)} />
                {secretsSet.length > 0 && (
                  <Box><Typography variant="caption" color="text.secondary">{t("connector.secretsSet")}</Typography>
                    {secretsSet.map((s) => <Chip key={s} size="small" label={s} sx={{ mr: 0.5 }} />)}</Box>
                )}
              </>
            )}

            <Stack direction="row" spacing={2}>
              <Button variant="contained" disabled={busy} onClick={() => run(false)}>{t("connector.saveConnector")}</Button>
              {type !== "native" && <Button disabled={busy} onClick={() => run(true)}>{t("connector.testConnection")}</Button>}
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </>
  );
}
