import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import RoleRoute from "./components/auth/RoleRoute";
import Layout from "./components/layout/Layout";
import { AuthProvider } from "./contexts/AuthContext";
import { AlertFeedProvider } from "./contexts/AlertFeedContext";
import Dashboard from "./pages/Dashboard";
import Portal from "./pages/Portal";
import ResetPassword from "./pages/ResetPassword";
import ModuleSelection from "./pages/ModuleSelection";
import Attendance from "./pages/Attendance";
import Settings from "./pages/Settings";
import Logs from "./pages/Logs";
import AIChatbot from "./pages/AIChatbot";
import Enrollment from "./pages/Enrollment";
import TwoFactorChallenge from "./pages/TwoFactorChallenge";
import UserManagement from "./pages/UserManagement";
import { ROLES } from "./utils/accessControl";

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AlertFeedProvider>
        <Routes>
          <Route path="/" element={<Portal />} />
          <Route path="/auth/2fa" element={<TwoFactorChallenge />} />
          <Route path="/auth/reset-password" element={<ResetPassword />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/modules" element={<ModuleSelection />} />
            <Route path="/" element={<Layout />}>
              <Route path="settings" element={<Settings />} />
              <Route element={<RoleRoute allowedRoles={[ROLES.ADMIN, ROLES.FLEET_OPERATOR, ROLES.GENERAL_MANAGER]} />}>
                <Route path="drivers" element={<Dashboard />} />
              </Route>
              <Route element={<RoleRoute allowedRoles={[ROLES.ADMIN, ROLES.SAFETY_OPERATOR, ROLES.GENERAL_MANAGER]} />}>
                <Route path="attendance" element={<Attendance />} />
              </Route>
              <Route element={<RoleRoute allowedRoles={[ROLES.ADMIN, ROLES.FLEET_OPERATOR, ROLES.SAFETY_OPERATOR, ROLES.GENERAL_MANAGER]} />}>
                <Route path="logs" element={<Logs />} />
              </Route>
              <Route element={<RoleRoute allowedRoles={[ROLES.ADMIN, ROLES.GENERAL_MANAGER]} />}>
                <Route path="ai-chatbot" element={<AIChatbot />} />
              </Route>
              <Route element={<RoleRoute allowedRoles={[ROLES.ADMIN]} />}>
                <Route path="enrollment" element={<Enrollment />} />
                <Route path="user-management" element={<UserManagement />} />
              </Route>
              <Route path="ppe" element={<Navigate to="/attendance" replace />} />
              <Route path="driver" element={<Navigate to="/drivers" replace />} />
              <Route path="alerts" element={<Navigate to="/logs" replace />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </AlertFeedProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
