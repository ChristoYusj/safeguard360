import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import Layout from "./components/layout/Layout";
import { AuthProvider } from "./contexts/AuthContext";
import Dashboard from "./pages/Dashboard";
import Portal from "./pages/Portal";
import ModuleSelection from "./pages/ModuleSelection";
import Attendance from "./pages/Attendance";
import Settings from "./pages/Settings";
import Logs from "./pages/Logs";
import AIChatbot from "./pages/AIChatbot";
import Enrollment from "./pages/Enrollment";

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Portal />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/modules" element={<ModuleSelection />} />
            <Route path="/" element={<Layout />}>
              <Route path="drivers" element={<Dashboard />} />
              <Route path="attendance" element={<Attendance />} />
              <Route path="settings" element={<Settings />} />
              <Route path="logs" element={<Logs />} />
              <Route path="ai-chatbot" element={<AIChatbot />} />
              <Route path="enrollment" element={<Enrollment />} />
              <Route path="ppe" element={<Navigate to="/attendance" replace />} />
              <Route path="driver" element={<Navigate to="/drivers" replace />} />
              <Route path="alerts" element={<Navigate to="/logs" replace />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
