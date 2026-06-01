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

const TYPES = [
  { v: "native", l: "Native (built-in calendar)" },
  { v: "google_calendar", l: "Google Calendar" },
  { v: "cliniko", l: "Cliniko" },
  { v: "custom_erp", l: "Custom ERP" },
  { v: "fhir", l: "FHIR" },
];

function MapEditor({ label, value, onChange, kHead = "Key", vHead = "Value" }: {
  label: string; value: Record<string, string>; onChange: (o: Record<string, string>) => void;
  kHead?: string; vHead?: string;
}) {
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
            <TableCell sx={{ pl: 0 }}><TextField size="small" variant="standard" placeholder={kHead} value={k} onChange={(e) => setRow(i, e.target.value, val)} /></TableCell>
            <TableCell><TextField size="small" variant="standard" placeholder={vHead} value={val} onChange={(e) => setRow(i, k, e.target.value)} fullWidth /></TableCell>
            <TableCell width={40}><IconButton size="small" onClick={() => del(i)}><DeleteIcon fontSize="small" /></IconButton></TableCell>
          </TableRow>
        ))}
      </TableBody></Table>
      <Button size="small" startIcon={<AddIcon />} onClick={add}>Add</Button>
    </Box>
  );
}

export default function Connector() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
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
  const secretPlaceholder = (name: string) => (secretsSet.includes(name) ? "•••• set — blank keeps" : "");

  const build = () => (type === "native" ? null : { ...cfg, type });

  const run = async (test: boolean) => {
    setBusy(true);
    try {
      const r = await apiPost(`/tenants/${id}/connector`, { config: build(), test });
      if (test) {
        const ok = r.result?.ok;
        ok ? toast.ok("Connection OK") : toast.err("Test failed: " + (r.result?.detail || ""));
      } else { toast.ok("Connector saved"); q.refetch(); }
    } catch (e) { toast.err(e instanceof ApiError ? e.message : "Failed"); }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title={`Connector · ${q.data?.name || ""}`}
        right={<Button startIcon={<ArrowBackIcon />} onClick={() => nav(`/tenants/${id}`)}>Back</Button>} />
      <Card>
        <CardContent>
          <Stack spacing={2.5}>
            <FormControl size="small" sx={{ maxWidth: 320 }}>
              <InputLabel>Appointment backend</InputLabel>
              <Select label="Appointment backend" value={type} onChange={(e) => setType(String(e.target.value))}>
                {TYPES.map((t) => <MenuItem key={t.v} value={t.v}>{t.l}</MenuItem>)}
              </Select>
            </FormControl>

            {type === "native" && (
              <Typography variant="body2" color="text.secondary">
                Appointments are stored in this app's own database — no external backend to configure.
              </Typography>
            )}

            {type === "cliniko" && (
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}><TextField fullWidth size="small" type="password" label="API key"
                  placeholder={secretPlaceholder("api_key")} value={f("api_key")} onChange={(e) => set("api_key", e.target.value)} /></Grid>
                <Grid item xs={12} md={6}><TextField fullWidth size="small" label="Business ID" value={f("business_id")} onChange={(e) => set("business_id", e.target.value)} /></Grid>
                <Grid item xs={12} md={6}><TextField fullWidth size="small" label="User agent" value={f("user_agent")} onChange={(e) => set("user_agent", e.target.value)} /></Grid>
                <Grid item xs={12} md={6}><MapEditor label="Practitioners (doctor → id)" value={cfg.practitioners || {}} onChange={(o) => set("practitioners", o)} kHead="Doctor" vHead="Practitioner id" /></Grid>
                <Grid item xs={12} md={6}><MapEditor label="Appointment types (service → id)" value={cfg.appointment_types || {}} onChange={(o) => set("appointment_types", o)} kHead="Service" vHead="Type id" /></Grid>
              </Grid>
            )}

            {type === "google_calendar" && (
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}><TextField fullWidth size="small" type="password" label="Refresh token"
                  placeholder={secretPlaceholder("refresh_token")} value={f("refresh_token")} onChange={(e) => set("refresh_token", e.target.value)} /></Grid>
                <Grid item xs={12} md={3}><TextField fullWidth size="small" label="Timezone" value={f("timezone")} onChange={(e) => set("timezone", e.target.value)} /></Grid>
                <Grid item xs={12} md={3}><TextField fullWidth size="small" label="Default calendar" value={f("default_calendar")} onChange={(e) => set("default_calendar", e.target.value)} /></Grid>
                <Grid item xs={12}><MapEditor label="Calendars (doctor → calendarId)" value={cfg.calendars || {}} onChange={(o) => set("calendars", o)} kHead="Doctor" vHead="Calendar id" /></Grid>
              </Grid>
            )}

            {(type === "custom_erp" || type === "fhir") && (
              <Grid container spacing={2}>
                <Grid item xs={12} md={8}><TextField fullWidth size="small" label="Base URL" value={f("base_url")} onChange={(e) => set("base_url", e.target.value)} /></Grid>
                {type === "fhir" && <Grid item xs={12} md={4}><TextField fullWidth size="small" label="Booking status" placeholder="booked" value={f("booking_status")} onChange={(e) => set("booking_status", e.target.value)} /></Grid>}
                <Grid item xs={12} md={4}>
                  <FormControl size="small" fullWidth>
                    <InputLabel>Auth type</InputLabel>
                    <Select label="Auth type" value={auth.type || "none"} onChange={(e) => setAuth({ type: e.target.value })}>
                      <MenuItem value="none">None</MenuItem>
                      <MenuItem value="bearer">Bearer token</MenuItem>
                      {type === "custom_erp" && <MenuItem value="header">Custom header</MenuItem>}
                      {type === "fhir" && <MenuItem value="client_credentials">Client credentials</MenuItem>}
                    </Select>
                  </FormControl>
                </Grid>
                {auth.type === "bearer" && <Grid item xs={12} md={8}><TextField fullWidth size="small" type="password" label="Token" placeholder={secretPlaceholder("auth.token")} value={auth.token || ""} onChange={(e) => setAuth({ token: e.target.value })} /></Grid>}
                {auth.type === "header" && <>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" label="Header name" value={auth.name || ""} onChange={(e) => setAuth({ name: e.target.value })} /></Grid>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" type="password" label="Header value" placeholder={secretPlaceholder("auth.value")} value={auth.value || ""} onChange={(e) => setAuth({ value: e.target.value })} /></Grid>
                </>}
                {auth.type === "client_credentials" && <>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" label="Token URL" value={auth.token_url || ""} onChange={(e) => setAuth({ token_url: e.target.value })} /></Grid>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" label="Client ID" value={auth.client_id || ""} onChange={(e) => setAuth({ client_id: e.target.value })} /></Grid>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" type="password" label="Client secret" placeholder={secretPlaceholder("auth.client_secret")} value={auth.client_secret || ""} onChange={(e) => setAuth({ client_secret: e.target.value })} /></Grid>
                  <Grid item xs={12} md={4}><TextField fullWidth size="small" label="Scope" value={auth.scope || ""} onChange={(e) => setAuth({ scope: e.target.value })} /></Grid>
                </>}
                {type === "fhir" && <>
                  <Grid item xs={12} md={6}><MapEditor label="Schedules (doctor → id)" value={cfg.schedules || {}} onChange={(o) => set("schedules", o)} kHead="Doctor" vHead="Schedule id" /></Grid>
                  <Grid item xs={12} md={6}><MapEditor label="Practitioners (doctor → id)" value={cfg.practitioners || {}} onChange={(o) => set("practitioners", o)} kHead="Doctor" vHead="Practitioner id" /></Grid>
                </>}
              </Grid>
            )}

            {type !== "native" && (
              <>
                <Divider />
                <TextField size="small" type="password" label="Webhook secret (optional)" sx={{ maxWidth: 320 }}
                  placeholder={secretPlaceholder("webhook_secret")} value={f("webhook_secret")} onChange={(e) => set("webhook_secret", e.target.value)} />
                {secretsSet.length > 0 && (
                  <Box><Typography variant="caption" color="text.secondary">Secrets set (blank keeps): </Typography>
                    {secretsSet.map((s) => <Chip key={s} size="small" label={s} sx={{ mr: 0.5 }} />)}</Box>
                )}
              </>
            )}

            <Stack direction="row" spacing={2}>
              <Button variant="contained" disabled={busy} onClick={() => run(false)}>Save connector</Button>
              {type !== "native" && <Button disabled={busy} onClick={() => run(true)}>Test connection</Button>}
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </>
  );
}
