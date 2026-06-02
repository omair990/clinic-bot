import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Box, Typography, Button, Stack, Chip, Grid, Paper, Avatar, Tabs, Tab,
  Table, TableHead, TableRow, TableCell, TableBody, Rating, alpha, keyframes, IconButton, Tooltip,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import RefreshIcon from "@mui/icons-material/Refresh";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesomeOutlined";
import DoneAllIcon from "@mui/icons-material/DoneAll";
import FireIcon from "@mui/icons-material/LocalFireDepartmentRounded";
import MedicalServicesIcon from "@mui/icons-material/MedicalServicesOutlined";
import ScheduleIcon from "@mui/icons-material/ScheduleOutlined";
import ShieldIcon from "@mui/icons-material/HealthAndSafetyOutlined";
import BoltIcon from "@mui/icons-material/BoltOutlined";
import MoodIcon from "@mui/icons-material/SentimentSatisfiedAltOutlined";
import TipsIcon from "@mui/icons-material/TipsAndUpdatesOutlined";
import { apiPost } from "../api";
import { useApiQuery, Loading, QueryError, fmtDate, fmtTime, dayLabel, displayName, initials as initialsOf, EmptyState, useToast } from "../lib";
import { useLive } from "../realtime";
import { useT } from "../i18n";

const statusColor: Record<string, any> = { confirmed: "success", completed: "info", cancelled: "default", no_show: "warning" };
const leadMeta: Record<string, { c: string; label: string }> = {
  hot: { c: "#ef4444", label: "Hot lead" }, warm: { c: "#f59e0b", label: "Warm lead" }, cold: { c: "#38bdf8", label: "Cold lead" },
};
const urgencyColor: Record<string, any> = { high: "error", medium: "warning", low: "default" };
const sentimentColor: Record<string, any> = { positive: "success", negative: "error", neutral: "default" };
// Apple system typeface for that native-chat feel; falls back to the app font elsewhere.
const APPLE_FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "Segoe UI", system-ui, sans-serif';
const GROUP_GAP_MS = 5 * 60 * 1000;

const popIn = keyframes`from { opacity: 0; transform: translateY(10px) scale(.96); } to { opacity: 1; transform: none; }`;
const wave = keyframes`0%,60%,100% { transform: translateY(0); opacity: .5; } 30% { transform: translateY(-5px); opacity: 1; }`;

