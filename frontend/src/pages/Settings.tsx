import { useEffect, useState, useMemo } from "react";
import {
  Card, CardContent, TextField, Button, Typography, Grid, Box, Chip, Stack, alpha,
} from "@mui/material";
import ShieldIcon from "@mui/icons-material/ShieldOutlined";
import WhatsAppIcon from "@mui/icons-material/WhatsApp";
import SmartToyIcon from "@mui/icons-material/SmartToyOutlined";
import TuneIcon from "@mui/icons-material/TuneRounded";
import CheckCircleIcon from "@mui/icons-material/CheckCircleRounded";
import WarningIcon from "@mui/icons-material/WarningAmberRounded";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError, useToast } from "../lib";

const isSecret = (k: string) => /TOKEN|KEY|SECRET|PASSWORD/i.test(k);

// Per-group visual language for both the editable cards and the status summary.
const GROUP: Record<string, { icon: React.ReactNode; color: string }> = {
  Core: { icon: <ShieldIcon fontSize="small" />, color: "#6366f1" },
  WhatsApp: { icon: <WhatsAppIcon fontSize="small" />, color: "#22c55e" },
  LLM: { icon: <SmartToyIcon fontSize="small" />, color: "#14b8a6" },
};
const groupOf = (g: string) => GROUP[g] || { icon: <TuneIcon fontSize="small" />, color: "#64748b" };

function GroupHeader({ group }: { group: string }) {
  const g = groupOf(group);
  return (
    <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 1.5 }}>
      <Box sx={{ width: 32, height: 32, borderRadius: 2, display: "grid", placeItems: "center",
        color: g.color, bgcolor: alpha(g.color, 0.14) }}>{g.icon}</Box>
      <Typography variant="subtitle2" fontWeight={800}>{group}</Typography>
    </Stack>
  );
}

// Final "configured or not" status for one group — no values, sources, or masked secrets.
function GroupStatusCard({ group, total, set }: { group: string; total: number; set: number }) {
  const g = groupOf(group);
  const complete = set >= total;
  const pct = total ? (set / total) * 100 : 0;
  const color = complete ? "#10b981" : "#f59e0b";
  return (
    <Card sx={{ height: "100%", position: "relative", overflow: "hidden",
      "&::before": { content: '""', position: "absolute", inset: 0, pointerEvents: "none",
        background: `radial-gradient(120% 90% at 100% 0%, ${alpha(g.color, 0.1)}, transparent 55%)` } }}>
      <CardContent sx={{ position: "relative" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.25 }}>
          <Stack direction="row" spacing={1.25} alignItems="center">
            <Box sx={{ width: 32, height: 32, borderRadius: 2, display: "grid", placeItems: "center",
              color: g.color, bgcolor: alpha(g.color, 0.14) }}>{g.icon}</Box>
            <Typography variant="subtitle2" fontWeight={800}>{group}</Typography>
          </Stack>
          {complete
            ? <CheckCircleIcon sx={{ color: "#10b981" }} />
            : <WarningIcon sx={{ color: "#f59e0b" }} />}
        </Stack>
        <Typography variant="h5" fontWeight={800}>{set}<Typography component="span" variant="body2" color="text.secondary"> / {total}</Typography></Typography>
        <Typography variant="caption" color="text.secondary">{complete ? "All configured" : `${total - set} not set`}</Typography>
        <Box sx={{ mt: 1.25, height: 7, borderRadius: 4, overflow: "hidden", bgcolor: (t) => alpha(t.palette.text.primary, 0.06) }}>
          <Box sx={{ width: `${pct}%`, height: "100%", bgcolor: color, transition: "width .4s ease" }} />
        </Box>
      </CardContent>
    </Card>
  );
}

