import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Facebook, Twitter, Instagram, Youtube, Mail, ArrowRight } from "lucide-react";
import BrandMark from "@/components/BrandMark";
import api from "@/lib/api";

const NewsletterStrip = () => {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | ok | error
  const [message, setMessage] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!email || !/@/.test(email)) return;
    setStatus("loading");
    setMessage("");
    try {
      const { data } = await api.post("/newsletter/subscribe", { email, source: "footer" });
      setStatus("ok");
      setMessage(data.already ? "You're already on the list ✓" : "You're in ✓");
      try { localStorage.setItem("mercuri-global_newsletter_email", email); } catch { /* ignore */ }
      setTimeout(() => { setStatus("idle"); setEmail(""); setMessage(""); }, 3500);
    } catch (err) {
      setStatus("error");
      setMessage(err.response?.data?.detail || "Please try again");
      setTimeout(() => { setStatus("idle"); setMessage(""); }, 3500);
    }
  };

  return (
    <div className="bg-gradient-to-r from-[#111827] via-[#0F1113] to-[#0B1220] border-b border-neutral-800/50">
      <div className="max-w-7xl mx-auto px-4 py-6 flex flex-col md:flex-row items-center gap-4 min-w-0">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="h-10 w-10 rounded-full bg-gradient-to-br from-[#7DD3FC] to-[#2563EB] grid place-items-center shrink-0">
            <Mail className="h-5 w-5 text-white" />
          </div>
          <div className="min-w-0">
            <div className="text-white font-semibold text-sm sm:text-base">Get the best deals in your inbox</div>
            <div className="text-neutral-400 text-xs">Weekly picks · Flash sales · Zero spam · Unsubscribe anytime</div>
          </div>
        </div>
        <form onSubmit={submit} className="w-full md:w-auto flex flex-col sm:flex-row items-stretch sm:items-center gap-2 min-w-0" data-testid="newsletter-form">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="flex-1 min-w-0 sm:w-72 h-11 px-4 rounded-full bg-white/10 border border-white/15 text-white placeholder:text-neutral-500 text-sm focus:outline-none focus:ring-2 focus:ring-[#2563EB]/50 focus:border-[#2563EB] transition"
            data-testid="newsletter-email-input"
            aria-label="Newsletter email"
          />
          <button
            type="submit"
            disabled={status === "loading"}
            className="h-11 px-5 rounded-full bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] hover:brightness-110 disabled:opacity-60 text-white text-sm font-semibold shadow-sm hover:shadow-md transition-all flex items-center gap-1.5 whitespace-nowrap"
            data-testid="newsletter-submit-btn"
          >
            {status === "loading" && "…"}
            {status === "ok" && (message || "You're in ✓")}
            {status === "error" && (message || "Try again")}
            {status === "idle" && (<>Subscribe <ArrowRight className="h-4 w-4" /></>)}
          </button>
        </form>
      </div>
    </div>
  );
};

const Footer = () => (
  <footer className="bg-[#0F1113] text-neutral-300 mt-16">
    <NewsletterStrip />
    <div className="max-w-7xl mx-auto px-4 py-14 grid grid-cols-2 md:grid-cols-4 gap-8">
      <div>
        <div className="flex items-center gap-2 mb-3">
          <BrandMark size={36} variant="outline" data-testid="footer-logo" />
          <span className="font-bold text-lg text-[#FF7A18]">Mercuri-global</span>
        </div>
        <p className="text-sm text-neutral-400 leading-relaxed">
          Your global marketplace for fashion, electronics, home & everyday essentials — millions of items, verified sellers, buyer protection.
        </p>
        <div className="flex items-center gap-1 mt-4">
          <a href="#" aria-label="Facebook" className="w-9 h-9 grid place-items-center rounded-lg text-neutral-500 hover:text-white hover:bg-neutral-800 transition"><Facebook className="h-4 w-4" /></a>
          <a href="#" aria-label="Twitter" className="w-9 h-9 grid place-items-center rounded-lg text-neutral-500 hover:text-white hover:bg-neutral-800 transition"><Twitter className="h-4 w-4" /></a>
          <a href="#" aria-label="Instagram" className="w-9 h-9 grid place-items-center rounded-lg text-neutral-500 hover:text-white hover:bg-neutral-800 transition"><Instagram className="h-4 w-4" /></a>
          <a href="#" aria-label="YouTube" className="w-9 h-9 grid place-items-center rounded-lg text-neutral-500 hover:text-white hover:bg-neutral-800 transition"><Youtube className="h-4 w-4" /></a>
        </div>
      </div>
      <div>
        <h4 className="font-semibold text-white mb-3">Customer Service</h4>
        <ul className="space-y-2 text-sm text-neutral-400">
          <li><Link to="/" className="hover:text-[#FF7A18]">Help Center</Link></li>
          <li><Link to="/" className="hover:text-[#FF7A18]">Returns</Link></li>
          <li><Link to="/" className="hover:text-[#FF7A18]">Shipping Info</Link></li>
          <li><Link to="/" className="hover:text-[#FF7A18]">Buyer Protection</Link></li>
        </ul>
      </div>
      <div>
        <h4 className="font-semibold text-white mb-3">About Us</h4>
        <ul className="space-y-2 text-sm text-neutral-400">
          <li><Link to="/" className="hover:text-[#FF7A18]">Company Info</Link></li>
          <li><Link to="/" className="hover:text-[#FF7A18]">Careers</Link></li>
          <li><Link to="/" className="hover:text-[#FF7A18]">Press &amp; News</Link></li>
          <li><Link to="/" className="hover:text-[#FF7A18]">Terms &amp; Privacy</Link></li>
        </ul>
      </div>
      <div>
        <h4 className="font-semibold text-white mb-3">Quick Links</h4>
        <ul className="space-y-2 text-sm text-neutral-400">
          <li><Link to="/" className="hover:text-[#FF7A18]">Gift Cards</Link></li>
          <li><Link to="/search?sort=trending" className="hover:text-[#FF7A18]">Deals</Link></li>
          <li><Link to="/search?sort=newest" className="hover:text-[#FF7A18]">Coupons</Link></li>
          <li><Link to="/sell" className="hover:text-[#FF7A18]">Sell on Mercuri-global</Link></li>
        </ul>
      </div>
    </div>
    <div className="border-t border-neutral-800">
      <div className="max-w-7xl mx-auto px-4 py-5 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-neutral-500">
        <span>© {new Date().getFullYear()} Mercuri-global. All rights reserved.</span>
        <span>Secure checkout · Global shipping · Buyer protection</span>
      </div>
    </div>
  </footer>
);

export default Footer;
