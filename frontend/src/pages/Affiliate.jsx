import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Link as LinkIcon, Copy, TrendingUp, MousePointerClick, DollarSign, ShoppingBag } from "lucide-react";

const StatBox = ({ icon: Icon, label, value, tone = "neutral" }) => (
  <div className="bg-white border border-neutral-200 rounded-lg p-5">
    <div className="flex items-center gap-2 text-neutral-500 text-sm">
      <Icon className="h-4 w-4" /> {label}
    </div>
    <div className={`text-2xl font-bold mt-1 ${tone === "good" ? "text-green-600" : ""}`}>{value}</div>
  </div>
);

const Affiliate = () => {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [stats, setStats] = useState(null);
  const [links, setLinks] = useState([]);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/affiliate/stats").then((r) => setStats(r.data));
    api.get("/affiliate/links").then((r) => setLinks(r.data));
  }, [user, loading, navigate]);

  const shareUrl = (code) => `${window.location.origin}/r/${code}`;

  const copy = (text) => {
    navigator.clipboard.writeText(text);
    toast({ title: "Copied to clipboard" });
  };

  if (!stats) return <div className="max-w-5xl mx-auto px-4 py-8">Loading…</div>;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="flex items-center gap-2 mb-6">
        <LinkIcon className="h-6 w-6 text-[#FF211F]" />
        <h1 className="text-3xl font-bold">Affiliate program</h1>
      </div>
      <p className="text-neutral-600 mb-6">Earn a commission every time someone buys through your link. No inventory, no fulfillment — just share.</p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatBox icon={LinkIcon} label="Active links" value={stats.links} />
        <StatBox icon={MousePointerClick} label="Clicks" value={stats.clicks} />
        <StatBox icon={ShoppingBag} label="Conversions" value={stats.conversions} />
        <StatBox icon={DollarSign} label="Earnings" value={formatPrice(stats.earnings)} tone="good" />
      </div>

      <div className="bg-[#FFF3F2] border border-[#FF211F]/20 rounded-lg p-5 mb-8">
        <h3 className="font-semibold flex items-center gap-2"><TrendingUp className="h-4 w-4 text-[#FF211F]" /> How it works</h3>
        <ol className="text-sm text-neutral-700 mt-2 space-y-1 list-decimal list-inside">
          <li>Browse any listing and click “Share as affiliate” on the product page.</li>
          <li>Copy your unique tracking link and share it anywhere — social, blog, email.</li>
          <li>When someone buys through your link, you earn a commission — credited to your wallet.</li>
        </ol>
      </div>

      <h2 className="font-semibold mb-3">My affiliate links</h2>
      {links.length === 0 ? (
        <div className="text-center py-10 border border-dashed rounded-xl">
          <p className="text-neutral-600">No links yet.</p>
          <Link to="/search"><Button className="mt-3 bg-[#FF211F] hover:bg-[#e01d1b]">Browse products</Button></Link>
        </div>
      ) : (
        <div className="space-y-2">
          {links.map((l) => (
            <div key={l.id} className="border border-neutral-200 rounded-lg p-4 flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-xs text-neutral-500">
                  {l.listing_id && (
                    <Link to={`/listing/${l.listing_id}`} className="hover:text-[#FF211F]">View product →</Link>
                  )}
                  {l.store_id && <span>Store link</span>}
                </div>
                <div className="font-mono text-sm text-neutral-800 truncate mt-1">{shareUrl(l.code)}</div>
                <div className="flex gap-4 mt-2 text-xs text-neutral-500">
                  <span>{l.clicks} clicks</span>
                  <span>{l.conversions} conversions</span>
                  <span className="text-green-600 font-medium">{formatPrice(l.earnings)} earned</span>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => copy(shareUrl(l.code))}>
                <Copy className="h-4 w-4 mr-1" /> Copy
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Affiliate;
