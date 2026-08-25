import React, { useCallback, useEffect, useRef, useState } from "react";
import { MessageCircle, X, Mail, Send, Loader2, ArrowLeft, Check, ChevronRight, Clock, ShieldCheck } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";

const POLL_MS = 15000;

const relTime = (iso) => {
  if (!iso) return "";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const SupportWidget = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("home"); // home | chat-list | chat | email
  const [tickets, setTickets] = useState([]);
  const [activeTicket, setActiveTicket] = useState(null);
  const [msgDraft, setMsgDraft] = useState("");
  const [emailForm, setEmailForm] = useState({ subject: "", message: "", guest_email: "", guest_name: "" });
  const [sending, setSending] = useState(false);
  const [unread, setUnread] = useState(0);
  const [emailSent, setEmailSent] = useState(false);
  const scrollRef = useRef(null);

  const loadTickets = useCallback(async () => {
    if (!user) { setTickets([]); return; }
    try {
      const { data } = await api.get("/support/tickets/my");
      setTickets(data.items || []);
    } catch { /* ignore */ }
  }, [user]);

  const loadUnread = useCallback(async () => {
    if (!user) { setUnread(0); return; }
    try {
      const { data } = await api.get("/support/unread-count");
      setUnread(data.unread || 0);
    } catch { /* ignore */ }
  }, [user]);

  // Background unread poll for the badge
  useEffect(() => {
    loadUnread();
    const t = setInterval(loadUnread, POLL_MS);
    return () => clearInterval(t);
  }, [loadUnread]);

  // Poll open ticket for admin replies
  useEffect(() => {
    if (!open || view !== "chat" || !activeTicket) return undefined;
    const t = setInterval(async () => {
      try {
        const { data } = await api.get(`/support/tickets/${activeTicket.id}`);
        setActiveTicket(data);
      } catch { /* ignore */ }
    }, POLL_MS);
    return () => clearInterval(t);
  }, [open, view, activeTicket]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [activeTicket]);

  const openWidget = () => {
    setOpen(true);
    if (user) loadTickets();
    setView("home");
    setEmailSent(false);
  };

  const startChat = async () => {
    if (!user) {
      toast({ title: "Please log in to chat with support", description: "You can still email us as a guest.", variant: "destructive" });
      setView("email");
      return;
    }
    // If user has an open chat, jump to the latest one
    await loadTickets();
    setView("chat-list");
  };

  const openTicket = async (t) => {
    try {
      const { data } = await api.get(`/support/tickets/${t.id}`);
      setActiveTicket(data);
      setView("chat");
      loadUnread();
    } catch (e) {
      toast({ title: "Couldn't open ticket", variant: "destructive" });
    }
  };

  const createNewChat = async () => {
    setActiveTicket({ id: null, channel: "chat", status: "open", subject: "New chat", messages: [] });
    setView("chat");
  };

  const sendChat = async () => {
    const text = msgDraft.trim();
    if (!text) return;
    setSending(true);
    try {
      if (!activeTicket?.id) {
        // First message → create ticket
        const { data } = await api.post("/support/tickets", { channel: "chat", message: text });
        const { data: fresh } = await api.get(`/support/tickets/${data.ticket_id}`);
        setActiveTicket(fresh);
      } else {
        await api.post(`/support/tickets/${activeTicket.id}/messages`, { text });
        const { data: fresh } = await api.get(`/support/tickets/${activeTicket.id}`);
        setActiveTicket(fresh);
      }
      setMsgDraft("");
      loadTickets();
    } catch (e) {
      toast({ title: "Send failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setSending(false); }
  };

  const sendEmail = async () => {
    const msg = emailForm.message.trim();
    const subject = emailForm.subject.trim() || "Support request";
    if (!msg) { toast({ title: "Please write a message", variant: "destructive" }); return; }
    if (!user && (!emailForm.guest_email.trim() || !emailForm.guest_email.includes("@"))) {
      toast({ title: "Please enter a valid email", variant: "destructive" });
      return;
    }
    setSending(true);
    try {
      const payload = { channel: "email", subject, message: msg };
      if (!user) {
        payload.guest_email = emailForm.guest_email.trim().toLowerCase();
        payload.guest_name = emailForm.guest_name.trim();
      }
      await api.post("/support/tickets", payload);
      setEmailSent(true);
      setEmailForm({ subject: "", message: "", guest_email: "", guest_name: "" });
    } catch (e) {
      toast({ title: "Send failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setSending(false); }
  };

  return (
    <>
      {/* Floating action button — visible on every page */}
      <button
        type="button"
        onClick={openWidget}
        aria-label="Open customer support"
        className={`fixed bottom-4 right-4 sm:bottom-6 sm:right-6 z-[60] group h-14 w-14 rounded-full shadow-xl shadow-black/20 grid place-items-center bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white hover:scale-105 hover:shadow-2xl active:scale-95 transition-all ${open ? "opacity-0 pointer-events-none" : "opacity-100"}`}
        data-testid="support-fab"
      >
        <MessageCircle className="h-6 w-6" />
        {unread > 0 && (
          <span
            className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-emerald-500 border-2 border-white text-[10px] font-bold grid place-items-center tabular-nums"
            data-testid="support-unread-badge"
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
        {/* Subtle pulse ring */}
        <span className="absolute inset-0 rounded-full bg-[#FF7A18]/40 animate-ping opacity-40 pointer-events-none" />
      </button>

      {/* Support panel */}
      {open && (
        <div
          className="fixed inset-x-0 bottom-0 sm:inset-auto sm:bottom-6 sm:right-6 z-[70] w-full sm:w-[380px] max-h-[92vh] sm:max-h-[640px] rounded-t-2xl sm:rounded-2xl bg-white dark:bg-neutral-900 shadow-2xl border border-neutral-200 dark:border-neutral-800 flex flex-col overflow-hidden animate-in slide-in-from-bottom-4"
          data-testid="support-panel"
          role="dialog"
          aria-label="Customer support"
        >
          {/* Header — gradient */}
          <div className="relative px-5 pt-5 pb-4 text-white overflow-hidden" style={{
            background: "linear-gradient(135deg, #FF7A18 0%, #FF211F 55%, #7C3AED 130%)",
          }}>
            <div className="pointer-events-none absolute -top-10 -right-10 h-40 w-40 rounded-full bg-white/10 blur-3xl" />
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                {view !== "home" && (
                  <button
                    type="button"
                    onClick={() => { setView(view === "chat" ? "chat-list" : "home"); setEmailSent(false); }}
                    className="h-8 w-8 rounded-full grid place-items-center bg-white/15 hover:bg-white/25 transition-colors"
                    aria-label="Back"
                    data-testid="support-back-btn"
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </button>
                )}
                <div>
                  <div className="text-[10px] uppercase tracking-[0.2em] font-semibold opacity-90">Mercarie-Global support</div>
                  <div className="text-lg font-extrabold leading-tight">
                    {view === "home" && "How can we help?"}
                    {view === "chat-list" && "Your conversations"}
                    {view === "chat" && (activeTicket?.subject || "Chat with support")}
                    {view === "email" && "Email support"}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="h-8 w-8 rounded-full grid place-items-center bg-white/15 hover:bg-white/25 transition-colors"
                aria-label="Close"
                data-testid="support-close-btn"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {view === "home" && (
              <p className="mt-2 text-xs text-white/80">Average reply time: under 15 minutes.</p>
            )}
          </div>

          {/* Body */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            {view === "home" && (
              <div className="p-4 space-y-3" data-testid="support-home">
                <button
                  type="button"
                  onClick={startChat}
                  className="w-full text-left group flex items-center gap-3 p-4 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 hover:border-[#FF211F] hover:shadow-md transition-all"
                  data-testid="support-open-chat-btn"
                >
                  <div className="h-11 w-11 rounded-xl grid place-items-center bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white shadow-lg shadow-red-500/20 shrink-0">
                    <MessageCircle className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-neutral-900 dark:text-neutral-100">Chat with us</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400">Live in-app messaging with our team.</div>
                  </div>
                  <ChevronRight className="h-5 w-5 text-neutral-400 group-hover:text-[#FF211F] group-hover:translate-x-1 transition-transform" />
                </button>

                <button
                  type="button"
                  onClick={() => setView("email")}
                  className="w-full text-left group flex items-center gap-3 p-4 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 hover:border-[#2563EB] hover:shadow-md transition-all"
                  data-testid="support-open-email-btn"
                >
                  <div className="h-11 w-11 rounded-xl grid place-items-center bg-gradient-to-br from-[#7DD3FC] to-[#2563EB] text-white shadow-lg shadow-blue-500/20 shrink-0">
                    <Mail className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-neutral-900 dark:text-neutral-100">Email support</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400">Send a message — we reply within one business day.</div>
                  </div>
                  <ChevronRight className="h-5 w-5 text-neutral-400 group-hover:text-[#2563EB] group-hover:translate-x-1 transition-transform" />
                </button>

                <div className="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-800">
                  <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold mb-2">Quick facts</div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="flex items-center gap-1.5 text-neutral-600 dark:text-neutral-300"><Clock className="h-3.5 w-3.5 text-emerald-500" /> 24/7 open</div>
                    <div className="flex items-center gap-1.5 text-neutral-600 dark:text-neutral-300"><ShieldCheck className="h-3.5 w-3.5 text-emerald-500" /> Encrypted</div>
                  </div>
                </div>
              </div>
            )}

            {view === "chat-list" && (
              <div className="p-3 space-y-2" data-testid="support-chat-list">
                <button
                  type="button"
                  onClick={createNewChat}
                  className="w-full min-h-[44px] rounded-lg bg-gradient-to-r from-[#FF7A18] to-[#FF211F] text-white text-sm font-semibold hover:brightness-110 transition-all"
                  data-testid="support-new-chat-btn"
                >
                  + Start a new chat
                </button>
                {tickets.length === 0 ? (
                  <div className="text-center text-sm text-neutral-500 py-8">No conversations yet. Start one!</div>
                ) : (
                  tickets.filter((t) => t.channel === "chat").map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => openTicket(t)}
                      className="w-full text-left p-3 rounded-lg border border-neutral-200 dark:border-neutral-800 hover:border-[#FF211F] hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
                      data-testid={`support-ticket-${t.id}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="font-semibold text-sm text-neutral-900 dark:text-neutral-100 truncate flex-1">{t.subject}</div>
                        {t.unread_by_user && <span className="h-2 w-2 rounded-full bg-emerald-500 shrink-0" title="New reply" />}
                      </div>
                      <div className="text-[11px] text-neutral-500 mt-0.5 flex items-center gap-1.5">
                        <span className={`inline-block px-1.5 py-0.5 rounded-full text-[9px] uppercase font-bold tracking-wider ${t.status === "closed" ? "bg-neutral-100 text-neutral-500" : "bg-emerald-100 text-emerald-700"}`}>
                          {t.status}
                        </span>
                        · {relTime(t.updated_at)}
                      </div>
                    </button>
                  ))
                )}
              </div>
            )}

            {view === "chat" && activeTicket && (
              <div className="flex flex-col h-full" data-testid="support-chat-view">
                <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
                  {(activeTicket.messages || []).length === 0 && (
                    <div className="text-center text-xs text-neutral-500 py-8">
                      Type your message below to start the conversation.
                    </div>
                  )}
                  {(activeTicket.messages || []).map((m) => (
                    <div key={m.id} className={`flex ${m.sender === "user" ? "justify-end" : "justify-start"}`}>
                      <div className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm leading-snug ${
                        m.sender === "user"
                          ? "bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white rounded-br-sm"
                          : "bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 rounded-bl-sm"
                      }`}>
                        <div className="text-[10px] uppercase tracking-wider font-semibold opacity-70 mb-0.5">
                          {m.sender === "admin" ? "Support" : "You"} · {relTime(m.created_at)}
                        </div>
                        <div className="whitespace-pre-wrap break-words">{m.text}</div>
                      </div>
                    </div>
                  ))}
                </div>
                {activeTicket.status !== "closed" ? (
                  <div className="border-t border-neutral-200 dark:border-neutral-800 p-3 flex items-end gap-2">
                    <textarea
                      value={msgDraft}
                      onChange={(e) => setMsgDraft(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
                      placeholder="Type a message… (Enter to send)"
                      rows={2}
                      className="flex-1 resize-none rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-950 px-3 py-2 text-sm focus:outline-none focus:border-[#FF211F] focus:ring-1 focus:ring-[#FF211F]"
                      data-testid="support-message-input"
                    />
                    <button
                      type="button"
                      onClick={sendChat}
                      disabled={sending || !msgDraft.trim()}
                      className="h-10 w-10 rounded-full bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white grid place-items-center disabled:opacity-50 hover:brightness-110 active:scale-95 transition-all"
                      aria-label="Send"
                      data-testid="support-send-btn"
                    >
                      {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    </button>
                  </div>
                ) : (
                  <div className="border-t p-3 text-center text-sm text-neutral-500">This ticket is closed. Start a new one from the home screen.</div>
                )}
              </div>
            )}

            {view === "email" && (
              <div className="p-4 space-y-3" data-testid="support-email-view">
                {emailSent ? (
                  <div className="text-center py-8" data-testid="support-email-sent">
                    <div className="mx-auto h-14 w-14 rounded-full bg-emerald-100 dark:bg-emerald-950 grid place-items-center mb-3">
                      <Check className="h-7 w-7 text-emerald-600 dark:text-emerald-300" />
                    </div>
                    <div className="font-bold text-lg">Message sent!</div>
                    <p className="text-sm text-neutral-500 mt-1">We&apos;ll reply to your email within one business day.</p>
                    <button
                      type="button"
                      onClick={() => { setEmailSent(false); setView("home"); }}
                      className="mt-4 min-h-[40px] px-4 rounded-full text-sm font-semibold bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
                    >
                      Back to home
                    </button>
                  </div>
                ) : (
                  <>
                    {!user && (
                      <>
                        <input
                          value={emailForm.guest_email}
                          onChange={(e) => setEmailForm((f) => ({ ...f, guest_email: e.target.value }))}
                          placeholder="Your email *"
                          type="email"
                          className="w-full min-h-[44px] rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-950 px-3 text-sm focus:outline-none focus:border-[#2563EB]"
                          data-testid="support-guest-email-input"
                        />
                        <input
                          value={emailForm.guest_name}
                          onChange={(e) => setEmailForm((f) => ({ ...f, guest_name: e.target.value }))}
                          placeholder="Your name (optional)"
                          className="w-full min-h-[44px] rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-950 px-3 text-sm focus:outline-none focus:border-[#2563EB]"
                          data-testid="support-guest-name-input"
                        />
                      </>
                    )}
                    <input
                      value={emailForm.subject}
                      onChange={(e) => setEmailForm((f) => ({ ...f, subject: e.target.value }))}
                      placeholder="Subject"
                      className="w-full min-h-[44px] rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-950 px-3 text-sm focus:outline-none focus:border-[#2563EB]"
                      data-testid="support-email-subject-input"
                    />
                    <textarea
                      value={emailForm.message}
                      onChange={(e) => setEmailForm((f) => ({ ...f, message: e.target.value }))}
                      placeholder="Describe your question or issue *"
                      rows={5}
                      className="w-full resize-none rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-950 px-3 py-2 text-sm focus:outline-none focus:border-[#2563EB]"
                      data-testid="support-email-message-input"
                    />
                    <button
                      type="button"
                      onClick={sendEmail}
                      disabled={sending || !emailForm.message.trim()}
                      className="w-full min-h-[44px] rounded-lg bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white font-semibold hover:brightness-110 disabled:opacity-60 transition-all inline-flex items-center justify-center gap-2"
                      data-testid="support-email-submit-btn"
                    >
                      {sending ? <><Loader2 className="h-4 w-4 animate-spin" /> Sending…</> : <><Send className="h-4 w-4" /> Send email</>}
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default SupportWidget;
