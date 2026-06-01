import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Card, CardContent, TextField, Button, Typography, Alert, Stack, MenuItem, Select, Box, Chip,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError } from "../lib";

const TYPES = ["native", "google_calendar", "cliniko", "custom_erp", "fhir"];

export default function Connector() {
  const { id } = useParams();
  const nav = useNavigate();
  const q = useApiQuery<any>(["connector", id], `/tenants/${id}/connector`);

  const [type, setType] = useState("native");
  const [configText, setConfigText] = useState("{}");
  const [msg, setMsg] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) {
      const cfg = q.data.config || {};
      setType(cfg.type || "native");
      setConfigText(JSON.stringify(cfg, null, 2));
    }
  }, [q.data]);
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;

  const build = () => {
    if (type === "native") return null;
    let cfg: any;
    try { cfg = JSON.parse(configText || "{}"); }
    catch (e) { throw new Error("Config is not valid JSON"); }
    cfg.type = type;
    return cfg;
  };

  const run = async (test: boolean) => {
    setBusy(true); setMsg(null);
    try {
      const config = build();
      const r = await apiPost(`/tenants/${id}/connector`, { config, test });
      if (test) {
        const ok = r.result?.ok;
        setMsg({ type: ok ? "success" : "error", text: (ok ? "Connection OK. " : "Test failed. ") + (r.result?.detail || "") });
      } else {
        setMsg({ type: "success", text: "Connector saved." });
        q.refetch();
      }
    } catch (e) {
      setMsg({ type: "error", text: e instanceof ApiError ? e.message : (e as Error).message });
    } finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title={`Connector · ${q.data?.name || ""}`}
        right={<Button startIcon={<ArrowBackIcon />} onClick={() => nav(`/tenants/${id}`)}>Back</Button>} />
      {msg && <Alert severity={msg.type} sx={{ mb: 2 }}>{msg.text}</Alert>}
      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Box>
              <Typography variant="body2" color="text.secondary">Backend type</Typography>
              <Select size="small" value={type} onChange={(e) => setType(String(e.target.value))} sx={{ minWidth: 220, mt: 0.5 }}>
                {TYPES.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
              </Select>
            </Box>
            {q.data?.secrets_set?.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary">Secrets currently set (leave blank in JSON to keep):</Typography>
                <Box sx={{ mt: 0.5 }}>{q.data.secrets_set.map((s: string) => <Chip key={s} size="small" label={s} sx={{ mr: 0.5 }} />)}</Box>
              </Box>
            )}
            {type !== "native" && (
              <TextField fullWidth multiline minRows={12} label="Connector config (JSON)"
                value={configText} onChange={(e) => setConfigText(e.target.value)}
                helperText="Includes type-specific fields (calendars, practitioners, base_url, auth, …). Blank secret fields keep their existing value."
                InputProps={{ sx: { fontFamily: "monospace", fontSize: 13 } }} />
            )}
            {type === "native" && <Typography variant="body2" color="text.secondary">Native — appointments are stored in this app's own database (no external backend).</Typography>}
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
