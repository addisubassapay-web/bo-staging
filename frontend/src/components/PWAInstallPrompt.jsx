import React, { useEffect, useState } from "react";
import { Download, Share, Plus, X as XIcon } from "lucide-react";

/**
 * PWA Install Prompt — a subtle bottom-sheet nudge that surfaces on mobile
 * once a visitor comes back for a 2nd+ session. Two branches:
 *
 *   • Chromium / Android → captures the `beforeinstallprompt` event, shows a
 *     custom "Install" button that fires the real native prompt.
 *   • iOS Safari → the event never fires, so we detect iOS + not-standalone
 *     and render a step-by-step "Tap Share → Add to Home Screen" panel.
 *
 * Not shown if:
 *   • The app is already running in standalone mode (already installed)
 *   • The user previously dismissed the prompt (localStorage flag)
 *   • This is the visitor's first-ever session (returning visitors only)
 *   • Viewport is desktop-wide
 */
const VISITS_KEY = "merchari-global_pwa_visit_count";
const DISMISS_KEY = "merchari-global_pwa_prompt_dismissed";
const INSTALLED_KEY = "merchari-global_pwa_installed";

const isStandalone = () => {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
};

const isIOS = () => {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  return /iPhone|iPad|iPod/i.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
};

const PWAInstallPrompt = () => {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [visible, setVisible] = useState(false);
  const [iosMode, setIosMode] = useState(false);

  useEffect(() => {
    if (isStandalone()) {
      try { localStorage.setItem(INSTALLED_KEY, "1"); } catch { /* ignore */ }
      return undefined;
    }
    // Count visits so we only nudge return visitors.
    let visits = 0;
    try { visits = parseInt(localStorage.getItem(VISITS_KEY) || "0", 10) || 0; } catch { /* ignore */ }
    visits += 1;
    try { localStorage.setItem(VISITS_KEY, String(visits)); } catch { /* ignore */ }

    let dismissed = false;
    try { dismissed = localStorage.getItem(DISMISS_KEY) === "1"; } catch { /* ignore */ }
    if (dismissed) return undefined;
    // Only nudge on mobile viewports and after the first return visit.
    const isMobile = window.innerWidth < 768;
    if (!isMobile || visits < 2) return undefined;

    const onBeforeInstall = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      // Small delay so the prompt doesn't jump-scare on page load.
      setTimeout(() => setVisible(true), 2500);
    };
    const onInstalled = () => {
      setVisible(false);
      try { localStorage.setItem(INSTALLED_KEY, "1"); } catch { /* ignore */ }
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);

    // iOS Safari never fires the event → surface the manual instructions
    // path after a similar delay.
    let iosTimer = null;
    if (isIOS()) {
      iosTimer = setTimeout(() => {
        setIosMode(true);
        setVisible(true);
      }, 3000);
    }
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
      if (iosTimer) clearTimeout(iosTimer);
    };
  }, []);

  const install = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    try {
      const choice = await deferredPrompt.userChoice;
      if (choice.outcome === "accepted") {
        try { localStorage.setItem(INSTALLED_KEY, "1"); } catch { /* ignore */ }
      }
    } catch { /* ignore */ }
    setDeferredPrompt(null);
    setVisible(false);
  };

  const dismiss = () => {
    setVisible(false);
    try { localStorage.setItem(DISMISS_KEY, "1"); } catch { /* ignore */ }
  };

  if (!visible) return null;

  return (
    <div
      className="fixed inset-x-3 bottom-3 z-50 sm:hidden animate-in slide-in-from-bottom-6 fade-in duration-500"
      role="dialog"
      aria-label="Add Merchari-global to your home screen"
      data-testid="pwa-install-prompt"
    >
      <div className="mx-auto max-w-md rounded-2xl shadow-2xl border border-neutral-200 bg-white overflow-hidden">
        <div className="flex items-start gap-3 p-4">
          <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-[#FF7A18] to-[#FF211F] grid place-items-center shrink-0 shadow-lg">
            <img src="/logo-mark.png" alt="" className="h-7 w-7 object-contain" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-neutral-900">Install Merchari-global</div>
            <div className="text-[12px] text-neutral-500 mt-0.5">
              {iosMode
                ? "Add to your home screen for one-tap access — no App Store required."
                : "Launch straight from your home screen, no browser needed."}
            </div>
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Dismiss"
            className="p-1.5 -m-1.5 text-neutral-400 hover:text-neutral-700"
            data-testid="pwa-install-dismiss"
          >
            <XIcon className="h-4 w-4" />
          </button>
        </div>

        {iosMode ? (
          <div className="px-4 pb-4 space-y-2 text-[12px] text-neutral-700">
            <div className="flex items-center gap-2 rounded-lg bg-neutral-50 border border-neutral-200 p-2">
              <span className="w-5 h-5 grid place-items-center rounded-full bg-neutral-200 text-[10px] font-bold">1</span>
              <span>Tap the</span>
              <Share className="h-3.5 w-3.5 text-sky-600" />
              <span className="font-medium">Share button</span>
              <span className="text-neutral-500">in Safari</span>
            </div>
            <div className="flex items-center gap-2 rounded-lg bg-neutral-50 border border-neutral-200 p-2">
              <span className="w-5 h-5 grid place-items-center rounded-full bg-neutral-200 text-[10px] font-bold">2</span>
              <span>Choose</span>
              <Plus className="h-3.5 w-3.5 text-emerald-600" />
              <span className="font-medium">Add to Home Screen</span>
            </div>
          </div>
        ) : (
          <div className="px-4 pb-4">
            <button
              type="button"
              onClick={install}
              className="w-full min-h-[44px] rounded-xl bg-gradient-to-r from-[#FF7A18] to-[#FF211F] text-white font-semibold text-sm inline-flex items-center justify-center gap-2 shadow hover:brightness-105 transition"
              data-testid="pwa-install-cta"
            >
              <Download className="h-4 w-4" /> Install app
            </button>
            <button
              type="button"
              onClick={dismiss}
              className="w-full mt-2 text-[11px] text-neutral-500 hover:text-neutral-800"
              data-testid="pwa-install-later"
            >
              Maybe later
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default PWAInstallPrompt;
