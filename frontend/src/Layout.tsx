import { useState } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  Box, Drawer, AppBar, Toolbar, Typography, List, ListItemButton, ListItemIcon,
  ListItemText, Divider, IconButton, Tooltip, Avatar, Menu, MenuItem, Breadcrumbs, Link,
  Fade, alpha,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/SpaceDashboard";
import ChatIcon from "@mui/icons-material/ForumOutlined";
import EventIcon from "@mui/icons-material/EventAvailableOutlined";
import EventBusyIcon from "@mui/icons-material/EventBusyOutlined";
import InsightsIcon from "@mui/icons-material/InsightsOutlined";
import StarIcon from "@mui/icons-material/StarBorderOutlined";
import SpeedIcon from "@mui/icons-material/SpeedOutlined";
import LayersIcon from "@mui/icons-material/LayersOutlined";
import ReportProblemIcon from "@mui/icons-material/ReportProblemOutlined";
import SettingsIcon from "@mui/icons-material/SettingsOutlined";
import MenuIcon from "@mui/icons-material/Menu";
import LightModeIcon from "@mui/icons-material/LightModeOutlined";
import DarkModeIcon from "@mui/icons-material/DarkModeOutlined";
import LogoutIcon from "@mui/icons-material/Logout";
import LocalHospitalIcon from "@mui/icons-material/LocalHospital";
import TranslateIcon from "@mui/icons-material/TranslateOutlined";
import { useAuth } from "./auth";
import { useColorMode } from "./ColorMode";
import { useI18n, useT } from "./i18n";
import NotificationBell from "./NotificationBell";

const FULL = 248;
const MINI = 76;

