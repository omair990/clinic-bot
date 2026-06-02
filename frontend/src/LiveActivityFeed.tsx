/** Real-time WhatsApp activity stream for the dashboard, fed by the SSE LiveProvider. */
import { useNavigate } from "react-router-dom";
import {
  Box, Card, CardContent, Chip, Stack, Typography, alpha, keyframes,
} from "@mui/material";
import SouthWestIcon from "@mui/icons-material/SouthWest";
import NorthEastIcon from "@mui/icons-material/NorthEast";
import BoltIcon from "@mui/icons-material/BoltOutlined";
import { useLive } from "./realtime";
import { useT } from "./i18n";

const pulse = keyframes`0%{opacity:1}50%{opacity:.35}100%{opacity:1}`;
const slideIn = keyframes`from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}`;

export default function LiveActivityFeed() {
  const { activity, typing, connected } = useLive();
  const nav = useNavigate();
  const t = useT();
  const typers = Array.from(typing);
  const ago = (ts: number): string => {
    const s = Math.max(0, (Date.now() - ts) / 1000);
    if (s < 60) return t("feed.justNow");
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    return `${Math.floor(s / 3600)}h`;
  };

  return (
    <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <CardContent sx={{ pb: 1.5 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack direction="row" spacing={1} alignItems="center">
            <BoltIcon fontSize="small" color="primary" />
            <Typography fontWeight={800}>{t("feed.title")}</Typography>
          </Stack>
          <Stack direction="row" spacing={0.75} alignItems="center">
            <Box sx={{ width: 8, height: 8, borderRadius: "50%",
              bgcolor: connected ? "success.main" : "text.disabled",
              animation: connected ? `${pulse} 1.6s ease-in-out infinite` : "none" }} />
            <Typography variant="caption" color="text.secondary">
              {connected ? t("feed.streaming") : t("feed.offline")}
            </Typography>
          </Stack>
        </Stack>
      </CardContent>

      <Box sx={{ flex: 1, overflow: "auto", px: 2, pb: 2, maxHeight: 460 }}>
        {typers.length > 0 && (
          <Typography variant="caption" color="primary"
            sx={{ display: "block", mb: 1, animation: `${pulse} 1.4s ease-in-out infinite` }}>
            {t(typers.length > 1 ? "feed.replyingMany" : "feed.replyingOne", { n: typers.length })}
          </Typography>
        )}

        {activity.length === 0 ? (
          <Box sx={{ textAlign: "center", py: 7, color: "text.secondary" }}>
            <Typography variant="body2">{t("feed.waitingTitle")}</Typography>
            <Typography variant="caption">{t("feed.waitingBody")}</Typography>
          </Box>
        ) : (
          <Stack spacing={1}>
            {activity.map((a) => {
              const inbound = a.direction === "in";
              return (
                <Box key={a.key} onClick={() => nav(`/conversations/${a.wa_user}`)}
                  sx={{
                    display: "flex", gap: 1.25, p: 1.25, borderRadius: 2, cursor: "pointer",
                    animation: `${slideIn} .28s ease`,
                    border: (t) => `1px solid ${t.palette.divider}`,
                    "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
                  }}>
                  <Box sx={{ mt: 0.25, width: 26, height: 26, borderRadius: "50%", flexShrink: 0,
                    display: "grid", placeItems: "center",
                    color: inbound ? "info.main" : "success.main",
                    bgcolor: (t) => alpha(inbound ? t.palette.info.main : t.palette.success.main, 0.14) }}>
                    {inbound ? <SouthWestIcon sx={{ fontSize: 15 }} /> : <NorthEastIcon sx={{ fontSize: 15 }} />}
                  </Box>
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="center">
                      <Typography variant="caption" fontWeight={700} noWrap>+{a.wa_user}</Typography>
                      <Stack direction="row" spacing={0.5} alignItems="center" sx={{ flexShrink: 0 }}>
                        {a.needs_human && <Chip size="small" color="warning" label={t("feed.needsHuman")} sx={{ height: 18, fontSize: 10 }} />}
                        {a.intent && <Chip size="small" variant="outlined" label={a.intent} sx={{ height: 18, fontSize: 10 }} />}
                        <Typography variant="caption" color="text.secondary">{ago(a.ts)}</Typography>
                      </Stack>
                    </Stack>
                    <Typography variant="body2" color="text.secondary" noWrap>{a.text}</Typography>
                  </Box>
                </Box>
              );
            })}
          </Stack>
        )}
      </Box>
    </Card>
  );
}
