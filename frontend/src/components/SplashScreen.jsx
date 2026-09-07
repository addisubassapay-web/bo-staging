import React, { useEffect, useMemo, useState } from "react";
import BrandMark from "@/components/BrandMark";

/**
 * SplashScreen — full-screen brand splash shown once per session on first paint.
 * Personalized: greets returning logged-in users by name, welcomes first-time visitors.
 */
const SplashScreen = () => {
  const [visible, setVisible] = useState(() => {
    if (typeof window === "undefined") return false;
    if (sessionStorage.getItem("blueocean_splash_seen")) return false;
    // Respect prefers-reduced-motion — skip splash entirely for a11y
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      try { sessionStorage.setItem("blueocean_splash_seen", "1"); } catch { /* ignore */ }
      return false;
    }
    return true;
  });
  const [fadeOut, setFadeOut] = useState(false);

  // Personalized headline — computed once at render time.
  const { headline, sub, isReturning } = useMemo(() => {
    if (typeof window === "undefined") return { headline: "", sub: "", isReturning: false };
    const token = localStorage.getItem("blueocean_token");
    const name = (localStorage.getItem("blueocean_username") || "").trim();
    const hasVisited = localStorage.getItem("blueocean_visited_before") === "1";
    if (token && name) {
      const first = name.charAt(0).toUpperCase() + name.slice(1);
      return {
        headline: `Welcome back, ${first}`,
        sub: "Your marketplace, ready when you are.",
        isReturning: true,
      };
    }
    if (hasVisited) {
      return {
        headline: "Welcome back",
        sub: "Continue where you left off.",
        isReturning: true,
      };
    }
    return {
      headline: "Welcome to BlueOcean",
      sub: "Millions of items · Verified sellers · Buyer protection",
      isReturning: false,
    };
  }, []);

  useEffect(() => {
    if (!visible) return;
    // Mark that this browser has seen the splash at least once.
    try { localStorage.setItem("blueocean_visited_before", "1"); } catch { /* ignore */ }
    const fadeTimer = setTimeout(() => setFadeOut(true), 1500);
    const hideTimer = setTimeout(() => {
      setVisible(false);
      try { sessionStorage.setItem("blueocean_splash_seen", "1"); } catch { /* ignore */ }
    }, 2000);
    return () => { clearTimeout(fadeTimer); clearTimeout(hideTimer); };
  }, [visible]);

  if (!visible) return null;

  const skip = () => {
    setFadeOut(true);
    setTimeout(() => {
      setVisible(false);
      try { sessionStorage.setItem("blueocean_splash_seen", "1"); } catch { /* ignore */ }
    }, 350);
  };

  return (
    <div
      className={`fixed inset-0 z-[9999] flex items-center justify-center transition-opacity duration-500 ${fadeOut ? "opacity-0 pointer-events-none" : "opacity-100"}`}
      style={{
        background: "radial-gradient(circle at 50% 40%, #EFF6FF 0%, #DBEAFE 45%, #BFDBFE 100%)",
      }}
      data-testid="splash-screen"
      aria-hidden={fadeOut}
    >
      {/* Decorative blobs */}
      <div className="absolute -top-24 -left-24 h-72 w-72 rounded-full bg-[#5459E8] opacity-25 blur-3xl" />
      <div className="absolute -bottom-24 -right-24 h-80 w-80 rounded-full bg-[#818CF8] opacity-20 blur-3xl" />
      <div className="absolute top-1/3 right-1/4 h-40 w-40 rounded-full bg-[#60A5FA] opacity-15 blur-3xl" />

      <div className="relative flex flex-col items-center gap-6 animate-hero-in text-center px-6">
        <BrandMark size={160} animated />
        <div className="flex flex-col items-center gap-2">
          <span
            className="text-3xl sm:text-4xl font-bold tracking-tight text-neutral-900"
            data-testid="splash-headline"
          >
            {headline}
          </span>
          <span className="text-sm text-neutral-600 max-w-md">{sub}</span>
          {isReturning && (
            <span className="mt-2 inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.25em] text-[#2563EB] font-semibold">
              <span className="h-1.5 w-1.5 rounded-full bg-[#2563EB]" />
              Good to see you again
            </span>
          )}
        </div>
      </div>

      <button
        type="button"
        onClick={skip}
        className="absolute top-6 right-6 h-9 px-4 rounded-full bg-white/70 hover:bg-white text-neutral-700 text-xs font-medium border border-neutral-200 shadow-sm backdrop-blur transition"
        data-testid="splash-skip-btn"
        aria-label="Skip splash"
      >
        Skip →
      </button>
    </div>
  );
};

export default SplashScreen;
