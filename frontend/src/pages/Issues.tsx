import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card, Table, TableHead, TableRow, TableCell, TableBody, Chip, Button, Typography,
  ToggleButton, ToggleButtonGroup, Stack,
} from "@mui/material";
import { useSearchParams } from "react-router-dom";
import { apiPost } from "../api";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, Loading, QueryError } from "../lib";

const levelColor: Record<string, any> = { error: "error", warning: "warning", info: "default" };

export default function Issues() {
  const [clinic] = useClinic();
  const [params, setParams] = useSearchParams();
  const show = params.get("show") || "open";
  const qc = useQueryClient();
  const q = useApiQuery<any>(["logs", clinic, show], `/logs?clinic=${clinic}&show=${show}`);
  const resolve = useMutation({
    mutationFn: (id: number) => apiPost(`/logs/${id}/resolve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["logs"] }),
  });
  const setShow = (s: string) => { const n = new URLSearchParams(params); n.set("show", s); setParams(n); };

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { events = [], open_count, is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;

  return (
    <>
      <PageTitle title="Issues" right={<Stack direction="row" spacing={2} alignItems="center">
        <ClinicFilter meta={q.data} />
        <ToggleButtonGroup size="small" exclusive value={show} onChange={(_, v) => v && setShow(v)}>
          <ToggleButton value="open">Open ({open_count})</ToggleButton>
          <ToggleButton value="resolved">Resolved</ToggleButton>
          <ToggleButton value="all">All</ToggleButton>
        </ToggleButtonGroup>
      </Stack>} />
      <Card>
        <Table size="small">
          <TableHead><TableRow>
            {showClinic && <TableCell>Clinic</TableCell>}
            <TableCell>When</TableCell><TableCell>Level</TableCell><TableCell>Category</TableCell>
            <TableCell>Issue</TableCell><TableCell align="right"></TableCell>
          </TableRow></TableHead>
          <TableBody>
            {events.map((e: any) => (
              <TableRow key={e.id} hover sx={{ opacity: e.resolved ? 0.6 : 1 }}>
                {showClinic && <TableCell><Typography variant="caption" color="text.secondary">{tenant_names[e.tenant_id] || "—"}</Typography></TableCell>}
                <TableCell><Typography variant="caption" color="text.secondary">{fmtDate(e.created_at)}</Typography></TableCell>
                <TableCell><Chip size="small" color={levelColor[e.level] || "default"} label={e.level} /></TableCell>
                <TableCell>{e.category}</TableCell>
                <TableCell>{e.message}<Typography variant="caption" color="text.secondary" display="block" sx={{ maxWidth: 420, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{e.detail}</Typography></TableCell>
                <TableCell align="right">{e.resolved ? <Typography variant="caption" color="success.main">resolved</Typography> : <Button size="small" variant="contained" onClick={() => resolve.mutate(e.id)}>Resolve</Button>}</TableCell>
              </TableRow>
            ))}
            {events.length === 0 && <TableRow><TableCell colSpan={showClinic ? 6 : 5} align="center" sx={{ py: 6, color: "text.secondary" }}>No issues 🎉</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
