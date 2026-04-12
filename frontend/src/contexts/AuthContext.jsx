import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  getCurrentOperator,
  loginOperator,
  logoutOperator,
} from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = async () => {
    try {
      const response = await getCurrentOperator();
      setUser(response.user || null);
      return response.user || null;
    } catch (error) {
      setUser(null);
      if (!String(error.message || "").includes("Authentication required")) {
        console.error("[Auth] Failed to fetch current operator.", error);
      }
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshUser();
  }, []);

  const login = async (credentials) => {
    const response = await loginOperator(credentials);
    setUser(response.user || null);
    return response.user || null;
  };

  const logout = async () => {
    try {
      await logoutOperator();
    } catch (error) {
      console.error("[Auth] Logout request failed.", error);
    } finally {
      setUser(null);
    }
  };

  const value = useMemo(
    () => ({
      user,
      isLoading,
      isAuthenticated: Boolean(user),
      login,
      logout,
      refreshUser,
    }),
    [user, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
