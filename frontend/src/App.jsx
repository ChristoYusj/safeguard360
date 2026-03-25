import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/layout/Layout";
import Dashboard from "./pages/Dashboard";
import Portal from "./pages/Portal";
import ModuleSelection from "./pages/ModuleSelection";
import Attendance from "./pages/Attendance";
import Settings from "./pages/Settings";
import Logs from "./pages/Logs";
import AIChatbot from "./pages/AIChatbot";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Portal />} />
        <Route path="/modules" element={<ModuleSelection />} />
        <Route path="/" element={<Layout />}>
          <Route path="drivers" element={<Dashboard />} />
          <Route path="attendance" element={<Attendance />} />
          <Route path="settings" element={<Settings />} />
          <Route path="logs" element={<Logs />} />
          <Route path="ai-chatbot" element={<AIChatbot />} />
          <Route path="ppe" element={<Navigate to="/attendance" replace />} />
          <Route path="driver" element={<Navigate to="/drivers" replace />} />
          <Route path="alerts" element={<Navigate to="/logs" replace />} />
          <Route
            path="enrollment"
            element={<Navigate to="/attendance" replace />}
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
