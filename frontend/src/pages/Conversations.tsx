import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Card, Stack, Typography, Chip, Avatar, TextField, InputAdornment, Grid,
  alpha, keyframes, Tooltip,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/SearchOutlined";
import ForumIcon from "@mui/icons-material/ForumOutlined";
import WarningIcon from "@mui/icons-material/WarningAmberOutlined";
import EventIcon from "@mui/icons-material/EventAvailableOutlined";
import SouthWestIcon from "@mui/icons-material/SouthWest";
import NorthEastIcon from "@mui/icons-material/NorthEast";
import { useApiQuery, PageTitle, ClinicFilter, useClinic, fmtDate, TableSkeleton, QueryError, KpiCard, EmptyState } from "../lib";
import { useLive } from "../realtime";

const intentColor: Record<string, any> = {
  appointment: "success", emergency: "error", handover: "warning", complaint: "warning",
};
const pulse = keyframes`0%{opacity:1}50%{opacity:.3}100%{opacity:1}`;

function initials(name: string | null, wa: string) {
  if (name) return name.slice(0, 2).toUpperCase();
  return wa.slice(-2);
}
function avatarHue(wa: string) {
  let h = 0; for (const c of wa) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}
function ago(iso?: string | null) {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 604800) return `${Math.floor(s / 86400)}d`;
  return fmtDate(iso);
}

function ChatRow({ row, showClinic, clinicName, typing, onClick }: {
  row: any; showClinic: boolean; clinicName?: string; typing: boolean; onClick: () => void;
}) {
  const inbound = row.last_direction === "in";
  const hue = avatarHue(row.wa_user);
  return (
    <Box onClick={onClick} sx={{
      display: "flex", gap: 1.5, px: 2, py: 1.5, cursor: "pointer", position: "relative",
      borderBottom: (t) => `1px solid ${t.palette.divider}`,
      transition: "background .15s ease",
      "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
      ...(row.needs_human ? { "&::before": {
        content: '""', position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
        bgcolor: "error.main" } } : {}),
    }}>
      <Box sx={{ position: "relative", flexShrink: 0 }}>
        <Avatar sx={{ width: 46, height: 46, fontWeight: 700, fontSize: 15,
          background: `linear-gradient(135deg, hsl(${hue} 70% 55%), hsl(${(hue + 40) % 360} 70% 45%))`, color: "#fff" }}>
          {initials(row.name, row.wa_user)}
        </Avatar>
        {typing && <Box sx={{ position: "absolute", right: -1, bottom: -1, width: 13, height: 13,
          borderRadius: "50%", bgcolor: "success.main", border: (t) => `2px solid ${t.palette.background.paper}`,
          animation: `${pulse} 1.3s ease-in-out infinite` }} />}
      </Box>

      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
          <Typography fontWeight={700} noWrap>
            {row.name || `+${row.wa_user}`}
            {showClinic && clinicName && (
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>· {clinicName}</Typography>
            )}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>{ago(row.last_at)}</Typography>
        </Stack>
        <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mt: 0.25 }}>
          {typing ? (
            <Typography variant="body2" color="success.main" fontWeight={600}
              sx={{ animation: `${pulse} 1.3s ease-in-out infinite` }}>typing…</Typography>
          ) : (
            <>
              {inbound
                ? <SouthWestIcon sx={{ fontSize: 14, color: "info.main", flexShrink: 0 }} />
                : <NorthEastIcon sx={{ fontSize: 14, color: "success.main", flexShrink: 0 }} />}
              <Typography variant="body2" color="text.secondary" noWrap>{row.last_message}</Typography>
            </>
          )}
        </Stack>
      </Box>

      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ flexShrink: 0 }}>
        {row.lead_band && <Chip size="small" variant="outlined" label={row.lead_band}
          sx={{ height: 22, display: { xs: "none", md: "flex" } }} />}
        {row.last_intent && <Chip size="small" variant="outlined" label={row.last_intent}
          color={intentColor[row.last_intent] || "default"} sx={{ height: 22, display: { xs: "none", sm: "flex" } }} />}
        {row.needs_human
          ? <Chip size="small" color="error" label="needs human" sx={{ height: 22 }} />
          : <Tooltip title="Messages"><Chip size="small" variant="outlined" icon={<ForumIcon sx={{ fontSize: "14px !important" }} />}
              label={row.msg_count} sx={{ height: 22 }} /></Tooltip>}
      </Stack>
    </Box>
  );
}

export default function Conversations() {
  const nav = useNavigate();
  const [clinic] = useClinic();
  const { typing } = useLive();
  const [search, setSearch] = useState("");
  const q = useApiQuery<any>(["conversations", clinic], `/conversations?clinic=${clinic}`);

  const rows: any[] = q.data?.rows ?? [];
  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    if (!s) return rows;
    return rows.filter((r) =>
      `${r.name || ""} ${r.wa_user} ${r.last_message || ""} ${r.last_intent || ""}`.toLowerCase().includes(s));
  }, [rows, search]);

  if (q.isLoading) return <><PageTitle title="Patient Chats" /><TableSkeleton /></>;
  if (q.error) return <QueryError error={q.error} />;
  const { is_super, tenant_names = {}, selected_clinic } = q.data;
  const showClinic = is_super && !selected_clinic;
  const needsHuman = rows.filter((r) => r.needs_human).length;
  const appts = rows.filter((r) => r.last_intent === "appointment").length;
  const totalMsgs = rows.reduce((a, r) => a + (r.msg_count || 0), 0);

  return (
    <>
      <PageTitle title="Patient Chats"
        subtitle={`${rows.length} active conversation${rows.length === 1 ? "" : "s"}`}
        right={<ClinicFilter meta={q.data} />} />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><KpiCard label="Active chats" value={rows.length} icon={<ForumIcon fontSize="small" />} color="primary" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Needs human" value={needsHuman} icon={<WarningIcon fontSize="small" />} color="error" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Booking intent" value={appts} icon={<EventIcon fontSize="small" />} color="success" /></Grid>
        <Grid item xs={6} md={3}><KpiCard label="Total messages" value={totalMsgs} icon={<ForumIcon fontSize="small" />} color="secondary" /></Grid>
      </Grid>

      <Card sx={{ p: 0, overflow: "hidden" }}>
        <Box sx={{ px: 2, py: 1.5, borderBottom: (t) => `1px solid ${t.palette.divider}`,
          background: (t) => alpha(t.palette.primary.main, 0.04) }}>
          <TextField fullWidth size="small" placeholder="Search by name, number, message or class…"
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: (<InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>) }}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: 2.5 } }} />
        </Box>

        {filtered.length === 0 ? (
          <EmptyState text={search ? "No chats match your search." : "No conversations yet."} />
        ) : (
          <Box sx={{ maxHeight: "calc(100vh - 380px)", minHeight: 240, overflow: "auto" }}>
            {filtered.map((r) => (
              <ChatRow key={r.wa_user} row={r} showClinic={showClinic}
                clinicName={tenant_names[r.tenant_id]} typing={typing.has(r.wa_user)}
                onClick={() => nav(`/patients/${r.wa_user}`)} />
            ))}
          </Box>
        )}
      </Card>
    </>
  );
}
