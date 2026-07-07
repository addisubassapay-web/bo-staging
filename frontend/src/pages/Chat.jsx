import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Send, ChevronLeft, ArrowRight } from "lucide-react";

export const ChatThreads = () => {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [threads, setThreads] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/chat/threads").then((r) => setThreads(r.data)).finally(() => setLoading(false));
  }, [user, authLoading, navigate]);

  if (loading) return <div className="max-w-3xl mx-auto px-4 py-8">Loading…</div>;

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-6">Messages</h1>
      {threads.length === 0 ? (
        <div className="text-center py-16 border border-dashed rounded-xl text-neutral-500">
          No conversations yet. Message a seller from any listing page.
        </div>
      ) : (
        <div className="space-y-2">
          {threads.map((t) => (
            <Link
              key={`${t.listing_id}-${t.other_user_id}`}
              to={`/chat/${t.listing_id}/${t.other_user_id}`}
              className="flex items-center gap-3 border border-neutral-200 rounded-lg p-3 hover:bg-neutral-50"
            >
              {t.listing_image ? (
                <img src={t.listing_image} alt="" className="h-14 w-14 rounded object-cover" />
              ) : (
                <div className="h-14 w-14 rounded bg-neutral-100" />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <div className="font-medium">{t.other_username}</div>
                  <div className="text-xs text-neutral-500">{t.last_at ? new Date(t.last_at).toLocaleDateString() : ""}</div>
                </div>
                <div className="text-sm text-neutral-500 line-clamp-1">Re: {t.listing_title}</div>
                <div className="text-sm text-neutral-700 line-clamp-1 mt-0.5">{t.last_message}</div>
              </div>
              <ArrowRight className="h-4 w-4 text-neutral-400" />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

export const ChatRoom = () => {
  const { listingId, otherId } = useParams();
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [messages, setMessages] = useState([]);
  const [listing, setListing] = useState(null);
  const [otherUser, setOtherUser] = useState(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const load = () => {
    api.get(`/chat/${listingId}/${otherId}`).then((r) => setMessages(r.data));
  };

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    load();
    api.get(`/listings/${listingId}`).then((r) => setListing(r.data)).catch(() => {});
    // Poll for new messages
    const iv = setInterval(load, 4000);
    return () => clearInterval(iv);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, authLoading, listingId, otherId]);

  useEffect(() => {
    if (messages.length > 0) {
      const other = messages.find((m) => m.sender_id === otherId);
      if (other) setOtherUser({ id: otherId, name: other.sender_name });
    }
  }, [messages, otherId]);

  const send = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    setSending(true);
    try {
      const { data } = await api.post("/chat", { listing_id: listingId, receiver_id: otherId, content: input });
      setMessages((prev) => [...prev, data]);
      setInput("");
    } catch {
      toast({ title: "Failed to send", variant: "destructive" });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-neutral-600 mb-4 hover:text-neutral-900">
        <ChevronLeft className="h-4 w-4" /> Back
      </button>

      {listing && (
        <Link to={`/listing/${listing.id}`} className="flex gap-3 items-center border border-neutral-200 rounded-lg p-3 mb-4 hover:bg-neutral-50">
          <img src={listing.images?.[0]} alt="" className="h-14 w-14 rounded object-cover" />
          <div className="flex-1 min-w-0">
            <div className="font-medium line-clamp-1">{listing.title}</div>
            <div className="text-sm text-neutral-500">${listing.price?.toFixed(2)}</div>
          </div>
        </Link>
      )}

      <div className="border border-neutral-200 rounded-lg bg-neutral-50 h-[520px] flex flex-col">
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {messages.length === 0 && (
            <div className="text-center text-neutral-500 text-sm py-8">No messages yet. Say hi 👋</div>
          )}
          {messages.map((m) => {
            const mine = m.sender_id === user?.id;
            return (
              <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${mine ? "bg-[#FF211F] text-white" : "bg-white border border-neutral-200 text-neutral-900"}`}>
                  <div>{m.content}</div>
                  <div className={`text-[10px] mt-0.5 ${mine ? "text-white/70" : "text-neutral-400"}`}>
                    {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <form onSubmit={send} className="border-t border-neutral-200 bg-white p-3 flex gap-2">
          <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type a message…" />
          <Button type="submit" disabled={sending || !input.trim()} className="bg-[#FF211F] hover:bg-[#e01d1b]">
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </div>
    </div>
  );
};
