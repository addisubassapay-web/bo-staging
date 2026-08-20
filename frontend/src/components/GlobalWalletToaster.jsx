import { useEffect, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { useLang } from "@/context/LanguageContext";
import { useNotificationStream } from "@/hooks/useNotificationStream";

/**
 * App-level wallet/payout toast broadcaster. Mounts once in App.js so
 * sellers browsing storefronts, product pages, or the checkout flow still
 * catch a "Funds released" or "Payout paid" toast the instant a wallet
 * notification lands — not only when they're already sitting on /wallet.
 *
 * The Wallet page keeps its own toast hook (so it can also refresh the
 * ledger view), but this global broadcaster dedupes against a shared
 * localStorage cursor so users don't see the same toast twice.
 */
const GLOBAL_CURSOR_KEY = "mercuri-global_wallet_stream_cursor";

const GlobalWalletToaster = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const { t } = useLang();
  const seenRef = useRef(new Set());

  useEffect(() => {
    if (!user) return;
    // Seed the seen-cache from localStorage so a page reload doesn't replay
    // toasts the user already dismissed elsewhere.
    try {
      const raw = localStorage.getItem(GLOBAL_CURSOR_KEY);
      if (raw) JSON.parse(raw).forEach((id) => seenRef.current.add(id));
    } catch { /* ignore */ }
  }, [user]);

  useNotificationStream(
    (rows) => {
      const fresh = rows.filter((n) => n && n.id && !seenRef.current.has(n.id));
      if (fresh.length === 0) return;
      fresh.forEach((n) => {
        seenRef.current.add(n.id);
        toast({
          title: n.title || (t("wallet.stream.newActivity") || "New wallet activity"),
          description: n.body || "",
          duration: 7000,
        });
      });
      // Persist only the last 50 ids to keep localStorage bounded.
      try {
        const arr = Array.from(seenRef.current).slice(-50);
        localStorage.setItem(GLOBAL_CURSOR_KEY, JSON.stringify(arr));
      } catch { /* ignore */ }
    },
    "wallet,payout",
    15000,
    !!user,
  );

  return null;
};

export default GlobalWalletToaster;
