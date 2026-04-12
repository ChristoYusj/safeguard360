import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";

function ProtectedRoute() {
  const location = useLocation();
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-base px-6">
        <div className="rounded-2xl border border-default bg-card px-6 py-5 text-center shadow-card">
          <p className="text-base font-semibold text-primary">Checking operator session</p>
          <p className="mt-2 text-sm text-secondary">
            Verifying your access to SafeGuard 360.
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace state={{ from: location }} />;
  }

  return <Outlet />;
}

export default ProtectedRoute;
