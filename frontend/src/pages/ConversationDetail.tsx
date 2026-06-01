import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, CardContent, Box, Typography, Button, Stack, Chip, Grid, Paper,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import RefreshIcon from "@mui/icons-material/Refresh";
import { apiPost } from "../api";
import { useApiQuery, PageTitle, fmtDate, Loading, QueryError } from "../lib";

export default function ConversationDetail() {
  const { wa } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useApiQuery<any>(["conversation", wa], `/conversations/${wa}`);
  const refresh = useMutation({
    mutationFn: () => apiPost(`/conversations/${wa}/analysis/refresh`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversation", wa] }),
  });

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { messages = [], analysis } = q.data;

  return (
    <>
      <PageTitle
        title={`+${wa}`}
        right={<Button startIcon={<ArrowBackIcon />} onClick={() => nav("/conversations")}>Back</Button>}
      />
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent sx={{ maxHeight: "70vh", overflow: "auto" }}>
              <Stack spacing={1}>
                {messages.map((m: any) => {
                  const inbound = m.direction === "in";
                  return (
                    <Box key={m.id} sx={{ display: "flex", justifyContent: inbound ? "flex-start" : "flex-end" }}>
                      <Paper sx={{
                        p: 1.2, px: 1.6, maxWidth: "75%",
                        bgcolor: inbound ? "#f1f5f9" : "primary.main",
                        color: inbound ? "text.primary" : "#fff",
                      }}>
                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{m.message}</Typography>
                        <Typography variant="caption" sx={{ opacity: 0.7, display: "block", mt: 0.5 }}>
                          {fmtDate(m.created_at)}{m.source ? ` · ${m.source}` : ""}
                        </Typography>
                      </Paper>
                    </Box>
                  );
                })}
                {messages.length === 0 && <Typography color="text.secondary">No messages.</Typography>}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography fontWeight={700}>AI analysis</Typography>
                <Button size="small" startIcon={<RefreshIcon />} disabled={refresh.isPending}
                  onClick={() => refresh.mutate()}>Refresh</Button>
              </Stack>
              {!analysis && <Typography variant="body2" color="text.secondary">No analysis yet.</Typography>}
              {analysis && (
                <Stack spacing={1}>
                  {analysis.customer_name && <Field k="Name" v={analysis.customer_name} />}
                  {analysis.requested_service && <Field k="Service" v={analysis.requested_service} />}
                  {analysis.lead_band && <Box><Chip size="small" label={`lead: ${analysis.lead_band} (${analysis.lead_score ?? "?"})`} /></Box>}
                  {analysis.next_action && <Field k="Next" v={analysis.next_action} />}
                  {analysis.summary && <Typography variant="body2" color="text.secondary">{analysis.summary}</Typography>}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}

function Field({ k, v }: { k: string; v: any }) {
  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 64 }}>{k}</Typography>
      <Typography variant="body2">{String(v)}</Typography>
    </Box>
  );
}
