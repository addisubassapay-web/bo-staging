import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import { useCurrency } from "@/context/CurrencyContext";
import {
  Search, ChevronDown, Clock, TrendingUp, X, Tag, Folder, Mic, Camera, Sparkles, Loader2,
} from "lucide-react";

const RECENT_KEY = "mercari_recent_searches";
const MAX_RECENT = 8;
const VIBE_HINTS = ["cozy autumn", "y2k glam", "minimalist desk", "streetwear", "beach picnic", "gamer setup"];

const readRecent = () => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; } };
const pushRecent = (q) => {
  if (!q || q.length < 2) return;
  const cur = readRecent().filter((x) => x.toLowerCase() !== q.toLowerCase());
  const next = [q, ...cur].slice(0, MAX_RECENT);
  localStorage.setItem(RECENT_KEY, JSON.stringify(next));
};
const clearRecent = () => localStorage.setItem(RECENT_KEY, JSON.stringify([]));

const SearchAutocomplete = ({ value, onChange, onSubmit, placeholder, categories = [] }) => {
  const navigate = useNavigate();
  const { t } = useLang();
  const { format } = useCurrency();
  const [suggestions, setSuggestions] = useState({ items: [], queries: [], brands: [], categories: [] });
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState("");
  const [scopePickerOpen, setScopePickerOpen] = useState(false);
  const [recent, setRecent] = useState([]);
  const [trending, setTrending] = useState([]);
  const [liveCount, setLiveCount] = useState(null);
  const [countLoading, setCountLoading] = useState(false);
  const [voiceListening, setVoiceListening] = useState(false);
  const [imgLoading, setImgLoading] = useState(false);
  const [hintIdx, setHintIdx] = useState(0);
  const boxRef = useRef(null);
  const scopeRef = useRef(null);
  const timerRef = useRef(null);
  const countTimerRef = useRef(null);
  const fileInputRef = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    setRecent(readRecent());
    api.get("/search/trending").then((r) => setTrending(r.data?.trending || [])).catch(() => {});
  }, []);

  // Rotate vibe hint every 3.5s (when idle)
  useEffect(() => {
    if (value) return;
    const iv = setInterval(() => setHintIdx((i) => (i + 1) % VIBE_HINTS.length), 3500);
    return () => clearInterval(iv);
  }, [value]);

  // Debounced suggestions
  useEffect(() => {
    const q = value.trim();
    if (q.length < 2) {
      setSuggestions({ items: [], queries: [], brands: [], categories: [] });
      return;
    }
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        const { data } = await api.get("/search/suggest", { params: { q, limit: 6 } });
        setSuggestions({
          items: data.items || [],
          queries: data.queries || [],
          brands: data.brands || [],
          categories: data.categories || [],
        });
      } catch { /* ignore */ }
    }, 180);
    return () => clearTimeout(timerRef.current);
  }, [value]);

  // Live results count (debounced, uses /listings/count)
  useEffect(() => {
    const q = value.trim();
    if (q.length < 2) { setLiveCount(null); return; }
    clearTimeout(countTimerRef.current);
    setCountLoading(true);
    countTimerRef.current = setTimeout(async () => {
      try {
        const params = { q };
        if (scope) params.category_id = scope;
        const { data } = await api.get("/listings/count", { params });
        setLiveCount(data?.total ?? 0);
      } catch { setLiveCount(null); }
      finally { setCountLoading(false); }
    }, 220);
    return () => clearTimeout(countTimerRef.current);
  }, [value, scope]);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) {
        setOpen(false);
        setScopePickerOpen(false);
      }
    };
    const onEsc = (e) => { if (e.key === "Escape") { setOpen(false); setScopePickerOpen(false); } };
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onEsc);
    };
  }, []);

  const scopeName = useMemo(() => {
    if (!scope) return "All";
    const cat = categories.find((c) => c.id === scope);
    return cat?.name || "All";
  }, [scope, categories]);

  const buildQueryStr = (q, categoryId) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (categoryId) params.set("category", categoryId);
    const str = params.toString();
    return str ? `/search?${str}` : "/search";
  };

  const submitQuery = (q) => {
    const trimmed = (q || "").trim();
    if (trimmed) pushRecent(trimmed);
    setRecent(readRecent());
    setOpen(false);
    setScopePickerOpen(false);
    navigate(buildQueryStr(trimmed, scope));
  };

  const goToProduct = (id) => { setOpen(false); navigate(`/listing/${id}`); };
  const goToBrand = (b) => submitQuery(b);
  const goToCategory = (id) => { setOpen(false); navigate(`/search?category=${id}`); };

  // --- Voice search (SpeechRecognition) ---
  const startVoice = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert("Voice search isn't supported in this browser."); return; }
    if (voiceListening) { recognitionRef.current?.stop?.(); return; }
    const rec = new SR();
    rec.lang = document.documentElement.getAttribute("lang") || "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (evt) => {
      const transcript = Array.from(evt.results).map((r) => r[0].transcript).join(" ").trim();
      if (transcript) onChange(transcript);
      if (evt.results[0]?.isFinal) {
        setVoiceListening(false);
        setTimeout(() => submitQuery(transcript), 250);
      }
    };
    rec.onerror = () => setVoiceListening(false);
    rec.onend = () => setVoiceListening(false);
    recognitionRef.current = rec;
    setVoiceListening(true);
    rec.start();
  };

  // --- Image search ---
  const onImageChosen = async (file) => {
    if (!file) return;
    setImgLoading(true);
    try {
      const b64 = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = () => reject(new Error("Read failed"));
        r.readAsDataURL(file);
      });
      const { data } = await api.post("/search/image", { image_base64: b64, limit: 24 });
      const kwStr = (data.keywords || []).slice(0, 3).join(" ") || (data.category?.name || "");
      onChange(kwStr);
      const cid = data.category?.id;
      setOpen(false);
      navigate(cid ? `/search?q=${encodeURIComponent(kwStr)}&category=${cid}` : `/search?q=${encodeURIComponent(kwStr)}`);
    } catch (e) {
      alert(e?.response?.data?.detail || "Image search failed. Please try another photo.");
    } finally {
      setImgLoading(false);
    }
  };

  const showEmptyState = value.trim().length < 2 && (recent.length > 0 || trending.length > 0);
  const hasSuggestionContent =
    (suggestions.items?.length || 0) +
    (suggestions.queries?.length || 0) +
    (suggestions.brands?.length || 0) +
    (suggestions.categories?.length || 0) > 0;

  return (
    <div ref={boxRef} className="relative flex-1 max-w-3xl">
      <form
        onSubmit={(e) => { e.preventDefault(); submitQuery(value); onSubmit?.(e); }}
        data-testid="header-search-form"
        className="flex items-stretch h-11 sm:h-12 w-full rounded-full border-2 border-[#FF7A18]/70 focus-within:border-[#FF7A18] bg-white dark:bg-neutral-900 overflow-hidden shadow-sm"
      >
        {/* Category scope */}
        <div ref={scopeRef} className="relative shrink-0 hidden sm:block">
          <button
            type="button"
            onClick={() => { setScopePickerOpen((v) => !v); setOpen(false); }}
            className="h-full px-3 sm:px-4 pl-4 flex items-center gap-1.5 text-sm font-medium text-neutral-700 dark:text-neutral-200 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition border-r border-neutral-200 dark:border-neutral-700 whitespace-nowrap"
            data-testid="header-search-scope-btn"
            aria-label="Search scope"
          >
            <span className="max-w-[110px] truncate">{scopeName}</span>
            <ChevronDown className={`h-4 w-4 transition-transform ${scopePickerOpen ? "rotate-180" : ""}`} />
          </button>
          {scopePickerOpen && (
            <div className="absolute left-0 top-[calc(100%+4px)] z-50 w-64 max-h-80 overflow-y-auto rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-xl py-1.5" data-testid="header-search-scope-menu">
              <button
                onMouseDown={(e) => { e.preventDefault(); setScope(""); setScopePickerOpen(false); }}
                className={`w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition ${!scope ? "font-semibold text-[#FF7A18]" : "text-neutral-700 dark:text-neutral-200"}`}
                data-testid="scope-item-all"
              >All categories</button>
              {categories.map((c) => (
                <button
                  key={c.id}
                  onMouseDown={(e) => { e.preventDefault(); setScope(c.id); setScopePickerOpen(false); }}
                  className={`w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition ${scope === c.id ? "font-semibold text-[#FF7A18]" : "text-neutral-700 dark:text-neutral-200"}`}
                  data-testid={`scope-item-${c.slug}`}
                >{c.name}</button>
              ))}
            </div>
          )}
        </div>

        {/* Input */}
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => { setOpen(true); setScopePickerOpen(false); }}
          placeholder={placeholder || t("search.placeholder")}
          className="flex-1 h-full px-4 bg-transparent text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400 dark:placeholder:text-neutral-500 focus:outline-none min-w-0"
          data-testid="header-search-input"
          autoComplete="off"
        />

        {/* Clear */}
        {value && (
          <button type="button" onClick={() => onChange("")} aria-label="Clear search"
            className="px-2 text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200" data-testid="header-search-clear">
            <X className="h-4 w-4" />
          </button>
        )}

        {/* Voice */}
        <button
          type="button"
          onClick={startVoice}
          title={voiceListening ? "Stop listening" : "Voice search"}
          aria-label="Voice search"
          className={`hidden sm:grid h-full aspect-square place-items-center border-l border-neutral-200 dark:border-neutral-700 transition ${voiceListening ? "bg-[#FF211F] text-white animate-pulse" : "text-neutral-500 hover:text-[#FF211F] hover:bg-neutral-50 dark:hover:bg-neutral-800"}`}
          data-testid="header-search-voice"
        >
          <Mic className="h-4.5 w-4.5" />
        </button>

        {/* Image */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          title="Search by image"
          aria-label="Search by image"
          disabled={imgLoading}
          className={`hidden sm:grid h-full aspect-square place-items-center border-l border-neutral-200 dark:border-neutral-700 transition text-neutral-500 hover:text-[#FF7A18] hover:bg-neutral-50 dark:hover:bg-neutral-800 disabled:opacity-50`}
          data-testid="header-search-image"
        >
          {imgLoading ? <Loader2 className="h-4.5 w-4.5 animate-spin" /> : <Camera className="h-4.5 w-4.5" />}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => onImageChosen(e.target.files?.[0])}
          data-testid="header-search-image-input"
        />

        {/* Submit */}
        <button type="submit" aria-label="Search"
          className="h-full aspect-square bg-[#FF7A18] hover:bg-[#e86a10] text-white grid place-items-center transition"
          data-testid="header-search-btn">
          <Search className="h-4 w-4 sm:h-5 sm:w-5" />
        </button>
      </form>

      {/* Live counter chip */}
      {value.trim().length >= 2 && (
        <div className="absolute -bottom-6 left-4 text-[11px] font-medium text-neutral-500 dark:text-neutral-400 tabular-nums flex items-center gap-1 pointer-events-none" data-testid="search-live-count">
          {countLoading ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> counting…
            </>
          ) : liveCount !== null ? (
            <span><span className="text-[#FF211F] font-bold">{liveCount.toLocaleString()}</span> matches</span>
          ) : null}
        </div>
      )}

      {/* Vibe hint chip (idle) */}
      {!value && !open && (
        <button
          type="button"
          onClick={() => navigate(`/search?vibe=${encodeURIComponent(VIBE_HINTS[hintIdx])}`)}
          className="hidden lg:flex absolute -bottom-6 left-4 text-[11px] items-center gap-1 text-[#FF211F] font-medium hover:underline"
          data-testid="search-vibe-hint"
        >
          <Sparkles className="h-3 w-3" /> Try &ldquo;{VIBE_HINTS[hintIdx]}&rdquo; →
        </button>
      )}

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-50 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl shadow-2xl overflow-hidden" data-testid="search-suggest-dropdown">
          {value.trim().length >= 2 && hasSuggestionContent && (
            <>
              {suggestions.queries?.length > 0 && (
                <div className="px-4 py-2.5 border-b border-neutral-100 dark:border-neutral-800">
                  <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold mb-1.5">{t("search.suggestions")}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {suggestions.queries.map((q) => (
                      <button key={q} onMouseDown={(e) => { e.preventDefault(); onChange(q); submitQuery(q); }}
                        className="px-3 h-7 rounded-full bg-neutral-100 dark:bg-neutral-800 hover:bg-[#FFF3F2] dark:hover:bg-[#3a1817] hover:text-[#FF211F] text-xs text-neutral-700 dark:text-neutral-200 transition"
                        data-testid={`suggest-query-${q.replace(/\s+/g, '-')}`}>{q}</button>
                    ))}
                  </div>
                </div>
              )}
              {suggestions.brands?.length > 0 && (
                <div className="px-4 py-2.5 border-b border-neutral-100 dark:border-neutral-800">
                  <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold mb-1.5 flex items-center gap-1.5"><Tag className="h-3 w-3" /> {t("search.brands")}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {suggestions.brands.map((b) => (
                      <button key={b.name} onMouseDown={(e) => { e.preventDefault(); goToBrand(b.name); }}
                        className="px-3 h-7 rounded-full border border-neutral-200 dark:border-neutral-700 hover:border-[#FF7A18] hover:text-[#FF7A18] text-xs text-neutral-700 dark:text-neutral-200 transition flex items-center gap-1.5"
                        data-testid={`suggest-brand-${b.name.replace(/\s+/g, '-')}`}>
                        <span className="font-medium">{b.name}</span>
                        <span className="text-neutral-400 tabular-nums">{b.count}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {suggestions.categories?.length > 0 && (
                <div className="px-4 py-2.5 border-b border-neutral-100 dark:border-neutral-800">
                  <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold mb-1.5 flex items-center gap-1.5"><Folder className="h-3 w-3" /> Categories</div>
                  <div className="flex flex-wrap gap-1.5">
                    {suggestions.categories.map((c) => (
                      <button key={c.id} onMouseDown={(e) => { e.preventDefault(); goToCategory(c.id); }}
                        className="px-3 h-7 rounded-full bg-neutral-100 dark:bg-neutral-800 hover:bg-[#FFF3F2] dark:hover:bg-[#3a1817] hover:text-[#FF211F] text-xs text-neutral-700 dark:text-neutral-200 transition"
                        data-testid={`suggest-cat-${c.slug}`}>{c.name}</button>
                    ))}
                  </div>
                </div>
              )}
              {suggestions.items?.length > 0 && (
                <ul className="max-h-96 overflow-y-auto">
                  {suggestions.items.map((it) => (
                    <li key={it.id}>
                      <button onMouseDown={(e) => { e.preventDefault(); goToProduct(it.id); }}
                        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-neutral-50 dark:hover:bg-neutral-800 text-left transition"
                        data-testid={`suggest-item-${it.id}`}>
                        <img src={it.image} alt="" className="h-11 w-11 rounded-lg object-cover bg-neutral-100 dark:bg-neutral-800" />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-neutral-900 dark:text-neutral-100 line-clamp-1">{it.title}</div>
                          <div className="text-xs text-neutral-500 dark:text-neutral-400">{it.brand || it.category_name}</div>
                        </div>
                        <div className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 tabular-nums">{format(it.price)}</div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <Link to={buildQueryStr(value.trim(), scope)} onMouseDown={(e) => { e.preventDefault(); submitQuery(value); }}
                className="block text-center py-2.5 text-sm text-[#FF7A18] hover:bg-[#FFF3F2] dark:hover:bg-[#3a1817] font-semibold border-t border-neutral-100 dark:border-neutral-800"
                data-testid="suggest-see-all">
                {t("search.seeAll")} &ldquo;{value.trim()}&rdquo; →
              </Link>
            </>
          )}
          {showEmptyState && (
            <div className="p-3">
              {recent.length > 0 && (
                <div className="mb-3">
                  <div className="flex items-center justify-between px-1.5 mb-1.5">
                    <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold flex items-center gap-1.5"><Clock className="h-3 w-3" /> {t("search.recentTitle")}</div>
                    <button onMouseDown={(e) => { e.preventDefault(); clearRecent(); setRecent([]); }} className="text-[11px] text-neutral-500 hover:text-[#FF211F]" data-testid="recent-clear-btn">Clear</button>
                  </div>
                  <div className="flex flex-wrap gap-1.5 px-1">
                    {recent.map((r) => (
                      <button key={r} onMouseDown={(e) => { e.preventDefault(); onChange(r); submitQuery(r); }}
                        className="px-3 h-7 rounded-full bg-neutral-100 dark:bg-neutral-800 hover:bg-[#FFF3F2] dark:hover:bg-[#3a1817] hover:text-[#FF211F] text-xs text-neutral-700 dark:text-neutral-200 transition"
                        data-testid={`recent-item-${r.replace(/\s+/g, '-')}`}>{r}</button>
                    ))}
                  </div>
                </div>
              )}
              {trending.length > 0 && (
                <div>
                  <div className="px-1.5 mb-1.5 text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold flex items-center gap-1.5"><TrendingUp className="h-3 w-3 text-[#FF7A18]" /> {t("search.trendingTitle")}</div>
                  <div className="flex flex-wrap gap-1.5 px-1">
                    {trending.map((tt) => (
                      <button key={tt} onMouseDown={(e) => { e.preventDefault(); onChange(tt); submitQuery(tt); }}
                        className="px-3 h-7 rounded-full bg-gradient-to-r from-[#FF7A18]/10 to-[#FF211F]/10 hover:from-[#FF7A18]/20 hover:to-[#FF211F]/20 text-xs text-[#FF211F] font-medium transition"
                        data-testid={`trending-item-${tt.replace(/\s+/g, '-')}`}>{tt}</button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SearchAutocomplete;
