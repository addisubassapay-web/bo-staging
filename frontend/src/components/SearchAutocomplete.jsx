import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Search } from "lucide-react";

/**
 * SearchAutocomplete
 * Debounced live suggestions dropdown for the header search bar.
 * Shows product matches (image + title + price) and brand/category chips.
 */
const SearchAutocomplete = ({ value, onChange, onSubmit, placeholder }) => {
  const navigate = useNavigate();
  const [suggestions, setSuggestions] = useState({ items: [], queries: [] });
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState(false);
  const boxRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    const q = value.trim();
    if (q.length < 2) {
      setSuggestions({ items: [], queries: [] });
      setOpen(false);
      return;
    }
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        const { data } = await api.get("/search/suggest", { params: { q, limit: 6 } });
        setSuggestions(data);
        setOpen(true);
      } catch { /* ignore */ }
    }, 200);
    return () => clearTimeout(timerRef.current);
  }, [value]);

  // Close on outside click
  useEffect(() => {
    const onClickOutside = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const hasContent = (suggestions.items?.length || 0) + (suggestions.queries?.length || 0) > 0;

  const goToProduct = (id) => {
    setOpen(false);
    navigate(`/listing/${id}`);
  };
  const goToQuery = (q) => {
    setOpen(false);
    onChange(q);
    navigate(`/search?q=${encodeURIComponent(q)}`);
  };

  return (
    <div ref={boxRef} className="relative flex-1 max-w-3xl">
      <form onSubmit={(e) => { e.preventDefault(); setOpen(false); onSubmit(e); }} data-testid="header-search-form">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => { setFocus(true); if (hasContent) setOpen(true); }}
          onBlur={() => setFocus(false)}
          placeholder={placeholder}
          className="h-12 w-full pl-5 pr-14 rounded-full border-2 border-[#FF7A18]/70 focus-visible:border-[#FF7A18] focus:outline-none bg-white text-neutral-900 placeholder:text-neutral-400"
          data-testid="header-search-input"
        />
        <button
          type="submit"
          aria-label="Search"
          className="absolute right-1.5 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-[#FF7A18] hover:bg-[#e86a10] text-white grid place-items-center transition"
          data-testid="header-search-btn"
        >
          <Search className="h-4 w-4" />
        </button>
      </form>

      {open && hasContent && (
        <div className="absolute left-0 right-0 top-14 z-50 bg-white border border-neutral-200 rounded-2xl shadow-xl overflow-hidden" data-testid="search-suggest-dropdown">
          {suggestions.queries?.length > 0 && (
            <div className="px-3 py-2 border-b border-neutral-100">
              <div className="text-[11px] uppercase tracking-wider text-neutral-500 font-medium mb-1.5">Suggestions</div>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.queries.map((q) => (
                  <button
                    key={q}
                    onMouseDown={(e) => { e.preventDefault(); goToQuery(q); }}
                    className="px-2.5 h-7 rounded-full bg-neutral-100 hover:bg-[#FFF3F2] hover:text-[#FF211F] text-xs text-neutral-700 transition"
                    data-testid={`suggest-query-${q}`}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {suggestions.items?.length > 0 && (
            <ul className="max-h-96 overflow-y-auto">
              {suggestions.items.map((it) => (
                <li key={it.id}>
                  <button
                    onMouseDown={(e) => { e.preventDefault(); goToProduct(it.id); }}
                    className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-neutral-50 text-left transition"
                    data-testid={`suggest-item-${it.id}`}
                  >
                    <img src={it.image} alt="" className="h-11 w-11 rounded object-cover bg-neutral-100" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-neutral-900 line-clamp-1">{it.title}</div>
                      <div className="text-xs text-neutral-500">{it.brand || it.category_name}</div>
                    </div>
                    <div className="text-sm font-semibold text-neutral-900">${Number(it.price).toFixed(2)}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Link
            to={value.trim() ? `/search?q=${encodeURIComponent(value.trim())}` : "/search"}
            onClick={() => setOpen(false)}
            className="block text-center py-2.5 text-sm text-[#FF7A18] hover:bg-[#FFF3F2] font-medium border-t border-neutral-100"
            data-testid="suggest-see-all"
          >
            See all results for &ldquo;{value.trim()}&rdquo; →
          </Link>
        </div>
      )}
    </div>
  );
};

export default SearchAutocomplete;
