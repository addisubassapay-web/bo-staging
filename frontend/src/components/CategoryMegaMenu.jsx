import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Menu as MenuIcon, ChevronDown, Shirt, Baby, Smartphone, Home as HomeIcon, Sparkles,
  Dumbbell, Gamepad2, Book, Palette, Clock, Package, Footprints, Briefcase, Gem,
  PawPrint, Car, Flower2, Music, PenTool, Medal, TrendingUp, Flame, Percent,
} from "lucide-react";

const ICONS = {
  shirt: Shirt, baby: Baby, smartphone: Smartphone, home: HomeIcon, sparkles: Sparkles,
  dumbbell: Dumbbell, "gamepad-2": Gamepad2, book: Book, palette: Palette, clock: Clock,
  package: Package, footprints: Footprints, briefcase: Briefcase, gem: Gem,
  "paw-print": PawPrint, car: Car, "flower-2": Flower2, music: Music, "pen-tool": PenTool,
  medal: Medal,
};

const iconFor = (name) => ICONS[name] || Package;

const CategoryMegaMenu = ({ categories = [] }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const closeTimer = useRef(null);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const handleEnter = () => { clearTimeout(closeTimer.current); setOpen(true); };
  const handleLeave = () => { closeTimer.current = setTimeout(() => setOpen(false), 200); };
  const handleClick = () => {
    // Always open on click (mouseenter may or may not have fired on touch devices)
    clearTimeout(closeTimer.current);
    setOpen(true);
  };

  return (
    <div
      ref={ref}
      className="relative shrink-0"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <button
        type="button"
        onClick={handleClick}
        className="h-10 sm:h-11 px-3 sm:px-4 inline-flex items-center gap-1.5 rounded-full bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-100 text-sm font-semibold transition"
        data-testid="header-mega-btn"
        aria-expanded={open}
        aria-haspopup="true"
      >
        <MenuIcon className="h-4 w-4" />
        <span className="hidden md:inline">Categories</span>
        <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          className="absolute left-0 top-[calc(100%+8px)] z-50 w-[92vw] max-w-5xl rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-2xl p-5 sm:p-6"
          data-testid="header-mega-menu"
          role="menu"
        >
          {/* Quick links row */}
          <div className="flex items-center gap-2 mb-5 flex-wrap">
            <Link
              to="/search?sort=trending"
              onClick={() => setOpen(false)}
              className="inline-flex items-center gap-1.5 px-3 h-8 rounded-full bg-gradient-to-r from-[#1E40AF] to-[#3B82F6] text-white text-xs font-semibold shadow-sm hover:shadow-md transition"
              data-testid="mega-quick-trending"
            >
              <TrendingUp className="h-3.5 w-3.5" /> Trending
            </Link>
            <Link
              to="/search?sort=newest"
              onClick={() => setOpen(false)}
              className="inline-flex items-center gap-1.5 px-3 h-8 rounded-full bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-100 text-xs font-semibold transition"
              data-testid="mega-quick-new"
            >
              <Sparkles className="h-3.5 w-3.5 text-[#1E40AF]" /> New arrivals
            </Link>
            <Link
              to="/search?sort=price_asc&max=25"
              onClick={() => setOpen(false)}
              className="inline-flex items-center gap-1.5 px-3 h-8 rounded-full bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-100 text-xs font-semibold transition"
              data-testid="mega-quick-under25"
            >
              <Percent className="h-3.5 w-3.5 text-[#1E40AF]" /> Under $25
            </Link>
            <Link
              to="/search?sort=popular"
              onClick={() => setOpen(false)}
              className="inline-flex items-center gap-1.5 px-3 h-8 rounded-full bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-100 text-xs font-semibold transition"
              data-testid="mega-quick-popular"
            >
              <Flame className="h-3.5 w-3.5 text-[#1E40AF]" /> Most loved
            </Link>
          </div>

          {/* Category grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
            {categories.map((c) => {
              const Icon = iconFor(c.icon);
              return (
                <Link
                  key={c.id}
                  to={`/search?category=${c.id}`}
                  onClick={() => setOpen(false)}
                  className="group flex items-center gap-2.5 px-3 py-2.5 rounded-xl border border-transparent hover:border-[#1E40AF]/30 hover:bg-[#FFF3F2] dark:hover:bg-[#3a1817]/40 transition"
                  data-testid={`mega-cat-${c.slug}`}
                  role="menuitem"
                >
                  <span className="h-9 w-9 shrink-0 rounded-lg bg-gradient-to-br from-[#1E40AF]/10 to-[#DC2626]/10 grid place-items-center text-[#1E40AF] group-hover:from-[#1E40AF]/20 group-hover:to-[#DC2626]/20 transition">
                    <Icon className="h-4.5 w-4.5" />
                  </span>
                  <span className="text-sm font-medium text-neutral-800 dark:text-neutral-100 group-hover:text-[#DC2626] transition truncate">
                    {c.name}
                  </span>
                </Link>
              );
            })}
          </div>

          {/* See all footer */}
          <div className="mt-5 pt-4 border-t border-neutral-100 dark:border-neutral-800 flex items-center justify-between text-sm">
            <span className="text-neutral-500 dark:text-neutral-400">Browse {categories.length}+ curated categories</span>
            <Link
              to="/search"
              onClick={() => setOpen(false)}
              className="text-[#DC2626] font-semibold hover:underline"
              data-testid="mega-see-all"
            >
              See all products →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
};

export default CategoryMegaMenu;
