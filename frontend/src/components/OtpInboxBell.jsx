import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Inbox, Copy, Check, X } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/**
 * OtpInboxBell — header bell + drawer that polls /api/otp/inbox so users
 * see verification codes without leaving the tab. Backend already stores
 * a per-user copy of every OTP code in `db.otp_inbox` (TTL 10 min).
 *
 * • Polls every 15s when logged in.
 * • Shows an unread badge count on the bell (matches Header's badge style).
 * • Drawer lists each active code with purpose, countdown, and copy-to-
 *   clipboard button.
 */
const POLL_MS = 15000;

const formatCountdown = (expiresAt) => {
  const left = Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000));
  const m = Math.floor(left / 60);
  const s = left % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
};

const OtpInboxBell = ({ compact = false }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [copiedId, setCopiedId] = useState(null);
  const [tick, setTick] = useState(0);
  const drawerRef = useRef(null);
  const buttonRef = useRef(null);

  const fetchInbox = useCallback(async () => {
    if (!user) return;
    try {
      const { data } = await api.get("/otp/inbox");
      const now = Date.now();
      const active = (data?.items || []).filter(
        (i) => new Date(i.expires_at).getTime() > now
      );
      setItems(active);
      // Any newly-arrived code (not yet marked read on server) counts as unread.
      setUnread(active.filter((i) => !i.read).length);
    } catch { /* silently ignore — the bell just stays quiet */ }
  }, [user]);

  // Poll on mount + interval.
  useEffect(() => {
    if (!user) { setItems([]); setUnread(0); return; }
    fetchInbox();
    const t = setInterval(fetchInbox, POLL_MS);
    return () => clearInterval(t);
  }, [user, fetchInbox]);

  // 1-second ticker so countdowns update live while the drawer is open.
  useEffect(() => {
    if (!open) return;
    const id = setInterval(() => setTick((n) => (n + 1) % 60), 1000);
    return () => clearInterval(id);
  }, [open]);

  // Click outside to close the drawer.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (
        drawerRef.current && !drawerRef.current.contains(e.target) &&
        buttonRef.current && !buttonRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const toggle = () => {
    setOpen((v) => !v);
    // Opening the drawer = user saw the codes → tell the server to
    // mark them read so the unread badge doesn't cling to the bell.
    if (!open) {
      api.get("/otp/inbox", { params: { mark_read: 1 } }).catch(() => {});
      setTimeout(() => setUnread(0), 200);
    }
  };

  const copy = async (item) => {
    try {
      await navigator.clipboard.writeText(item.code);
      setCopiedId(item.id);
      toast({ title: "Code copied", description: `Ready to paste into ${item.label}.` });
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      toast({ title: "Copy failed", description: "Long-press the code to select it manually.", variant: "destructive" });
    }
  };

  const btnSize = compact ? "h-9 w-9" : "h-10 w-10";
  const iconSize = "h-5 w-5";

  // Compute visible items OUTSIDE the early return so hook order stays stable.
  // useMemo depends on `tick` so countdowns refresh once per second.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const visibleItems = useMemo(() => items, [items, tick]);

  if (!user) return null;

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={toggle}
        aria-label="Open OTP inbox"
        className={`relative ${btnSize} rounded-full bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 hover:border-[#5459E8] dark:hover:border-[#818CF8] hover:text-[#5459E8] dark:hover:text-[#818CF8] grid place-items-center transition-colors`}
        data-testid="otp-inbox-bell"
      >
        <Inbox className={iconSize} />
        {unread > 0 && (
          <span
            className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-[#FF0515] text-white text-[10px] font-extrabold grid place-items-center ring-2 ring-white dark:ring-neutral-900 shadow"
            data-testid="otp-inbox-badge"
          >
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={drawerRef}
          className="absolute right-0 mt-2 w-[320px] sm:w-[380px] rounded-2xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 shadow-2xl z-50 overflow-hidden"
          data-testid="otp-inbox-drawer"
        >
          <div className="p-4 border-b border-neutral-100 dark:border-neutral-800 flex items-start justify-between gap-2">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-[#FF0515] font-extrabold">Verification codes</div>
              <div className="mt-1 text-sm font-bold text-[#5459E8] dark:text-[#818CF8]">In-App OTP Inbox</div>
              <div className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5">Codes disappear after 10 minutes</div>
            </div>
            <button
              type="button"
              className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
              onClick={() => setOpen(false)}
              aria-label="Close inbox"
              data-testid="otp-inbox-close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="max-h-[360px] overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800">
            {visibleItems.length === 0 ? (
              <div className="p-6 text-center text-neutral-500 dark:text-neutral-400 text-sm">
                <Inbox className="h-10 w-10 mx-auto text-neutral-300 dark:text-neutral-700 mb-2" />
                No active codes.
                <div className="text-[11px] mt-1">Request an OTP from any verify screen and it'll show up here instantly.</div>
              </div>
            ) : (
              visibleItems.map((it) => (
                <div key={it.id} className="p-4 flex items-center gap-3" data-testid={`otp-inbox-item-${it.purpose}`}>
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] uppercase tracking-[0.2em] text-[#FF0515] font-extrabold">{it.label}</div>
                    <div className="mt-1 text-2xl font-extrabold tabular-nums tracking-widest text-[#5459E8] dark:text-[#818CF8]" data-testid={`otp-inbox-code-${it.purpose}`}>
                      {it.code}
                    </div>
                    <div className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-1">
                      Expires in <span className="font-semibold">{formatCountdown(it.expires_at)}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => copy(it)}
                    className="shrink-0 h-9 px-3 rounded-full bg-gradient-to-r from-[#5459E8] to-[#818CF8] hover:brightness-110 text-white text-xs font-bold inline-flex items-center gap-1.5 shadow-sm"
                    data-testid={`otp-inbox-copy-${it.purpose}`}
                  >
                    {copiedId === it.id ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    {copiedId === it.id ? "Copied" : "Copy"}
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default OtpInboxBell;
