import React from "react";
import { Link } from "react-router-dom";
import { Facebook, Twitter, Instagram, Youtube } from "lucide-react";

const Footer = () => (
  <footer className="bg-[#0F1113] text-neutral-300 mt-16">
    <div className="max-w-7xl mx-auto px-4 py-14 grid grid-cols-2 md:grid-cols-4 gap-8">
      <div>
        <div className="flex items-center gap-2 mb-3">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-[#FF7A18] to-[#FF211F] grid place-items-center text-white font-bold">M</div>
          <span className="font-bold text-lg text-[#FF7A18]">Mercari Global</span>
        </div>
        <p className="text-sm text-neutral-400 leading-relaxed">
          Your global marketplace for fashion, electronics, home & everyday essentials — millions of items, verified sellers, buyer protection.
        </p>
        <div className="flex items-center gap-3 mt-4">
          <a href="#" aria-label="Facebook" className="text-neutral-500 hover:text-white"><Facebook className="h-4 w-4" /></a>
          <a href="#" aria-label="Twitter" className="text-neutral-500 hover:text-white"><Twitter className="h-4 w-4" /></a>
          <a href="#" aria-label="Instagram" className="text-neutral-500 hover:text-white"><Instagram className="h-4 w-4" /></a>
          <a href="#" aria-label="YouTube" className="text-neutral-500 hover:text-white"><Youtube className="h-4 w-4" /></a>
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
          <li><Link to="/sell" className="hover:text-[#FF7A18]">Sell on Mercari</Link></li>
        </ul>
      </div>
    </div>
    <div className="border-t border-neutral-800">
      <div className="max-w-7xl mx-auto px-4 py-5 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-neutral-500">
        <span>© {new Date().getFullYear()} Mercari Global. All rights reserved.</span>
        <span>Secure checkout · Global shipping · Buyer protection</span>
      </div>
    </div>
  </footer>
);

export default Footer;
