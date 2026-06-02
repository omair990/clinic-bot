import { Card, CardContent, Grid, Typography, Box, Stack, Chip, alpha, CircularProgress } from "@mui/material";
import TextsmsIcon from "@mui/icons-material/TextsmsOutlined";
import GraphicEqIcon from "@mui/icons-material/GraphicEqOutlined";
import PremiumIcon from "@mui/icons-material/WorkspacePremiumOutlined";
import { useApiQuery, PageTitle, Loading, QueryError } from "../lib";
import { useT } from "../i18n";

const C = { teal: "#14b8a6", amber: "#f59e0b", red: "#ef4444", grey: "#94a3b8" };
const fmt = (n: number | null | undefined) => (n == null ? "∞" : n.toLocaleString());

// Circular usage gauge: track ring + value ring + a centered used/quota readout.
function Gauge({ used, quota, color, disabled }: { used: number; quota: number | null; color: string; disabled?: boolean }) {
  const t = useT();
  const unlimited = quota == null;
  const pct = disabled ? 0 : unlimited ? 100 : Math.min(100, quota ? (used / quota) * 100 : 0);
  const size = 156, thickness = 5;
  return (
    <Box sx={{ position: "relative", width: size, height: size, mx: "auto" }}>
      <CircularProgress variant="determinate" value={100} size={size} thickness={thickness}
        sx={{ color: (t) => alpha(t.palette.text.primary, 0.08), position: "absolute", left: 0 }} />
      {!disabled && (
        <CircularProgress variant="determinate" value={unlimited ? 100 : pct} size={size} thickness={thickness}
          sx={{ color, position: "absolute", left: 0, "& .MuiCircularProgress-circle": { strokeLinecap: "round" } }} />
      )}
      <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
        {disabled ? (
          <Typography variant="body2" color="text.secondary">{t("usage.off")}</Typography>
        ) : (
          <Box>
            <Typography variant="h4" fontWeight={800} sx={{ lineHeight: 1 }}>{fmt(used)}</Typography>
            <Typography variant="caption" color="text.secondary">{t("usage.ofQuota", { quota: fmt(quota) })}</Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}

function MeterCard({ label, icon, used, quota, on }: {
  label: string; icon: React.ReactNode; used: number; quota: number | null; on: boolean;
}) {
  const t = useT();
  const unlimited = quota == null;
  const pct = quota ? Math.min(100, (used / quota) * 100) : 0;
  const over = on && !unlimited && pct >= 100;
  const near = on && !unlimited && pct >= 80 && !over;
  const color = !on ? C.grey : over ? C.red : near ? C.amber : C.teal;
  const status = !on ? { label: t("usage.notIncluded"), c: "default" as const }
    : over ? { label: t("usage.limitReached"), c: "error" as const }
    : near ? { label: t("usage.approachingLimit"), c: "warning" as const }
    : unlimited ? { label: t("usage.unlimited"), c: "success" as const }
    : { label: t("usage.healthy"), c: "success" as const };
  return (
    <Card sx={{ height: "100%", position: "relative", overflow: "hidden",
      "&::before": { content: '""', position: "absolute", inset: 0, pointerEvents: "none",
        background: `radial-gradient(120% 90% at 100% 0%, ${alpha(color, 0.12)}, transparent 55%)` } }}>
      <CardContent sx={{ position: "relative" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
          <Stack direction="row" spacing={1.25} alignItems="center">
            <Box sx={{ width: 34, height: 34, borderRadius: 2, display: "grid", placeItems: "center",
              color, bgcolor: alpha(color, 0.14) }}>{icon}</Box>
            <Typography variant="subtitle1" fontWeight={800}>{label}</Typography>
          </Stack>
          <Chip size="small" color={status.c} variant={status.c === "default" ? "outlined" : "filled"} label={status.label} />
        </Stack>
        <Gauge used={used} quota={quota} color={color} disabled={!on} />
        <Typography variant="body2" color="text.secondary" align="center" sx={{ mt: 2 }}>
          {!on ? t("usage.footerNotIncluded")
            : unlimited ? t("usage.footerUnlimited")
            : t("usage.footerUsed", { pct: Math.round(pct) })}
        </Typography>
      </CardContent>
    </Card>
  );
}

export default function Usage() {
  const t = useT();
  const q = useApiQuery<any>(["usage"], "/usage");
  if (q.isLoading) return <Loading />;
  if (q.error) return <QueryError error={q.error} />;
  const u = q.data.usage;
  if (!u) return <Typography color="text.secondary">{t("usage.noData")}</Typography>;

  const tp = u.monthly_text_quota ? (u.text_count / u.monthly_text_quota) * 100 : 0;
  const vp = u.voice_enabled && u.monthly_voice_quota ? (u.voice_count / u.monthly_voice_quota) * 100 : 0;
  const over = tp >= 100 || vp >= 100;
  const near = (u.monthly_text_quota && tp >= 80) || (u.voice_enabled && u.monthly_voice_quota && vp >= 80);

  return (
    <>
      <PageTitle title={t("usage.title")} subtitle={t("usage.subtitle")} right={
        <Chip variant="outlined" label={t("common.period", { period: q.data.period })} />} />

      <Card sx={{ mb: 2, position: "relative", overflow: "hidden", color: "#fff",
        background: over ? "linear-gradient(120deg,#b91c1c 0%,#ef4444 55%,#6366f1 100%)"
          : near ? "linear-gradient(120deg,#b45309 0%,#f59e0b 55%,#6366f1 100%)"
          : "linear-gradient(120deg,#0f766e 0%,#14b8a6 45%,#6366f1 100%)" }}>
        <CardContent sx={{ p: { xs: 2.5, md: 3 } }}>
          <Stack direction="row" spacing={2} alignItems="center">
            <Box sx={{ width: 50, height: 50, borderRadius: 2.5, display: "grid", placeItems: "center", flexShrink: 0,
              bgcolor: alpha("#fff", 0.18), border: `1px solid ${alpha("#fff", 0.35)}` }}><PremiumIcon /></Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="overline" sx={{ color: alpha("#fff", 0.85), letterSpacing: 1 }}>{t("usage.yourPlan")}</Typography>
              <Typography variant="h5" sx={{ color: "#fff", lineHeight: 1.1 }}>{u.plan_name || "—"}</Typography>
            </Box>
            <Box sx={{ flex: 1 }} />
            <Chip label={over ? t("usage.statusReached") : near ? t("usage.statusNear") : t("usage.statusGood")}
              sx={{ bgcolor: alpha("#fff", 0.22), color: "#fff", fontWeight: 700, flexShrink: 0 }} />
          </Stack>
          {(over || near) && (
            <Typography variant="body2" sx={{ mt: 1.5, color: alpha("#fff", 0.95) }}>
              {over ? t("usage.warnOver")
                : t("usage.warnNear")}
            </Typography>
          )}
        </CardContent>
      </Card>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <MeterCard label={t("usage.textMessages")} icon={<TextsmsIcon fontSize="small" />}
            used={u.text_count} quota={u.monthly_text_quota} on />
        </Grid>
        <Grid item xs={12} md={6}>
          <MeterCard label={t("usage.voiceNotes")} icon={<GraphicEqIcon fontSize="small" />}
            used={u.voice_count} quota={u.monthly_voice_quota} on={u.voice_enabled} />
        </Grid>
      </Grid>
    </>
  );
}
