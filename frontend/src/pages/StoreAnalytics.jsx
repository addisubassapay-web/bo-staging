import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { BarChart3, Eye, Heart, ShoppingBag, TrendingUp, Star, Package } from "lucide-react";

const Stat = ({ icon: Icon, label, value, tone = "neutral" }) => (
  <div className="bg-white border border-neutral-200 rounded-lg p-5">
    <div className="flex items-center gap-2 text-neutral-500 text-sm">
      <Icon className="h-4 w-4" /> {label}
    </div>
    <div className={`text-2xl font-bold mt-1 ${tone === "good" ? "text-green-600" : ""}`}>{value}</div>
  </div>
);

const StoreAnalytics = () => {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/store/analytics").then((r) => setData(r.data));
  }, [user, authLoading, navigate]);

  if (!data) return <div className="max-w-6xl mx-auto px-4 py-8">Loading…</div>;

  const maxRevenue = Math.max(...data.sales_last_30d.map((d) => d.revenue), 1);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex items-center gap-2 mb-6">
        <BarChart3 className="h-6 w-6 text-[#FF211F]" />
        <h1 className="text-3xl font-bold">Store analytics</h1>
      </div>
      <p className="text-neutral-600 mb-6">Track your store’s performance in one place.</p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Stat icon={Package} label="Active listings" value={data.active_listings} />
        <Stat icon={ShoppingBag} label="Sold listings" value={data.sold_listings} />
        <Stat icon={Eye} label="Total views" value={data.total_views} />
        <Stat icon={Heart} label="Total likes" value={data.total_likes} />
        <Stat icon={ShoppingBag} label="Orders" value={data.orders} />
        <Stat icon={TrendingUp} label="Revenue" value={formatPrice(data.revenue)} tone="good" />
        <Stat icon={TrendingUp} label="Earnings" value={formatPrice(data.earnings)} tone="good" />
        <Stat icon={Star} label="Avg rating" value={data.avg_rating ? `${data.avg_rating} (${data.review_count})` : "—"} />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white border border-neutral-200 rounded-lg p-5">
          <h3 className="font-semibold mb-4">Sales — last 30 days</h3>
          {data.sales_last_30d.length === 0 ? (
            <div className="text-sm text-neutral-500 py-8 text-center">No sales in the last 30 days.</div>
          ) : (
            <div className="space-y-1">
              {data.sales_last_30d.map((d) => (
                <div key={d.date} className="flex items-center gap-2 text-sm">
                  <div className="w-20 text-neutral-500 text-xs">{d.date.slice(5)}</div>
                  <div className="flex-1 bg-neutral-100 rounded h-6 overflow-hidden">
                    <div className="h-full bg-[#FF211F]" style={{ width: `${(d.revenue / maxRevenue) * 100}%` }} />
                  </div>
                  <div className="w-20 text-right font-medium">{formatPrice(d.revenue)}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="bg-white border border-neutral-200 rounded-lg p-5">
          <h3 className="font-semibold mb-4">Top listings by views</h3>
          {data.top_listings.length === 0 ? (
            <div className="text-sm text-neutral-500 py-8 text-center">No listings yet.</div>
          ) : (
            <div className="space-y-2">
              {data.top_listings.map((l) => (
                <div key={l.id} className="flex items-center gap-3">
                  <img src={l.images?.[0]} alt="" className="h-12 w-12 rounded object-cover bg-neutral-100" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium line-clamp-1">{l.title}</div>
                    <div className="text-xs text-neutral-500">{formatPrice(l.price)}</div>
                  </div>
                  <div className="text-right text-sm">
                    <div className="flex items-center gap-1 text-neutral-600"><Eye className="h-3 w-3" /> {l.views_count}</div>
                    <div className="flex items-center gap-1 text-neutral-500 text-xs"><Heart className="h-3 w-3" /> {l.likes_count}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StoreAnalytics;
