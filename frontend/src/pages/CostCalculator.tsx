import { useState, useEffect, useMemo } from "react";
import {
  Card, CardContent, Typography, Grid, Stack, TextField, ToggleButton, ToggleButtonGroup,
  Divider, Box, Chip, Button, Table, TableBody, TableCell, TableHead, TableRow, InputAdornment,
  alpha,
} from "@mui/material";
import SmartToyIcon from "@mui/icons-material/SmartToyOutlined";
import WhatsAppIcon from "@mui/icons-material/WhatsApp";
import NotificationsIcon from "@mui/icons-material/NotificationsActiveOutlined";
import GraphicEqIcon from "@mui/icons-material/GraphicEqOutlined";
import CloudIcon from "@mui/icons-material/CloudOutlined";
import PaymentsIcon from "@mui/icons-material/PaymentsOutlined";
import ForumIcon from "@mui/icons-material/ForumOutlined";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import { useApiQuery, PageTitle, Loading, QueryError, KpiCard } from "../lib";
import { useT } from "../i18n";

type Rates = {
  usd_to_sar: number;
  claude_input_usd_per_mtok: number;
  claude_output_usd_per_mtok: number;
  avg_input_tokens_per_inquiry: number;
  avg_output_tokens_per_inquiry: number;
  whatsapp_sar_per_conversation: number;
  messages_per_conversation: number;
  whatsapp_sar_per_reminder: number;
  reminders_per_inquiry: number;
  replies_per_inquiry: number;
  voice_sar_per_message: number;
  railway_usd_per_month: number;
  target_margin_pct: number;
};

const LS_KEY = "costCalculatorRates.v2";
const num = (v: any, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);
const sar = (n: number) =>
  n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const intf = (n: number) => Math.round(n).toLocaleString();

