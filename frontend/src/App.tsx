import { Routes, Route, Navigate } from "react-router-dom";
import { Box, CircularProgress } from "@mui/material";
import { useAuth } from "./auth";
import Layout from "./Layout";
import Login from "./pages/Login";
import Home from "./pages/Home";
import Conversations from "./pages/Conversations";
import PatientDetail from "./pages/PatientDetail";
import ClinicDetail from "./pages/ClinicDetail";
import Appointments from "./pages/Appointments";
import NoShows from "./pages/NoShows";
import Reviews from "./pages/Reviews";
import Insights from "./pages/Insights";
import Usage from "./pages/Usage";
import Plans from "./pages/Plans";
import CostCalculator from "./pages/CostCalculator";
import Capacity from "./pages/Capacity";
import Issues from "./pages/Issues";
import TenantEdit from "./pages/TenantEdit";
import Connector from "./pages/Connector";
import Settings from "./pages/Settings";

function Splash() {
  return (
    <Box sx={{ height: "100vh", display: "grid", placeItems: "center" }}>
      <CircularProgress />
    </Box>
  );
}

export default function App() {
  const { me, loading } = useAuth();
  if (loading) return <Splash />;
  if (!me) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  const isSuper = me.role === "super";
  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/conversations" element={<Conversations />} />
        <Route path="/patients/:wa" element={<PatientDetail />} />
        <Route path="/conversations/:wa" element={<PatientDetail />} />
        {isSuper && <Route path="/clinics/:id" element={<ClinicDetail />} />}
        <Route path="/appointments" element={<Appointments />} />
        <Route path="/no-shows" element={<NoShows />} />
        <Route path="/insights" element={<Insights />} />
        <Route path="/reviews" element={<Reviews />} />
        {!isSuper && <Route path="/usage" element={<Usage />} />}
        {isSuper && <Route path="/plans" element={<Plans />} />}
        {isSuper && <Route path="/calculator" element={<CostCalculator />} />}
        {isSuper && <Route path="/capacity" element={<Capacity />} />}
        {isSuper && <Route path="/issues" element={<Issues />} />}
        {isSuper && <Route path="/settings" element={<Settings />} />}
        {isSuper && <Route path="/tenants/:id" element={<TenantEdit />} />}
        {isSuper && <Route path="/tenants/:id/connector" element={<Connector />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
