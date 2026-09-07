import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

// Token lives in localStorage by default (persists across browser restarts).
// When the user unchecks "Keep me signed in" on Login, we store it in
// sessionStorage instead — so closing the tab clears the session, matching
// the checkbox contract.
const TOKEN_KEY = "blueocean_token";
const USERNAME_KEY = "blueocean_username";

// One-shot migration for anyone who signed in before the rebrand — read the
// legacy `mercari-global_*` keys and copy them into the new names so users
// don't get silently signed out on their next visit. Safe to remove after a
// few months.
try {
  for (const [oldK, newK] of [
    ["mercari-global_token", TOKEN_KEY],
    ["mercari-global_username", USERNAME_KEY],
  ]) {
    for (const store of [localStorage, sessionStorage]) {
      if (!store.getItem(newK) && store.getItem(oldK)) {
        store.setItem(newK, store.getItem(oldK));
      }
      store.removeItem(oldK);
    }
  }
} catch { /* storage disabled — ignore */ }

const readToken = () => {
  try { return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || null; }
  catch { return null; }
};

const writeToken = (token, remember = true) => {
  try {
    // Always clear both first so we never end up with two conflicting tokens.
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    if (remember) localStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.setItem(TOKEN_KEY, token);
  } catch { /* storage disabled */ }
};

const clearToken = () => {
  try {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
    sessionStorage.removeItem(USERNAME_KEY);
  } catch { /* ignore */ }
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    const token = readToken();
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      try { localStorage.setItem(USERNAME_KEY, data.username || ""); } catch { /* ignore */ }
    } catch (err) {
      // Only clear the token when the server tells us the credential is bad
      // (401 or 403). Any other error — 5xx gateway blip, Cloudflare edge
      // rewrite, network drop, CORS during redeploys — leaves the token
      // intact so we don't dump a signed-in user back to /login just because
      // of a transient failure. Previously an unconditional catch here caused
      // /apply-seller to render "Please log in to apply" whenever an OTP
      // endpoint returned 5xx.
      const status = err?.response?.status;
      if (status === 401 || status === 403) {
        clearToken();
        setUser(null);
      }
      // else: keep the last-known user + token; the next real request will
      // recover automatically if the backend comes back.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const login = async (email, password, opts = {}) => {
    const remember = opts.remember !== false; // default true
    const { data } = await api.post("/auth/login", { email, password });
    writeToken(data.token, remember);
    try { localStorage.setItem(USERNAME_KEY, data.user?.username || ""); } catch { /* ignore */ }
    // Carry the server-issued must-change flag onto the client user so
    // downstream components can gate on `user.must_change_password`.
    const merged = { ...data.user, must_change_password: !!data.password_change_required };
    setUser(merged);
    return merged;
  };

  const register = async (email, username, password) => {
    const { data } = await api.post("/auth/register", { email, username, password });
    writeToken(data.token, true);
    try { localStorage.setItem(USERNAME_KEY, data.user?.username || ""); } catch { /* ignore */ }
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    clearToken();
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