export default function Settings() {
  const q = useApiQuery<any>(["settings"], "/settings");
  const toast = useToast();
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) {
      const init: Record<string, string> = {};
      Object.entries(q.data.editable).forEach(([k, v]: any) => (init[k] = v.value || ""));
      setValues(init);
    }
  }, [q.data]);

  // Aggregate the inventory into a final per-group configured/not summary.
  const summary = useMemo(() => {
    const inv: any[] = q.data?.inventory || [];
    const m = new Map<string, { total: number; set: number }>();
    inv.forEach((s) => {
      const e = m.get(s.group) || { total: 0, set: 0 };
      e.total += 1; if (s.is_set) e.set += 1;
      m.set(s.group, e);
    });
    const groups = [...m.entries()].map(([group, v]) => ({ group, ...v }));
    const total = groups.reduce((a, g) => a + g.total, 0);
    const set = groups.reduce((a, g) => a + g.set, 0);
    return { groups, total, set, complete: set >= total };
  }, [q.data]);

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;

  const editable = q.data.editable as Record<string, { label: string; group: string; value: string }>;
  const groups: Record<string, string[]> = {};
  Object.entries(editable).forEach(([k, v]) => { (groups[v.group] ||= []).push(k); });

  const save = async () => {
    setBusy(true);
    try {
      // Only send fields the operator actually changed (don't blank a masked secret).
      const changed: Record<string, string> = {};
      Object.keys(values).forEach((k) => { if (values[k] !== (editable[k].value || "")) changed[k] = values[k]; });
      await apiPost("/settings", { values: changed });
      toast.ok("Settings saved");
      q.refetch();
    } catch (e) { toast.err(e instanceof ApiError ? e.message : "Save failed"); }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title="Platform settings" subtitle="Database overrides take precedence over environment variables"
        right={<Button variant="contained" disabled={busy} onClick={save}>Save settings</Button>} />

      {/* Configuration health — final configured/not status, grouped (no values exposed). */}
      <Card sx={{ mb: 2, position: "relative", overflow: "hidden", color: "#fff",
        background: summary.complete
          ? "linear-gradient(120deg,#0f766e 0%,#10b981 50%,#6366f1 100%)"
          : "linear-gradient(120deg,#b45309 0%,#f59e0b 55%,#6366f1 100%)" }}>
        <CardContent sx={{ p: { xs: 2.5, md: 3 } }}>
          <Stack direction="row" spacing={2} alignItems="center">
            <Box sx={{ width: 48, height: 48, borderRadius: 2.5, display: "grid", placeItems: "center", flexShrink: 0,
              bgcolor: alpha("#fff", 0.18), border: `1px solid ${alpha("#fff", 0.35)}` }}>
              {summary.complete ? <CheckCircleIcon /> : <WarningIcon />}
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="overline" sx={{ color: alpha("#fff", 0.85), letterSpacing: 1 }}>Configuration status</Typography>
              <Typography variant="h6" sx={{ color: "#fff", lineHeight: 1.15 }}>
                {summary.complete ? "All systems configured" : "Some settings need attention"}
              </Typography>
            </Box>
            <Box sx={{ flex: 1 }} />
            <Chip label={`${summary.set} / ${summary.total} configured`}
              sx={{ bgcolor: alpha("#fff", 0.22), color: "#fff", fontWeight: 700, flexShrink: 0 }} />
          </Stack>
        </CardContent>
      </Card>

      {summary.groups.length > 0 && (
        <Grid container spacing={2} sx={{ mb: 2 }}>
          {summary.groups.map((g) => (
            <Grid item xs={12} sm={6} md={4} key={g.group}>
              <GroupStatusCard group={g.group} total={g.total} set={g.set} />
            </Grid>
          ))}
        </Grid>
      )}

      {/* Editable settings — the runtime-effective subset operators can change here. */}
      {Object.entries(groups).map(([group, keys]) => (
        <Card key={group} sx={{ mb: 2 }}>
          <CardContent>
            <GroupHeader group={group} />
            <Grid container spacing={2}>
              {keys.map((k) => (
                <Grid item xs={12} md={6} key={k}>
                  <TextField fullWidth size="small" label={editable[k].label}
                    type={isSecret(k) ? "password" : "text"}
                    value={values[k] ?? ""} onChange={(e) => setValues({ ...values, [k]: e.target.value })}
                    helperText={isSecret(k) ? "Stored encrypted; leave blank to keep" : k} />
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      ))}
    </>
  );
}
