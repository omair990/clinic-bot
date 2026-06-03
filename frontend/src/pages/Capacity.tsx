import { useState, useEffect, useMemo } from "react";
import {
  Card, CardContent, Typography, Grid, Stack, TextField, Divider, Box, Chip, Button, Alert,
  Table, TableBody, TableCell, TableHead, TableRow, InputAdornment, alpha,
} from "@mui/material";
import GroupsIcon from "@mui/icons-material/GroupsOutlined";
import SpeedIcon from "@mui/icons-material/SpeedOutlined";
import BlockIcon from "@mui/icons-material/BlockOutlined";
import TimerIcon from "@mui/icons-material/TimerOutlined";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import { useApiQuery, PageTitle, Loading, QueryError, KpiCard } from "../lib";
import { useT } from "../i18n";

type Inputs = {
  rpm: number; itpm: number; otpm: number;
  calls: number; inTok: number; outTok: number; seconds: number;
  threads: number; replicas: number;
};
const LS_KEY = "capacityInputs.v1";
const num = (v: any, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);

function fmtMinutes(mins: number): string {
  if (!Number.isFinite(mins) || mins <= 0) return "—";
  if (mins < 1) return `${Math.ceil(mins * 60)} s`;
  if (mins < 90) return `${Math.round(mins)} min`;
  return `${(mins / 60).toFixed(1)} h`;
}

