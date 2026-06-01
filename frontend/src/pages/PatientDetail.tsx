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
import { apiPost } from "../api";
import { useApiQuery, Loading, QueryError, fmtDate, EmptyState, useToast } from "../lib";
import { useLive } from "../realtime";

const statusColor: Record<string, any> = { confirmed: "success", completed: "info", cancelled: "default", no_show: "warning" };
// Apple system typeface for that native-chat feel; falls back to the app font elsewhere.
const APPLE_FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "Segoe UI", system-ui, sans-serif';
const GROUP_GAP_MS = 5 * 60 * 1000;

const popIn = keyframes`from { opacity: 0; transform: translateY(10px) scale(.96); } to { opacity: 1; transform: none; }`;
const wave = keyframes`0%,60%,100% { transform: translateY(0); opacity: .5; } 30% { transform: translateY(-5px); opacity: 1; }`;

function dayLabel(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso); const now = new Date();
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = (day(now) - day(d)) / 86400000;
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", day: "2-digit", month: "short" });
}
function clock(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

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
              {clock(m.created_at)}{m.source && m.source !== "text" ? ` · ${m.source}` : ""}
            </Typography>
            {!inb && <DoneAllIcon sx={{ fontSize: 13, color: "#0A84FF" }} />}
          </Stack>
        )}
      </Box>
    </Box>
  );
}

