import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Trash2, ShoppingBag } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";

const Cart = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { toast } = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) {
      navigate("/login");
      return;
    }
    api.get("/cart").then((r) => setItems(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [user, navigate]);

  const remove = async (id) => {
    await api.delete(`/cart/${id}`);
    setItems((prev) => prev.filter((i) => i.id !== id));
    toast({ title: "Removed from cart" });
  };

  const subtotal = items.reduce((s, i) => s + i.price, 0);
  const shipping = items.reduce((s, i) => s + (i.shipping_paid_by === "buyer" ? 5.99 : 0), 0);

  if (loading) return <div className="max-w-4xl mx-auto px-4 py-8">Loading…</div>;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-6">Your cart</h1>

      {items.length === 0 ? (
        <div className="text-center py-20 border border-dashed rounded-xl">
          <ShoppingBag className="h-12 w-12 mx-auto text-neutral-300 mb-3" />
          <p className="text-neutral-600">Your cart is empty.</p>
          <Link to="/search"><Button className="mt-4 bg-[#FF211F] hover:bg-[#e01d1b]">Start shopping</Button></Link>
        </div>
      ) : (
        <div className="grid lg:grid-cols-[1fr_360px] gap-8">
          <div className="space-y-3">
            {items.map((item) => (
              <div key={item.id} className="flex gap-4 border border-neutral-200 rounded-lg p-3">
                <Link to={`/listing/${item.id}`} className="h-24 w-24 rounded-md overflow-hidden bg-neutral-100 shrink-0">
                  <img src={item.images?.[0]} alt="" className="w-full h-full object-cover" />
                </Link>
                <div className="flex-1 min-w-0">
                  <Link to={`/listing/${item.id}`} className="font-medium text-neutral-900 line-clamp-2 hover:text-[#FF211F]">{item.title}</Link>
                  <div className="text-xs text-neutral-500 mt-1">Sold by {item.seller_name}</div>
                  <div className="text-xs text-neutral-500">
                    {item.shipping_paid_by === "seller" ? "Free shipping" : `Shipping: ${formatPrice(5.99)}`}
                  </div>
                </div>
                <div className="flex flex-col items-end justify-between">
                  <div className="font-semibold">{formatPrice(item.price)}</div>
                  <button onClick={() => remove(item.id)} className="text-neutral-400 hover:text-[#FF211F]">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="border border-neutral-200 rounded-lg p-5 h-fit">
            <h2 className="font-semibold mb-4">Order summary</h2>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span>Subtotal</span><span>{formatPrice(subtotal)}</span></div>
              <div className="flex justify-between"><span>Shipping</span><span>{formatPrice(shipping)}</span></div>
              <div className="flex justify-between"><span>Tax</span><span className="text-neutral-500">Calculated at checkout</span></div>
              <div className="h-px bg-neutral-200 my-2" />
              <div className="flex justify-between font-semibold text-base"><span>Total</span><span>{formatPrice(subtotal + shipping)}</span></div>
            </div>
            <Button
              onClick={() => navigate(`/checkout/${items[0].id}`)}
              className="w-full mt-4 bg-[#FF211F] hover:bg-[#e01d1b] h-11"
            >
              Checkout ({items.length})
            </Button>
            <p className="text-[11px] text-neutral-500 mt-3 text-center">Demo checkout — no real payment is charged.</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default Cart;
