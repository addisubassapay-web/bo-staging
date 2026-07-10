import React, { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Search, ShoppingCart, Heart, User, Menu, LogOut, Package, Settings, Store, X, Wallet, Link as LinkIcon, Users, MessageSquare, BarChart3 } from "lucide-react";
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
import api from "@/lib/api";
import NotificationsBell from "@/components/NotificationsBell";
import LiveSyncBadge from "@/components/LiveSyncBadge";

const Header = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [q, setQ] = useState("");
  const [cartCount, setCartCount] = useState(0);
  const [favCount, setFavCount] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!user) {
      setCartCount(0);
      setFavCount(0);
      return;
    }
    api.get("/cart").then((r) => setCartCount(r.data.length)).catch(() => {});
    api.get("/favorites").then((r) => setFavCount(r.data.length)).catch(() => {});
  }, [user, location.pathname]);

  const handleSearch = (e) => {
    e.preventDefault();
    const query = q.trim();
    navigate(query ? `/search?q=${encodeURIComponent(query)}` : "/search");
  };

  return (
    <header className="sticky top-0 z-40 bg-white border-b border-neutral-200">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center gap-4">
        <Link to="/" className="flex items-center gap-2 shrink-0">
          <div className="h-9 w-9 rounded-md bg-[#FF211F] text-white grid place-items-center font-bold text-lg">M</div>
          <span className="text-xl font-bold text-neutral-900 hidden sm:inline">mercari</span>
        </Link>

        <form onSubmit={handleSearch} className="flex-1 max-w-2xl relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search for anything"
            className="pl-9 h-10 bg-neutral-100 border-transparent focus-visible:bg-white focus-visible:border-neutral-300"
          />
        </form>

        <nav className="hidden md:flex items-center gap-1">
          <LiveSyncBadge />
          <NotificationsBell />
          <Link to="/favorites">
            <Button variant="ghost" size="sm" className="relative">
              <Heart className="h-5 w-5" />
              {favCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-[#FF211F] text-white text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center">
                  {favCount}
                </span>
              )}
            </Button>
          </Link>
          <Link to="/cart">
            <Button variant="ghost" size="sm" className="relative">
              <ShoppingCart className="h-5 w-5" />
              {cartCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-[#FF211F] text-white text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center">
                  {cartCount}
                </span>
              )}
            </Button>
          </Link>

          <Link to="/sell">
            <Button className="bg-[#FF211F] hover:bg-[#e01d1b] text-white h-9">Sell</Button>
          </Link>

          {user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="gap-2">
                  <div className="h-7 w-7 rounded-full bg-neutral-200 grid place-items-center text-sm font-semibold text-neutral-700">
                    {user.username[0].toUpperCase()}
                  </div>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="font-normal">
                  <div className="font-semibold">{user.username}</div>
                  <div className="text-xs text-neutral-500">{user.email}</div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/profile")}>
                  <User className="h-4 w-4 mr-2" /> Profile
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/profile?tab=listings")}>
                  <Store className="h-4 w-4 mr-2" /> My listings
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/profile?tab=orders")}>
                  <Package className="h-4 w-4 mr-2" /> Orders
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/wallet")}>
                  <Wallet className="h-4 w-4 mr-2" /> Wallet
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/my/store")}>
                  <Store className="h-4 w-4 mr-2" /> My store
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/store/analytics")}>
                  <BarChart3 className="h-4 w-4 mr-2" /> Analytics
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/chat")}>
                  <MessageSquare className="h-4 w-4 mr-2" /> Messages
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/affiliate")}>
                  <LinkIcon className="h-4 w-4 mr-2" /> Affiliate
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate("/referrals")}>
                  <Users className="h-4 w-4 mr-2" /> Referrals
                </DropdownMenuItem>
                {user.role === "admin" && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => navigate("/admin")}>
                      <Settings className="h-4 w-4 mr-2" /> Admin panel
                    </DropdownMenuItem>
                  </>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => { logout(); navigate("/"); }}>
                  <LogOut className="h-4 w-4 mr-2" /> Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <div className="flex items-center gap-1">
              <Link to="/login">
                <Button variant="ghost" size="sm">Log in</Button>
              </Link>
              <Link to="/register">
                <Button variant="outline" size="sm">Sign up</Button>
              </Link>
            </div>
          )}
        </nav>

        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={() => setMobileOpen((v) => !v)}
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </Button>
      </div>

      {mobileOpen && (
        <div className="md:hidden border-t border-neutral-200 bg-white px-4 py-3 flex flex-col gap-2">
          <Link to="/sell" onClick={() => setMobileOpen(false)}>
            <Button className="w-full bg-[#FF211F] hover:bg-[#e01d1b]">Sell an item</Button>
          </Link>
          <Link to="/favorites" onClick={() => setMobileOpen(false)} className="py-2">Favorites ({favCount})</Link>
          <Link to="/cart" onClick={() => setMobileOpen(false)} className="py-2">Cart ({cartCount})</Link>
          {user ? (
            <>
              <Link to="/profile" onClick={() => setMobileOpen(false)} className="py-2">Profile</Link>
              {user.role === "admin" && (
                <Link to="/admin" onClick={() => setMobileOpen(false)} className="py-2">Admin</Link>
              )}
              <button className="py-2 text-left" onClick={() => { logout(); setMobileOpen(false); navigate("/"); }}>Log out</button>
            </>
          ) : (
            <>
              <Link to="/login" onClick={() => setMobileOpen(false)} className="py-2">Log in</Link>
              <Link to="/register" onClick={() => setMobileOpen(false)} className="py-2">Sign up</Link>
            </>
          )}
        </div>
      )}
    </header>
  );
};

export default Header;
