import React, { useEffect, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  Search, ShoppingCart, User, LogOut, Package, Settings, Store, Wallet,
  Link as LinkIcon, Users, MessageSquare, BarChart3, ShieldCheck, Heart,
  Sun, Moon, AlertCircle, Menu, X, Tag,
} from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import api from "@/lib/api";
import NotificationsBell from "@/components/NotificationsBell";
import LiveSyncBadge from "@/components/LiveSyncBadge";
import SearchAutocomplete from "@/components/SearchAutocomplete";
import CategoryMegaMenu from "@/components/CategoryMegaMenu";

/* --- Slim top strip --- */
const TopStrip = ({ user, onLogout }) => (
  <div className="bg-[#0F1113] text-neutral-200 text-xs dark:bg-black dark:text-neutral-300">
    <div className="max-w-7xl mx-auto px-4 h-8 flex items-center justify-between">
      <div className="flex items-center gap-4 overflow-x-auto whitespace-nowrap">
        <span className="flex items-center gap-1.5"><span className="text-cyan-400">◈</span>Mercari Global Marketplace</span>
        <span className="hidden sm:flex items-center gap-1.5"><span className="text-emerald-400">◆</span>Free returns on eligible items</span>
        <span className="hidden md:flex items-center gap-1.5"><span className="text-orange-400">◔</span>Daily Flash Deals</span>
      </div>
      <div className="flex items-center gap-3">
        <Link to="/disputes" className="hidden sm:inline hover:text-white" data-testid="topstrip-help">Help</Link>
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

/* --- Theme toggle --- */
const ThemeToggle = () => {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] grid place-items-center transition-colors relative overflow-hidden dark:border-neutral-700 dark:hover:border-[#FF7A18]"
      data-testid="theme-toggle"
    >
      <Sun className={`h-5 w-5 text-neutral-700 absolute transition-all duration-300 ${isDark ? "opacity-0 rotate-90 scale-50" : "opacity-100 rotate-0 scale-100"}`} />
      <Moon className={`h-5 w-5 text-[#FF7A18] absolute transition-all duration-300 ${isDark ? "opacity-100 rotate-0 scale-100" : "opacity-0 -rotate-90 scale-50"}`} />
    </button>
  );
};

