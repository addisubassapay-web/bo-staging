import React, { useEffect, useState } from "react";
import BrandMark from "@/components/BrandMark";

/**
 * SplashScreen — full-screen brand splash shown once per session on first paint.
 * Fades out after ~1.2s. Skips if the user has already seen it this session.
 */
const SplashScreen = () => {
  const [visible, setVisible] = useState(() => {
    if (typeof window === "undefined") return false;
    return !sessionStorage.getItem("mercari_splash_seen");
  });
  const [fadeOut, setFadeOut] = useState(false);

  useEffect(() => {
    if (!visible) return;
    const fadeTimer = setTimeout(() => setFadeOut(true), 1200);
    const hideTimer = setTimeout(() => {
      setVisible(false);
      try { sessionStorage.setItem("mercari_splash_seen", "1"); } catch { /* ignore storage errors */ }
    }, 1700);
    return () => { clearTimeout(fadeTimer); clearTimeout(hideTimer); };
  }, [visible]);

  if (!visible) return null;

  const skip = () => {
    setFadeOut(true);
    setTimeout(() => {
      setVisible(false);
      try { sessionStorage.setItem("mercari_splash_seen", "1"); } catch { /* ignore */ }
    }, 350);
  };

  return (
    <div
      className={`fixed inset-0 z-[9999] flex items-center justify-center transition-opacity duration-500 ${fadeOut ? "opacity-0 pointer-events-none" : "opacity-100"}`}
      style={{
        background: "radial-gradient(circle at 50% 40%, #FFF7ED 0%, #FFE4D6 45%, #FFD5C1 100%)",
      }}
      data-testid="splash-screen"
      aria-hidden={fadeOut}
    >
      {/* Decorative blobs */}
      <div className="absolute -top-24 -left-24 h-72 w-72 rounded-full bg-[#FF7A18] opacity-20 blur-3xl" />
      <div className="absolute -bottom-24 -right-24 h-80 w-80 rounded-full bg-[#FF211F] opacity-15 blur-3xl" />
      <div className="absolute top-1/3 right-1/4 h-40 w-40 rounded-full bg-[#2563EB] opacity-10 blur-3xl" />

      <div className="relative flex flex-col items-center gap-6 animate-hero-in">
        <BrandMark size={160} animated />
        <div className="flex flex-col items-center gap-1">
          <span className="text-3xl font-bold tracking-tight text-neutral-900">mercarie</span>
          <span className="text-xs uppercase tracking-[0.3em] text-neutral-500">Global marketplace</span>
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