export default function Layout() {
  const { me, logout } = useAuth();
  const { mode, toggle } = useColorMode();
  const { lang, setLang } = useI18n();
  const t = useT();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(true);
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  const isSuper = me?.role === "super";
  const W = open ? FULL : MINI;

  const items = [
    { label: t(isSuper ? "nav.overview" : "nav.dashboard"), to: "/", icon: <DashboardIcon /> },
    { label: t("nav.conversations"), to: "/conversations", icon: <ChatIcon /> },
    { label: t("nav.appointments"), to: "/appointments", icon: <EventIcon /> },
    { label: t("nav.no-shows"), to: "/no-shows", icon: <EventBusyIcon /> },
    { label: t("nav.insights"), to: "/insights", icon: <InsightsIcon /> },
    { label: t("nav.reviews"), to: "/reviews", icon: <StarIcon /> },
    ...(!isSuper ? [{ label: t("nav.usage"), to: "/usage", icon: <SpeedIcon /> }] : []),
    ...(isSuper ? [
      { label: t("nav.issues"), to: "/issues", icon: <ReportProblemIcon /> },
      { label: t("nav.plans"), to: "/plans", icon: <LayersIcon /> },
      { label: t("nav.settings"), to: "/settings", icon: <SettingsIcon /> },
    ] : []),
  ];
  const active = (to: string) => (to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(to));
  const seg = loc.pathname.split("/").filter(Boolean);
  const crumbKey = seg[0] ?? "";
  const crumbLabel = crumbKey === "" ? t(isSuper ? "nav.overview" : "nav.dashboard")
    : t(`nav.${crumbKey}`);

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Drawer variant="permanent" sx={{
        width: W, flexShrink: 0, whiteSpace: "nowrap",
        "& .MuiDrawer-paper": {
          width: W, boxSizing: "border-box", border: 0, overflowX: "hidden",
          transition: "width .22s ease",
          background: (t) => t.palette.mode === "dark"
            ? "linear-gradient(180deg, #0d1424 0%, #0a101d 100%)"
            : "linear-gradient(180deg, #0f172a 0%, #111a2e 100%)",
          color: "#cbd5e1",
        },
      }}>
        <Box sx={{ px: open ? 2.5 : 0, py: 2.4, display: "flex", alignItems: "center",
          justifyContent: open ? "flex-start" : "center", gap: 1.2 }}>
          <Box sx={{ width: 38, height: 38, borderRadius: 2.5, display: "grid", placeItems: "center",
            background: "linear-gradient(135deg,#14b8a6,#6366f1)", color: "#fff", flexShrink: 0 }}>
            <LocalHospitalIcon fontSize="small" />
          </Box>
          {open && (
            <Box sx={{ overflow: "hidden" }}>
              <Typography noWrap sx={{ fontWeight: 800, color: "#fff", fontSize: 15 }}>
                {me?.tenant_name || t("common.clinicPlatform")}
              </Typography>
              <Typography noWrap variant="caption" sx={{ color: "#5eead4" }}>
                {isSuper ? t("common.platformAdmin") : t("common.clinicConsole")}
              </Typography>
            </Box>
          )}
        </Box>
        <Divider sx={{ borderColor: alpha("#fff", 0.08) }} />
        <List sx={{ px: 1, py: 1 }}>
          {items.map((it) => (
            <Tooltip key={it.to} title={open ? "" : it.label} placement="right">
              <ListItemButton selected={active(it.to)} onClick={() => nav(it.to)}
                sx={{
                  borderRadius: 2, mb: 0.5, minHeight: 44, px: open ? 1.5 : 0,
                  justifyContent: open ? "flex-start" : "center", color: "#cbd5e1",
                  "& .MuiListItemIcon-root": { color: "inherit", minWidth: 0, mr: open ? 1.5 : 0 },
                  "&.Mui-selected": {
                    color: "#fff",
                    background: "linear-gradient(90deg, rgba(20,184,166,.25), rgba(99,102,241,.18))",
                    boxShadow: "inset 2px 0 0 #14b8a6",
                  },
                  "&.Mui-selected:hover": { background: "linear-gradient(90deg, rgba(20,184,166,.32), rgba(99,102,241,.24))" },
                  "&:hover": { background: alpha("#fff", 0.06) },
                }}>
                <ListItemIcon>{it.icon}</ListItemIcon>
                {open && <ListItemText primaryTypographyProps={{ fontSize: 14, fontWeight: 600 }} primary={it.label} />}
              </ListItemButton>
            </Tooltip>
          ))}
        </List>
      </Drawer>

      <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <AppBar position="sticky" color="transparent"
          sx={{ backdropFilter: "blur(10px)", bgcolor: (t) => alpha(t.palette.background.default, 0.7),
            borderBottom: (t) => `1px solid ${t.palette.divider}` }}>
          <Toolbar sx={{ gap: 1 }}>
            <IconButton onClick={() => setOpen((o) => !o)} edge="start"><MenuIcon /></IconButton>
            <Breadcrumbs sx={{ flexGrow: 1 }}>
              <Link underline="hover" color="inherit" sx={{ cursor: "pointer" }} onClick={() => nav("/")}>{t("common.home")}</Link>
              <Typography color="text.primary" sx={{ fontWeight: 700 }}>{crumbLabel}</Typography>
            </Breadcrumbs>
            <NotificationBell />
            <Tooltip title={lang === "ar" ? "English" : "العربية"}>
              <IconButton onClick={() => setLang(lang === "ar" ? "en" : "ar")} sx={{ gap: 0.5 }}>
                <TranslateIcon fontSize="small" />
                <Typography variant="caption" fontWeight={800}>{lang === "ar" ? "EN" : "ع"}</Typography>
              </IconButton>
            </Tooltip>
            <Tooltip title={mode === "dark" ? t("common.lightMode") : t("common.darkMode")}>
              <IconButton onClick={toggle}>{mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}</IconButton>
            </Tooltip>
            <Tooltip title={t("common.account")}>
              <IconButton onClick={(e) => setAnchor(e.currentTarget)}>
                <Avatar sx={{ width: 32, height: 32, background: "linear-gradient(135deg,#14b8a6,#6366f1)", fontSize: 14 }}>
                  {(me?.tenant_name || "PA").slice(0, 2).toUpperCase()}
                </Avatar>
              </IconButton>
            </Tooltip>
            <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
              <MenuItem disabled sx={{ opacity: "1 !important" }}>
                <Box>
                  <Typography variant="body2" fontWeight={700}>{me?.tenant_name || t("common.platformAdmin")}</Typography>
                  <Typography variant="caption" color="text.secondary">{isSuper ? t("common.superAdmin") : t("common.clinicStaff")}</Typography>
                </Box>
              </MenuItem>
              <Divider />
              <MenuItem onClick={logout}><LogoutIcon fontSize="small" style={{ marginInlineEnd: 10 }} /> {t("common.signOut")}</MenuItem>
            </Menu>
          </Toolbar>
        </AppBar>

        <Fade in key={loc.pathname} timeout={260}>
          <Box sx={{ p: { xs: 2, md: 3 }, flexGrow: 1, overflow: "auto" }}>
            <Outlet />
          </Box>
        </Fade>
      </Box>
    </Box>
  );
}
