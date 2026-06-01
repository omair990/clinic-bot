/** AppBar notification bell + live-connection pulse, driven by the SSE LiveProvider. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Badge, Box, Button, Divider, IconButton, List, ListItemButton, Popover, Stack,
  Tooltip, Typography, alpha, keyframes,
} from "@mui/material";
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNoneOutlined";
import HandshakeIcon from "@mui/icons-material/HandshakeOutlined";
import EventAvailableIcon from "@mui/icons-material/EventAvailableOutlined";
import StarIcon from "@mui/icons-material/StarOutlined";
import ReportProblemIcon from "@mui/icons-material/ReportProblemOutlined";
import CircleIcon from "@mui/icons-material/Circle";
import { useLive, Level, Note } from "./realtime";

const pulse = keyframes`
  0% { box-shadow: 0 0 0 0 currentColor; opacity: 1; }
  70% { box-shadow: 0 0 0 6px transparent; opacity: .85; }
  100% { box-shadow: 0 0 0 0 transparent; opacity: 1; }
`;

const LEVEL_COLOR: Record<Level, string> = {
  info: "info.main", success: "success.main", warning: "warning.main", error: "error.main",
};

function iconFor(c?: string) {
  const sx = { fontSize: 18 };
  if (c === "handover") return <HandshakeIcon sx={sx} />;
  if (c === "booking") return <EventAvailableIcon sx={sx} />;
  if (c === "review") return <StarIcon sx={sx} />;
  return <ReportProblemIcon sx={sx} />;
}

function ago(ts: string): string {
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function Row({ n, onClick }: { n: Note; onClick: () => void }) {
  const color = LEVEL_COLOR[n.level] ?? "info.main";
  return (
    <ListItemButton onClick={onClick} sx={{ alignItems: "flex-start", gap: 1.25, py: 1.25 }}>
      <Box sx={{ mt: 0.25, width: 30, height: 30, borderRadius: 2, flexShrink: 0,
        display: "grid", placeItems: "center", color, bgcolor: (t) => alpha((t.palette as any)[n.level]?.main ?? "#888", 0.14) }}>
        {iconFor(n.category)}
      </Box>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Stack direction="row" justifyContent="space-between" spacing={1}>
          <Typography variant="body2" fontWeight={700} noWrap>{n.title}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>{ago(n.ts)}</Typography>
        </Stack>
        {n.body && (
          <Typography variant="caption" color="text.secondary"
            sx={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
            {n.body}
          </Typography>
        )}
      </Box>
    </ListItemButton>
  );
}

export default function NotificationBell() {
  const { notes, unread, connected, markAllRead, clear } = useLive();
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  const nav = useNavigate();
  const open = Boolean(anchor);

  const onOpen = (e: React.MouseEvent<HTMLElement>) => { setAnchor(e.currentTarget); markAllRead(); };
  const go = (link?: string | null) => { setAnchor(null); if (link) nav(link); };

  return (
    <>
      <Tooltip title={connected ? "Live · connected" : "Reconnecting…"}>
        <IconButton onClick={onOpen} sx={{ position: "relative" }}>
          <Badge badgeContent={unread} color="error" max={99}>
            <NotificationsNoneIcon />
          </Badge>
          <CircleIcon sx={{
            position: "absolute", top: 7, right: 7, fontSize: 9,
            color: connected ? "success.main" : "text.disabled",
            ...(connected ? { animation: `${pulse} 2s ease-out infinite` } : {}),
          }} />
        </IconButton>
      </Tooltip>

      <Popover open={open} anchorEl={anchor} onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { width: 392, maxWidth: "92vw", mt: 1, borderRadius: 3, overflow: "hidden" } } }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1.5 }}>
          <Box>
            <Typography fontWeight={800}>Notifications</Typography>
            <Stack direction="row" alignItems="center" spacing={0.75}>
              <CircleIcon sx={{ fontSize: 8, color: connected ? "success.main" : "text.disabled" }} />
              <Typography variant="caption" color="text.secondary">
                {connected ? "Live" : "Reconnecting…"}
              </Typography>
            </Stack>
          </Box>
          {notes.length > 0 && <Button size="small" color="inherit" onClick={clear}>Clear</Button>}
        </Stack>
        <Divider />
        {notes.length === 0 ? (
          <Box sx={{ textAlign: "center", py: 6, px: 2, color: "text.secondary" }}>
            <NotificationsNoneIcon sx={{ fontSize: 36, opacity: 0.4 }} />
            <Typography variant="body2" sx={{ mt: 1 }}>You're all caught up.</Typography>
            <Typography variant="caption">New activity will appear here in real time.</Typography>
          </Box>
        ) : (
          <List sx={{ py: 0, maxHeight: 420, overflow: "auto" }}>
            {notes.map((n) => <Row key={n.id} n={n} onClick={() => go(n.link)} />)}
          </List>
        )}
      </Popover>
    </>
  );
}
