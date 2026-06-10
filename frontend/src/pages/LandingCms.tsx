import { useEffect, useState } from "react";
import {
  Accordion, AccordionSummary, AccordionDetails, TextField, Button, Typography,
  Grid, Box, Stack, Chip,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMoreRounded";
import OpenInNewIcon from "@mui/icons-material/OpenInNewRounded";
import { apiPost, ApiError } from "../api";
import { useApiQuery, PageTitle, Loading, QueryError, useToast } from "../lib";
import { useT } from "../i18n";

type Field = { key: string; label: string; multiline?: boolean; html?: boolean; en: string; ar: string };
type Section = { key: string; title: string; fields: Field[] };

export default function LandingCms() {
  const t = useT();
  const toast = useToast();
  const q = useApiQuery<{ sections: Section[] }>(["landing-cms"], "/landing/cms");
  const [values, setValues] = useState<Record<string, { en: string; ar: string }>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) {
      const init: Record<string, { en: string; ar: string }> = {};
      q.data.sections.forEach((s) => s.fields.forEach((f) => (init[f.key] = { en: f.en, ar: f.ar })));
      setValues(init);
    }
  }, [q.data]);

  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;

  const setVal = (key: string, lang: "en" | "ar", v: string) =>
    setValues((prev) => ({ ...prev, [key]: { ...prev[key], [lang]: v } }));

  const save = async () => {
    setBusy(true);
    try {
      await apiPost("/landing/cms", { values });
      toast.ok(t("landingCms.saved"));
      q.refetch();
    } catch (e) {
      toast.err(e instanceof ApiError ? e.message : t("landingCms.saveFailed"));
    } finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title={t("landingCms.title")} subtitle={t("landingCms.subtitle")}
        right={
          <Stack direction="row" spacing={1.5}>
            <Button variant="outlined" startIcon={<OpenInNewIcon />} component="a" href="/landing" target="_blank" rel="noopener">
              {t("landingCms.viewPage")}
            </Button>
            <Button variant="contained" disabled={busy} onClick={save}>{t("landingCms.save")}</Button>
          </Stack>
        } />

      {q.data!.sections.map((s) => (
        <Accordion key={s.key} disableGutters defaultExpanded={s.key === "hero"} sx={{ mb: 1, borderRadius: 2, "&:before": { display: "none" } }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography fontWeight={800}>{s.title}</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={2.5}>
              {s.fields.map((f) => (
                <Box key={f.key}>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
                    <Typography variant="subtitle2" fontWeight={700}>{f.label}</Typography>
                    {f.html && <Chip size="small" variant="outlined" label={t("landingCms.htmlHint")} />}
                  </Stack>
                  <Grid container spacing={1.5}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth size="small" label={t("landingCms.english")} dir="ltr"
                        multiline={!!f.multiline} minRows={f.multiline ? 2 : undefined}
                        value={values[f.key]?.en ?? ""} onChange={(e) => setVal(f.key, "en", e.target.value)} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth size="small" label={t("landingCms.arabic")}
                        multiline={!!f.multiline} minRows={f.multiline ? 2 : undefined}
                        value={values[f.key]?.ar ?? ""} onChange={(e) => setVal(f.key, "ar", e.target.value)}
                        inputProps={{ dir: "rtl" }} />
                    </Grid>
                  </Grid>
                </Box>
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}
    </>
  );
}
