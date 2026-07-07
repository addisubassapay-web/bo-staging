import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Star, Edit, Trash2, Package as PackageIcon } from "lucide-react";
import { ReviewOrderCard } from "@/components/Reviews";

const Profile = () => {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "listings";
  const [listings, setListings] = useState([]);
  const [orders, setOrders] = useState([]);
  const [sales, setSales] = useState([]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    api.get("/listings", { params: { seller_id: user.id, status_filter: "" } }).then((r) => setListings(r.data));
    api.get("/orders", { params: { role: "buyer" } }).then((r) => setOrders(r.data));
    api.get("/orders", { params: { role: "seller" } }).then((r) => setSales(r.data));
  }, [user, authLoading, navigate]);

  const deleteListing = async (id) => {
    if (!window.confirm("Delete this listing?")) return;
    await api.delete(`/listings/${id}`);
    setListings((prev) => prev.filter((l) => l.id !== id));
    toast({ title: "Listing deleted" });
  };

  const setStatus = (v) => setParams({ tab: v });

  if (!user) return null;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex items-center gap-4 mb-8">
        <div className="h-20 w-20 rounded-full bg-neutral-200 grid place-items-center text-2xl font-bold text-neutral-700">
          {user.username[0].toUpperCase()}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">{user.username}</h1>
            {user.role === "admin" && <Badge className="bg-[#FF211F] hover:bg-[#FF211F]">Admin</Badge>}
          </div>
          <div className="text-sm text-neutral-500 flex items-center gap-3 mt-1">
            <span className="flex items-center gap-1"><Star className="h-3 w-3 fill-yellow-400 text-yellow-400" /> {user.rating}</span>
            <span>{user.sales_count} sales</span>
            <span>Joined {new Date(user.created_at).toLocaleDateString()}</span>
          </div>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setStatus}>
        <TabsList className="mb-4">
          <TabsTrigger value="listings">My listings ({listings.length})</TabsTrigger>
          <TabsTrigger value="orders">Purchases ({orders.length})</TabsTrigger>
          <TabsTrigger value="sales">Sales ({sales.length})</TabsTrigger>
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
                        <Edit className="h-3 w-3 mr-1" /> View
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
              {orders.map((o) => (
                <div key={o.id} className="border border-neutral-200 rounded-lg">
                  <div className="flex gap-4 p-4">
                    <img src={o.listing_image} alt="" className="h-20 w-20 rounded object-cover bg-neutral-100" />
                    <div className="flex-1">
                      <Link to={`/listing/${o.listing_id}`} className="font-medium hover:text-[#FF211F]">{o.listing_title}</Link>
                      <div className="text-sm text-neutral-500">Seller: {o.seller_name} · {new Date(o.created_at).toLocaleDateString()}</div>
                      <Badge variant="secondary" className="mt-1 capitalize">{o.status}</Badge>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold">{formatPrice(o.amount + o.shipping_fee)}</div>
                      <div className="text-xs text-neutral-500 font-mono">#{o.id.slice(0, 8)}</div>
                    </div>
                  </div>
                  <div className="px-4 pb-4">
                    <ReviewOrderCard order={o} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="sales">
          {sales.length === 0 ? (
            <div className="text-center py-16 border border-dashed rounded-xl text-neutral-600">No sales yet.</div>
          ) : (
            <div className="space-y-3">
              {sales.map((o) => (
                <div key={o.id} className="flex gap-4 border border-neutral-200 rounded-lg p-4">
                  <img src={o.listing_image} alt="" className="h-20 w-20 rounded object-cover bg-neutral-100" />
                  <div className="flex-1">
                    <div className="font-medium">{o.listing_title}</div>
                    <div className="text-sm text-neutral-500">Buyer: {o.buyer_name} · {new Date(o.created_at).toLocaleDateString()}</div>
                    <Badge variant="secondary" className="mt-1 capitalize">{o.status}</Badge>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-green-600">+{formatPrice(o.amount)}</div>
                    <div className="text-xs text-neutral-500 font-mono">#{o.id.slice(0, 8)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Profile;
