import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    const token = localStorage.getItem("mercari-global_token");
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      try { localStorage.setItem("mercari-global_username", data.username || ""); } catch { /* ignore */ }
    } catch {
      localStorage.removeItem("mercari-global_token");
      localStorage.removeItem("mercari-global_username");
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("mercari-global_token", data.token);
    try { localStorage.setItem("mercari-global_username", data.user?.username || ""); } catch { /* ignore */ }
    setUser(data.user);
    return data.user;
  };

  const register = async (email, username, password) => {
    const { data } = await api.post("/auth/register", { email, username, password });
    localStorage.setItem("mercari-global_token", data.token);
    try { localStorage.setItem("mercari-global_username", data.user?.username || ""); } catch { /* ignore */ }
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem("mercari-global_token");
    localStorage.removeItem("mercari-global_username");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh: fetchMe }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
