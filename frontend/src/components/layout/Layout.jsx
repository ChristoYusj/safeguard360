import { Outlet, Link, useLocation } from "react-router-dom";

const navItems = [
  { path: "/", label: "Dashboard", icon: "📊" },
  { path: "/attendance", label: "Attendance", icon: "👥" },
  { path: "/ppe", label: "PPE Events", icon: "🦺" },
  { path: "/driver", label: "Driver Events", icon: "🚗" },
  { path: "/alerts", label: "Alerts", icon: "🔔" },
  { path: "/enrollment", label: "Enrollment", icon: "📝" },
  { path: "/settings", label: "Settings", icon: "⚙️" },
];

function Layout() {
  const location = useLocation();

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-800 text-white">
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-xl font-bold">SafeGuard 360</h1>
        </div>
        <nav className="p-4">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-4 py-2 rounded mb-1 ${
                location.pathname === item.path
                  ? "bg-blue-600"
                  : "hover:bg-gray-700"
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

export default Layout;
