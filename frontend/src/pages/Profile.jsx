import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Star, Edit, Trash2, Package as PackageIcon, CheckCircle2, Snowflake, Truck, Wallet as WalletIcon, BarChart3, Sparkles, Copy, Check, Share2, MessageSquare, Users, TrendingUp, Settings as SettingsIcon } from "lucide-react";
import { ReviewOrderCard } from "@/components/Reviews";
import { VerificationBadges } from "@/components/VerificationBadges";
import ShippingTracker from "@/components/ShippingTracker";
import DigestCard from "@/components/DigestCard";
import EmailPreferences from "@/components/EmailPreferences";
import AutoConfirmCountdown from "@/components/AutoConfirmCountdown";
import PickupOrderDialog from "@/components/PickupOrderDialog";
import StoreHealthCard from "@/components/StoreHealthCard";
import ReactivationChecklist from "@/components/ReactivationChecklist";
import OrderWalletTimeline from "@/components/OrderWalletTimeline";

const BADGE_STEPS = [
  { key: "new", label: "New", threshold: { sales: 0, rating: 0 } },
  { key: "bronze", label: "Bronze", threshold: { sales: 5, rating: 4.0 } },
  { key: "silver", label: "Silver", threshold: { sales: 20, rating: 4.5 } },
  { key: "gold", label: "Gold", threshold: { sales: 50, rating: 4.7 } },
];

const BadgeProgress = ({ info }) => {
  const currentIdx = Math.max(0, BADGE_STEPS.findIndex((s) => s.key === info.badge));
  const next = BADGE_STEPS[currentIdx + 1];
  const cur = BADGE_STEPS[currentIdx];
  const sales = Number(info.sales_count || 0);
  const rating = Number(info.rating || 0);

  let pct = 100;
  let subline = "You're at the top tier — enjoy your maximum markup.";
  if (next) {
    const salesProgress = Math.min(1, (sales - cur.threshold.sales) / Math.max(1, next.threshold.sales - cur.threshold.sales));
    const ratingProgress = Math.min(1, rating / Math.max(0.01, next.threshold.rating));
    pct = Math.round(Math.min(salesProgress, ratingProgress) * 100);
    const salesNeeded = Math.max(0, next.threshold.sales - sales);
    const ratingNeeded = Math.max(0, +(next.threshold.rating - rating).toFixed(2));
    const parts = [];
    if (salesNeeded > 0) parts.push(`${salesNeeded} more sale${salesNeeded === 1 ? "" : "s"}`);
    if (ratingNeeded > 0) parts.push(`${ratingNeeded.toFixed(1)}★ higher rating`);
    subline = parts.length ? `Unlock ${next.label} with ${parts.join(" + ")}.` : `Ready to unlock ${next.label}!`;
  }

  return (
    <div className="mt-5 rounded-2xl bg-white/15 backdrop-blur-sm ring-1 ring-white/25 p-4" data-testid="badge-progress">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <div className="text-[10px] uppercase tracking-wider font-semibold text-white/90 flex items-center gap-1.5">
          Seller tier · <span className="capitalize">{info.applied === "override" ? "Admin cap" : info.badge}</span>
          <span className="ml-1 bg-white/25 rounded-full px-1.5 h-4 grid place-items-center text-[10px] tabular-nums">Max {info.max_markup_pct}% markup</span>
        </div>
        {next && (
          <div className="text-[11px] text-white/85 tabular-nums" data-testid="badge-progress-pct">{pct}% to <span className="capitalize font-semibold">{next.label}</span></div>
        )}
      </div>
      <div className="h-2 rounded-full bg-black/25 overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-yellow-300 via-orange-200 to-white transition-all duration-500"
          style={{ width: `${pct}%` }}
          data-testid="badge-progress-bar"
        />
      </div>
      <div className="flex justify-between mt-1.5 text-[10px] text-white/80">
        {BADGE_STEPS.map((s, i) => (
          <span key={s.key} className={i === currentIdx ? "font-bold text-white" : ""}>{s.label}</span>
        ))}
      </div>
      <p className="mt-2 text-xs text-white/90" data-testid="badge-progress-hint">{subline}</p>
    </div>
  );
};

