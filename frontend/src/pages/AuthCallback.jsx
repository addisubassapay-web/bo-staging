import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import BrandMark from "@/components/BrandMark";

/**
 * AuthCallback — handles the return trip from Emergent Google Auth.
 *
 * Emergent redirects the user back to `${window.location.origin}/auth/callback#session_id=...`
 * We parse the session_id from the URL fragment, POST it to our backend which
 * exchanges it with Emergent for verified user data and returns our own JWT.
 * Then we drop the JWT into localStorage (same shape as email/password login)
 * and navigate to the home page.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
const AuthCallback = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const processed = useRef(false);
  const [state, setState] = useState({ status: "processing", message: "Signing you in…" });

  useEffect(() => {
    // Guard against React 18 StrictMode double-invocation
    if (processed.current) return;
    processed.current = true;

    const hash = location.hash || window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    const sessionId = match ? decodeURIComponent(match[1]) : null;

    if (!sessionId) {
      setState({ status: "error", message: "Missing session — please try again." });
      setTimeout(() => navigate("/login"), 1600);
      return;
    }

    (async () => {
      try {
        // Optional referral code carried over from the /register?ref=CODE flow
        const referralCode = (() => {
          try { return localStorage.getItem("mercari-global_pending_referral") || null; } catch { return null; }
        })();
        const { data } = await api.post("/auth/google/session", {
          session_id: sessionId,
          referral_code: referralCode,
        });
        try {
          localStorage.setItem("mercari-global_token", data.token);
          if (data.user?.username) localStorage.setItem("mercari-global_username", data.user.username);
          localStorage.removeItem("mercari-global_pending_referral");
        } catch { /* ignore storage errors */ }
        // Clear the hash so back-nav doesn't re-run this
        window.history.replaceState(null, "", "/");
        setState({ status: "ok", message: data.created ? "Welcome to Mercarie-Global!" : "Welcome back!" });
        // Full reload so AuthProvider picks up the fresh token
        setTimeout(() => { window.location.href = "/"; }, 600);
      } catch (err) {
        const detail = err.response?.data?.detail || "Sign-in failed";
        setState({ status: "error", message: detail });
        setTimeout(() => navigate("/login"), 2000);
      }
    })();
  }, [location, navigate]);

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="bg-white/80 dark:bg-neutral-900/70 backdrop-blur border border-white/60 dark:border-neutral-800 rounded-2xl p-10 shadow-xl ring-1 ring-neutral-100 dark:ring-neutral-800 text-center max-w-sm w-full">
        <div className="flex justify-center mb-5">
          <BrandMark size={72} animated />
        </div>
        <div className="text-lg font-semibold dark:text-neutral-100" data-testid="auth-callback-status">
          {state.message}
        </div>
        {state.status === "processing" && (
          <div className="mt-4 h-1 rounded-full bg-neutral-100 dark:bg-neutral-800 overflow-hidden">
            <div className="h-full w-1/3 bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] animate-pulse" />
          </div>
        )}
      </div>
    </div>
  );
};

export default AuthCallback;
