import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { Badge } from "@/components/ui/badge";
import { Store as StoreIcon, Award, ShieldCheck } from "lucide-react";

const tierMeta = {
  none: null,
  bronze: { color: "bg-amber-700 text-white hover:bg-amber-700", label: "Bronze verified" },
  silver: { color: "bg-neutral-400 text-white hover:bg-neutral-400", label: "Silver verified" },
  gold: { color: "bg-yellow-500 text-white hover:bg-yellow-500", label: "Gold verified" },
};

const StorePage = () => {
  const { slug } = useParams();
  const [store, setStore] = useState(null);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get(`/stores/${slug}`).then((r) => setStore(r.data)),
      api.get(`/stores/${slug}/listings`).then((r) => setListings(r.data)),
    ]).catch(() => {}).finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <div className="max-w-6xl mx-auto px-4 py-8">Loading…</div>;
  if (!store) return <div className="max-w-6xl mx-auto px-4 py-16 text-center text-neutral-600">Store not found.</div>;

  const tier = tierMeta[store.verified_tier];

  return (
    <div>
      <div
        className="h-40 md:h-56 bg-gradient-to-br from-[#FFF3F2] to-[#FF211F]/10"
        style={store.banner ? { backgroundImage: `url(${store.banner})`, backgroundSize: "cover", backgroundPosition: "center" } : {}}
      />
      <div className="max-w-6xl mx-auto px-4">
        <div className="-mt-10 md:-mt-14 flex items-end gap-4">
          <div className="h-20 w-20 md:h-28 md:w-28 rounded-xl bg-white border-4 border-white shadow-md grid place-items-center overflow-hidden">
            {store.logo ? (
              <img src={store.logo} alt="" className="w-full h-full object-cover" />
            ) : (
              <StoreIcon className="h-10 w-10 text-[#FF211F]" />
            )}
          </div>
          <div className="pb-2">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl md:text-3xl font-bold">{store.name}</h1>
              {tier && <Badge className={tier.color}><Award className="h-3 w-3 mr-1" /> {tier.label}</Badge>}
            </div>
            {store.tagline && <p className="text-neutral-600 text-sm">{store.tagline}</p>}
            <div className="flex gap-4 text-xs text-neutral-500 mt-1">
              <span>{store.total_sales} sales</span>
              <span>{store.followers_count} followers</span>
              <span>Since {new Date(store.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        </div>

        {store.bio && <p className="mt-6 text-neutral-700 leading-relaxed max-w-3xl">{store.bio}</p>}

        <div className="mt-8 flex items-center gap-2 text-sm text-neutral-600">
          <ShieldCheck className="h-4 w-4 text-[#FF211F]" />
          Purchases from this store are protected by Mercari Buyer Protection.
        </div>

        <div className="mt-10">
          <h2 className="text-xl font-bold mb-4">Store listings</h2>
          {listings.length === 0 ? (
            <div className="text-center py-16 border border-dashed rounded-xl text-neutral-500">This store has no active listings yet.</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 pb-10">
              {listings.map((l) => <ProductCard key={l.id} listing={l} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StorePage;