const Profile = () => {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [params, setParams] = useSearchParams();
  const pickupOrderIdFromUrl = params.get("pickup");
  // If a pickup deep-link is present, force the Sales tab where the CTA
  // renders (older notification/email links used tab=orders which hid it).
  const tab = pickupOrderIdFromUrl ? "sales" : (params.get("tab") || "listings");
  const [pickupTargetId, setPickupTargetId] = useState(null);

  const [listings, setListings] = useState([]);
  const [orders, setOrders] = useState([]);
  const [sales, setSales] = useState([]);
  const [wallet, setWallet] = useState({ balance: 0, frozen_balance: 0 });
  const [resellInfo, setResellInfo] = useState(null);
  const [pushStats, setPushStats] = useState(null);
  const [copied, setCopied] = useState(false);

  // Deep-link: /profile?tab=orders&pickup=<orderId> auto-opens the pickup
  // modal for that order. Notification/email CTAs land here.
  useEffect(() => {
    if (pickupOrderIdFromUrl) {
      setPickupTargetId(pickupOrderIdFromUrl);
    }
  }, [pickupOrderIdFromUrl]);

  // Scroll the target row into view once sales are loaded.
  useEffect(() => {
    if (!pickupTargetId || !sales?.length) return;
    const el = document.querySelector(`[data-testid="pickup-cta-${pickupTargetId}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [pickupTargetId, sales]);

  const clearPickupDeepLink = React.useCallback(() => {
    // Strip ?pickup=... so refresh doesn't re-open the modal. Also force
    // tab=sales because the deep-link may have arrived with the legacy
    // tab=orders value (old notification/email link format) — if we let
    // the URL fall back to that, the Sales tab (and the mounted dialog)
    // would unmount right after auto-open.
    const next = new URLSearchParams(params);
    next.delete("pickup");
    next.set("tab", "sales");
    setParams(next, { replace: true });
    setPickupTargetId(null);
  }, [params, setParams]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/listings", { params: { seller_id: user.id, status_filter: "" } }).then((r) => setListings(r.data));
    api.get("/orders", { params: { role: "buyer" } }).then((r) => setOrders(r.data));
    api.get("/orders", { params: { role: "seller" } }).then((r) => setSales(r.data));
    api.get("/wallet").then((r) => setWallet({ balance: r.data.balance, frozen_balance: r.data.frozen_balance || 0 })).catch(() => {});
    api.get("/seller/resell-info").then((r) => setResellInfo(r.data)).catch(() => {});
    api.get("/seller/push-stats").then((r) => setPushStats(r.data)).catch(() => {});
  }, [user, authLoading, navigate]);

  const deleteListing = async (id) => {
    if (!window.confirm("Delete this listing?")) return;
    await api.delete(`/listings/${id}`);
    setListings((prev) => prev.filter((l) => l.id !== id));
    toast({ title: "Listing deleted" });
  };

  const confirmDelivery = async (orderId) => {
    if (!window.confirm("Confirm you received this item? This will release the seller's payment.")) return;
    try {
      const { data } = await api.post(`/orders/${orderId}/confirm-delivery`);
      setOrders((prev) => prev.map((o) => (o.id === orderId ? data : o)));
      toast({ title: "Delivery confirmed", description: "Seller has been paid out." });
    } catch (e) {
      toast({ title: "Could not confirm", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    }
  };

  const setStatus = (v) => setParams({ tab: v });

  const copyReferral = async () => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/register?ref=${user.referral_code}`);
      setCopied(true);
      toast({ title: "Referral link copied!", description: "Share it and earn on every sale from your invites." });
      setTimeout(() => setCopied(false), 2000);
    } catch (e) { console.warn("[referral] copy failed:", e); }
  };

  const shareProfile = async () => {
    const url = `${window.location.origin}/store/${user.username}`;
    const text = `Check out ${user.username}'s store on Mercari-Smarthub`;
    if (navigator.share) {
      try { await navigator.share({ title: text, url }); }
      catch (e) { if (e?.name !== "AbortError") console.warn("[share] failed:", e); }
    } else {
      try { await navigator.clipboard.writeText(url); toast({ title: "Store link copied" }); }
      catch (e) { console.warn("[share] clipboard failed:", e); }
    }
  };

  if (!user) return null;

  // Derived seller metrics for the hero
  const activeListings = listings.filter((l) => l.status === "active").length;
  const soldListings = listings.filter((l) => l.status === "sold").length;
  const totalEarnings = sales.reduce((s, o) => s + (Number(o.seller_earnings) || Number(o.amount) || 0), 0);
  const memberYear = new Date(user.created_at).getFullYear();

  return (
    <div className="max-w-6xl mx-auto px-4 py-8" data-testid="profile-page">
      <ReactivationChecklist />
      {/* Modern gradient hero */}
      <div className="relative rounded-3xl overflow-hidden mb-8 shadow-[0_20px_50px_-25px_rgba(255,33,31,0.35)]" data-testid="profile-hero">
        {/* Decorative gradient background */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#FF7A18] via-[#FF5722] to-[#FF211F]" />
        <div className="absolute -top-24 -right-24 h-72 w-72 rounded-full bg-white/20 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-20 -left-16 h-64 w-64 rounded-full bg-black/25 blur-3xl pointer-events-none" />
        {/* Subtle grid pattern */}
        <div
          className="absolute inset-0 opacity-[0.08] pointer-events-none"
          style={{
            backgroundImage: "linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />

        <div className="relative p-5 sm:p-8 text-white">
          <div className="flex items-start gap-4 sm:gap-6 flex-wrap">
            {/* Avatar with ring */}
            <div className="relative">
              <div className="h-20 w-20 sm:h-24 sm:w-24 rounded-2xl bg-white text-[#FF211F] grid place-items-center text-3xl sm:text-4xl font-extrabold shadow-xl ring-4 ring-white/40" data-testid="profile-avatar">
                {user.username[0].toUpperCase()}
              </div>
              {user.role === "admin" && (
                <span className="absolute -bottom-2 -right-2 h-6 w-6 rounded-full bg-yellow-400 text-yellow-900 grid place-items-center text-[11px] font-black ring-2 ring-white" title="Admin">
                  ★
                </span>
              )}
            </div>

            {/* Identity + chips */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight" data-testid="profile-username">{user.username}</h1>
                {user.role === "admin" && (
                  <span className="text-[10px] uppercase tracking-wider font-bold bg-white/25 backdrop-blur-sm px-2 py-1 rounded-full ring-1 ring-white/30">Admin</span>
                )}
                <span className="hidden sm:inline-flex items-center gap-1 text-[11px] bg-white/15 backdrop-blur-sm px-2 py-0.5 rounded-full ring-1 ring-white/30">
                  <Sparkles className="h-3 w-3" /> Member since {memberYear}
                </span>
              </div>
              <div className="mt-1"><VerificationBadges user={user} /></div>
              <div className="text-sm text-white/90 flex items-center gap-3 mt-2 flex-wrap">
                <span className="inline-flex items-center gap-1"><Star className="h-3.5 w-3.5 fill-yellow-300 text-yellow-300" /> {user.rating}</span>
                <span>·</span>
                <span className="tabular-nums">{user.sales_count} sales</span>
                {user.email_verified && (
                  <>
                    <span>·</span>
                    <span className="inline-flex items-center gap-1 text-emerald-100"><CheckCircle2 className="h-3.5 w-3.5" /> Verified email</span>
                  </>
                )}
              </div>

              {/* Quick action buttons */}
              <div className="mt-4 flex items-center gap-2 flex-wrap" data-testid="profile-quick-actions">
                <Link to="/sell">
                  <Button className="h-9 rounded-full bg-white text-[#FF211F] hover:bg-neutral-100 font-semibold gap-1.5 px-4 shadow-sm" data-testid="profile-cta-sell">
                    <PackageIcon className="h-4 w-4" /> Sell an item
                  </Button>
                </Link>
                <Link to="/seller/payouts">
                  <Button variant="outline" className="h-9 rounded-full bg-white/10 backdrop-blur-sm border-white/40 text-white hover:bg-white hover:text-[#FF211F] font-semibold gap-1.5 px-4" data-testid="profile-cta-payouts">
                    <BarChart3 className="h-4 w-4" /> Payout dashboard
                  </Button>
                </Link>
                <Link to="/wallet">
                  <Button variant="outline" className="h-9 rounded-full bg-white/10 backdrop-blur-sm border-white/40 text-white hover:bg-white hover:text-[#FF211F] font-semibold gap-1.5 px-4" data-testid="profile-cta-wallet">
                    <WalletIcon className="h-4 w-4" /> Wallet
                  </Button>
                </Link>
                <button
                  onClick={shareProfile}
                  className="h-9 rounded-full bg-white/10 backdrop-blur-sm border border-white/40 text-white hover:bg-white/20 font-semibold gap-1.5 px-3 inline-flex items-center transition"
                  data-testid="profile-cta-share"
                >
                  <Share2 className="h-4 w-4" /> Share
                </button>
              </div>
            </div>
          </div>

          {/* Stat cards row */}
          <div className="mt-6 sm:mt-8 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-2xl bg-white/15 backdrop-blur-sm ring-1 ring-white/25 p-4" data-testid="stat-available">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-semibold text-white/90">
                <WalletIcon className="h-3 w-3" /> Available
              </div>
              <div className="mt-1.5 text-xl sm:text-2xl font-extrabold tabular-nums">{formatPrice(wallet.balance)}</div>
              <div className="text-[11px] text-white/80 mt-0.5">Ready to withdraw</div>
            </div>
            <div className="rounded-2xl bg-amber-400/25 backdrop-blur-sm ring-1 ring-amber-200/40 p-4" data-testid="stat-frozen">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-semibold text-amber-50">
                <Snowflake className="h-3 w-3" /> Frozen
              </div>
              <div className="mt-1.5 text-xl sm:text-2xl font-extrabold tabular-nums">{formatPrice(wallet.frozen_balance)}</div>
              <div className="text-[11px] text-amber-50/90 mt-0.5">Releases on delivery</div>
            </div>
            <div className="rounded-2xl bg-emerald-400/25 backdrop-blur-sm ring-1 ring-emerald-200/40 p-4" data-testid="stat-earnings">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-semibold text-emerald-50">
                <TrendingUp className="h-3 w-3" /> Lifetime sales
              </div>
              <div className="mt-1.5 text-xl sm:text-2xl font-extrabold tabular-nums">{formatPrice(totalEarnings)}</div>
              <div className="text-[11px] text-emerald-50/90 mt-0.5">{sales.length} order{sales.length === 1 ? "" : "s"}</div>
            </div>
            <div className="rounded-2xl bg-white/15 backdrop-blur-sm ring-1 ring-white/25 p-4" data-testid="stat-listings">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-semibold text-white/90">
                <PackageIcon className="h-3 w-3" /> Listings
              </div>
              <div className="mt-1.5 text-xl sm:text-2xl font-extrabold tabular-nums">{activeListings}</div>
              <div className="text-[11px] text-white/80 mt-0.5">{soldListings} sold · {listings.length} total</div>
            </div>
          </div>

          {/* Badge tier progress */}
          {resellInfo && (
            <BadgeProgress info={resellInfo} />
          )}

          {/* Referral code strip */}
          {user.referral_code && (
            <div className="mt-5 rounded-2xl bg-black/25 backdrop-blur-sm ring-1 ring-white/20 p-3 flex items-center gap-3 flex-wrap" data-testid="referral-strip">
              <div className="h-8 w-8 shrink-0 rounded-lg bg-white/20 grid place-items-center">
                <Users className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[10px] uppercase tracking-wider font-semibold text-white/80">Your referral code</div>
                <div className="font-mono font-bold text-lg tracking-widest" data-testid="referral-code">{user.referral_code}</div>
              </div>
              <button
                onClick={copyReferral}
                className={`h-9 px-4 rounded-full font-semibold text-sm transition inline-flex items-center gap-1.5 ${copied ? "bg-emerald-400 text-emerald-900" : "bg-white text-[#FF211F] hover:bg-neutral-100"}`}
                data-testid="referral-copy-btn"
              >
                {copied ? <><Check className="h-4 w-4" /> Copied!</> : <><Copy className="h-4 w-4" /> Copy link</>}
              </button>
              <Link to="/referrals" className="text-xs text-white/90 hover:text-white underline whitespace-nowrap">See referral earnings →</Link>
            </div>
          )}
        </div>
      </div>

      {/* Digest card in its own row (previously nested in hero) */}
      <div className="mb-6"><DigestCard /></div>

      {/* Storefront Push stats widget — visible for any approved seller */}
      {pushStats && (user?.seller_status === "approved" || user?.role === "admin" || pushStats.share_attributed_sales > 0 || pushStats.bonuses_count > 0) && (
        <div className="mb-6 rounded-2xl border border-neutral-200 bg-white p-4 sm:p-5 relative overflow-hidden" data-testid="push-stats-widget">
          <div className="pointer-events-none absolute -top-10 -right-10 h-40 w-40 rounded-full bg-orange-100/70 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-14 -left-10 h-40 w-40 rounded-full bg-purple-100/70 blur-3xl" />
          <div className="relative flex items-start justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-[#FF7A18] to-[#FF211F] grid place-items-center shrink-0 shadow-sm">
                <Share2 className="h-5 w-5 text-white" />
              </div>
              <div>
                <h3 className="font-bold text-neutral-900">Storefront Push</h3>
                <p className="text-xs text-neutral-500">Share links convert followers into sales.</p>
              </div>
            </div>
            {pushStats.eligible_for_next_bonus && pushStats.push_reward_amount > 0 && (
              <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2.5 py-1" data-testid="push-eligible-chip">
                +${pushStats.push_reward_amount.toFixed(0)} first-sale bonus available
              </span>
            )}
          </div>

          <div className="relative mt-4 grid grid-cols-3 gap-2 sm:gap-3">
            <div className="rounded-xl border border-neutral-200 bg-neutral-50 p-3 text-center" data-testid="push-stat-reach">
              <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">Reach</div>
              <div className="text-xl sm:text-2xl font-extrabold text-neutral-900 tabular-nums mt-0.5">{pushStats.share_reach_followers.toLocaleString()}</div>
              <div className="text-[10px] text-neutral-500">followers</div>
            </div>
            <div className="rounded-xl border border-[#FF7A18]/30 bg-[#FFF3F2] p-3 text-center" data-testid="push-stat-sales">
              <div className="text-[10px] uppercase tracking-wider text-[#FF211F] font-semibold">Sales</div>
              <div className="text-xl sm:text-2xl font-extrabold text-neutral-900 tabular-nums mt-0.5">{pushStats.share_attributed_sales.toLocaleString()}</div>
              <div className="text-[10px] text-neutral-500">from shares</div>
            </div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-center" data-testid="push-stat-bonus">
              <div className="text-[10px] uppercase tracking-wider text-emerald-700 font-semibold">Bonuses</div>
              <div className="text-xl sm:text-2xl font-extrabold text-emerald-700 tabular-nums mt-0.5">${pushStats.bonuses_total.toFixed(2)}</div>
              <div className="text-[10px] text-emerald-700">{pushStats.bonuses_count} paid</div>
            </div>
          </div>

          {pushStats.share_attributed_earnings > 0 && (
            <div className="relative mt-3 text-xs text-neutral-600 flex justify-between items-center flex-wrap gap-2">
              <span>Earnings from share-attributed orders: <b className="text-neutral-900 tabular-nums">${pushStats.share_attributed_earnings.toFixed(2)}</b></span>
              {pushStats.last_share_sale_at && (
                <span className="text-neutral-400 text-[11px]">last on {new Date(pushStats.last_share_sale_at).toLocaleDateString()}</span>
              )}
            </div>
          )}

          <p className="relative mt-3 text-[11px] text-neutral-500 leading-relaxed">
            Every share adds <code className="bg-neutral-100 px-1 rounded text-[10px]">?ref=push</code> automatically. Your first share-attributed sale earns a <b>${pushStats.push_reward_amount.toFixed(0)} bonus</b>.
          </p>
        </div>
      )}

      <Tabs value={tab} onValueChange={setStatus}>
        <TabsList className="mb-4">
          <TabsTrigger value="listings">My listings ({listings.length})</TabsTrigger>
          <TabsTrigger value="orders">Purchases ({orders.length})</TabsTrigger>
          <TabsTrigger value="sales">Sales ({sales.length})</TabsTrigger>
          <TabsTrigger value="settings" data-testid="profile-tab-settings">
            <SettingsIcon className="h-3.5 w-3.5 mr-1.5" /> Settings
          </TabsTrigger>
        </TabsList>

        <TabsContent value="listings">
          {listings.length === 0 ? (
            <div className="text-center py-16 border border-dashed rounded-xl">
              <PackageIcon className="h-10 w-10 mx-auto text-neutral-300 mb-2" />
              <p className="text-neutral-600">No listings yet.</p>
              <Link to="/sell"><Button className="mt-4 bg-[#FF211F] hover:bg-[#e01d1b]">List your first item</Button></Link>
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {listings.map((l) => (
                <div key={l.id} className="border border-neutral-200 rounded-lg overflow-hidden">
                  <Link to={`/listing/${l.id}`}>
                    <div className="aspect-square bg-neutral-100 relative">
                      <img src={l.images?.[0]} alt="" className="w-full h-full object-cover" />
                      {l.status !== "active" && (
                        <span className="absolute top-2 left-2 bg-black/70 text-white text-xs px-2 py-0.5 rounded uppercase">{l.status}</span>
                      )}
                    </div>
                  </Link>
                  <div className="p-3">
                    <div className="font-medium line-clamp-1">{l.title}</div>
                    <div className="flex items-center justify-between mt-1">
                      <span className="font-semibold">{formatPrice(l.price)}</span>
                      <span className="text-xs text-neutral-500">{l.views_count} views · {l.likes_count} ♥</span>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <Button variant="outline" size="sm" className="flex-1" onClick={() => navigate(`/listing/${l.id}`)}>
                        View
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => navigate(`/listing/${l.id}/edit`)} data-testid={`edit-listing-${l.id}`}>
                        <Edit className="h-3 w-3" />
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => deleteListing(l.id)}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="orders">
          {orders.length === 0 ? (
            <div className="text-center py-16 border border-dashed rounded-xl text-neutral-600">No purchases yet.</div>
          ) : (
            <div className="space-y-3">
              {orders.map((o) => {
                const eta = o.estimated_delivery_at ? new Date(o.estimated_delivery_at) : null;
                const daysLeft = eta ? Math.max(0, Math.ceil((eta - new Date()) / (1000 * 60 * 60 * 24))) : null;
                const canConfirm = !o.funds_released && o.status !== "cancelled";
                return (
                <div key={o.id} className="border border-neutral-200 rounded-lg" data-testid={`buyer-order-${o.id}`}>
                  <div className="flex gap-4 p-4">
                    <img src={o.listing_image} alt="" className="h-20 w-20 rounded object-cover bg-neutral-100" />
                    <div className="flex-1">
                      <Link to={`/listing/${o.listing_id}`} className="font-medium hover:text-[#FF211F]">{o.listing_title}</Link>
                      <div className="text-sm text-neutral-500">Seller: {o.seller_name} · {new Date(o.created_at).toLocaleDateString()}</div>
                      <div className="mt-1 flex items-center gap-2 flex-wrap">
                        <Badge variant="secondary" className="capitalize">{o.status}</Badge>
                        {eta && !o.funds_released && (
                          <span className="inline-flex items-center gap-1 text-xs text-neutral-600 bg-neutral-100 rounded-full px-2 py-0.5" data-testid={`order-eta-${o.id}`}>
                            <Truck className="h-3 w-3" />
                            {daysLeft > 0 ? `Arrives in ~${daysLeft} day${daysLeft === 1 ? "" : "s"}` : `Expected any day now`}
                          </span>
                        )}
                        {o.funds_released && (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 rounded-full px-2 py-0.5">
                            <CheckCircle2 className="h-3 w-3" /> Delivered
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold">{formatPrice(o.amount + o.shipping_fee)}</div>
                      <div className="text-xs text-neutral-500 font-mono">#{o.id.slice(0, 8)}</div>
                    </div>
                  </div>
                  <div className="px-4 pb-4">
                    <ShippingTracker orderId={o.id} />
                    {canConfirm && (
                      <div className="mt-3 flex items-center justify-between gap-3 flex-wrap bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                        <div className="text-xs text-emerald-800">
                          Received your item? Confirming releases the seller&apos;s frozen payment.
                        </div>
                        <Button
                          size="sm"
                          onClick={() => confirmDelivery(o.id)}
                          className="bg-emerald-600 hover:bg-emerald-700 rounded-full"
                          data-testid={`confirm-delivery-${o.id}`}
                        >
                          <CheckCircle2 className="h-4 w-4 mr-1.5" /> Confirm delivery
                        </Button>
                      </div>
                    )}
                    <ReviewOrderCard order={o} />
                    <OrderWalletTimeline orderId={o.id} />
                  </div>
                </div>
              );})}
            </div>
          )}
        </TabsContent>

        <TabsContent value="sales">
          <div className="mb-4">
            <StoreHealthCard />
          </div>
          {sales.length === 0 ? (
            <div className="text-center py-16 border border-dashed rounded-xl text-neutral-600">No sales yet.</div>
          ) : (
            <div className="space-y-3">
              {sales.map((o) => (
                <div key={o.id} className="border border-neutral-200 rounded-lg p-4" data-testid={`seller-order-${o.id}`}>
                  <div className="flex gap-4">
                    <img src={o.listing_image} alt="" className="h-20 w-20 rounded object-cover bg-neutral-100" />
                    <div className="flex-1">
                      <div className="font-medium">{o.listing_title}</div>
                      <div className="text-sm text-neutral-500">Buyer: {o.buyer_name} · {new Date(o.created_at).toLocaleDateString()}</div>
                      <div className="mt-1 flex items-center gap-2 flex-wrap">
                        <Badge variant="secondary" className="capitalize">{o.status}</Badge>
                        {!o.funds_released && (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5" data-testid={`seller-frozen-${o.id}`}>
                            <Snowflake className="h-3 w-3" /> Funds frozen · releases on delivery
                          </span>
                        )}
                        <AutoConfirmCountdown order={o} />
                        {o.funds_released && (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 rounded-full px-2 py-0.5">
                            <CheckCircle2 className="h-3 w-3" /> Paid out
                          </span>
                        )}
                        {o.reinvest_funded_amount > 0 && (
                          <span
                            className="inline-flex items-center gap-1 text-xs font-semibold text-blue-800 bg-gradient-to-r from-sky-100 to-blue-100 border border-blue-200 rounded-full px-2 py-0.5"
                            title={`$${o.reinvest_funded_amount.toFixed(2)} was reinvested from your frozen escrow to cover wholesale on this order.`}
                            data-testid={`reinvest-pill-${o.id}`}
                          >
                            <Sparkles className="h-3 w-3" /> Reinvested from frozen · {formatPrice(o.reinvest_funded_amount)}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-semibold ${o.funds_released ? "text-green-600" : "text-amber-600"}`}>+{formatPrice(o.seller_earnings || o.amount)}</div>
                      <div className="text-xs text-neutral-500 font-mono">#{o.id.slice(0, 8)}</div>
                    </div>
                  </div>
                  <ShippingTracker orderId={o.id} />
                  <OrderWalletTimeline orderId={o.id} />
                  {o.fulfillment_status === "pending_pickup" && (
                    <div
                      className="mt-3 flex items-center justify-between gap-3 flex-wrap bg-red-50 border border-red-200 rounded-lg px-3 py-2"
                      data-testid={`pickup-cta-${o.id}`}
                    >
                      <div className="text-xs text-red-900">
                        <span className="font-semibold">New order awaiting pickup.</span>{" "}
                        Pay the source cost{" "}
                        <span className="font-semibold">{formatPrice(o.reseller_wholesale_cost || 0)}</span>{" "}
                        to start delivery. Auto-cancels if not accepted in time.
                      </div>
                      <PickupOrderDialog
                        orderId={o.id}
                        autoOpen={pickupTargetId === o.id}
                        onAutoOpenConsumed={clearPickupDeepLink}
                        onPicked={() => {
                          // Refresh sales after successful pickup
                          api.get("/orders", { params: { role: "seller" } }).then((r) => setSales(r.data));
                        }}
                      />
                    </div>
                  )}
                  {o.fulfillment_status === "auto_cancelled" && (
                    <div
                      className="mt-3 bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-xs text-neutral-600"
                      data-testid={`pickup-cancelled-${o.id}`}
                    >
                      This order was auto-cancelled because you didn&apos;t accept within the pickup window. The buyer has been refunded.
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="settings">
          <EmailPreferences />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Profile;
