import { useState } from "react";
import {
  Tabs, Tab, Box, TextField, Button, IconButton, Table, TableHead, TableRow, TableCell,
  TableBody, MenuItem, Select, Chip, Switch, FormControlLabel, Stack, Typography, Autocomplete,
  Card, CardContent,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import { useT } from "./i18n";

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export interface ClinicData {
  clinic?: any; services?: any[]; doctors?: any[]; faqs?: any[]; appointment_policy?: any;
  [k: string]: any;
}

export default function ClinicDataEditor({ value, onChange }: {
  value: ClinicData; onChange: (v: ClinicData) => void;
}) {
  const t = useT();
  const [tab, setTab] = useState(0);
  const v = value || {};
  const clinic = v.clinic || {};
  const services = v.services || [];
  const doctors = v.doctors || [];
  const faqs = v.faqs || [];
  const pol = v.appointment_policy || {};

  const notif = v.notifications || {};
  const recipients: any[] = notif.recipients || [];

  const patch = (p: Partial<ClinicData>) => onChange({ ...v, ...p });
  const setClinic = (p: any) => patch({ clinic: { ...clinic, ...p } });
  const setPol = (p: any) => patch({ appointment_policy: { ...pol, ...p } });
  const setRecipients = (list: any[]) => patch({ notifications: { ...notif, recipients: list } });
  const updRec = (i: number, p: any) => setRecipients(recipients.map((r, j) => (j === i ? { ...r, ...p } : r)));
  const updRow = (key: string, list: any[], i: number, p: any) =>
    patch({ [key]: list.map((r, j) => (j === i ? { ...r, ...p } : r)) });
  const addRow = (key: string, list: any[], blank: any) => patch({ [key]: [...list, blank] });
  const delRow = (key: string, list: any[], i: number) => patch({ [key]: list.filter((_, j) => j !== i) });

  return (
    <Card>
      <Tabs value={tab} onChange={(_e, t) => setTab(t)} variant="scrollable"
        sx={{ borderBottom: 1, borderColor: "divider", px: 1 }}>
        <Tab label={t("clinicData.tabClinicInfo")} />
        <Tab label={t("clinicData.tabServices", { n: services.length })} />
        <Tab label={t("clinicData.tabDoctors", { n: doctors.length })} />
        <Tab label={t("clinicData.tabFaqs", { n: faqs.length })} />
        <Tab label={t("clinicData.tabPolicy")} />
        <Tab label={t("clinicData.tabNotifications", { n: recipients.length })} />
      </Tabs>
      <CardContent>
        {tab === 0 && (
          <Stack spacing={2} sx={{ maxWidth: 560 }}>
            <TextField label={t("clinicData.clinicName")} size="small" value={clinic.name || ""}
              onChange={(e) => setClinic({ name: e.target.value })} required />
            <TextField label={t("clinicData.address")} size="small" value={clinic.address || ""}
              onChange={(e) => setClinic({ address: e.target.value })} />
            <TextField label={t("clinicData.phone")} size="small" value={clinic.phone || ""}
              onChange={(e) => setClinic({ phone: e.target.value })} />
            <Autocomplete multiple freeSolo options={["Arabic", "English", "Urdu", "Hindi"]}
              value={clinic.languages || []} onChange={(_e, val) => setClinic({ languages: val })}
              renderInput={(p) => <TextField {...p} size="small" label={t("clinicData.languages")} />} />
            <TextField select size="small" label={t("clinicData.defaultLanguage")}
              value={clinic.default_language || ""}
              onChange={(e) => setClinic({ default_language: e.target.value })}
              helperText={t("clinicData.defaultLanguageHelper")}>
              <MenuItem value="">{t("clinicData.autoMatch")}</MenuItem>
              {(clinic.languages || []).map((l: string) => <MenuItem key={l} value={l}>{l}</MenuItem>)}
            </TextField>
          </Stack>
        )}

        {tab === 1 && (
          <>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>{t("clinicData.name")}</TableCell><TableCell width={130}>{t("clinicData.priceSar")}</TableCell>
                <TableCell width={130}>{t("clinicData.durationMin")}</TableCell><TableCell width={48} />
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
              onClick={() => addRow("services", services, { name: "", price_sar: "", duration_min: "" })}>{t("clinicData.addService")}</Button>
          </>
        )}

        {tab === 2 && (
          <>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>{t("clinicData.name")}</TableCell><TableCell>{t("clinicData.specialty")}</TableCell>
                <TableCell width={220}>{t("clinicData.availableDays")}</TableCell>
                <TableCell width={170}>{t("clinicData.hours")}</TableCell><TableCell width={48} />
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
              onClick={() => addRow("doctors", doctors, { name: "", specialty: "", available_days: [], available_hours: "" })}>{t("clinicData.addDoctor")}</Button>
          </>
        )}

        {tab === 3 && (
          <Stack spacing={2}>
            {faqs.map((f, i) => (
              <Box key={i} sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                <Stack spacing={1} sx={{ flex: 1 }}>
                  <TextField size="small" label={t("clinicData.question")} value={f.q || ""}
                    onChange={(e) => updRow("faqs", faqs, i, { q: e.target.value })} />
                  <TextField size="small" label={t("clinicData.answer")} multiline minRows={2} value={f.a || ""}
                    onChange={(e) => updRow("faqs", faqs, i, { a: e.target.value })} />
                </Stack>
                <IconButton size="small" onClick={() => delRow("faqs", faqs, i)}><DeleteIcon fontSize="small" /></IconButton>
              </Box>
            ))}
            <Button startIcon={<AddIcon />} onClick={() => addRow("faqs", faqs, { q: "", a: "" })} sx={{ alignSelf: "flex-start" }}>{t("clinicData.addFaq")}</Button>
          </Stack>
        )}

        {tab === 4 && (
          <Stack spacing={2} sx={{ maxWidth: 560 }}>
            <Stack direction="row" spacing={2}>
              <TextField type="number" size="small" label={t("clinicData.bookingLeadTime")} value={pol.booking_lead_time_hours ?? ""}
                onChange={(e) => setPol({ booking_lead_time_hours: e.target.value })} />
              <TextField type="number" size="small" label={t("clinicData.cancellationNotice")} value={pol.cancellation_notice_hours ?? ""}
                onChange={(e) => setPol({ cancellation_notice_hours: e.target.value })} />
            </Stack>
            <FormControlLabel control={<Switch checked={!!pol.walk_ins_accepted}
              onChange={(e) => setPol({ walk_ins_accepted: e.target.checked })} />} label={t("clinicData.walkInsAccepted")} />
            <Autocomplete multiple freeSolo options={["Cash", "Card", "mada", "Insurance"]}
              value={pol.payment_methods || []} onChange={(_e, val) => setPol({ payment_methods: val })}
              renderInput={(p) => <TextField {...p} size="small" label={t("clinicData.paymentMethods")} />} />
            <Typography variant="caption" color="text.secondary">
              {t("clinicData.policyNote")}
            </Typography>
          </Stack>
        )}

        {tab === 5 && (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              {t("clinicData.notifIntroBefore")}<b>{t("clinicData.notifIntroEscalations")}</b>
              {t("clinicData.notifIntroMiddle")}<b>{t("clinicData.notifIntroDigest")}</b>
              {t("clinicData.notifIntroAfter")}<code>9665XXXXXXXX</code>.
            </Typography>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>{t("clinicData.label")}</TableCell><TableCell>{t("clinicData.whatsappNumber")}</TableCell>
                <TableCell width={120} align="center">{t("clinicData.escalations")}</TableCell>
                <TableCell width={100} align="center">{t("clinicData.digest")}</TableCell><TableCell width={48} />
              </TableRow></TableHead>
              <TableBody>
                {recipients.map((r, i) => (
                  <TableRow key={i}>
                    <TableCell><TextField fullWidth size="small" variant="standard" placeholder={t("clinicData.ownerPlaceholder")}
                      value={r.label || ""} onChange={(e) => updRec(i, { label: e.target.value })} /></TableCell>
                    <TableCell><TextField fullWidth size="small" variant="standard" placeholder={t("clinicData.numberPlaceholder")}
                      value={r.number || ""} onChange={(e) => updRec(i, { number: e.target.value })} /></TableCell>
                    <TableCell align="center"><Switch size="small" checked={r.escalation !== false}
                      onChange={(e) => updRec(i, { escalation: e.target.checked })} /></TableCell>
                    <TableCell align="center"><Switch size="small" checked={!!r.digest}
                      onChange={(e) => updRec(i, { digest: e.target.checked })} /></TableCell>
                    <TableCell><IconButton size="small" onClick={() => setRecipients(recipients.filter((_, j) => j !== i))}><DeleteIcon fontSize="small" /></IconButton></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Button startIcon={<AddIcon />} sx={{ mt: 1 }}
              onClick={() => setRecipients([...recipients, { label: "", number: "", escalation: true, digest: false }])}>{t("clinicData.addRecipient")}</Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
