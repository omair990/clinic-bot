import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Box, Typography, Button, Stack, Chip, Grid, Paper, Avatar, Tabs, Tab,
  Table, TableHead, TableRow, TableCell, TableBody, Rating, Divider, alpha,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import RefreshIcon from "@mui/icons-material/Refresh";
import { apiPost } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError, fmtDate, EmptyState, useToast } from "../lib";

const statusColor: Record<string, any> = { confirmed: "success", completed: "info", cancelled: "default", no_show: "warning" };

export default function PatientDetail() {
  const { wa } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState(0);
  const q = useApiQuery<any>(["patient", wa], `/patients/${wa}`);
  const refresh = useMutation({
    mutationFn: () => apiPost(`/conversations/${wa}/analysis/refresh`),
    onSuccess: () => { toast.ok("Analysis refreshed"); qc.invalidateQueries({ queryKey: ["patient", wa] }); },
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const p = q.data;
  const a = p.analysis;
  const initials = (p.name || "P").slice(0, 2).toUpperCase();

  return (
    <>
      <PageTitle title={`+${wa}`} right={<Button startIcon={<ArrowBackIcon />} onClick={() => nav("/conversations")}>Back</Button>} />

      {/* Profile header */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
            <Avatar sx={{ width: 56, height: 56, background: "linear-gradient(135deg,#14b8a6,#6366f1)" }}>{initials}</Avatar>
            <Box sx={{ flex: 1, minWidth: 200 }}>
              <Typography variant="h6">{p.name || "Unknown patient"}</Typography>
              <Typography variant="body2" color="text.secondary">+{p.wa_user}{p.clinic ? ` · ${p.clinic}` : ""}</Typography>
            </Box>
            <Stack direction="row" spacing={3}>
              <Metric label="Messages" value={p.message_count} />
              <Metric label="Appointments" value={p.appointments?.length ?? 0} />
              <Metric label="Reviews" value={p.reviews?.length ?? 0} />
              <Metric label="No-shows" value={p.no_shows?.length ?? 0} />
            </Stack>
            {a?.lead_band && <Chip color="secondary" variant="outlined" label={`lead: ${a.lead_band}${a.lead_score != null ? ` (${a.lead_score})` : ""}`} />}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <Tabs value={tab} onChange={(_e, t) => setTab(t)} sx={{ borderBottom: 1, borderColor: "divider", px: 1 }}>
          <Tab label="Conversation" />
          <Tab label={`Appointments (${p.appointments?.length ?? 0})`} />
          <Tab label={`Reviews (${p.reviews?.length ?? 0})`} />
          <Tab label={`No-shows (${p.no_shows?.length ?? 0})`} />
        </Tabs>
        <CardContent>
          {tab === 0 && (
            <Grid container spacing={2}>
              <Grid item xs={12} md={8}>
                <Box sx={{ maxHeight: "60vh", overflow: "auto", pr: 1 }}>
                  <Stack spacing={1}>
                    {(p.messages || []).map((m: any) => {
                      const inb = m.direction === "in";
                      return (
                        <Box key={m.id} sx={{ display: "flex", justifyContent: inb ? "flex-start" : "flex-end" }}>
                          <Paper sx={{ p: 1.2, px: 1.6, maxWidth: "78%", bgcolor: inb ? (t) => alpha(t.palette.text.primary, 0.06) : "primary.main", color: inb ? "text.primary" : "#fff" }}>
                            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{m.message}</Typography>
                            <Typography variant="caption" sx={{ opacity: 0.7, display: "block", mt: 0.5 }}>{fmtDate(m.created_at)}{m.source ? ` · ${m.source}` : ""}</Typography>
                          </Paper>
                        </Box>
                      );
                    })}
                    {(p.messages || []).length === 0 && <EmptyState text="No messages." />}
                  </Stack>
                </Box>
              </Grid>
              <Grid item xs={12} md={4}>
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                    <Typography fontWeight={700}>AI analysis</Typography>
                    <Button size="small" startIcon={<RefreshIcon />} disabled={refresh.isPending} onClick={() => refresh.mutate()}>Refresh</Button>
                  </Stack>
                  {!a && <Typography variant="body2" color="text.secondary">No analysis yet.</Typography>}
                  {a && <Stack spacing={0.8}>
                    {a.requested_service && <Field k="Service" v={a.requested_service} />}
                    {a.next_action && <Field k="Next" v={a.next_action} />}
                    {a.urgency && <Field k="Urgency" v={a.urgency} />}
                    {a.sentiment && <Field k="Sentiment" v={a.sentiment} />}
                    {a.summary && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{a.summary}</Typography>}
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

function Metric({ label, value }: { label: string; value: any }) {
  return <Box sx={{ textAlign: "center" }}><Typography variant="h6">{value ?? 0}</Typography><Typography variant="caption" color="text.secondary">{label}</Typography></Box>;
}
function Field({ k, v }: { k: string; v: any }) {
  return <Box sx={{ display: "flex", gap: 1 }}><Typography variant="body2" color="text.secondary" sx={{ minWidth: 70 }}>{k}</Typography><Typography variant="body2">{String(v)}</Typography></Box>;
}
function MiniTable({ cols, rows, empty }: { cols: string[]; rows: any[][]; empty: string }) {
  if (!rows.length) return <EmptyState text={empty} />;
  return (
    <Table size="small">
      <TableHead><TableRow>{cols.map((c) => <TableCell key={c}>{c}</TableCell>)}</TableRow></TableHead>
      <TableBody>{rows.map((r, i) => <TableRow key={i}>{r.map((cell, j) => <TableCell key={j}>{cell}</TableCell>)}</TableRow>)}</TableBody>
    </Table>
  );
}