/* --- Header icon button with badge --- */
const IconButton = ({ to, label, badge, children, testid, onClick }) => {
  const Inner = (
    <button
      aria-label={label}
      onClick={onClick}
      className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#FF7A18] dark:hover:border-[#FF7A18] grid place-items-center transition relative text-neutral-700 dark:text-neutral-200"
      data-testid={testid}
    >
      {children}
      {badge > 0 && (
        <span className="absolute -top-1 -right-1 bg-[#FF211F] text-white text-[10px] font-semibold rounded-full h-4.5 min-w-4.5 px-1 grid place-items-center leading-none tabular-nums">
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </button>
  );
  return to ? <Link to={to}>{Inner}</Link> : Inner;
};

/* --- Drawer nav item --- */
const DrawerNavItem = ({ to, icon: Icon, children, badge, onNavigate }) => {
  const slug = to === "/" ? "home" : to.replace(/[^a-z0-9]/gi, "-").replace(/^-+|-+$/g, "");
  return (
    <Link
      to={to}
      onClick={() => { onNavigate?.(); }}
      className="flex items-center gap-3 px-4 py-3 rounded-xl text-neutral-800 dark:text-neutral-100 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition"
      data-testid={`drawer-link-${slug}`}
    >
      <Icon className="h-5 w-5 text-[#FF7A18]" />
      <span className="flex-1 font-medium">{children}</span>
      {badge > 0 && (
        <span className="bg-[#FF211F] text-white text-[11px] font-bold rounded-full h-5 min-w-5 px-1.5 grid place-items-center">{badge}</span>
      )}
    </Link>
  );
};

/* --- Mobile drawer --- */
const MobileDrawer = ({ open, onClose, user, onLogout, notifCount, cartCount, categories }) => {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  return (
    <>
      <div
        onClick={onClose}
        className={`fixed inset-0 z-50 bg-black/50 backdrop-blur-sm transition-opacity md:hidden ${open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"}`}
        data-testid="mobile-drawer-backdrop"
      />
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 w-[86%] max-w-sm bg-white dark:bg-neutral-950 shadow-2xl transform transition-transform duration-300 md:hidden flex flex-col ${open ? "translate-x-0" : "-translate-x-full"}`}
        aria-hidden={!open}
        data-testid="mobile-drawer"
      >
        <div className="flex items-center justify-between px-4 h-16 border-b border-neutral-200 dark:border-neutral-800 shrink-0">
          <Link to="/" onClick={onClose} className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white grid place-items-center font-bold shadow-sm">M</div>
            <div className="leading-tight">
              <div className="text-base font-bold text-neutral-900 dark:text-neutral-100">Mercari <span className="text-[#FF7A18]">Global</span></div>
              <div className="text-[10px] text-neutral-500 dark:text-neutral-400 -mt-0.5">Smart Ecommerce Platform</div>
            </div>
          </Link>
          <button onClick={onClose} aria-label="Close menu" className="h-10 w-10 rounded-full grid place-items-center text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800" data-testid="drawer-close-btn">
            <X className="h-5 w-5" />
          </button>
        </div>

        {user && (
          <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-800 shrink-0">
            <div className="flex items-center gap-3">
              <div className="h-11 w-11 rounded-full bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white grid place-items-center font-bold text-lg">
                {user.username?.[0]?.toUpperCase() || "U"}
              </div>
              <div className="min-w-0">
                <div className="font-semibold text-neutral-900 dark:text-neutral-100 truncate">{user.username}</div>
                <div className="text-xs text-neutral-500 dark:text-neutral-400 truncate">{user.email}</div>
              </div>
            </div>
          </div>
        )}

        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
          <DrawerNavItem to="/" icon={Package} onNavigate={onClose}>Home</DrawerNavItem>
          <DrawerNavItem to="/search" icon={Search} onNavigate={onClose}>Browse all</DrawerNavItem>
          <DrawerNavItem to="/cart" icon={ShoppingCart} badge={cartCount} onNavigate={onClose}>Cart</DrawerNavItem>
          <DrawerNavItem to="/favorites" icon={Heart} onNavigate={onClose}>Favorites</DrawerNavItem>

          {/* Categories accordion */}
          <div className="pt-2 mt-2 border-t border-neutral-100 dark:border-neutral-800">
            <div className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Categories</div>
            <div className="grid grid-cols-2 gap-1 px-2">
              {categories.map((c) => (
                <Link
                  key={c.id}
                  to={`/search?category=${c.id}`}
                  onClick={onClose}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-neutral-800 dark:text-neutral-100 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition"
                  data-testid={`drawer-cat-${c.slug}`}
                >
                  <Tag className="h-3.5 w-3.5 text-[#FF7A18] shrink-0" />
                  <span className="truncate">{c.name}</span>
                </Link>
              ))}
            </div>
          </div>

          {user ? (
            <div className="pt-3 mt-3 border-t border-neutral-100 dark:border-neutral-800">
              <DrawerNavItem to="/sell" icon={Package} onNavigate={onClose}>Sell an item</DrawerNavItem>
              <DrawerNavItem to="/profile" icon={User} onNavigate={onClose}>Profile</DrawerNavItem>
              <DrawerNavItem to="/chat" icon={MessageSquare} badge={notifCount} onNavigate={onClose}>Messages</DrawerNavItem>
              <DrawerNavItem to="/wallet" icon={Wallet} onNavigate={onClose}>Wallet</DrawerNavItem>
              <DrawerNavItem to="/disputes" icon={AlertCircle} onNavigate={onClose}>Disputes</DrawerNavItem>
              <DrawerNavItem to="/my/store" icon={Store} onNavigate={onClose}>My store</DrawerNavItem>
              <DrawerNavItem to="/store/analytics" icon={BarChart3} onNavigate={onClose}>Store analytics</DrawerNavItem>
              <DrawerNavItem to="/referrals" icon={Users} onNavigate={onClose}>Referrals</DrawerNavItem>
              <DrawerNavItem to="/affiliate" icon={LinkIcon} onNavigate={onClose}>Affiliate</DrawerNavItem>
              <DrawerNavItem to="/verify" icon={ShieldCheck} onNavigate={onClose}>Verification</DrawerNavItem>
              {user.role === "admin" && <DrawerNavItem to="/admin" icon={Settings} onNavigate={onClose}>Admin panel</DrawerNavItem>}
            </div>
          ) : (
            <div className="pt-3 mt-3 border-t border-neutral-100 dark:border-neutral-800">
              <DrawerNavItem to="/login" icon={User} onNavigate={onClose}>Log in</DrawerNavItem>
              <DrawerNavItem to="/register" icon={User} onNavigate={onClose}>Sign up</DrawerNavItem>
            </div>
          )}
        </nav>

        {user && (
          <div className="p-3 border-t border-neutral-200 dark:border-neutral-800 shrink-0">
            <button
              onClick={() => { onClose(); onLogout(); }}
              className="w-full flex items-center gap-2 justify-center px-4 py-2.5 rounded-xl bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-100 font-medium transition"
              data-testid="drawer-logout"
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </div>
        )}
      </aside>
    </>
  );
};

/* --- Main header --- */
const Header = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [q, setQ] = useState("");
  const [cartCount, setCartCount] = useState(0);
  const [notifCount, setNotifCount] = useState(0);
  const [categories, setCategories] = useState([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

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

  useEffect(() => { setDrawerOpen(false); }, [location.pathname]);

  return (
    <header className="sticky top-0 z-40 bg-white dark:bg-neutral-950 transition-colors">
      <TopStrip user={user} onLogout={() => { logout(); navigate("/"); }} />

      {/* Main bar */}
      <div className="border-b border-neutral-200 dark:border-neutral-800">
        <div className="max-w-7xl mx-auto px-3 sm:px-4 h-16 sm:h-20 flex items-center gap-2 sm:gap-3">
          {/* Mobile hamburger */}
          <button
            aria-label="Open menu"
            onClick={() => setDrawerOpen(true)}
            className="md:hidden h-10 w-10 -ml-1 rounded-full grid place-items-center text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition"
            data-testid="mobile-menu-btn"
          >
            <Menu className="h-5 w-5" />
          </button>

          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 sm:gap-3 shrink-0" data-testid="brand-link">
            <div className="h-9 w-9 sm:h-11 sm:w-11 rounded-lg bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white grid place-items-center font-bold text-base sm:text-lg shadow-sm">M</div>
            <div className="hidden lg:block leading-tight">
              <div className="text-lg xl:text-xl font-bold text-neutral-900 dark:text-neutral-100">Mercari <span className="text-[#FF7A18]">Global</span></div>
              <div className="text-[11px] text-neutral-500 dark:text-neutral-400 -mt-0.5">Smart Ecommerce</div>
            </div>
          </Link>

          {/* Categories mega menu (desktop only) */}
          <div className="hidden md:block">
            <CategoryMegaMenu categories={categories} />
          </div>

          {/* Search bar (fills remaining space) */}
          <SearchAutocomplete
            value={q}
            onChange={setQ}
            onSubmit={() => {}}
            placeholder="Search for anything you love…"
            categories={categories}
          />

          {/* Right action cluster */}
          <div className="hidden md:flex items-center gap-1.5 shrink-0">
            <LiveSyncBadge />

            {/* Sell CTA */}
            <Link to={user ? "/sell" : "/login"} data-testid="header-sell-cta-wrap">
              <button
                className="h-11 px-5 rounded-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F] hover:brightness-110 text-white font-semibold text-sm shadow-sm hover:shadow-md transition-all flex items-center gap-1.5"
                data-testid="header-sell-btn"
              >
                <Package className="h-4 w-4" /> Sell
              </button>
            </Link>

            <ThemeToggle />

            <IconButton to="/favorites" label="Favorites" testid="header-fav-btn">
              <Heart className="h-5 w-5" />
            </IconButton>

            <div className="h-11 w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] dark:border-neutral-700 dark:hover:border-[#FF7A18] grid place-items-center transition relative">
              <NotificationsBell />
              {notifCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-[#FF211F] text-white text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center pointer-events-none">
                  {notifCount}
                </span>
              )}
            </div>

            {user && (
              <IconButton to="/chat" label="Messages" testid="header-msg-btn">
                <MessageSquare className="h-5 w-5" />
              </IconButton>
            )}

            <IconButton to="/cart" label="Cart" testid="header-cart-btn" badge={cartCount}>
              <ShoppingCart className="h-5 w-5" />
            </IconButton>

            {/* User menu */}
            {user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    aria-label="Account"
                    className="h-11 w-11 rounded-full bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white grid place-items-center font-bold text-sm hover:brightness-110 transition"
                    data-testid="header-user-btn"
                  >
                    {user.username?.[0]?.toUpperCase() || "U"}
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel>Hi, {user.username}</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate("/profile")}><User className="h-4 w-4 mr-2" /> Profile</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/verify")}><ShieldCheck className="h-4 w-4 mr-2" /> Verification</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/wallet")}><Wallet className="h-4 w-4 mr-2" /> Wallet</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/disputes")}><AlertCircle className="h-4 w-4 mr-2" /> Disputes</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/referrals")}><Users className="h-4 w-4 mr-2" /> Referrals</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/affiliate")}><LinkIcon className="h-4 w-4 mr-2" /> Affiliate links</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/my/store")}><Store className="h-4 w-4 mr-2" /> My store</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate("/store/analytics")}><BarChart3 className="h-4 w-4 mr-2" /> Store analytics</DropdownMenuItem>
                  {user.role === "admin" && (
                    <DropdownMenuItem onClick={() => navigate("/admin")}><Settings className="h-4 w-4 mr-2" /> Admin panel</DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => { logout(); navigate("/"); }}><LogOut className="h-4 w-4 mr-2" /> Logout</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link to="/login">
                <button
                  className="h-11 px-4 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#FF7A18] dark:hover:border-[#FF7A18] text-sm font-semibold text-neutral-800 dark:text-neutral-100 transition flex items-center gap-1.5"
                  data-testid="header-login-btn"
                >
                  <User className="h-4 w-4" /> Sign in
                </button>
              </Link>
            )}
          </div>

          {/* Mobile action row */}
          <div className="md:hidden flex items-center gap-1 shrink-0">
            <ThemeToggle />
            <Link to="/cart" aria-label="Cart" className="h-10 w-10 rounded-full grid place-items-center relative text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition" data-testid="header-cart-btn-mobile">
              <ShoppingCart className="h-5 w-5" />
              {cartCount > 0 && (
                <span className="absolute top-0.5 right-0.5 bg-[#FF211F] text-white text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center">{cartCount}</span>
              )}
            </Link>
          </div>
        </div>
      </div>

      {/* Category ribbon */}
      <div className="border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950">
        <div className="max-w-7xl mx-auto px-3 sm:px-4 py-2 sm:py-2.5 flex items-center gap-2 overflow-x-auto scrollbar-hide">
          <Link to="/search" data-testid="cat-pill-all">
            <button className="whitespace-nowrap px-4 sm:px-5 h-8 sm:h-9 rounded-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F] text-white font-semibold text-xs sm:text-sm flex items-center gap-1.5 shrink-0 shadow-sm">
              <span className="text-base leading-none">▦</span> All Products
            </button>
          </Link>
          {categories.map((c) => (
            <Link key={c.id} to={`/search?category=${c.id}`} data-testid={`cat-pill-${c.slug}`}>
              <button className="whitespace-nowrap px-3 sm:px-4 h-8 sm:h-9 rounded-full bg-neutral-100 hover:bg-neutral-200 dark:bg-neutral-800 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-200 font-medium text-xs sm:text-sm shrink-0 transition">
                {c.name}
              </button>
            </Link>
          ))}
        </div>
      </div>

      <MobileDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        user={user}
        onLogout={() => { logout(); navigate("/"); }}
        notifCount={notifCount}
        cartCount={cartCount}
        categories={categories}
      />
    </header>
  );
};

export default Header;
