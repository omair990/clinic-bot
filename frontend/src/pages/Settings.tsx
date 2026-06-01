import { useEffect, useState } from "react";
import {
  Card, CardContent, TextField, Button, Typography, Grid, Box, Chip, Stack, Table, TableHead,
  TableRow, TableCell, TableBody, Divider,
} from "@mui/material";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError, useToast } from "../lib";

const isSecret = (k: string) => /TOKEN|KEY|SECRET|PASSWORD/i.test(k);

export default function Settings() {
  const q = useApiQuery<any>(["settings"], "/settings");
  const toast = useToast();
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) {
      const init: Record<string, string> = {};
      Object.entries(q.data.editable).forEach(([k, v]: any) => (init[k] = v.value || ""));
      setValues(init);
    }
  }, [q.data]);
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;

  const editable = q.data.editable as Record<string, { label: string; group: string; value: string }>;
  const inventory: any[] = q.data.inventory || [];
  const groups: Record<string, string[]> = {};
  Object.entries(editable).forEach(([k, v]) => { (groups[v.group] ||= []).push(k); });

  const save = async () => {
    setBusy(true);
    try {
      // Only send fields the operator actually changed (don't blank a masked secret).
      const changed: Record<string, string> = {};
      Object.keys(values).forEach((k) => { if (values[k] !== (editable[k].value || "")) changed[k] = values[k]; });
      await apiPost("/settings", { values: changed });
      toast.ok("Settings saved");
      q.refetch();
    } catch (e) { toast.err(e instanceof ApiError ? e.message : "Save failed"); }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title="Platform settings" subtitle="Overrides stored in the database take precedence over environment variables"
        right={<Button variant="contained" disabled={busy} onClick={save}>Save settings</Button>} />

      {Object.entries(groups).map(([group, keys]) => (
        <Card key={group} sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="subtitle2" sx={{ mb: 1.5 }}>{group}</Typography>
            <Grid container spacing={2}>
              {keys.map((k) => (
                <Grid item xs={12} md={6} key={k}>
                  <TextField fullWidth size="small" label={editable[k].label}
                    type={isSecret(k) ? "password" : "text"}
                    value={values[k] ?? ""} onChange={(e) => setValues({ ...values, [k]: e.target.value })}
                    helperText={isSecret(k) ? "Stored encrypted; leave to keep" : k} />
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      ))}

      {inventory.length > 0 && (
        <Card>
          <CardContent sx={{ pb: 0 }}><Typography variant="subtitle2">Configuration status</Typography></CardContent>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Setting</TableCell><TableCell>Group</TableCell><TableCell>Value</TableCell>
              <TableCell>Source</TableCell><TableCell>Status</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {inventory.map((s) => (
                <TableRow key={s.key}>
                  <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{s.key}</TableCell>
                  <TableCell><Typography variant="caption" color="text.secondary">{s.group}</Typography></TableCell>
                  <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{s.display || <Box component="span" sx={{ color: "text.disabled" }}>—</Box>}</TableCell>
                  <TableCell><Typography variant="caption" color="text.secondary">{s.db_override ? "database" : s.is_set ? "env" : "unset"}</Typography></TableCell>
                  <TableCell>
                    <Chip size="small" variant="outlined" color={s.is_set ? "success" : "default"} label={s.is_set ? "set" : "not set"} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </>
  );
}
