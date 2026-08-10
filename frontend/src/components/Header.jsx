import React, { useEffect, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Search, ShoppingCart, User, LogOut, Package, Settings, Store, Wallet, Link as LinkIcon, Users, MessageSquare, BarChart3, ShieldCheck, Heart, ChevronDown, Sun, Moon, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import api from "@/lib/api";
import NotificationsBell from "@/components/NotificationsBell";
import LiveSyncBadge from "@/components/LiveSyncBadge";
import SearchAutocomplete from "@/components/SearchAutocomplete";

const TopStrip = ({ user, onLogout }) => (
  <div className="bg-[#0F1113] text-neutral-200 text-xs dark:bg-black dark:text-neutral-300">
    <div className="max-w-7xl mx-auto px-4 h-8 flex items-center justify-between">
      <div className="flex items-center gap-4 overflow-x-auto whitespace-nowrap">
        <span className="flex items-center gap-1.5"><span className="text-cyan-400">◈</span>Mercari Global Marketplace</span>
        <span className="hidden sm:flex items-center gap-1.5"><span className="text-emerald-400">◆</span>Millions of Products</span>
        <span className="hidden md:flex items-center gap-1.5"><span className="text-orange-400">◔</span>Daily Flash Deals</span>
      </div>
      <div className="flex items-center gap-3">
        {!user ? (
          <>
            <Link to="/login" className="hover:text-white" data-testid="topstrip-login">Login</Link>
            <Link to="/register" className="hover:text-white" data-testid="topstrip-register">Register</Link>
          </>
        ) : (
          <>
            <Link to="/profile" className="hover:text-white">Hi, {user.username}</Link>
            <button onClick={onLogout} className="hover:text-white" data-testid="topstrip-logout">Logout</button>
          </>
        )}
      </div>
    </div>
  </div>
);

const ThemeToggle = () => {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="h-11 w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] grid place-items-center transition-colors relative overflow-hidden dark:border-neutral-700 dark:hover:border-[#FF7A18] group"
      data-testid="theme-toggle"
    >
      <Sun
        className={`h-5 w-5 text-neutral-700 absolute transition-all duration-300 ${
          isDark ? "opacity-0 rotate-90 scale-50" : "opacity-100 rotate-0 scale-100"
        }`}
      />
      <Moon
        className={`h-5 w-5 text-[#FF7A18] absolute transition-all duration-300 ${
          isDark ? "opacity-100 rotate-0 scale-100" : "opacity-0 -rotate-90 scale-50"
        }`}
      />
    </button>
  );
};