export default function CostCalculator() {
  const t = useT();
  const q = useApiQuery<any>(["cost-calculator"], "/cost-calculator");

  const serverDefaults: Rates | null = useMemo(
    () => (q.data ? { ...q.data.defaults, target_margin_pct: 40 } : null),
    [q.data],
  );

  const [rates, setRates] = useState<Rates | null>(null);
  const [mode, setMode] = useState<"actual" | "projected">("projected");
  const [messages, setMessages] = useState<number>(1000);   // headline input
  const [voiceSharePct, setVoiceSharePct] = useState<number>(0);

  // Seed editable rates from server defaults, overlaying any the owner saved locally.
  useEffect(() => {
    if (!serverDefaults) return;
    let saved: Partial<Rates> = {};
    try { saved = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { /* ignore */ }
    setRates({ ...serverDefaults, ...saved });
  }, [serverDefaults]);

  // Default the voice mix from the period's real ratio, once loaded.
  useEffect(() => {
    if (!q.data) return;
    const { inbound, voice } = q.data.totals;
    setVoiceSharePct(inbound ? Math.round((voice / inbound) * 100) : 0);
  }, [q.data]);

  if (q.isLoading || !rates) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;

  const { totals, clinics, period, model } = q.data;
  const r = rates;
  const setRate = (k: keyof Rates) => (e: any) => {
    const next = { ...r, [k]: num(e.target.value) };
    setRates(next);
    const { target_margin_pct, ...persist } = next;          // margin is a planning knob, not a rate
    try { localStorage.setItem(LS_KEY, JSON.stringify(persist)); } catch { /* ignore */ }
  };
  const reset = () => {
    if (!serverDefaults) return;
    setRates(serverDefaults);
    try { localStorage.removeItem(LS_KEY); } catch { /* ignore */ }
  };

  // ---- Volume: headline messages drive replies/reminders/voice via current ratios. ----
  const inbound = mode === "actual" ? totals.inbound : messages;
  const reminders = mode === "actual" ? totals.reminders : Math.round(inbound * r.reminders_per_inquiry);
  const replies = mode === "actual" ? totals.replies : Math.round(inbound * r.replies_per_inquiry);
  const voiceMsgs = mode === "actual" ? totals.voice : Math.round((inbound * voiceSharePct) / 100);

  // ---- Cost model (per month, SAR). Replies live inside the service conversation, so they
  // don't add a separate WhatsApp charge; reminders are billed as proactive messages. ----
  const claudePerMsgSar =
    ((r.avg_input_tokens_per_inquiry / 1e6) * r.claude_input_usd_per_mtok +
      (r.avg_output_tokens_per_inquiry / 1e6) * r.claude_output_usd_per_mtok) * r.usd_to_sar;
  const waConvRate = r.messages_per_conversation > 0
    ? r.whatsapp_sar_per_conversation / r.messages_per_conversation : 0;

  const claudeMonthly = claudePerMsgSar * inbound;
  const waMonthly = waConvRate * inbound;                      // service conversations
  const reminderMonthly = reminders * r.whatsapp_sar_per_reminder;
  const voiceMonthly = voiceMsgs * r.voice_sar_per_message;
  const railwayMonthly = r.railway_usd_per_month * r.usd_to_sar;
  const totalMonthly = claudeMonthly + waMonthly + reminderMonthly + voiceMonthly + railwayMonthly;

  const perMsg = inbound > 0 ? totalMonthly / inbound : 0;
  const margin = 1 + r.target_margin_pct / 100;
  const suggestedPerMsg = perMsg * margin;
  const suggestedMonthly = totalMonthly * margin;

  // Per-clinic estimate from each clinic's REAL usage (hosting is platform-wide, excluded here).
  const clinicCost = (c: any) =>
    c.inbound * (claudePerMsgSar + waConvRate) +
    c.reminders * r.whatsapp_sar_per_reminder +
    c.voice * r.voice_sar_per_message;
  const clinicsTotalCost = clinics.reduce((s: number, c: any) => s + clinicCost(c), 0);

  const costRows = [
    { key: "claude", label: t("calculator.claudeCost"), icon: <SmartToyIcon fontSize="small" />, color: "#6366f1", value: claudeMonthly },
    { key: "wa", label: t("calculator.waCost"), icon: <WhatsAppIcon fontSize="small" />, color: "#25D366", value: waMonthly },
    { key: "reminders", label: t("calculator.reminderCost"), icon: <NotificationsIcon fontSize="small" />, color: "#f43f5e", value: reminderMonthly },
    { key: "voice", label: t("calculator.voiceCost"), icon: <GraphicEqIcon fontSize="small" />, color: "#0ea5e9", value: voiceMonthly },
    { key: "railway", label: t("calculator.railwayCost"), icon: <CloudIcon fontSize="small" />, color: "#f59e0b", value: railwayMonthly },
  ];

  const numField = (k: keyof Rates, label: string, step = "any") => (
    <TextField fullWidth size="small" type="number" label={label} value={r[k]}
      onChange={setRate(k)} inputProps={{ step, min: 0 }} />
  );

  return (
    <>
      <PageTitle title={t("calculator.title")} subtitle={t("calculator.subtitle")} right={
        <Chip variant="outlined" label={t("common.period", { period })} />
      } />

      {/* Headline numbers */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}>
          <KpiCard label={t("calculator.totalCost")} value={`${sar(totalMonthly)} ${t("calculator.sar")}`}
            icon={<PaymentsIcon fontSize="small" />} color="primary" />
        </Grid>
        <Grid item xs={6} md={3}>
          <KpiCard label={t("calculator.perInquiry")} value={`${sar(perMsg)} ${t("calculator.sar")}`}
            icon={<ForumIcon fontSize="small" />} color="secondary" />
        </Grid>
        <Grid item xs={6} md={3}>
          <KpiCard label={t("calculator.suggestedPrice")} value={`${sar(suggestedPerMsg)} ${t("calculator.sar")}`}
            icon={<PaymentsIcon fontSize="small" />} color="success" />
        </Grid>
        <Grid item xs={6} md={3}>
          <KpiCard label={t("calculator.suggestedMonthly")} value={`${sar(suggestedMonthly)} ${t("calculator.sar")}`}
            icon={<PaymentsIcon fontSize="small" />} color="info" />
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        {/* Left: inputs */}
        <Grid item xs={12} md={7}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
                <Typography variant="subtitle2" fontWeight={800}>{t("calculator.volumeSection")}</Typography>
                <ToggleButtonGroup size="small" exclusive value={mode} onChange={(_, v) => v && setMode(v)}>
                  <ToggleButton value="projected">{t("calculator.volumeProjected")}</ToggleButton>
                  <ToggleButton value="actual">{t("calculator.volumeActual")}</ToggleButton>
                </ToggleButtonGroup>
              </Stack>
              {mode === "actual" ? (
                <Typography variant="body2" color="text.secondary">
                  {t("calculator.actualNote", {
                    period, inbound: intf(totals.inbound), replies: intf(totals.replies),
                    reminders: intf(totals.reminders), voice: intf(totals.voice),
                  })}
                </Typography>
              ) : (
                <Grid container spacing={2} alignItems="center">
                  <Grid item xs={12} sm={7}>
                    <TextField fullWidth label={t("calculator.messagesInput")} type="number"
                      value={messages} onChange={(e) => setMessages(num(e.target.value))}
                      inputProps={{ min: 0, step: 50 }}
                      InputProps={{ startAdornment: <InputAdornment position="start"><ForumIcon fontSize="small" /></InputAdornment> }}
                      helperText={t("calculator.messagesHelp")} />
                  </Grid>
                  <Grid item xs={12} sm={5}>
                    <TextField fullWidth size="small" type="number" label={t("calculator.voiceShare")}
                      value={voiceSharePct} onChange={(e) => setVoiceSharePct(num(e.target.value))}
                      inputProps={{ min: 0, max: 100 }} />
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">
                      {t("calculator.derived", { replies: intf(replies), reminders: intf(reminders) })}
                    </Typography>
                  </Grid>
                </Grid>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="subtitle2" fontWeight={800}>{t("calculator.ratesSection")}</Typography>
                <Button size="small" color="inherit" startIcon={<RestartAltIcon fontSize="small" />} onClick={reset}>
                  {t("calculator.resetRates")}
                </Button>
              </Stack>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                {t("calculator.ratesHint")}
              </Typography>

              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>{numField("usd_to_sar", t("calculator.fx"))}</Grid>
                <Grid item xs={12} sm={6}>{numField("railway_usd_per_month", t("calculator.railwayMonthly"))}</Grid>
              </Grid>

              <Divider sx={{ my: 2 }}><Chip size="small" icon={<SmartToyIcon sx={{ fontSize: 15 }} />}
                label={t("calculator.claudeGroup", { model })} /></Divider>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>{numField("claude_input_usd_per_mtok", t("calculator.claudeInPrice"))}</Grid>
                <Grid item xs={12} sm={6}>{numField("claude_output_usd_per_mtok", t("calculator.claudeOutPrice"))}</Grid>
                <Grid item xs={12} sm={6}>{numField("avg_input_tokens_per_inquiry", t("calculator.avgInTokens"), "1")}</Grid>
                <Grid item xs={12} sm={6}>{numField("avg_output_tokens_per_inquiry", t("calculator.avgOutTokens"), "1")}</Grid>
              </Grid>

              <Divider sx={{ my: 2 }}><Chip size="small" icon={<WhatsAppIcon sx={{ fontSize: 15 }} />}
                label={t("calculator.waGroup")} /></Divider>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>{numField("whatsapp_sar_per_conversation", t("calculator.waPerConv"))}</Grid>
                <Grid item xs={12} sm={6}>{numField("messages_per_conversation", t("calculator.msgsPerConv"), "1")}</Grid>
                <Grid item xs={12} sm={6}>{numField("whatsapp_sar_per_reminder", t("calculator.waReminderRate"))}</Grid>
                <Grid item xs={12} sm={6}>{numField("reminders_per_inquiry", t("calculator.remindersPer"), "0.01")}</Grid>
                <Grid item xs={12} sm={6}>{numField("replies_per_inquiry", t("calculator.repliesPer"), "0.1")}</Grid>
                <Grid item xs={12} sm={6}>{numField("voice_sar_per_message", t("calculator.voicePerMsg"))}</Grid>
              </Grid>

              <Divider sx={{ my: 2 }}><Chip size="small" icon={<PaymentsIcon sx={{ fontSize: 15 }} />}
                label={t("calculator.targetMargin")} /></Divider>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>{numField("target_margin_pct", t("calculator.targetMargin"), "1")}</Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Right: results + exact per-clinic usage */}
        <Grid item xs={12} md={5}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1.5 }}>{t("calculator.resultsSection")}</Typography>
              <Stack spacing={1.25}>
                {costRows.map((row) => {
                  const pct = totalMonthly > 0 ? (row.value / totalMonthly) * 100 : 0;
                  return (
                    <Box key={row.key}>
                      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
                        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ color: row.color }}>
                          {row.icon}
                          <Typography variant="body2" fontWeight={700} color="text.primary">{row.label}</Typography>
                        </Stack>
                        <Typography variant="body2" fontWeight={700}>{sar(row.value)} {t("calculator.sar")}</Typography>
                      </Stack>
                      <Box sx={{ height: 7, borderRadius: 4, overflow: "hidden", bgcolor: (th) => alpha(th.palette.text.primary, 0.06) }}>
                        <Box sx={{ width: `${pct}%`, height: "100%", bgcolor: row.color, transition: "width .4s ease" }} />
                      </Box>
                    </Box>
                  );
                })}
              </Stack>
              <Divider sx={{ my: 2 }} />
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Typography fontWeight={800}>{t("calculator.totalCost")}</Typography>
                <Typography fontWeight={800} variant="h6">{sar(totalMonthly)} {t("calculator.sar")}</Typography>
              </Stack>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 0.5 }}>
                <Typography variant="body2" color="text.secondary">{t("calculator.perInquiry")}</Typography>
                <Typography variant="body2" fontWeight={700}>{sar(perMsg)} {t("calculator.sar")}</Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
                {t("calculator.disclaimer")}
              </Typography>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1 }}>{t("calculator.perClinicSection")}</Typography>
              {clinics.length === 0 ? (
                <Typography variant="body2" color="text.secondary">{t("calculator.noClinics")}</Typography>
              ) : (
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>{t("calculator.colClinic")}</TableCell>
                      <TableCell align="right">{t("calculator.colInbound")}</TableCell>
                      <TableCell align="right">{t("calculator.colReplies")}</TableCell>
                      <TableCell align="right">{t("calculator.colReminders")}</TableCell>
                      <TableCell align="right">{t("calculator.colVoice")}</TableCell>
                      <TableCell align="right">{t("calculator.colCost")}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {clinics.map((c: any) => (
                      <TableRow key={c.id}>
                        <TableCell sx={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</TableCell>
                        <TableCell align="right">{intf(c.inbound)}</TableCell>
                        <TableCell align="right">{intf(c.replies)}</TableCell>
                        <TableCell align="right">{intf(c.reminders)}</TableCell>
                        <TableCell align="right">{intf(c.voice)}</TableCell>
                        <TableCell align="right">{sar(clinicCost(c))}</TableCell>
                      </TableRow>
                    ))}
                    {clinics.length > 1 && (
                      <TableRow sx={{ "& td": { fontWeight: 800, borderTop: (th) => `2px solid ${th.palette.divider}` } }}>
                        <TableCell>{t("calculator.totalRow")}</TableCell>
                        <TableCell align="right">{intf(totals.inbound)}</TableCell>
                        <TableCell align="right">{intf(totals.replies)}</TableCell>
                        <TableCell align="right">{intf(totals.reminders)}</TableCell>
                        <TableCell align="right">{intf(totals.voice)}</TableCell>
                        <TableCell align="right">{sar(clinicsTotalCost)}</TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
