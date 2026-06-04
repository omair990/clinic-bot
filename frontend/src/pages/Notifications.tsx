/** Full-page notification center — the sidebar "Notifications" destination.
 * Reuses the live SSE feed (useLive) for history + real-time arrivals, and clears the
 * unread badge on open. */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Card, List, ListItemButton, Stack, Typography, Button, Chip, Divider, alpha,
  ToggleButton, ToggleButtonGroup,
} from "@mui/material";
import HandshakeIcon from "@mui/icons-material/HandshakeOutlined";
import EventAvailableIcon from "@mui/icons-material/EventAvailableOutlined";
import EventBusyIcon from "@mui/icons-material/EventBusyOutlined";
import StarIcon from "@mui/icons-material/StarOutlined";
import ReportProblemIcon from "@mui/icons-material/ReportProblemOutlined";
import DoneAllIcon from "@mui/icons-material/DoneAllOutlined";
import { useLive, Level, Note } from "../realtime";
import { PageTitle, EmptyState } from "../lib";
import { useT } from "../i18n";
import { fmtDate } from "../tz";

const LEVEL_COLOR: Record<Level, string> = {
  info: "info.main", success: "success.main", warning: "warning.main", error: "error.main",
};

function iconFor(c?: string) {
  const sx = { fontSize: 20 };
  if (c === "handover") return <HandshakeIcon sx={sx} />;
  if (c === "booking") return <EventAvailableIcon sx={sx} />;
  if (c === "review") return <StarIcon sx={sx} />;
  if (c === "no_show") return <EventBusyIcon sx={sx} />;
  return <ReportProblemIcon sx={sx} />;
}

export default function Notifications() {
  const t = useT();
  const nav = useNavigate();
  const { notes, connected, markAllRead, clear } = useLive();
  const [cat, setCat] = useState("");

  // Opening the center counts as reading everything currently shown.
  useEffect(() => { markAllRead(); }, [markAllRead]);

  const cats = useMemo(() => {
    const set = new Set<string>();
    notes.forEach((n) => set.add(n.category || "general"));
    return Array.from(set);
  }, [notes]);

  const shown = cat ? notes.filter((n) => (n.category || "general") === cat) : notes;
  const catLabel = (c: string) => t(`notifications.cat.${c}`) || c;

  const go = (n: Note) => { if (n.link) nav(n.link); };

  return (
    <>
      <PageTitle title={t("notifications.title")} subtitle={t("notifications.subtitle")}
        right={
          <Stack direction="row" spacing={1}>
            <Button size="small" startIcon={<DoneAllIcon />} onClick={markAllRead}>
              {t("notifications.markAllRead")}</Button>
            {notes.length > 0 && (
              <Button size="small" color="inherit" onClick={clear}>{t("notifications.clearAll")}</Button>
            )}
          </Stack>
        } />

      {cats.length > 1 && (
        <ToggleButtonGroup size="small" exclusive value={cat} sx={{ mb: 2, flexWrap: "wrap" }}
          onChange={(_e, v) => setCat(v ?? "")}>
          <ToggleButton value="">{t("notifications.filterAll")}</ToggleButton>
          {cats.map((c) => <ToggleButton key={c} value={c}>{catLabel(c)}</ToggleButton>)}
        </ToggleButtonGroup>
      )}

      <Card sx={{ p: 0, overflow: "hidden" }}>
        {shown.length === 0 ? (
          <EmptyState text={t("notifications.empty")} />
        ) : (
          <List sx={{ py: 0 }}>
            {shown.map((n, i) => {
              const color = LEVEL_COLOR[n.level] ?? "info.main";
              return (
                <Box key={n.id}>
                  {i > 0 && <Divider component="li" />}
                  <ListItemButton onClick={() => go(n)} sx={{ alignItems: "flex-start", gap: 1.5, py: 1.5 }}>
                    <Box sx={{ mt: 0.25, width: 38, height: 38, borderRadius: 2, flexShrink: 0,
                      display: "grid", placeItems: "center", color,
                      bgcolor: (th) => alpha((th.palette as any)[n.level]?.main ?? "#888", 0.14) }}>
                      {iconFor(n.category)}
                    </Box>
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="center">
                        <Typography fontWeight={700} noWrap>{n.title}</Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                          {fmtDate(n.ts)}</Typography>
                      </Stack>
                      {n.body && (
                        <Typography variant="body2" color="text.secondary"
                          sx={{ mt: 0.25, whiteSpace: "pre-wrap" }}>{n.body}</Typography>
                      )}
                      {n.category && (
                        <Chip size="small" variant="outlined" label={catLabel(n.category)}
                          sx={{ mt: 0.75, height: 22 }} />
                      )}
                    </Box>
                  </ListItemButton>
                </Box>
              );
            })}
          </List>
        )}
      </Card>

      {!connected && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
          {t("common.reconnecting")}
        </Typography>
      )}
    </>
  );
}
