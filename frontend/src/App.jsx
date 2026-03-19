import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/layout/Layout";
import Dashboard from "./pages/Dashboard";
import Attendance from "./pages/Attendance";
import PPEEvents from "./pages/PPEEvents";
import DriverEvents from "./pages/DriverEvents";
import Alerts from "./pages/Alerts";
import Enrollment from "./pages/Enrollment";
import Settings from "./pages/Settings";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="attendance" element={<Attendance />} />
          <Route path="ppe" element={<PPEEvents />} />
          <Route path="driver" element={<DriverEvents />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="enrollment" element={<Enrollment />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