export default function Capacity() {
  const t = useT();
  const q = useApiQuery<any>(["capacity"], "/capacity");

  const serverInputs: Inputs | null = useMemo(() => {
    if (!q.data) return null;
    const { tier, per_turn, server } = q.data;
    return {
      rpm: tier.requests_per_min, itpm: tier.input_tpm, otpm: tier.output_tpm,
      calls: per_turn.llm_calls, inTok: per_turn.input_tokens, outTok: per_turn.output_tokens,
      seconds: per_turn.seconds, threads: server.threads, replicas: server.replicas,
    };
  }, [q.data]);

  const [inp, setInp] = useState<Inputs | null>(null);
  const [burst, setBurst] = useState<number>(1000);

  useEffect(() => {
    if (!serverInputs) return;
    let saved: Partial<Inputs> = {};
    try { saved = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { /* ignore */ }
    setInp({ ...serverInputs, ...saved });
  }, [serverInputs]);

  if (q.isLoading || !inp) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;

  const { tier, per_turn } = q.data;
  const set = (k: keyof Inputs) => (e: any) => {
    const next = { ...inp, [k]: num(e.target.value) };
    setInp(next);
    try { localStorage.setItem(LS_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  };
  const reset = () => { if (serverInputs) { setInp(serverInputs); try { localStorage.removeItem(LS_KEY); } catch { /* ignore */ } } };

  // Each ceiling, in conversations/min. Server threads scale per replica; LLM limits are
  // account-wide and do NOT multiply by replicas.
  const ceilings = [
    { key: "itpm", label: t("capacity.limitItpm"), value: inp.inTok > 0 ? inp.itpm / inp.inTok : Infinity },
    { key: "rpm", label: t("capacity.limitRpm"), value: inp.calls > 0 ? inp.rpm / inp.calls : Infinity },
    { key: "otpm", label: t("capacity.limitOtpm"), value: inp.outTok > 0 ? inp.otpm / inp.outTok : Infinity },
    { key: "threads", label: t("capacity.limitThreads"), value: inp.seconds > 0 ? inp.threads * inp.replicas * (60 / inp.seconds) : Infinity },
  ];
  const sustained = Math.min(...ceilings.map((c) => c.value));
  const bind = ceilings.reduce((a, b) => (b.value < a.value ? b : a));
  const drainMin = (n: number) => (sustained > 0 ? n / sustained : Infinity);
  const fmt = (mins: number) => fmtMinutes(mins);

  const burstDrain = drainMin(burst);
  const verdictKey = burstDrain < 2 ? "verdictOk" : burstDrain < 30 ? "verdictTight" : "verdictBad";
  const verdictSeverity = burstDrain < 2 ? "success" : burstDrain < 30 ? "warning" : "error";

  const numField = (k: keyof Inputs, label: string, step = "any") => (
    <TextField fullWidth size="small" type="number" label={label} value={inp[k]}
      onChange={set(k)} inputProps={{ step, min: 0 }} />
  );

  const scenarios = [1000, 5000, burst].filter((v, i, a) => a.indexOf(v) === i && v > 0);

  return (
    <>
      <PageTitle title={t("capacity.title")} subtitle={t("capacity.subtitle")} right={
        <Chip variant="outlined" color={tier.live ? "success" : "default"}
          label={tier.live ? t("capacity.liveChip") : t("capacity.defaultsChip")} />
      } />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={4}>
          <KpiCard label={t("capacity.sustained")} value={`${Math.floor(sustained)} ${t("capacity.perMin")}`}
            icon={<SpeedIcon fontSize="small" />} color="primary" />
        </Grid>
        <Grid item xs={6} md={4}>
          <KpiCard label={t("capacity.bottleneck")} value={bind.label}
            icon={<BlockIcon fontSize="small" />} color="warning" />
        </Grid>
        <Grid item xs={6} md={4}>
          <KpiCard label={t("capacity.drainFor", { n: burst.toLocaleString() })} value={fmt(burstDrain)}
            icon={<TimerIcon fontSize="small" />} color={verdictSeverity as any} />
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        {/* Left: scenario + inputs */}
        <Grid item xs={12} md={7}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1.5 }}>{t("capacity.burstSection")}</Typography>
              <TextField fullWidth label={t("capacity.burstInput")} type="number" value={burst}
                onChange={(e) => setBurst(num(e.target.value))} inputProps={{ min: 0, step: 100 }}
                InputProps={{ startAdornment: <InputAdornment position="start"><GroupsIcon fontSize="small" /></InputAdornment> }}
                helperText={t("capacity.burstHelp")} />
              <Alert severity={verdictSeverity as any} sx={{ mt: 2 }}>
                {t(`capacity.${verdictKey}`, { n: burst.toLocaleString(), t: fmt(burstDrain), b: bind.label })}
              </Alert>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
                <Typography variant="subtitle2" fontWeight={800}>{t("capacity.tierSection")}</Typography>
                <Button size="small" color="inherit" startIcon={<RestartAltIcon fontSize="small" />} onClick={reset}>
                  {t("capacity.resetRates")}
                </Button>
              </Stack>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={4}>{numField("rpm", t("capacity.rpm"), "1")}</Grid>
                <Grid item xs={12} sm={4}>{numField("itpm", t("capacity.itpm"), "1000")}</Grid>
                <Grid item xs={12} sm={4}>{numField("otpm", t("capacity.otpm"), "1000")}</Grid>
              </Grid>

              <Divider sx={{ my: 2 }}><Chip size="small" label={t("capacity.turnSection")} /></Divider>
              <Grid container spacing={2}>
                <Grid item xs={6} sm={3}>{numField("calls", t("capacity.calls"), "1")}</Grid>
                <Grid item xs={6} sm={3}>{numField("inTok", t("capacity.inTok"), "100")}</Grid>
                <Grid item xs={6} sm={3}>{numField("outTok", t("capacity.outTok"), "50")}</Grid>
                <Grid item xs={6} sm={3}>{numField("seconds", t("capacity.seconds"), "1")}</Grid>
              </Grid>

              <Divider sx={{ my: 2 }}><Chip size="small" label={t("capacity.serverSection")} /></Divider>
              <Grid container spacing={2}>
                <Grid item xs={6} sm={4}>{numField("threads", t("capacity.threads"), "1")}</Grid>
                <Grid item xs={6} sm={4}>{numField("replicas", t("capacity.replicas"), "1")}</Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label={t("capacity.dbPool")} value={q.data.server.db_pool_max} disabled />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Right: where the limit is + scenarios + recommendations */}
        <Grid item xs={12} md={5}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1 }}>{t("capacity.limitsSection")}</Typography>
              <Table size="small">
                <TableHead>
                  <TableRow><TableCell>{t("capacity.colLimit")}</TableCell><TableCell align="right">{t("capacity.colCapacity")}</TableCell></TableRow>
                </TableHead>
                <TableBody>
                  {ceilings.slice().sort((a, b) => a.value - b.value).map((c) => {
                    const isBind = c.key === bind.key;
                    return (
                      <TableRow key={c.key} sx={isBind ? { "& td": { fontWeight: 800, bgcolor: (th) => alpha(th.palette.warning.main, 0.12) } } : undefined}>
                        <TableCell>{c.label}{isBind && <Chip size="small" color="warning" label={t("capacity.binds")} sx={{ ml: 1, height: 18 }} />}</TableCell>
                        <TableCell align="right">{Number.isFinite(c.value) ? `${Math.floor(c.value)} /min` : "∞"}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1 }}>{t("capacity.scenarioSection")}</Typography>
              <Table size="small">
                <TableHead>
                  <TableRow><TableCell>{t("capacity.colBurst")}</TableCell><TableCell align="right">{t("capacity.colDrain")}</TableCell></TableRow>
                </TableHead>
                <TableBody>
                  {scenarios.sort((a, b) => a - b).map((n) => (
                    <TableRow key={n}>
                      <TableCell>{n.toLocaleString()}</TableCell>
                      <TableCell align="right">{fmt(drainMin(n))}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1 }}>{t("capacity.recTitle")}</Typography>
              <Stack spacing={0.75}>
                {["rec1", "rec2", "rec3"].map((k) => (
                  <Typography key={k} variant="body2" color="text.secondary">• {t(`capacity.${k}`)}</Typography>
                ))}
              </Stack>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
                {t("capacity.note")}{per_turn.tokens_captured ? "" : ""}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
