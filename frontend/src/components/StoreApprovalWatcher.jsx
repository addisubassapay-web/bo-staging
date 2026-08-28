import React, { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import StoreApprovedModal from "@/components/ui/StoreApprovedModal";

/**
 * StoreApprovalWatcher — mount once at the App root. Whenever the logged-in
 * user's `seller_status` flips to "approved", we fetch their store and pop
 * the StoreApprovedModal. Uses localStorage to guarantee the modal shows
 * exactly once per approval (survives refresh, doesn't nag afterwards).
 */
const StoreApprovalWatcher = () => {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [store, setStore] = useState(null);
  const prevStatus = useRef(null);

  useEffect(() => {
    if (!user) {
      prevStatus.current = null;
      return;
    }
    const flagKey = `mercari-global_store_approved_shown_${user.id}`;
    const alreadyShown = localStorage.getItem(flagKey);
    const isApproved = user.seller_status === "approved";

    // Two trigger paths:
    //  1. Transition mid-session (prev was pending/none/rejected → approved)
    //  2. First load post-approval (flag not yet set)
    const transitioned = prevStatus.current && prevStatus.current !== "approved" && isApproved;
    const firstLoadAfterApproval = isApproved && !alreadyShown;

    if (transitioned || firstLoadAfterApproval) {
      // Best-effort store fetch — modal renders even if this 404s
      api.get("/my/store").then((r) => setStore(r.data)).catch(() => setStore(null)).finally(() => {
        setOpen(true);
        localStorage.setItem(flagKey, "1");
      });
    }

    prevStatus.current = user.seller_status || null;
  }, [user]);

  if (!user) return null;
  return (
    <StoreApprovedModal
      open={open}
      onOpenChange={setOpen}
      store={store}
      user={user}
    />
  );
};

export default StoreApprovalWatcher;
