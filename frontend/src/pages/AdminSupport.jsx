import React, { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MessageCircle, Mail, Send, Loader2, X, Circle, Search, User, Clock, Check, CheckCheck } from "lucide-react";

const POLL_MS = 20000;

const relTime = (iso) => {
  if (!iso) return "";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const StatusPill = ({ status }) => {
  const cls = {
    open: "bg-emerald-100 text-emerald-700 border-emerald-200",
    pending: "bg-amber-100 text-amber-700 border-amber-200",
    closed: "bg-neutral-100 text-neutral-500 border-neutral-200",
  }[status] || "bg-neutral-100 text-neutral-500 border-neutral-200";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] uppercase font-bold tracking-wider border ${cls}`}>
      {status}
    </span>
  );
};

const ChannelBadge = ({ channel }) => (
  <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
    channel === "chat"
      ? "bg-orange-50 text-orange-700 border border-orange-200"
      : "bg-blue-50 text-blue-700 border border-blue-200"
  }`}>
    {channel === "chat" ? <MessageCircle className="h-3 w-3" /> : <Mail className="h-3 w-3" />}
    {channel}
  </span>
);

const AdminSupport = () => {
  const { toast } = useToast();
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [channelFilter, setChannelFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [unread, setUnread] = useState(0);
  const scrollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const params = {};
      if (statusFilter !== "all") params.status = statusFilter;
      if (channelFilter !== "all") params.channel = channelFilter;
      const { data } = await api.get("/admin/support/tickets", { params });
      setTickets(data.items || []);
      setUnread(data.unread_by_admin || 0);
    } catch (e) {
      toast({ title: "Failed to load tickets", variant: "destructive" });
    } finally { setLoading(false); }
  }, [statusFilter, channelFilter, toast]);

  useEffect(() => {
    setLoading(true);
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  // Refresh the open ticket every 20s so a buyer typing shows live
  useEffect(() => {
    if (!selected) return undefined;
    const t = setInterval(async () => {
      try {
        const { data } = await api.get(`/support/tickets/${selected.id}`);
        setSelected(data);
      } catch { /* ignore */ }
    }, POLL_MS);
    return () => clearInterval(t);
  }, [selected]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [selected]);

  const openTicket = async (t) => {
    try {
      const { data } = await api.get(`/support/tickets/${t.id}`);
      setSelected(data);
      // Marking read is server-side; reload list to update unread badge
      load();
    } catch (e) {
      toast({ title: "Couldn't open ticket", variant: "destructive" });
    }
  };

  const sendReply = async () => {
    const text = reply.trim();
    if (!text || !selected) return;
    setSending(true);
    try {
      await api.post(`/support/tickets/${selected.id}/messages`, { text });
      setReply("");
      const { data } = await api.get(`/support/tickets/${selected.id}`);
      setSelected(data);
      load();
    } catch (e) {
      toast({ title: "Send failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setSending(false); }
  };

  const closeTicket = async () => {
    if (!selected) return;
    if (!window.confirm("Close this ticket? The buyer will need to start a new one to reply.")) return;
    try {
      await api.post(`/support/tickets/${selected.id}/close`);
      const { data } = await api.get(`/support/tickets/${selected.id}`);
      setSelected(data);
      load();
      toast({ title: "Ticket closed" });
    } catch (e) {
      toast({ title: "Failed to close", variant: "destructive" });
    }
  };

  const filtered = tickets.filter((t) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      (t.subject || "").toLowerCase().includes(q) ||
      (t.user_email || "").toLowerCase().includes(q) ||
      (t.user_name || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-4 h-[calc(100vh-8rem)]" data-testid="admin-support-page">
      {/* Left rail — ticket list */}
      <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-xl overflow-hidden flex flex-col">
        <div className="p-3 border-b border-neutral-200 dark:border-neutral-800">
          <div className="flex items-center justify-between mb-2">
            <div className="font-bold text-neutral-900 dark:text-neutral-100 flex items-center gap-1.5">
              <MessageCircle className="h-4 w-4 text-[#FF211F]" /> Support inbox
            </div>
            {unread > 0 && (
              <span className="text-[11px] font-bold bg-emerald-100 text-emerald-700 rounded-full px-2 py-0.5" data-testid="admin-support-unread-badge">
                {unread} new
              </span>
            )}
          </div>
          <div className="relative">
            <Search className="h-4 w-4 text-neutral-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search subject, name, email…"
              className="pl-8 h-9 text-sm"
              data-testid="admin-support-search"
            />
          </div>
          <div className="mt-2 flex gap-2">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="h-8 text-xs" data-testid="admin-support-status-filter"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="open">Open</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
              </SelectContent>
            </Select>
            <Select value={channelFilter} onValueChange={setChannelFilter}>
              <SelectTrigger className="h-8 text-xs" data-testid="admin-support-channel-filter"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All channels</SelectItem>
                <SelectItem value="chat">Chat</SelectItem>
                <SelectItem value="email">Email</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto" data-testid="admin-support-ticket-list">
          {loading ? (
            <div className="grid place-items-center py-16 text-neutral-400"><Loader2 className="h-5 w-5 animate-spin" /></div>
          ) : filtered.length === 0 ? (
            <div className="text-center text-sm text-neutral-500 py-12">No tickets match your filters.</div>
          ) : (
            filtered.map((t) => {
              const isActive = selected?.id === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => openTicket(t)}
                  className={`w-full text-left px-3 py-3 border-b border-neutral-100 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors ${isActive ? "bg-orange-50 dark:bg-orange-950/40 border-l-4 border-l-[#FF211F]" : ""}`}
                  data-testid={`admin-ticket-${t.id}`}
                >
                  <div className="flex items-center gap-2">
                    {t.unread_by_admin && <Circle className="h-2 w-2 fill-emerald-500 text-emerald-500 shrink-0" data-testid={`admin-ticket-unread-${t.id}`} />}
                    <div className={`font-semibold text-sm text-neutral-900 dark:text-neutral-100 truncate flex-1 ${t.unread_by_admin ? "font-bold" : ""}`}>
                      {t.subject}
                    </div>
                    <ChannelBadge channel={t.channel} />
                  </div>
                  <div className="text-[11px] text-neutral-500 mt-0.5 truncate">
                    <User className="h-3 w-3 inline mr-1" /> {t.user_name} · {t.user_email}
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-neutral-500">
                    <StatusPill status={t.status} />
                    <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {relTime(t.updated_at)}</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Right pane — conversation */}
      <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-xl overflow-hidden flex flex-col" data-testid="admin-support-conversation">
        {selected ? (
          <>
            <div className="p-4 border-b border-neutral-200 dark:border-neutral-800 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="font-bold text-lg text-neutral-900 dark:text-neutral-100 truncate">{selected.subject}</div>
                  <ChannelBadge channel={selected.channel} />
                  <StatusPill status={selected.status} />
                </div>
                <div className="text-xs text-neutral-500 mt-0.5">
                  {selected.user_name} · <a className="text-[#2563EB] hover:underline" href={`mailto:${selected.user_email}`}>{selected.user_email}</a>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {selected.status !== "closed" && (
                  <Button size="sm" variant="outline" onClick={closeTicket} data-testid="admin-support-close-btn">
                    <Check className="h-4 w-4 mr-1" /> Close
                  </Button>
                )}
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  className="h-8 w-8 rounded-full grid place-items-center hover:bg-neutral-100 dark:hover:bg-neutral-800 lg:hidden"
                  aria-label="Deselect"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 bg-neutral-50/50 dark:bg-neutral-950/50" data-testid="admin-support-messages">
              {(selected.messages || []).length === 0 && (
                <div className="text-center text-xs text-neutral-500 py-8">No messages yet.</div>
              )}
              {(selected.messages || []).map((m) => (
                <div key={m.id} className={`flex ${m.sender === "admin" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-snug ${
                    m.sender === "admin"
                      ? "bg-gradient-to-br from-[#7DD3FC] to-[#2563EB] text-white rounded-br-sm"
                      : "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 border border-neutral-200 dark:border-neutral-700 rounded-bl-sm"
                  }`}>
                    <div className="text-[10px] uppercase tracking-wider font-semibold opacity-80 mb-0.5 flex items-center gap-1">
                      {m.sender === "admin" ? <><CheckCheck className="h-3 w-3" /> {m.sender_name || "Support"}</> : (m.sender_name || "Buyer")}
                      <span className="opacity-60">· {relTime(m.created_at)}</span>
                    </div>
                    <div className="whitespace-pre-wrap break-words">{m.text}</div>
                  </div>
                </div>
              ))}
            </div>

            {selected.status !== "closed" ? (
              <div className="border-t border-neutral-200 dark:border-neutral-800 p-3 flex items-end gap-2 bg-white dark:bg-neutral-900">
                <textarea
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); sendReply(); } }}
                  placeholder="Reply to buyer… (Cmd/Ctrl+Enter to send)"
                  rows={3}
                  className="flex-1 resize-none rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-950 px-3 py-2 text-sm focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB]"
                  data-testid="admin-support-reply-input"
                />
                <Button
                  onClick={sendReply}
                  disabled={sending || !reply.trim()}
                  className="h-11 px-4 bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] hover:brightness-110 text-white gap-1 shadow"
                  data-testid="admin-support-send-btn"
                >
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  Send
                </Button>
              </div>
            ) : (
              <div className="border-t p-3 text-center text-sm text-neutral-500">This ticket is closed.</div>
            )}
          </>
        ) : (
          <div className="grid place-items-center h-full text-center px-8 text-neutral-500">
            <div>
              <div className="mx-auto h-16 w-16 rounded-full bg-neutral-100 dark:bg-neutral-800 grid place-items-center mb-4">
                <MessageCircle className="h-8 w-8 text-neutral-400" />
              </div>
              <div className="font-semibold text-neutral-700 dark:text-neutral-300">Select a ticket to read the thread</div>
              <p className="text-sm mt-1">Buyer messages appear on the left. Click any card to open the conversation.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminSupport;