export default function PatientDetail() {
  const { wa } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { typing, activity } = useLive();
  const [tab, setTab] = useState(0);
  const q = useApiQuery<any>(["patient", wa], `/patients/${wa}`);
  const refresh = useMutation({
    mutationFn: () => apiPost(`/conversations/${wa}/analysis/refresh`),
    onSuccess: () => { toast.ok("Analysis refreshed"); qc.invalidateQueries({ queryKey: ["patient", wa] }); },
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
  const initials = (p.name || "P").slice(0, 2).toUpperCase();
  const laid = layout(messages);

  return (
    <>
      <Button startIcon={<ArrowBackIcon />} onClick={() => nav("/conversations")} sx={{ mb: 1.5 }}>
        Back to Patient Chats
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
            <Typography variant="h5" sx={{ color: "#fff" }}>{p.name || "Unknown patient"}</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography sx={{ color: alpha("#fff", 0.85) }}>+{p.wa_user}{p.clinic ? ` · ${p.clinic}` : ""}</Typography>
              {isTyping && (
                <Stack direction="row" spacing={0.6} alignItems="center">
                  <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "#34d399",
                    boxShadow: "0 0 0 0 #34d399", animation: `${wave} 1.2s ease-in-out infinite` }} />
                  <Typography sx={{ color: "#d1fae5", fontWeight: 700, fontSize: 13 }}>typing…</Typography>
                </Stack>
              )}
            </Stack>
            <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
              {a?.lead_band && <Chip size="small" label={`Lead: ${a.lead_band}${a.lead_score != null ? ` (${a.lead_score})` : ""}`}
                sx={{ bgcolor: alpha("#fff", 0.18), color: "#fff", fontWeight: 700 }} />}
              {a?.urgency && <Chip size="small" label={`Urgency: ${a.urgency}`} sx={{ bgcolor: alpha("#fff", 0.18), color: "#fff", fontWeight: 700 }} />}
            </Stack>
          </Box>
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
            <Stat label="Messages" value={p.message_count} />
            <Stat label="Appointments" value={p.appointments?.length ?? 0} />
            <Stat label="Reviews" value={p.reviews?.length ?? 0} />
            <Stat label="No-shows" value={p.no_shows?.length ?? 0} />
          </Stack>
        </Stack>
      </Box>

      <Card>
        <Tabs value={tab} onChange={(_e, t) => setTab(t)}
          sx={{ borderBottom: 1, borderColor: "divider", px: 1,
            "& .MuiTab-root": { fontWeight: 700, textTransform: "none" } }}>
          <Tab label="Conversation" />
          <Tab label={`Appointments (${p.appointments?.length ?? 0})`} />
          <Tab label={`Reviews (${p.reviews?.length ?? 0})`} />
          <Tab label={`No-shows (${p.no_shows?.length ?? 0})`} />
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
                            {clock(m.created_at)}
                          </Typography>
                        </Box>
                      )}
                      <Bubble m={m} isFirst={isFirst} isLast={isLast} />
                    </Box>
                  ))}
                  {isTyping && <Box sx={{ mt: 0.9 }}><TypingBubble /></Box>}
                  {messages.length === 0 && !isTyping && <EmptyState text="No messages yet." />}
                </Box>
              </Grid>
              <Grid item xs={12} md={4}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3,
                  background: (t) => `linear-gradient(180deg, ${alpha(t.palette.secondary.main, 0.06)}, transparent)` }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <AutoAwesomeIcon fontSize="small" color="secondary" />
                      <Typography fontWeight={800}>AI analysis</Typography>
                    </Stack>
                    <Tooltip title="Re-run analysis">
                      <span><IconButton size="small" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
                        <RefreshIcon fontSize="small" />
                      </IconButton></span>
                    </Tooltip>
                  </Stack>
                  {!a && <Typography variant="body2" color="text.secondary">No analysis yet.</Typography>}
                  {a && <Stack spacing={1}>
                    {a.requested_service && <Field k="Service" v={a.requested_service} />}
                    {a.next_action && <Field k="Next" v={a.next_action} />}
                    {a.urgency && <Field k="Urgency" v={a.urgency} />}
                    {a.sentiment && <Field k="Sentiment" v={a.sentiment} />}
                    {a.summary && <Box sx={{ mt: 1, p: 1.5, borderRadius: 2, bgcolor: (t) => alpha(t.palette.text.primary, 0.04) }}>
                      <Typography variant="body2" color="text.secondary">{a.summary}</Typography>
                    </Box>}
                  </Stack>}
                </Paper>
              </Grid>
            </Grid>
          )}

          {tab === 1 && (<MiniTable cols={["Service", "Doctor", "When", "Status"]} empty="No appointments."
            rows={(p.appointments || []).map((x: any) => [x.service || "—", x.doctor || "—", fmtDate(x.start_at),
              <Chip size="small" color={statusColor[x.status] || "default"} label={x.status} />])} />)}

          {tab === 2 && (<MiniTable cols={["Rating", "Visit", "Comment", "When"]} empty="No reviews."
            rows={(p.reviews || []).map((x: any) => [
              x.rating ? <Rating value={x.rating} readOnly size="small" /> : "—",
              `${x.service || "—"}${x.doctor ? " · " + x.doctor : ""}`, x.comment || "", fmtDate(x.responded_at || x.created_at)])} />)}

          {tab === 3 && (<MiniTable cols={["Missed", "Stage", "Outcome", "Reason", "When"]} empty="No no-shows."
            rows={(p.no_shows || []).map((x: any) => [`${x.service || "—"}${x.doctor ? " · " + x.doctor : ""}`,
              <Chip size="small" variant="outlined" label={(x.stage || "").replace("_", " ")} />, x.outcome || "—", x.reason || "—", fmtDate(x.created_at)])} />)}
        </CardContent>
      </Card>
    </>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return (
    <Box sx={{ textAlign: "center", px: 1.5, py: 0.5, borderRadius: 2, bgcolor: alpha("#fff", 0.14), minWidth: 64 }}>
      <Typography variant="h6" sx={{ color: "#fff", lineHeight: 1.2 }}>{value ?? 0}</Typography>
      <Typography variant="caption" sx={{ color: alpha("#fff", 0.85) }}>{label}</Typography>
    </Box>
  );
}
function Field({ k, v }: { k: string; v: any }) {
  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 72 }}>{k}</Typography>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>{String(v)}</Typography>
    </Box>
  );
}
function MiniTable({ cols, rows, empty }: { cols: string[]; rows: any[][]; empty: string }) {
  if (!rows.length) return <EmptyState text={empty} />;
  return (
    <Table size="small">
      <TableHead><TableRow>{cols.map((c) => <TableCell key={c} sx={{ fontWeight: 700 }}>{c}</TableCell>)}</TableRow></TableHead>
      <TableBody>{rows.map((r, i) => <TableRow key={i} hover>{r.map((cell, j) => <TableCell key={j}>{cell}</TableCell>)}</TableRow>)}</TableBody>
    </Table>
  );
}
