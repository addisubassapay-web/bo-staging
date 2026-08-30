import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Bell, CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useAuth } from "@/context/AuthContext";

const typeIcon = {
  order: "📦",
  sale: "💰",
  message: "💬",
  review: "⭐",
  payout: "💵",
  system: "🔔",
};

const NotificationsBell = () => {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);

  const load = () => {
    api.get("/notifications").then((r) => setItems(r.data)).catch(() => {});
  };

  useEffect(() => {
    if (!user) return;
    load();
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, [user]);

  const unreadCount = items.filter((i) => !i.read).length;

  const markAllRead = async () => {
    await api.post("/notifications/read-all");
    setItems((prev) => prev.map((i) => ({ ...i, read: true })));
  };

  if (!user) return null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="relative">
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 bg-[#DC2626] text-white text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center">
              {unreadCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between p-3 border-b">
          <div className="font-semibold">Notifications</div>
          {unreadCount > 0 && (
            <button onClick={markAllRead} className="text-xs text-[#DC2626] hover:underline flex items-center gap-1">
              <CheckCheck className="h-3 w-3" /> Mark all read
            </button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {items.length === 0 ? (
            <div className="p-6 text-center text-sm text-neutral-500">No notifications</div>
          ) : (
            items.slice(0, 30).map((n) => (
              <Link
                key={n.id}
                to={n.link || "#"}
                onClick={() => { setOpen(false); if (!n.read) api.post(`/notifications/${n.id}/read`).catch(() => {}); }}
                className={`flex gap-3 p-3 border-b border-neutral-100 hover:bg-neutral-50 ${!n.read ? "bg-[#FFF3F2]/50" : ""}`}
              >
                <div className="text-lg leading-none">{typeIcon[n.type] || "🔔"}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium line-clamp-1">{n.title}</div>
                  {n.body && <div className="text-xs text-neutral-600 line-clamp-2 mt-0.5">{n.body}</div>}
                  <div className="text-[10px] text-neutral-400 mt-1">{new Date(n.created_at).toLocaleString()}</div>
                </div>
              </Link>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default NotificationsBell;
