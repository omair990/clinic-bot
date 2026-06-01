import { Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  Box, Drawer, AppBar, Toolbar, Typography, List, ListItemButton, ListItemIcon,
  ListItemText, Divider, Button, Chip,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ChatIcon from "@mui/icons-material/Chat";
import EventIcon from "@mui/icons-material/Event";
import EventBusyIcon from "@mui/icons-material/EventBusy";
import InsightsIcon from "@mui/icons-material/Insights";
import StarIcon from "@mui/icons-material/Star";
import SpeedIcon from "@mui/icons-material/Speed";
import LayersIcon from "@mui/icons-material/Layers";
import ReportProblemIcon from "@mui/icons-material/ReportProblem";
import LogoutIcon from "@mui/icons-material/Logout";
import { useAuth } from "./auth";

const DRAWER = 248;

interface NavItem { label: string; to: string; icon: JSX.Element; }

export default function Layout() {
  const { me, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const isSuper = me?.role === "super";

  const items: NavItem[] = [
    { label: isSuper ? "Overview" : "Dashboard", to: "/", icon: <DashboardIcon /> },
    { label: "Conversations", to: "/conversations", icon: <ChatIcon /> },
    { label: "Appointments", to: "/appointments", icon: <EventIcon /> },
    { label: "No-shows", to: "/no-shows", icon: <EventBusyIcon /> },
    { label: "Insights", to: "/insights", icon: <InsightsIcon /> },
    { label: "Reviews", to: "/reviews", icon: <StarIcon /> },
    ...(!isSuper ? [{ label: "Usage", to: "/usage", icon: <SpeedIcon /> }] : []),
    ...(isSuper ? [
      { label: "Issues", to: "/issues", icon: <ReportProblemIcon /> },
      { label: "Plans & Usage", to: "/plans", icon: <LayersIcon /> },
    ] : []),
  ];

  const active = (to: string) => (to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(to));

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER, flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: DRAWER, boxSizing: "border-box", bgcolor: "#0f172a", color: "#e2e8f0",
            border: 0,
          },
        }}
      >
        <Box sx={{ px: 2.5, py: 2.5 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: "#fff" }}>
            {me?.tenant_name || "Platform Admin"}
          </Typography>
          <Chip
            size="small"
            label={isSuper ? "Platform" : "Clinic"}
            sx={{ mt: 0.5, bgcolor: "rgba(20,184,166,.15)", color: "#5eead4", height: 20 }}
          />
        </Box>
        <Divider sx={{ borderColor: "rgba(255,255,255,.08)" }} />
        <List sx={{ px: 1, py: 1 }}>
          {items.map((it) => (
            <ListItemButton
              key={it.to}
              selected={active(it.to)}
              onClick={() => nav(it.to)}
              sx={{
                borderRadius: 1.5, mb: 0.5, color: "#cbd5e1",
                "& .MuiListItemIcon-root": { color: "inherit", minWidth: 38 },
                "&.Mui-selected": { bgcolor: "rgba(255,255,255,.10)", color: "#fff" },
                "&.Mui-selected:hover": { bgcolor: "rgba(255,255,255,.14)" },
                "&:hover": { bgcolor: "rgba(255,255,255,.06)" },
              }}
            >
              <ListItemIcon>{it.icon}</ListItemIcon>
              <ListItemText primaryTypographyProps={{ fontSize: 14 }} primary={it.label} />
            </ListItemButton>
          ))}
        </List>
        <Box sx={{ mt: "auto", p: 2 }}>
          <Button
            fullWidth size="small" startIcon={<LogoutIcon />} onClick={logout}
            sx={{ color: "#94a3b8", justifyContent: "flex-start" }}
          >
            Sign out
          </Button>
        </Box>
      </Drawer>

      <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
        <AppBar position="static" color="inherit" sx={{ bgcolor: "#fff", borderBottom: "1px solid #e2e8f0" }}>
          <Toolbar variant="dense" sx={{ minHeight: 52 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "success.main" }} />
              <Typography variant="body2" color="text.secondary">Live</Typography>
            </Box>
          </Toolbar>
        </AppBar>
        <Box sx={{ p: 3, flexGrow: 1, overflow: "auto" }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
