import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  confirmTwoFactorEnable as confirmTwoFactorEnableRequest,
  disableTwoFactorAuth as disableTwoFactorAuthRequest,
  getCurrentOperator,
  loginOperator,
  logoutOperator,
  refreshOperatorSession as refreshOperatorSessionRequest,
  startTwoFactorSetup as startTwoFactorSetupRequest,
  verifyTwoFactorLogin,
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
      const message = String(error.message || "");
      if (message.includes("Authentication required")) {
        try {
          const refreshResponse = await refreshOperatorSessionRequest();
          setUser(refreshResponse.user || null);
          return refreshResponse.user || null;
        } catch {
          setUser(null);
          return null;
        }
      }

      setUser(null);
      if (!message.includes("Authentication required")) {
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
    if (response.user) {
      setUser(response.user);
    }
    return response;
  };

  const verifyTwoFactor = async (payload) => {
    const response = await verifyTwoFactorLogin(payload);
    setUser(response.user || null);
    return response;
  };

  const startTwoFactorSetup = async () => startTwoFactorSetupRequest();

  const confirmTwoFactorEnable = async (payload) => {
    const response = await confirmTwoFactorEnableRequest(payload);
    if (response.user) {
      setUser(response.user);
    }
    return response;
  };

  const disableTwoFactorAuth = async (payload) => {
    const response = await disableTwoFactorAuthRequest(payload);
    if (response.user) {
      setUser(response.user);
    }
    return response;
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
      verifyTwoFactor,
      logout,
      refreshUser,
      startTwoFactorSetup,
      confirmTwoFactorEnable,
      disableTwoFactorAuth,
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
