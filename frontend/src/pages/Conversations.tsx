import { useNavigate } from "react-router-dom";
import {
  Card, Table, TableHead, TableRow, TableCell, TableBody, Chip, Typography,
} from "@mui/material";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, Loading, QueryError } from "../lib";

const intentColor: Record<string, any> = {
  appointment: "success", emergency: "error", handover: "warning", complaint: "warning",
};

export default function Conversations() {
  const nav = useNavigate();
  const [clinic] = useClinic();
  const q = useApiQuery<any>(["conversations", clinic], `/conversations?clinic=${clinic}`);
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { rows = [], is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  return (
    <>
      <PageTitle title="Conversations" right={<ClinicFilter meta={q.data} />} />
      <Card>
        <Table size="small">
          <TableHead>
            <TableRow>
              {showClinic && <TableCell>Clinic</TableCell>}
              <TableCell>User</TableCell>
              <TableCell>Last message</TableCell>
              <TableCell>Class</TableCell>
              <TableCell>Lead</TableCell>
              <TableCell align="right">Msgs</TableCell>
              <TableCell>Last activity</TableCell>
              <TableCell>Flag</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r: any) => (
              <TableRow key={r.wa_user} hover sx={{ cursor: "pointer" }}
                onClick={() => nav(`/conversations/${r.wa_user}`)}>
                {showClinic && <TableCell><Typography variant="caption" color="text.secondary">{tenant_names[r.tenant_id] || "—"}</Typography></TableCell>}
                <TableCell>+{r.wa_user}</TableCell>
                <TableCell sx={{ maxWidth: 360, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  <Typography variant="caption" color="text.secondary">{r.last_direction === "in" ? "← " : "→ "}</Typography>
                  {r.last_message}
                </TableCell>
                <TableCell>{r.last_intent && <Chip size="small" label={r.last_intent} color={intentColor[r.last_intent] || "default"} />}</TableCell>
                <TableCell>{r.lead_band && <Chip size="small" variant="outlined" label={r.lead_band} />}</TableCell>
                <TableCell align="right">{r.msg_count}</TableCell>
                <TableCell><Typography variant="caption" color="text.secondary">{fmtDate(r.last_at)}</Typography></TableCell>
                <TableCell>{r.needs_human && <Chip size="small" color="error" label="needs human" />}</TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={showClinic ? 8 : 7} align="center" sx={{ py: 6, color: "text.secondary" }}>No conversations yet</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
