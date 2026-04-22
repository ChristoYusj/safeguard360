import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { canAccessPath, getDefaultRouteForRole } from "../../utils/accessControl";

function RoleRoute({ allowedRoles = null }) {
  const location = useLocation();
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/" replace state={{ from: location }} />;
  }

  const currentRole = user.role;
  const canAccess =
    Array.isArray(allowedRoles) && allowedRoles.length > 0
      ? allowedRoles.includes(currentRole)
      : canAccessPath(currentRole, location.pathname);

  if (!canAccess) {
    return <Navigate to={getDefaultRouteForRole(currentRole)} replace />;
  }

  return <Outlet />;
}

export default RoleRoute;
