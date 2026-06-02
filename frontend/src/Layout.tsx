import { useState, type ReactNode } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  Box, Drawer, AppBar, Toolbar, Typography, List, ListItemButton, ListItemIcon,
  ListItemText, Divider, IconButton, Tooltip, Avatar, Menu, MenuItem, Breadcrumbs, Link,
  Fade, alpha, useMediaQuery, useTheme, Paper, BottomNavigation, BottomNavigationAction,
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
import MoreHorizIcon from "@mui/icons-material/MoreHorizRounded";
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
const MOBILE_W = 280;

export default function Layout() {
  const { me, logout } = useAuth();
  const { mode, toggle } = useColorMode();
  const { lang, dir, setLang } = useI18n();
  const t = useT();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(true);          // desktop: full/mini
  const [mobileOpen, setMobileOpen] = useState(false);  // mobile: drawer overlay
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  const isSuper = me?.role === "super";
  const W = open ? FULL : MINI;

  const items: { label: string; short?: string; to: string; icon: ReactNode }[] = [
    { label: t(isSuper ? "nav.overview" : "nav.dashboard"), short: t("nav.shortOverview"), to: "/", icon: <DashboardIcon /> },
    { label: t("nav.conversations"), short: t("nav.shortChats"), to: "/conversations", icon: <ChatIcon /> },
    { label: t("nav.appointments"), short: t("nav.shortAppointments"), to: "/appointments", icon: <EventIcon /> },
    { label: t("nav.no-shows"), short: t("nav.shortMissed"), to: "/no-shows", icon: <EventBusyIcon /> },
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
  const crumbLabel = crumbKey === "" ? t(isSuper ? "nav.overview" : "nav.dashboard") : t(`nav.${crumbKey}`);

  const go = (to: string) => { nav(to); setMobileOpen(false); };

  // Drawer contents, reused by the desktop (docked) and mobile (overlay) drawers.
  // `expanded` controls label visibility — always true on the mobile overlay.
  const drawerBody = (expanded: boolean) => (
    <>
      <Box sx={{ px: expanded ? 2.5 : 0, py: 2.4, display: "flex", alignItems: "center",
        justifyContent: expanded ? "flex-start" : "center", gap: 1.2 }}>
        <Box sx={{ width: 38, height: 38, borderRadius: 2.5, display: "grid", placeItems: "center",
          background: "linear-gradient(135deg,#14b8a6,#6366f1)", color: "#fff", flexShrink: 0 }}>
          <LocalHospitalIcon fontSize="small" />
        </Box>
        {expanded && (
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
          <Tooltip key={it.to} title={expanded ? "" : it.label} placement={dir === "rtl" ? "left" : "right"}>
            <ListItemButton selected={active(it.to)} onClick={() => go(it.to)}
              sx={{
                borderRadius: 2, mb: 0.5, minHeight: 44, px: expanded ? 1.5 : 0,
                justifyContent: expanded ? "flex-start" : "center", color: "#cbd5e1",
                "& .MuiListItemIcon-root": { color: "inherit", minWidth: 0, marginInlineEnd: expanded ? 1.5 : 0 },
                "&.Mui-selected": {
                  color: "#fff",
                  background: "linear-gradient(90deg, rgba(20,184,166,.25), rgba(99,102,241,.18))",
                  boxShadow: "inset 2px 0 0 #14b8a6",
                },
                "&.Mui-selected:hover": { background: "linear-gradient(90deg, rgba(20,184,166,.32), rgba(99,102,241,.24))" },
                "&:hover": { background: alpha("#fff", 0.06) },
              }}>
              <ListItemIcon>{it.icon}</ListItemIcon>
              {expanded && <ListItemText primaryTypographyProps={{ fontSize: 14, fontWeight: 600 }} primary={it.label} />}
            </ListItemButton>
          </Tooltip>
        ))}
      </List>
    </>
  );

  const paperGradient = (th: any) => (th.palette.mode === "dark"
    ? "linear-gradient(180deg, #0d1424 0%, #0a101d 100%)"
    : "linear-gradient(180deg, #0f172a 0%, #111a2e 100%)");

  // Mobile bottom tab bar: the four primary destinations + a "More" button (opens the drawer).
  const primary = items.slice(0, 4);
  const activeIdx = primary.findIndex((it) => active(it.to));

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      {/* Desktop: docked, collapsible sidebar */}
      <Drawer variant="permanent" sx={{
        display: { xs: "none", md: "block" }, width: W, flexShrink: 0, whiteSpace: "nowrap",
        "& .MuiDrawer-paper": {
          width: W, boxSizing: "border-box", border: 0, overflowX: "hidden",
          transition: "width .22s ease", background: paperGradient, color: "#cbd5e1",
        },
      }}>
        {drawerBody(open)}
      </Drawer>

      {/* Mobile: overlay drawer. MUI flips left/right anchors by theme.direction, so a constant
          "left" resolves to the start side automatically — left in LTR, right in RTL (matching the
          edge="start" hamburger). Passing "right" for RTL would double-flip back to the left. */}
      <Drawer variant="temporary" open={mobileOpen} onClose={() => setMobileOpen(false)}
        anchor="left" ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: "block", md: "none" },
          "& .MuiDrawer-paper": { width: MOBILE_W, boxSizing: "border-box", border: 0,
            background: paperGradient, color: "#cbd5e1" },
        }}>
        {drawerBody(true)}
      </Drawer>

      <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <AppBar position="sticky" color="transparent"
          sx={{ backdropFilter: "blur(10px)", bgcolor: (t) => alpha(t.palette.background.default, 0.7),
            borderBottom: (t) => `1px solid ${t.palette.divider}` }}>
          <Toolbar sx={{ gap: { xs: 0.25, sm: 1 } }}>
            <IconButton edge="start" onClick={() => (isMobile ? setMobileOpen((o) => !o) : setOpen((o) => !o))}><MenuIcon /></IconButton>
            <Breadcrumbs sx={{ flexGrow: 1, "& .MuiBreadcrumbs-ol": { flexWrap: "nowrap" } }}>
              <Link underline="hover" color="inherit" sx={{ cursor: "pointer", display: { xs: "none", sm: "block" } }} onClick={() => nav("/")}>{t("common.home")}</Link>
              <Typography color="text.primary" noWrap sx={{ fontWeight: 700 }}>{crumbLabel}</Typography>
            </Breadcrumbs>
            <NotificationBell />
            <Tooltip title={lang === "ar" ? "English" : "العربية"}>
              <IconButton onClick={() => setLang(lang === "ar" ? "en" : "ar")} sx={{ gap: 0.5 }}>
                <TranslateIcon fontSize="small" />
                <Typography variant="caption" fontWeight={800}>{lang === "ar" ? "EN" : "ع"}</Typography>
              </IconButton>
            </Tooltip>
            <Tooltip title={mode === "dark" ? t("common.lightMode") : t("common.darkMode")}>
              <IconButton sx={{ display: { xs: "none", sm: "inline-flex" } }} onClick={toggle}>{mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}</IconButton>
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
              {/* On mobile the dark-mode toggle moves into the account menu (hidden in the bar). */}
              <MenuItem sx={{ display: { sm: "none" } }} onClick={() => { toggle(); setAnchor(null); }}>
                {mode === "dark" ? <LightModeIcon fontSize="small" style={{ marginInlineEnd: 10 }} /> : <DarkModeIcon fontSize="small" style={{ marginInlineEnd: 10 }} />}
                {mode === "dark" ? t("common.lightMode") : t("common.darkMode")}
              </MenuItem>
              <Divider />
              <MenuItem onClick={logout}><LogoutIcon fontSize="small" style={{ marginInlineEnd: 10 }} /> {t("common.signOut")}</MenuItem>
            </Menu>
          </Toolbar>
        </AppBar>

        <Fade in key={loc.pathname} timeout={260}>
          <Box sx={{ p: { xs: 2, md: 3 }, pb: { xs: 11, md: 3 }, flexGrow: 1, overflow: "auto" }}>
            <Outlet />
          </Box>
        </Fade>
      </Box>

      {/* Mobile bottom tab bar */}
      <Paper elevation={8} sx={{
        display: { xs: "block", md: "none" }, position: "fixed", left: 0, right: 0, bottom: 0,
        zIndex: (t) => t.zIndex.appBar + 1, borderTop: (t) => `1px solid ${t.palette.divider}`,
        bgcolor: (t) => alpha(t.palette.background.paper, 0.96), backdropFilter: "blur(10px)",
        pb: "env(safe-area-inset-bottom)",   // clear the iOS home indicator
      }}>
        <BottomNavigation showLabels value={activeIdx === -1 ? false : activeIdx}
          sx={{
            bgcolor: "transparent", height: 62,
            "& .MuiBottomNavigationAction-root": {
              minWidth: 0, maxWidth: "none", px: 0.5, py: 0.75, gap: 0.25,
            },
            // Keep every label one line at a fixed size (default BottomNav grows the selected
            // label, which overflowed the cramped tabs). Ellipsis only as a last resort.
            "& .MuiBottomNavigationAction-label": {
              fontSize: 11, fontWeight: 600, lineHeight: 1.25, mt: 0.25, maxWidth: "100%",
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", transition: "none",
              "&.Mui-selected": { fontSize: 11 },
            },
            "& .MuiSvgIcon-root": { fontSize: 22 },
          }}>
          {primary.map((it, i) => (
            <BottomNavigationAction key={it.to} label={it.short ?? it.label} icon={it.icon}
              onClick={() => go(it.to)} value={i} />
          ))}
          <BottomNavigationAction label={t("common.more")} icon={<MoreHorizIcon />}
            onClick={() => setMobileOpen(true)} value="more" />
        </BottomNavigation>
      </Paper>
    </Box>
  );
}
