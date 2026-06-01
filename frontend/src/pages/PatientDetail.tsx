import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Box, Typography, Button, Stack, Chip, Grid, Paper, Avatar, Tabs, Tab,
  Table, TableHead, TableRow, TableCell, TableBody, Rating, alpha, keyframes, IconButton, Tooltip,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import RefreshIcon from "@mui/icons-material/Refresh";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesomeOutlined";
import { apiPost } from "../api";
import { useApiQuery, Loading, QueryError, fmtDate, EmptyState, useToast } from "../lib";
import { useLive } from "../realtime";

const statusColor: Record<string, any> = { confirmed: "success", completed: "info", cancelled: "default", no_show: "warning" };
const blink = keyframes`0%,80%,100%{opacity:.25}40%{opacity:1}`;

function dayLabel(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso); const now = new Date();
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = (day(now) - day(d)) / 86400000;
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", day: "2-digit", month: "short" });
}

function TypingBubble() {
  return (
    <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
      <Paper elevation={0} sx={{ p: 1.4, px: 1.8, borderRadius: "16px 16px 16px 4px",
        bgcolor: (t) => alpha(t.palette.text.primary, 0.06), display: "flex", gap: 0.6 }}>
        {[0, 1, 2].map((i) => (
          <Box key={i} sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "text.secondary",
            animation: `${blink} 1.3s infinite`, animationDelay: `${i * 0.18}s` }} />
        ))}
      </Paper>
    </Box>
  );
}

export default function PatientDetail() {
  const { wa } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { typing } = useLive();
  const [tab, setTab] = useState(0);
  const q = useApiQuery<any>(["patient", wa], `/patients/${wa}`);
  const refresh = useMutation({
    mutationFn: () => apiPost(`/conversations/${wa}/analysis/refresh`),
    onSuccess: () => { toast.ok("Analysis refreshed"); qc.invalidateQueries({ queryKey: ["patient", wa] }); },
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  const messages = q.data?.messages || [];
  const isTyping = !!wa && typing.has(wa);
  // Keep the thread pinned to the newest message as live turns stream in.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && tab === 0) el.scrollTop = el.scrollHeight;
  }, [messages.length, isTyping, tab]);

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const p = q.data;
  const a = p.analysis;
  const initials = (p.name || "P").slice(0, 2).toUpperCase();

  let lastDay = "";

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
            <Typography sx={{ color: alpha("#fff", 0.85) }}>
              +{p.wa_user}{p.clinic ? ` · ${p.clinic}` : ""}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
              {isTyping && <Chip size="small" label="online · typing" sx={{ bgcolor: alpha("#fff", 0.22), color: "#fff", fontWeight: 700 }} />}
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
                <Box ref={scrollRef} sx={{ maxHeight: "62vh", overflow: "auto", pr: 1, py: 1,
                  borderRadius: 3, bgcolor: (t) => alpha(t.palette.text.primary, 0.02) }}>
                  <Stack spacing={1.2} sx={{ px: 1 }}>
                    {messages.map((m: any) => {
                      const inb = m.direction === "in";
                      const d = dayLabel(m.created_at);
                      const showDay = d !== lastDay; lastDay = d;
                      return (
                        <Box key={m.id}>
                          {showDay && (
                            <Box sx={{ display: "flex", justifyContent: "center", my: 1 }}>
                              <Chip size="small" label={d} sx={{ bgcolor: (t) => alpha(t.palette.text.primary, 0.06), fontWeight: 600 }} />
                            </Box>
                          )}
                          <Box sx={{ display: "flex", justifyContent: inb ? "flex-start" : "flex-end" }}>
                            <Paper elevation={0} sx={{
                              p: 1.2, px: 1.6, maxWidth: "80%",
                              borderRadius: inb ? "16px 16px 16px 4px" : "16px 16px 4px 16px",
                              bgcolor: inb ? (t) => alpha(t.palette.text.primary, 0.06) : "transparent",
                              background: inb ? undefined : "linear-gradient(135deg,#14b8a6,#6366f1)",
                              color: inb ? "text.primary" : "#fff",
                            }}>
                              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{m.message}</Typography>
                              <Typography variant="caption" sx={{ opacity: 0.7, display: "block", mt: 0.4, textAlign: "right" }}>
                                {fmtDate(m.created_at)}{m.source ? ` · ${m.source}` : ""}
                              </Typography>
                            </Paper>
                          </Box>
                        </Box>
                      );
                    })}
                    {isTyping && <TypingBubble />}
                    {messages.length === 0 && !isTyping && <EmptyState text="No messages yet." />}
                  </Stack>
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