// Render WhatsApp / markdown inline formatting the same way the patient sees it on WhatsApp:
// **bold** or *bold*, _italic_, ~strike~, `mono`. Output is React nodes (never raw HTML),
// so patient/AI text can't inject markup. Newlines are preserved by the bubble's pre-wrap.
const FMT = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|_[^_\n]+_|~[^~\n]+~|`[^`\n]+`)/g;
function formatText(text: string) {
  return text.split(FMT).map((part, i) => {
    if (!part) return null;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*")) return <strong key={i}>{part.slice(1, -1)}</strong>;
    if (part.startsWith("_") && part.endsWith("_")) return <em key={i}>{part.slice(1, -1)}</em>;
    if (part.startsWith("~") && part.endsWith("~")) return <s key={i}>{part.slice(1, -1)}</s>;
    if (part.startsWith("`") && part.endsWith("`")) return (
      <Box component="code" key={i} sx={{ fontFamily: "monospace", fontSize: "0.92em", px: 0.5,
        borderRadius: 0.75, bgcolor: "rgba(127,127,127,.18)" }}>{part.slice(1, -1)}</Box>);
    return <span key={i}>{part}</span>;
  });
}

type Msg = { id: any; direction: "in" | "out"; message: string; created_at: string; source?: string; _live?: boolean };

// Group consecutive same-direction messages (within GROUP_GAP_MS) and flag day breaks,
// so we can render iMessage-style stacks with a single tail + timestamp per group.
function layout(messages: Msg[]) {
  return messages.map((m, i) => {
    const prev = messages[i - 1], next = messages[i + 1];
    const t = new Date(m.created_at).getTime();
    const samePrev = prev && prev.direction === m.direction && t - new Date(prev.created_at).getTime() < GROUP_GAP_MS;
    const sameNext = next && next.direction === m.direction && new Date(next.created_at).getTime() - t < GROUP_GAP_MS;
    const newDay = !prev || dayLabel(prev.created_at) !== dayLabel(m.created_at);
    return { m, isFirst: !samePrev, isLast: !sameNext, showSep: newDay };
  });
}

function TypingBubble() {
  return (
    <Box sx={{ display: "flex", justifyContent: "flex-start", animation: `${popIn} .25s ease both` }}>
      <Box sx={{ py: 1.3, px: 1.8, borderRadius: "20px 20px 20px 6px", display: "flex", gap: 0.7, alignItems: "center",
        bgcolor: (t) => (t.palette.mode === "dark" ? "#2C2C2E" : "#E9E9EB"),
        boxShadow: "0 1px 1px rgba(0,0,0,.06)" }}>
        {[0, 1, 2].map((i) => (
          <Box key={i} sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "text.secondary",
            animation: `${wave} 1.2s ease-in-out infinite`, animationDelay: `${i * 0.16}s` }} />
        ))}
      </Box>
    </Box>
  );
}

function Bubble({ m, isFirst, isLast }: { m: Msg; isFirst: boolean; isLast: boolean }) {
  const inb = m.direction === "in";
  const r = 20, tail = 6;
  const radius = inb
    ? `${isFirst ? r : tail}px ${r}px ${r}px ${isLast ? tail : r}px`
    : `${r}px ${isFirst ? r : tail}px ${isLast ? tail : r}px ${r}px`;
  return (
    <Box sx={{ display: "flex", justifyContent: inb ? "flex-start" : "flex-end", mt: isFirst ? 0.9 : 0.25 }}>
      <Box sx={{ maxWidth: "74%", animation: `${popIn} .26s cubic-bezier(.2,.7,.3,1) both` }}>
        <Box sx={{
          py: 0.95, px: 1.5, borderRadius: radius, fontFamily: APPLE_FONT,
          boxShadow: "0 1px 1px rgba(0,0,0,.07)",
          color: inb ? "text.primary" : "#fff",
          bgcolor: inb ? (t) => (t.palette.mode === "dark" ? "#2C2C2E" : "#E9E9EB") : undefined,
          background: inb ? undefined : "linear-gradient(180deg,#0A84FF 0%,#0066FF 100%)",
        }}>
          <Typography sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 15, lineHeight: 1.35, fontFamily: APPLE_FONT }}>
            {formatText(m.message)}
          </Typography>
        </Box>
        {isLast && (
          <Stack direction="row" spacing={0.5} alignItems="center"
            sx={{ justifyContent: inb ? "flex-start" : "flex-end", px: 0.5, mt: 0.4 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: 11 }}>
              {fmtTime(m.created_at)}{m.source && m.source !== "text" ? ` · ${m.source}` : ""}
            </Typography>
            {!inb && <DoneAllIcon sx={{ fontSize: 13, color: "#0A84FF" }} />}
          </Stack>
        )}
      </Box>
    </Box>
  );
}

// Premium AI analysis panel: lead temperature + score bar, icon'd fields, rationale.
function AIPanel({ a, busy, onRefresh }: { a: any; busy: boolean; onRefresh: () => void }) {
  const t = useT();
  const lead = a?.lead_band ? leadMeta[a.lead_band] : null;
  const leadLabel = a?.lead_band
    ? t(`patient.lead${a.lead_band.charAt(0).toUpperCase()}${a.lead_band.slice(1)}`)
    : "";
  const score = a?.lead_score;
  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, height: "100%",
      background: (t) => `linear-gradient(180deg, ${alpha(t.palette.secondary.main, 0.06)}, transparent)` }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <AutoAwesomeIcon fontSize="small" color="secondary" />
          <Typography fontWeight={800}>{t("patient.aiAnalysis")}</Typography>
        </Stack>
        <Tooltip title={t("patient.reRunAnalysis")}>
          <span><IconButton size="small" disabled={busy} onClick={onRefresh}><RefreshIcon fontSize="small" /></IconButton></span>
        </Tooltip>
      </Stack>

      {!a ? <Typography variant="body2" color="text.secondary">{t("patient.noAnalysis")}</Typography> : (
        <Stack spacing={1.75}>
          {lead && (
            <Box sx={{ p: 1.5, borderRadius: 2.5, border: (t) => `1px solid ${alpha(lead.c, 0.4)}`,
              bgcolor: alpha(lead.c, 0.1) }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Stack direction="row" spacing={0.75} alignItems="center">
                  {a.lead_band === "hot" && <FireIcon sx={{ color: lead.c, fontSize: 18 }} />}
                  <Typography fontWeight={800} sx={{ color: lead.c }}>{leadLabel}</Typography>
                </Stack>
                {score != null && <Typography fontWeight={800} sx={{ color: lead.c }}>{score}<Typography component="span" variant="caption" color="text.secondary"> / 100</Typography></Typography>}
              </Stack>
              {score != null && (
                <Box sx={{ mt: 1, height: 7, borderRadius: 4, overflow: "hidden", bgcolor: (t) => alpha(t.palette.text.primary, 0.08) }}>
                  <Box sx={{ width: `${Math.max(0, Math.min(100, score))}%`, height: "100%", bgcolor: lead.c, transition: "width .4s ease" }} />
                </Box>
              )}
            </Box>
          )}

          <Stack spacing={1.25}>
            {a.requested_service && <FieldRow icon={<MedicalServicesIcon fontSize="small" />} label={t("patient.fieldService")} value={a.requested_service} />}
            {a.appointment_preference && <FieldRow icon={<ScheduleIcon fontSize="small" />} label={t("patient.fieldPreference")} value={a.appointment_preference} />}
            {a.insurance && <FieldRow icon={<ShieldIcon fontSize="small" />} label={t("patient.fieldInsurance")} value={a.insurance} />}
            {a.urgency && <FieldRow icon={<BoltIcon fontSize="small" />} label={t("patient.fieldUrgency")}
              value={<Chip size="small" color={urgencyColor[a.urgency] || "default"} variant="outlined" label={t(`patient.urgency_${a.urgency}`)} sx={{ textTransform: "capitalize", height: 22 }} />} />}
            {a.sentiment && <FieldRow icon={<MoodIcon fontSize="small" />} label={t("patient.fieldSentiment")}
              value={<Chip size="small" color={sentimentColor[a.sentiment] || "default"} variant="outlined" label={t(`patient.sentiment_${a.sentiment}`)} sx={{ textTransform: "capitalize", height: 22 }} />} />}
            {a.next_action && <FieldRow icon={<BoltIcon fontSize="small" />} label={t("patient.fieldNext")} value={a.next_action} />}
          </Stack>

          {a.lead_rationale && (
            <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: (t) => alpha(t.palette.text.primary, 0.04) }}>
              <Stack direction="row" spacing={1} alignItems="flex-start">
                <TipsIcon fontSize="small" color="secondary" sx={{ mt: 0.1 }} />
                <Typography variant="body2" color="text.secondary">{a.lead_rationale}</Typography>
              </Stack>
            </Box>
          )}
        </Stack>
      )}
    </Paper>
  );
}

export default function PatientDetail() {
  const { wa } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const { typing, activity } = useLive();
  const [tab, setTab] = useState(0);
  const q = useApiQuery<any>(["patient", wa], `/patients/${wa}`);
  const refresh = useMutation({
    mutationFn: () => apiPost(`/conversations/${wa}/analysis/refresh`),
    onSuccess: () => { toast.ok(t("patient.analysisRefreshed")); qc.invalidateQueries({ queryKey: ["patient", wa] }); },
  });

  const fetched: Msg[] = q.data?.messages || [];
  const isTyping = !!wa && typing.has(wa);

  // Live merge: append SSE turns for this patient that the refetch hasn't landed yet, so
  // new messages pop in instantly. Once the (debounced) refetch includes them, they match
  // a fetched row by direction+text and drop out of `pending` — no duplicates, no flicker.
  const messages: Msg[] = useMemo(() => {
    const recent = new Set(fetched.slice(-14).map((m) => `${m.direction}|${m.message}`));
    const pending = activity
      .filter((a) => a.wa_user === wa && !recent.has(`${a.direction}|${a.text}`))
      .slice().reverse()
      .map((a) => ({ id: `live-${a.key}`, direction: a.direction, message: a.text,
                     created_at: new Date(a.ts).toISOString(), source: a.intent, _live: true } as Msg));
    return [...fetched, ...pending];
  }, [fetched, activity, wa]);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el && tab === 0) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages.length, isTyping, tab]);

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const p = q.data;
  const a = p.analysis;
  const initials = initialsOf(p.name, p.wa_user);
  const laid = layout(messages);

  return (
    <>
      <Button startIcon={<ArrowBackIcon />} onClick={() => nav("/conversations")} sx={{ mb: 1.5 }}>
        {t("patient.backToChats")}
      </Button>

      {/* Premium gradient profile header */}
      <Box sx={{ position: "relative", overflow: "hidden", borderRadius: 4, mb: 2, p: { xs: 2.5, md: 3 },
        color: "#fff", background: "linear-gradient(120deg,#0f766e 0%,#14b8a6 45%,#6366f1 100%)",
        boxShadow: "0 16px 40px -20px rgba(20,184,166,.6)" }}>
        <Box sx={{ position: "absolute", right: -50, top: -60, width: 200, height: 200, borderRadius: "50%", background: alpha("#fff", 0.1) }} />
        <Stack direction="row" spacing={2.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ position: "relative" }}>
          <Avatar sx={{ width: 64, height: 64, fontSize: 22, fontWeight: 800, bgcolor: alpha("#fff", 0.2), color: "#fff",
            border: `2px solid ${alpha("#fff", 0.5)}` }}>{initials}</Avatar>
          <Box sx={{ flex: 1, minWidth: 200 }}>
            <Typography variant="h5" sx={{ color: "#fff" }}>{displayName(p.name, p.wa_user)}</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography sx={{ color: alpha("#fff", 0.85) }}>+{p.wa_user}{p.clinic ? ` · ${p.clinic}` : ""}</Typography>
              {isTyping && (
                <Stack direction="row" spacing={0.6} alignItems="center">
                  <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "#34d399",
                    boxShadow: "0 0 0 0 #34d399", animation: `${wave} 1.2s ease-in-out infinite` }} />
                  <Typography sx={{ color: "#d1fae5", fontWeight: 700, fontSize: 13 }}>{t("patient.typing")}</Typography>
                </Stack>
              )}
            </Stack>
            <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
              {a?.lead_band && <Chip size="small" icon={a.lead_band === "hot" ? <FireIcon sx={{ fontSize: "15px !important", color: "#fff !important" }} /> : undefined}
                label={`${t("patient.leadChip", { band: t(`patient.band_${a.lead_band}`) })}${a.lead_score != null ? ` (${a.lead_score})` : ""}`}
                sx={{ bgcolor: alpha("#fff", 0.18), color: "#fff", fontWeight: 700, textTransform: "capitalize" }} />}
              {a?.urgency && <Chip size="small" label={t("patient.urgencyChip", { x: t(`patient.urgency_${a.urgency}`) })} sx={{ bgcolor: alpha("#fff", 0.18), color: "#fff", fontWeight: 700, textTransform: "capitalize" }} />}
            </Stack>
          </Box>
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
            <Stat label={t("patient.statMessages")} value={p.message_count} active={tab === 0} onClick={() => setTab(0)} />
            <Stat label={t("patient.statAppointments")} value={p.appointments?.length ?? 0} active={tab === 1} onClick={() => setTab(1)} />
            <Stat label={t("patient.statReviews")} value={p.reviews?.length ?? 0} active={tab === 2} onClick={() => setTab(2)} />
            <Stat label={t("patient.statMissed")} value={p.no_shows?.length ?? 0} active={tab === 3} onClick={() => setTab(3)} />
          </Stack>
        </Stack>
      </Box>

      <Card>
        <Tabs value={tab} onChange={(_e, t) => setTab(t)}
          sx={{ borderBottom: 1, borderColor: "divider", px: 1,
            "& .MuiTab-root": { fontWeight: 700, textTransform: "none" } }}>
          <Tab label={t("patient.tabConversation")} />
          <Tab label={t("patient.tabAppointments", { n: p.appointments?.length ?? 0 })} />
          <Tab label={t("patient.tabReviews", { n: p.reviews?.length ?? 0 })} />
          <Tab label={t("patient.tabMissed", { n: p.no_shows?.length ?? 0 })} />
        </Tabs>
        <CardContent>
          {tab === 0 && (
            <Grid container spacing={2}>
              <Grid item xs={12} md={8}>
                <Box ref={scrollRef} sx={{ height: "62vh", overflow: "auto", px: { xs: 1, sm: 2 }, py: 1.5,
                  borderRadius: 3, scrollBehavior: "smooth",
                  bgcolor: (t) => (t.palette.mode === "dark" ? alpha("#000", 0.18) : alpha("#000", 0.015)) }}>
                  {laid.map(({ m, isFirst, isLast, showSep }) => (
                    <Box key={m.id}>
                      {showSep && (
                        <Box sx={{ textAlign: "center", my: 1.5 }}>
                          <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 700, fontFamily: APPLE_FONT }}>
                            {dayLabel(m.created_at)}
                          </Typography>
                          <Typography component="span" variant="caption" sx={{ color: "text.disabled", ml: 0.8, fontFamily: APPLE_FONT }}>
                            {fmtTime(m.created_at)}
                          </Typography>
                        </Box>
                      )}
                      <Bubble m={m} isFirst={isFirst} isLast={isLast} />
                    </Box>
                  ))}
                  {isTyping && <Box sx={{ mt: 0.9 }}><TypingBubble /></Box>}
                  {messages.length === 0 && !isTyping && <EmptyState text={t("patient.noMessages")} />}
                </Box>
              </Grid>
              <Grid item xs={12} md={4}>
                <AIPanel a={a} busy={refresh.isPending} onRefresh={() => refresh.mutate()} />
              </Grid>
            </Grid>
          )}

          {tab === 1 && (<MiniTable cols={[t("patient.colService"), t("patient.colDoctor"), t("patient.colWhen"), t("patient.colStatus")]} empty={t("patient.noAppointments")}
            rows={(p.appointments || []).map((x: any) => [x.service || "—", x.doctor || "—", fmtDate(x.start_at),
              <Chip size="small" color={statusColor[x.status] || "default"} label={t(`enums.appt.${x.status}`)} />])} />)}

          {tab === 2 && (<MiniTable cols={[t("patient.colRating"), t("patient.colVisit"), t("patient.colComment"), t("patient.colWhen")]} empty={t("patient.noReviews")}
            rows={(p.reviews || []).map((x: any) => [
              x.rating ? <Rating value={x.rating} readOnly size="small" /> : "—",
              `${x.service || "—"}${x.doctor ? " · " + x.doctor : ""}`, x.comment || "", fmtDate(x.responded_at || x.created_at)])} />)}

          {tab === 3 && (<MiniTable cols={[t("patient.colService"), t("patient.colStage"), t("patient.colOutcome"), t("patient.colReason"), t("patient.colWhen")]} empty={t("patient.noMissedVisits")}
            rows={(p.no_shows || []).map((x: any) => [`${x.service || "—"}${x.doctor ? " · " + x.doctor : ""}`,
              <Chip size="small" variant="outlined" label={t(`enums.stage.${x.stage}`)} />, x.outcome || "—", x.reason || "—", fmtDate(x.created_at)])} />)}
        </CardContent>
      </Card>
    </>
  );
}

function Stat({ label, value, active, onClick }: { label: string; value: any; active?: boolean; onClick?: () => void }) {
  return (
    <Box onClick={onClick} sx={{ textAlign: "center", px: 1.5, py: 0.5, borderRadius: 2, minWidth: 64, cursor: onClick ? "pointer" : "default",
      bgcolor: alpha("#fff", active ? 0.28 : 0.14), border: `1px solid ${alpha("#fff", active ? 0.5 : 0)}`,
      transition: "background .15s ease", "&:hover": onClick ? { bgcolor: alpha("#fff", 0.24) } : undefined }}>
      <Typography variant="h6" sx={{ color: "#fff", lineHeight: 1.2 }}>{value ?? 0}</Typography>
      <Typography variant="caption" sx={{ color: alpha("#fff", 0.85) }}>{label}</Typography>
    </Box>
  );
}
function FieldRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <Stack direction="row" spacing={1.25} alignItems="flex-start">
      <Box sx={{ color: "text.secondary", mt: 0.1 }}>{icon}</Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={700}>{label}</Typography>
        <Box sx={{ fontSize: 14, fontWeight: 600 }}>{value}</Box>
      </Box>
    </Stack>
  );
}
function MiniTable({ cols, rows, empty }: { cols: string[]; rows: any[][]; empty: string }) {
  if (!rows.length) return <EmptyState text={empty} />;
  return (
    <Box sx={{ borderRadius: 2.5, overflow: "hidden", border: (t) => `1px solid ${t.palette.divider}` }}>
      <Table size="small">
        <TableHead><TableRow sx={{ "& th": { bgcolor: (t) => alpha(t.palette.text.primary, 0.04), borderBottom: "none" } }}>
          {cols.map((c) => <TableCell key={c} sx={{ fontWeight: 800 }}>{c}</TableCell>)}
        </TableRow></TableHead>
        <TableBody>{rows.map((r, i) => (
          <TableRow key={i} hover sx={{ "&:last-child td": { border: 0 } }}>
            {r.map((cell, j) => <TableCell key={j}>{cell}</TableCell>)}
          </TableRow>
        ))}</TableBody>
      </Table>
    </Box>
  );
}