const Header = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [q, setQ] = useState("");
  const [cartCount, setCartCount] = useState(0);
  const [notifCount, setNotifCount] = useState(0);
  const [categories, setCategories] = useState([]);

  useEffect(() => {
    if (!user) {
      setCartCount(0);
      setNotifCount(0);
      return;
    }
    api.get("/cart").then((r) => setCartCount(r.data.length)).catch(() => {});
    api.get("/notifications").then((r) => setNotifCount(r.data.filter((n) => !n.read).length)).catch(() => {});
  }, [user, location.pathname]);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data)).catch(() => {});
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    const query = q.trim();
    navigate(query ? `/search?q=${encodeURIComponent(query)}` : "/search");
  };

  return (
    <header className="sticky top-0 z-40 bg-white dark:bg-neutral-950 transition-colors">
      <TopStrip user={user} onLogout={() => { logout(); navigate("/"); }} />

      {/* Main bar */}
      <div className="border-b border-neutral-200 dark:border-neutral-800">
        <div className="max-w-7xl mx-auto px-4 h-20 flex items-center gap-4">
          <Link to="/" className="flex items-center gap-3 shrink-0" data-testid="brand-link">
            <div className="h-11 w-11 rounded-lg bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white grid place-items-center font-bold text-lg shadow-sm">M</div>
            <div className="hidden sm:block leading-tight">
              <div className="text-xl font-bold text-neutral-900 dark:text-neutral-100">Mercari <span className="text-[#FF7A18]">Global</span></div>
              <div className="text-[11px] text-neutral-500 dark:text-neutral-400 -mt-0.5">Smart Ecommerce Platform</div>
            </div>
          </Link>

          <SearchAutocomplete
            value={q}
            onChange={setQ}
            onSubmit={handleSearch}
            placeholder="Search products, brands, categories..."
          />

          {/* Mobile-only theme toggle (kept next to search on small screens) */}
          <div className="md:hidden shrink-0">
            <ThemeToggle />
          </div>

          <nav className="hidden md:flex items-center gap-1.5 shrink-0">
            <LiveSyncBadge />
            <ThemeToggle />
            {user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button aria-label="Account" className="h-11 w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] dark:border-neutral-700 dark:hover:border-[#FF7A18] grid place-items-center transition" data-testid="header-user-btn">
                    <User className="h-5 w-5 text-neutral-700 dark:text-neutral-200" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel>Hi, {user.username}</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate("/profile")}><User className="h-4 w-4 mr-2" /> Profile</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/verify")}><ShieldCheck className="h-4 w-4 mr-2" /> Verification</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/favorites")}><Heart className="h-4 w-4 mr-2" /> Favorites</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/chat")}><MessageSquare className="h-4 w-4 mr-2" /> Messages</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/wallet")}><Wallet className="h-4 w-4 mr-2" /> Wallet</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/disputes")}><AlertCircle className="h-4 w-4 mr-2" /> Disputes</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/referrals")}><Users className="h-4 w-4 mr-2" /> Referrals</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/affiliate")}><LinkIcon className="h-4 w-4 mr-2" /> Affiliate links</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/store")}><Store className="h-4 w-4 mr-2" /> My store</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/store/analytics")}><BarChart3 className="h-4 w-4 mr-2" /> Store analytics</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/sell")}><Package className="h-4 w-4 mr-2" /> Sell an item</DropdownMenuItem>
                  {user.role === "admin" && (
                    <DropdownMenuItem onClick={() => navigate("/admin")}><Settings className="h-4 w-4 mr-2" /> Admin panel</DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => { logout(); navigate("/"); }}><LogOut className="h-4 w-4 mr-2" /> Logout</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link to="/login">
                <button aria-label="Login" className="h-11 w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] dark:border-neutral-700 dark:hover:border-[#FF7A18] grid place-items-center transition" data-testid="header-login-btn">
                  <User className="h-5 w-5 text-neutral-700 dark:text-neutral-200" />
                </button>
              </Link>
            )}

            <div className="h-11 w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] dark:border-neutral-700 dark:hover:border-[#FF7A18] grid place-items-center transition relative">
              <NotificationsBell />
              {notifCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-[#FF211F] text-white text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center pointer-events-none">
                  {notifCount}
                </span>
              )}
            </div>

            <Link to="/cart">
              <button aria-label="Cart" className="h-11 w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] dark:border-neutral-700 dark:hover:border-[#FF7A18] grid place-items-center transition relative" data-testid="header-cart-btn">
                <ShoppingCart className="h-5 w-5 text-neutral-700 dark:text-neutral-200" />
                {cartCount > 0 && (
                  <span className="absolute -top-1 -right-1 bg-[#FF211F] text-white text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center">
                    {cartCount}
                  </span>
                )}
              </button>
            </Link>
          </nav>
        </div>
      </div>

      {/* Category pills */}
      <div className="border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-2 overflow-x-auto scrollbar-hide">
          <Link to="/search" data-testid="cat-pill-all">
            <button className="whitespace-nowrap px-5 h-9 rounded-full bg-[#FF7A18] text-white font-medium text-sm flex items-center gap-1.5 shrink-0">
              <span className="text-base">▦</span> All Products
            </button>
          </Link>
          {categories.slice(0, 10).map((c) => (
            <Link key={c.id} to={`/search?category=${c.id}`} data-testid={`cat-pill-${c.slug}`}>
              <button className="whitespace-nowrap px-4 h-9 rounded-full bg-neutral-100 hover:bg-neutral-200 dark:bg-neutral-800 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-200 font-medium text-sm shrink-0 transition">
                {c.name}
              </button>
            </Link>
          ))}
        </div>
      </div>
    </header>
  );
};

export default Header;
