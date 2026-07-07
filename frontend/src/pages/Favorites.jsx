import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { useAuth } from "@/context/AuthContext";
import { Heart } from "lucide-react";

const Favorites = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) { navigate("/login"); return; }
    api.get("/favorites").then((r) => setItems(r.data)).finally(() => setLoading(false));
  }, [user, navigate]);

  const onChange = (id, isFav) => {
    if (!isFav) setItems((prev) => prev.filter((i) => i.id !== id));
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-6">Favorites</h1>
      {loading ? (
        <div>Loading…</div>
      ) : items.length === 0 ? (
        <div className="text-center py-20 border border-dashed rounded-xl">
          <Heart className="h-12 w-12 mx-auto text-neutral-300 mb-3" />
          <p className="text-neutral-600">No favorites yet. Save items you love — they’ll show up here.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {items.map((l) => <ProductCard key={l.id} listing={l} isFavorite onFavoriteChange={onChange} />)}
        </div>
      )}
    </div>
  );
};

export default Favorites;
