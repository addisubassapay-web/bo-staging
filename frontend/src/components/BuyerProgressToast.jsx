import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Truck } from "lucide-react";

/**
 * BuyerProgressToast
 * Polls /api/notifications every 30s (authenticated users only) and shows a
 * floating toast whenever a NEW shipping-update notification appears.
 *
 * Persists last-seen notification id in localStorage so the toast only fires
 * for genuinely new events (not on every page load).
 */
const LS_KEY = "mercari-global_last_seen_shipping_notif";
const POLL_MS = 30000;

const BuyerProgressToast = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const lastSeenRef = useRef(localStorage.getItem(LS_KEY) || "");
  const bootstrappedRef = useRef(false);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const { data } = await api.get("/notifications");
        if (cancelled) return;
        // Filter shipping-related notifications (order type with shipping keywords)
        const shippingNotifs = (data || []).filter((n) =>
          n.type === "order" &&
          (n.title?.toLowerCase().includes("shipping") || n.title?.toLowerCase().includes("delivered")),
        );
        if (shippingNotifs.length === 0) return;
        // Notifications are returned newest-first (backend sorts by created_at desc).
        const newest = shippingNotifs[0];
        // On very first load, don't fire — just record the newest id so we only alert on future updates.
        if (!bootstrappedRef.current) {
          bootstrappedRef.current = true;
          if (!lastSeenRef.current) {
            lastSeenRef.current = newest.id;
            localStorage.setItem(LS_KEY, newest.id);
          }
          return;
        }
        if (newest.id !== lastSeenRef.current) {
          // Fire toast(s) for every new item newer than lastSeen
          const idx = shippingNotifs.findIndex((n) => n.id === lastSeenRef.current);
          const fresh = idx === -1 ? shippingNotifs.slice(0, 3) : shippingNotifs.slice(0, idx);
          fresh.reverse().forEach((n) => {
            toast({
              title: n.title,
              description: n.body,
              action: n.link ? (
                <button
                  onClick={() => navigate(n.link)}
                  className="text-xs font-semibold text-[#1E40AF] hover:underline"
                >
                  Track →
                </button>
              ) : undefined,
            });
          });
          lastSeenRef.current = newest.id;
          localStorage.setItem(LS_KEY, newest.id);
        }
      } catch {
        /* silent */
      }
    };

    // Fire immediately, then interval
    poll();
    const iv = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(iv); };
  }, [user, toast, navigate]);

  return null;
};

// Small pulsing icon we can drop next to the notifications bell — unused for now but exported for future.
export const ShippingPulseIcon = () => (
  <span className="relative inline-flex">
    <Truck className="h-4 w-4 text-emerald-500" />
    <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
  </span>
);

export default BuyerProgressToast;
