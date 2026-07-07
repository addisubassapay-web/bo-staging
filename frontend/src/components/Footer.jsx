import React from "react";
import { Link } from "react-router-dom";

const Footer = () => (
  <footer className="bg-neutral-50 border-t border-neutral-200 mt-16">
    <div className="max-w-7xl mx-auto px-4 py-12 grid grid-cols-2 md:grid-cols-4 gap-8">
      <div>
        <h4 className="font-semibold text-neutral-900 mb-3">Company</h4>
        <ul className="space-y-2 text-sm text-neutral-600">
          <li><Link to="/" className="hover:text-[#FF211F]">About</Link></li>
          <li><Link to="/" className="hover:text-[#FF211F]">Careers</Link></li>
          <li><Link to="/" className="hover:text-[#FF211F]">Press</Link></li>
        </ul>
      </div>
      <div>
        <h4 className="font-semibold text-neutral-900 mb-3">Support</h4>
        <ul className="space-y-2 text-sm text-neutral-600">
          <li><Link to="/" className="hover:text-[#FF211F]">Help center</Link></li>
          <li><Link to="/" className="hover:text-[#FF211F]">Buyer protection</Link></li>
          <li><Link to="/" className="hover:text-[#FF211F]">Shipping</Link></li>
        </ul>
      </div>
      <div>
        <h4 className="font-semibold text-neutral-900 mb-3">Sell</h4>
        <ul className="space-y-2 text-sm text-neutral-600">
          <li><Link to="/sell" className="hover:text-[#FF211F]">Start selling</Link></li>
          <li><Link to="/" className="hover:text-[#FF211F]">Seller guide</Link></li>
          <li><Link to="/" className="hover:text-[#FF211F]">Fees</Link></li>
        </ul>
      </div>
      <div>
        <h4 className="font-semibold text-neutral-900 mb-3">Legal</h4>
        <ul className="space-y-2 text-sm text-neutral-600">
          <li><Link to="/" className="hover:text-[#FF211F]">Terms</Link></li>
          <li><Link to="/" className="hover:text-[#FF211F]">Privacy</Link></li>
          <li><Link to="/" className="hover:text-[#FF211F]">Cookies</Link></li>
        </ul>
      </div>
    </div>
    <div className="border-t border-neutral-200">
      <div className="max-w-7xl mx-auto px-4 py-6 flex items-center justify-between text-sm text-neutral-500">
        <span>© {new Date().getFullYear()} Mercari Clone. Demo build.</span>
        <span className="font-semibold text-[#FF211F]">mercari</span>
      </div>
    </div>
  </footer>
);

export default Footer;
