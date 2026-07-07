import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import ProductCard from "@/components/ProductCard";
import { Button } from "@/components/ui/button";
import { ArrowRight, ShieldCheck, Truck, MessageCircle } from "lucide-react";
import * as Icons from "lucide-react";

const iconFor = (name) => {
  const key = (name || "package").split("-").map((s, i) => (i === 0 ? s : s[0].toUpperCase() + s.slice(1))).join("");
  const Comp = Icons[key[0].toUpperCase() + key.slice(1)] || Icons.Package;
  return Comp;
};

const Home = () => {
  const [categories, setCategories] = useState([]);
  const [featured, setFeatured] = useState([]);
  const [recent, setRecent] = useState([]);
  const [favIds, setFavIds] = useState(new Set());

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data)).catch(() => {});
    api.get("/listings", { params: { featured: true, limit: 12 } }).then((r) => setFeatured(r.data)).catch(() => {});
    api.get("/listings", { params: { sort: "newest", limit: 18 } }).then((r) => setRecent(r.data)).catch(() => {});
    const token = localStorage.getItem("mercari_token");
    if (token) {
      api.get("/favorites").then((r) => setFavIds(new Set(r.data.map((l) => l.id)))).catch(() => {});
    }
  }, []);

  const onFavChange = (id, isFav) => {
    setFavIds((prev) => {
      const s = new Set(prev);
      if (isFav) s.add(id);
      else s.delete(id);
      return s;
    });
  };

  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-b from-[#FFF3F2] to-white">
        <div className="max-w-7xl mx-auto px-4 py-12 md:py-20 grid md:grid-cols-2 gap-10 items-center">
          <div>
            <span className="inline-block bg-[#FF211F] text-white text-xs font-semibold px-3 py-1 rounded-full mb-4">New · Free shipping over $50</span>
            <h1 className="text-4xl md:text-5xl font-bold text-neutral-900 leading-tight">
              Your marketplace for <span className="text-[#FF211F]">everything</span>
            </h1>
            <p className="mt-4 text-lg text-neutral-600 max-w-lg">
              Buy and sell secondhand fashion, electronics, home goods and more. Millions of items from real people, priced to move.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/search">
                <Button className="bg-[#FF211F] hover:bg-[#e01d1b] h-11 px-6">Start shopping <ArrowRight className="h-4 w-4 ml-2" /></Button>
              </Link>
              <Link to="/sell">
                <Button variant="outline" className="h-11 px-6">Sell in 60 seconds</Button>
              </Link>
            </div>
            <div className="mt-8 flex flex-wrap gap-6 text-sm text-neutral-600">
              <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-[#FF211F]" /> Buyer protection</div>
              <div className="flex items-center gap-2"><Truck className="h-4 w-4 text-[#FF211F]" /> Fast shipping</div>
              <div className="flex items-center gap-2"><MessageCircle className="h-4 w-4 text-[#FF211F]" /> In-app chat</div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {featured.slice(0, 6).map((l, i) => (
              <Link key={l.id} to={`/listing/${l.id}`} className={`rounded-lg overflow-hidden bg-neutral-100 aspect-square ${i === 0 ? "col-span-2 row-span-2" : ""}`}>
                <img src={l.images?.[0]} alt={l.title} className="w-full h-full object-cover hover:scale-105 transition-transform duration-300" />
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Categories */}
      <section className="max-w-7xl mx-auto px-4 py-10">
        <div className="flex items-baseline justify-between mb-6">
          <h2 className="text-2xl font-bold text-neutral-900">Browse categories</h2>
          <Link to="/search" className="text-sm text-[#FF211F] font-medium hover:underline">See all</Link>
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-12 gap-3">
          {categories.map((c) => {
            const Icon = iconFor(c.icon);
            return (
              <Link
                key={c.id}
                to={`/search?category=${c.id}`}
                className="flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-neutral-50 border border-transparent hover:border-neutral-200 transition"
              >
                <div className="h-12 w-12 rounded-full bg-[#FFF3F2] grid place-items-center text-[#FF211F]">
                  <Icon className="h-5 w-5" />
                </div>
                <span className="text-xs text-center text-neutral-700">{c.name}</span>
              </Link>
            );
          })}
        </div>
      </section>

      {/* Featured */}
      <section className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-2xl font-bold text-neutral-900">Featured picks</h2>
          <Link to="/search" className="text-sm text-[#FF211F] font-medium hover:underline">View more</Link>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {featured.map((l) => (
            <ProductCard key={l.id} listing={l} isFavorite={favIds.has(l.id)} onFavoriteChange={onFavChange} />
          ))}
        </div>
      </section>

      {/* Recent */}
      <section className="max-w-7xl mx-auto px-4 py-10">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-2xl font-bold text-neutral-900">Just listed</h2>
          <Link to="/search?sort=newest" className="text-sm text-[#FF211F] font-medium hover:underline">View more</Link>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {recent.map((l) => (
            <ProductCard key={l.id} listing={l} isFavorite={favIds.has(l.id)} onFavoriteChange={onFavChange} />
          ))}
        </div>
      </section>

      {/* Value props */}
      <section className="bg-neutral-50 py-14 mt-8">
        <div className="max-w-7xl mx-auto px-4 grid md:grid-cols-3 gap-6">
          {[
            { icon: ShieldCheck, title: "Buyer protection", body: "Your money is held safely until you confirm delivery. Not what you expected? Get your money back." },
            { icon: Truck, title: "Simple shipping", body: "Print a prepaid label right from the app. Drop off at the nearest carrier and you're done." },
            { icon: MessageCircle, title: "Chat with sellers", body: "Ask questions, negotiate, and coordinate delivery — all inside Mercari." },
          ].map((f, i) => (
            <div key={i} className="bg-white rounded-xl p-6 border border-neutral-200">
              <div className="h-11 w-11 rounded-lg bg-[#FFF3F2] grid place-items-center text-[#FF211F] mb-4">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="font-semibold text-lg text-neutral-900">{f.title}</h3>
              <p className="mt-2 text-sm text-neutral-600">{f.body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default Home;
