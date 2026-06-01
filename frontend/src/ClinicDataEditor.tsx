import { useState } from "react";
import {
  Tabs, Tab, Box, TextField, Button, IconButton, Table, TableHead, TableRow, TableCell,
  TableBody, MenuItem, Select, Chip, Switch, FormControlLabel, Stack, Typography, Autocomplete,
  Card, CardContent,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutline";

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export interface ClinicData {
  clinic?: any; services?: any[]; doctors?: any[]; faqs?: any[]; appointment_policy?: any;
  [k: string]: any;
}

export default function ClinicDataEditor({ value, onChange }: {
  value: ClinicData; onChange: (v: ClinicData) => void;
}) {
  const [tab, setTab] = useState(0);
  const v = value || {};
  const clinic = v.clinic || {};
  const services = v.services || [];
  const doctors = v.doctors || [];
  const faqs = v.faqs || [];
  const pol = v.appointment_policy || {};

  const patch = (p: Partial<ClinicData>) => onChange({ ...v, ...p });
  const setClinic = (p: any) => patch({ clinic: { ...clinic, ...p } });
  const setPol = (p: any) => patch({ appointment_policy: { ...pol, ...p } });
  const updRow = (key: string, list: any[], i: number, p: any) =>
    patch({ [key]: list.map((r, j) => (j === i ? { ...r, ...p } : r)) });
  const addRow = (key: string, list: any[], blank: any) => patch({ [key]: [...list, blank] });
  const delRow = (key: string, list: any[], i: number) => patch({ [key]: list.filter((_, j) => j !== i) });

  return (
    <Card>
      <Tabs value={tab} onChange={(_e, t) => setTab(t)} variant="scrollable"
        sx={{ borderBottom: 1, borderColor: "divider", px: 1 }}>
        <Tab label="Clinic info" />
        <Tab label={`Services (${services.length})`} />
        <Tab label={`Doctors (${doctors.length})`} />
        <Tab label={`FAQs (${faqs.length})`} />
        <Tab label="Policy" />
      </Tabs>
      <CardContent>
        {tab === 0 && (
          <Stack spacing={2} sx={{ maxWidth: 560 }}>
            <TextField label="Clinic name *" size="small" value={clinic.name || ""}
              onChange={(e) => setClinic({ name: e.target.value })} required />
            <TextField label="Address" size="small" value={clinic.address || ""}
              onChange={(e) => setClinic({ address: e.target.value })} />
            <TextField label="Phone" size="small" value={clinic.phone || ""}
              onChange={(e) => setClinic({ phone: e.target.value })} />
            <Autocomplete multiple freeSolo options={["Arabic", "English", "Urdu", "Hindi"]}
              value={clinic.languages || []} onChange={(_e, val) => setClinic({ languages: val })}
              renderInput={(p) => <TextField {...p} size="small" label="Languages" />} />
          </Stack>
        )}

        {tab === 1 && (
          <>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>Name *</TableCell><TableCell width={130}>Price (SAR) *</TableCell>
                <TableCell width={130}>Duration (min) *</TableCell><TableCell width={48} />
              </TableRow></TableHead>
              <TableBody>
                {services.map((s, i) => (
                  <TableRow key={i}>
                    <TableCell><TextField fullWidth size="small" variant="standard" value={s.name || ""}
                      onChange={(e) => updRow("services", services, i, { name: e.target.value })} /></TableCell>
                    <TableCell><TextField type="number" size="small" variant="standard" value={s.price_sar ?? ""}
                      onChange={(e) => updRow("services", services, i, { price_sar: e.target.value })} /></TableCell>
                    <TableCell><TextField type="number" size="small" variant="standard" value={s.duration_min ?? ""}
                      onChange={(e) => updRow("services", services, i, { duration_min: e.target.value })} /></TableCell>
                    <TableCell><IconButton size="small" onClick={() => delRow("services", services, i)}><DeleteIcon fontSize="small" /></IconButton></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Button startIcon={<AddIcon />} sx={{ mt: 1 }}
              onClick={() => addRow("services", services, { name: "", price_sar: "", duration_min: "" })}>Add service</Button>
          </>
        )}

        {tab === 2 && (
          <>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>Name *</TableCell><TableCell>Specialty *</TableCell>
                <TableCell width={220}>Available days *</TableCell>
                <TableCell width={170}>Hours *</TableCell><TableCell width={48} />
              </TableRow></TableHead>
              <TableBody>
                {doctors.map((d, i) => (
                  <TableRow key={i}>
                    <TableCell><TextField fullWidth size="small" variant="standard" value={d.name || ""}
                      onChange={(e) => updRow("doctors", doctors, i, { name: e.target.value })} /></TableCell>
                    <TableCell><TextField fullWidth size="small" variant="standard" value={d.specialty || ""}
                      onChange={(e) => updRow("doctors", doctors, i, { specialty: e.target.value })} /></TableCell>
                    <TableCell>
                      <Select multiple fullWidth size="small" variant="standard" value={d.available_days || []}
                        onChange={(e) => updRow("doctors", doctors, i, { available_days: e.target.value })}
                        renderValue={(sel: any) => (
                          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.3 }}>
                            {sel.map((x: string) => <Chip key={x} size="small" label={x.slice(0, 3)} />)}
                          </Box>)}>
                        {DAYS.map((day) => <MenuItem key={day} value={day}>{day}</MenuItem>)}
                      </Select>
                    </TableCell>
                    <TableCell><TextField fullWidth size="small" variant="standard" placeholder="5:00 PM - 9:00 PM"
                      value={d.available_hours || ""}
                      onChange={(e) => updRow("doctors", doctors, i, { available_hours: e.target.value })} /></TableCell>
                    <TableCell><IconButton size="small" onClick={() => delRow("doctors", doctors, i)}><DeleteIcon fontSize="small" /></IconButton></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Button startIcon={<AddIcon />} sx={{ mt: 1 }}
              onClick={() => addRow("doctors", doctors, { name: "", specialty: "", available_days: [], available_hours: "" })}>Add doctor</Button>
          </>
        )}

        {tab === 3 && (
          <Stack spacing={2}>
            {faqs.map((f, i) => (
              <Box key={i} sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                <Stack spacing={1} sx={{ flex: 1 }}>
                  <TextField size="small" label="Question" value={f.q || ""}
                    onChange={(e) => updRow("faqs", faqs, i, { q: e.target.value })} />
                  <TextField size="small" label="Answer" multiline minRows={2} value={f.a || ""}
                    onChange={(e) => updRow("faqs", faqs, i, { a: e.target.value })} />
                </Stack>
                <IconButton size="small" onClick={() => delRow("faqs", faqs, i)}><DeleteIcon fontSize="small" /></IconButton>
              </Box>
            ))}
            <Button startIcon={<AddIcon />} onClick={() => addRow("faqs", faqs, { q: "", a: "" })} sx={{ alignSelf: "flex-start" }}>Add FAQ</Button>
          </Stack>
        )}

        {tab === 4 && (
          <Stack spacing={2} sx={{ maxWidth: 560 }}>
            <Stack direction="row" spacing={2}>
              <TextField type="number" size="small" label="Booking lead time (hours)" value={pol.booking_lead_time_hours ?? ""}
                onChange={(e) => setPol({ booking_lead_time_hours: e.target.value })} />
              <TextField type="number" size="small" label="Cancellation notice (hours)" value={pol.cancellation_notice_hours ?? ""}
                onChange={(e) => setPol({ cancellation_notice_hours: e.target.value })} />
            </Stack>
            <FormControlLabel control={<Switch checked={!!pol.walk_ins_accepted}
              onChange={(e) => setPol({ walk_ins_accepted: e.target.checked })} />} label="Walk-ins accepted" />
            <Autocomplete multiple freeSolo options={["Cash", "Card", "mada", "Insurance"]}
              value={pol.payment_methods || []} onChange={(_e, val) => setPol({ payment_methods: val })}
              renderInput={(p) => <TextField {...p} size="small" label="Payment methods" />} />
            <Typography variant="caption" color="text.secondary">
              Other sections (branches, booking fields, connector) are preserved automatically.
            </Typography>
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}
