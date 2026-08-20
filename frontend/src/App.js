import React from "react";
import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { CurrencyProvider } from "@/context/CurrencyContext";
import { LanguageProvider } from "@/context/LanguageContext";
import { Toaster } from "@/components/ui/toaster";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import Home from "@/pages/Home";
import Search from "@/pages/Search";
import ListingDetail from "@/pages/ListingDetail";
import Products from "@/pages/Products";
import ProductDetail from "@/pages/ProductDetail";
import Sell from "@/pages/Sell";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import Cart from "@/pages/Cart";
import Checkout from "@/pages/Checkout";
import Favorites from "@/pages/Favorites";
import Profile from "@/pages/Profile";
import Admin from "@/pages/Admin";
import Wallet from "@/pages/Wallet";
import Affiliate from "@/pages/Affiliate";
import Referrals from "@/pages/Referrals";
import StoreManage from "@/pages/StoreManage";
import StorePage from "@/pages/StorePage";
import AffiliateRedirect from "@/pages/AffiliateRedirect";
import { ChatThreads, ChatRoom } from "@/pages/Chat";
import StoreAnalytics from "@/pages/StoreAnalytics";
import PayoutDashboard from "@/pages/PayoutDashboard";
import Verification from "@/pages/Verification";
import SellerApply from "@/pages/SellerApply";
import EditListing from "@/pages/EditListing";
import BuyerProgressToast from "@/components/BuyerProgressToast";
import Disputes from "@/pages/Disputes";
import SplashScreen from "@/components/SplashScreen";
import AuthCallback from "@/pages/AuthCallback";
import StoresMarketplace from "@/pages/StoresMarketplace";
import AdminCoupons from "@/pages/AdminCoupons";
import PaymentSuccess from "@/pages/PaymentSuccess";
import PaymentCancel from "@/pages/PaymentCancel";
import GeoCurrencyPrompt from "@/components/GeoCurrencyPrompt";
import GlobalWalletToaster from "@/components/GlobalWalletToaster";
import PWAInstallPrompt from "@/components/PWAInstallPrompt";

function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <CurrencyProvider>
          <div className="App min-h-screen w-full max-w-full overflow-x-hidden flex flex-col bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100 transition-colors">
            <SplashScreen />
            <BrowserRouter>
              <AuthProvider>
                <Header />
                <BuyerProgressToast />
                <main className="flex-1">
                  <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/search" element={<Search />} />
                    <Route path="/marketplace" element={<Search />} />
                    <Route path="/marketplace/stores" element={<StoresMarketplace />} />
                    <Route path="/listing/:id" element={<ListingDetail />} />
                    <Route path="/products" element={<Products />} />
                    <Route path="/products/:id" element={<ProductDetail />} />
                    <Route path="/sell" element={<Sell />} />
                    <Route path="/dashboard/list-product" element={<Sell />} />
                    <Route path="/login" element={<Login />} />
                    <Route path="/register" element={<Register />} />
                    <Route path="/forgot" element={<ForgotPassword />} />
                    <Route path="/reset-password" element={<ResetPassword />} />
                    <Route path="/auth/callback" element={<AuthCallback />} />
                    <Route path="/cart" element={<Cart />} />
                    <Route path="/checkout/:id" element={<Checkout />} />
                    <Route path="/payment/success" element={<PaymentSuccess />} />
                    <Route path="/payment/cancel" element={<PaymentCancel />} />
                    <Route path="/favorites" element={<Favorites />} />
                    <Route path="/profile" element={<Profile />} />
                    <Route path="/wallet" element={<Wallet />} />
                    <Route path="/affiliate" element={<Affiliate />} />
                    <Route path="/referrals" element={<Referrals />} />
                    <Route path="/my/store" element={<StoreManage />} />
                    <Route path="/store/analytics" element={<StoreAnalytics />} />
                    <Route path="/seller/payouts" element={<PayoutDashboard />} />
                    <Route path="/store/:slug" element={<StorePage />} />
                    <Route path="/chat" element={<ChatThreads />} />
                    <Route path="/chat/:listingId/:otherId" element={<ChatRoom />} />
                    <Route path="/verify" element={<Verification />} />
                    <Route path="/seller/apply" element={<SellerApply />} />
                    <Route path="/listing/:id/edit" element={<EditListing />} />
                    <Route path="/disputes" element={<Disputes />} />
                    <Route path="/r/:code" element={<AffiliateRedirect />} />
                    <Route path="/admin/coupons" element={<AdminCoupons />} />
                    <Route path="/admin/*" element={<Admin />} />
                  </Routes>
                </main>
                <Footer />
                <Toaster />
                <GeoCurrencyPrompt />
                <GlobalWalletToaster />
                <PWAInstallPrompt />
              </AuthProvider>
            </BrowserRouter>
          </div>
        </CurrencyProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}

export default App;
