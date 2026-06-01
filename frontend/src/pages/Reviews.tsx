import {
  Card, CardContent, Grid, Table, TableHead, TableRow, TableCell, TableBody, Chip, Typography, Rating,
} from "@mui/material";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, Loading, QueryError } from "../lib";

export default function Reviews() {
  const [clinic] = useClinic();
  const q = useApiQuery<any>(["reviews", clinic], `/reviews?clinic=${clinic}`);
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const { rows = [], stats = {}, is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const rate = stats.requested ? Math.floor((stats.responded / stats.requested) * 100) : 0;

  return (
    <>
      <PageTitle title="Patient reviews" right={<ClinicFilter meta={q.data} />} />
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={4}><Card><CardContent>
          <Typography variant="h4" fontWeight={700}>{stats.avg_rating != null ? stats.avg_rating : "—"} <Typography component="span" color="warning.main">★</Typography></Typography>
          <Typography variant="caption" color="text.secondary">Average rating</Typography>
        </CardContent></Card></Grid>
        <Grid item xs={4}><Card><CardContent>
          <Typography variant="h4" fontWeight={700}>{stats.responded ?? 0}</Typography>
          <Typography variant="caption" color="text.secondary">Reviews received</Typography>
        </CardContent></Card></Grid>
        <Grid item xs={4}><Card><CardContent>
          <Typography variant="h4" fontWeight={700}>{rate}%</Typography>
          <Typography variant="caption" color="text.secondary">Response rate ({stats.responded ?? 0}/{stats.requested ?? 0})</Typography>
        </CardContent></Card></Grid>
      </Grid>
      <Card>
        <Table size="small">
          <TableHead><TableRow>
            {showClinic && <TableCell>Clinic</TableCell>}
            <TableCell>Patient</TableCell><TableCell>Visit</TableCell><TableCell>Rating</TableCell>
            <TableCell>Comment</TableCell><TableCell>Status</TableCell><TableCell>When</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {rows.map((r: any) => (
              <TableRow key={r.id} hover>
                {showClinic && <TableCell><Typography variant="caption" color="text.secondary">{tenant_names[r.tenant_id] || "—"}</Typography></TableCell>}
                <TableCell>{r.patient_name || "—"}<Typography variant="caption" color="text.secondary" display="block">+{r.wa_user}</Typography></TableCell>
                <TableCell>{r.service || "—"}<Typography variant="caption" color="text.secondary" display="block">{r.doctor || ""}</Typography></TableCell>
                <TableCell>{r.rating ? <Rating value={r.rating} readOnly size="small" /> : "—"}</TableCell>
                <TableCell sx={{ maxWidth: 280, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.comment || ""}</TableCell>
                <TableCell><Chip size="small" color={r.stage === "done" ? "success" : "warning"} label={r.stage === "done" ? "received" : "awaiting"} /></TableCell>
                <TableCell><Typography variant="caption" color="text.secondary">{fmtDate(r.responded_at || r.created_at)}</Typography></TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && <TableRow><TableCell colSpan={showClinic ? 7 : 6} align="center" sx={{ py: 6, color: "text.secondary" }}>No reviews yet</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
