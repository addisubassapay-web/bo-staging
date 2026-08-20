import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Users, Copy, Share2, Award } from "lucide-react";

const Referrals = () => {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [data, setData] = useState(null);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/referrals/me").then((r) => setData(r.data));
  }, [user, loading, navigate]);

  if (!data) return <div className="max-w-4xl mx-auto px-4 py-8">Loading…</div>;

  const referralLink = `${window.location.origin}/register?ref=${data.referral_code}`;

  const copy = (text) => {
    navigator.clipboard.writeText(text);
    toast({ title: "Copied to clipboard" });
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center gap-2 mb-6">
        <Users className="h-6 w-6 text-[#FF211F]" />
        <h1 className="text-3xl font-bold">Referral program</h1>
      </div>
      <p className="text-neutral-600 mb-6">Invite friends to Merchari-global and earn from their activity across 3 levels of your network.</p>

      <div className="bg-gradient-to-br from-[#FF211F] to-[#c81816] text-white rounded-xl p-6 mb-8">
        <div className="text-sm opacity-90">Your referral code</div>
        <div className="text-4xl font-bold font-mono mt-2 tracking-wider">{data.referral_code}</div>
        <div className="mt-4 flex flex-col sm:flex-row gap-2">
          <div className="flex-1 bg-white/10 border border-white/20 rounded px-3 py-2 text-sm font-mono truncate">
            {referralLink}
          </div>
          <Button variant="secondary" className="bg-white text-[#FF211F] hover:bg-neutral-100" onClick={() => copy(referralLink)}>
            <Copy className="h-4 w-4 mr-1" /> Copy link
          </Button>
        </div>
        <div className="mt-4 text-sm opacity-90">
          Total earned from referrals: <span className="font-bold">{formatPrice(data.total_referral_earnings)}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { level: 1, count: data.counts.l1, pct: "3%" },
          { level: 2, count: data.counts.l2, pct: "1%" },
          { level: 3, count: data.counts.l3, pct: "0.5%" },
        ].map((tier) => (
          <div key={tier.level} className="bg-white border border-neutral-200 rounded-lg p-5 text-center">
            <Award className="h-6 w-6 mx-auto text-[#FF211F]" />
            <div className="text-xs text-neutral-500 uppercase mt-2">Level {tier.level}</div>
            <div className="text-3xl font-bold mt-1">{tier.count}</div>
            <div className="text-xs text-neutral-500 mt-1">{tier.pct} of platform fees</div>
          </div>
        ))}
      </div>

      <div className="space-y-6">
        {[
          { key: "l1", label: "Direct referrals (Level 1)" },
          { key: "l2", label: "Second tier (Level 2)" },
          { key: "l3", label: "Third tier (Level 3)" },
        ].map((tier) => (
          <div key={tier.key}>
            <h3 className="font-semibold mb-2">{tier.label}</h3>
            {data.levels[tier.key].length === 0 ? (
              <div className="text-sm text-neutral-500 border border-dashed rounded-lg p-4">No referrals at this level yet.</div>
            ) : (
              <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-2">
                {data.levels[tier.key].map((u) => (
                  <div key={u.id} className="flex items-center gap-2 border border-neutral-200 rounded-lg p-2">
                    <div className="h-8 w-8 rounded-full bg-neutral-200 grid place-items-center text-xs font-semibold">{u.username[0].toUpperCase()}</div>
                    <div>
                      <div className="font-medium text-sm">{u.username}</div>
                      <div className="text-xs text-neutral-500">Joined {new Date(u.created_at).toLocaleDateString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default Referrals;
