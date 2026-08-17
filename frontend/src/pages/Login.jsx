import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import BrandMark from "@/components/BrandMark";
import GoogleLoginButton from "@/components/GoogleLoginButton";
import PasswordInput from "@/components/PasswordInput";
import { ShieldCheck, Mail, Lock, ArrowRight } from "lucide-react";

const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const { toast } = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [lockedUntil, setLockedUntil] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (lockedUntil && Date.now() < lockedUntil) {
      const secs = Math.ceil((lockedUntil - Date.now()) / 1000);
      toast({ title: `Too many attempts`, description: `Please wait ${secs}s before trying again.`, variant: "destructive" });
      return;
    }
    setLoading(true);
    try {
      const u = await login(email, password, { remember });
      toast({ title: `Welcome back, ${u.username}!` });
      const next = location.state?.from || "/";
      navigate(next);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const retryAfter = err.response?.data?.retry_after;
      if (retryAfter) setLockedUntil(Date.now() + retryAfter * 1000);
      toast({
        title: "Sign-in failed",
        description: typeof detail === "string" ? detail : "Please check your credentials and try again.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] relative overflow-hidden" data-testid="login-page">
      {/* Split-panel professional layout */}
      <div className="grid lg:grid-cols-2 min-h-[calc(100vh-4rem)]">
        {/* Left — brand pane */}
        <div
          className="relative hidden lg:flex flex-col justify-between p-12 text-white overflow-hidden"
          style={{
            background:
              "radial-gradient(circle at 20% 15%, rgba(255,122,24,0.55) 0%, transparent 45%), radial-gradient(circle at 85% 85%, rgba(37,99,235,0.6) 0%, transparent 45%), linear-gradient(160deg, #0F172A 0%, #1E293B 100%)",
          }}
        >
          <div className="pointer-events-none absolute -top-24 -right-24 h-96 w-96 rounded-full bg-[#7DD3FC] opacity-20 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-24 -left-24 h-96 w-96 rounded-full bg-[#FF7A18] opacity-20 blur-3xl" />

          <BrandMark size={64} showWordmark animated wordmarkClassName="text-white" />

          <div className="max-w-md">
            <h2 className="text-4xl font-extrabold leading-tight">Trusted marketplace for every seller.</h2>
            <p className="mt-4 text-white/80 leading-relaxed">
              Buy, sell, and grow with 200+ curated products, live Amazon-refreshed inventory, and a secure escrow wallet.
            </p>
            <ul className="mt-8 space-y-3 text-sm text-white/90">
              <li className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-emerald-300" /> Bank-grade encryption & rate-limited login</li>
              <li className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-emerald-300" /> Escrow protection with dispute resolution</li>
              <li className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-emerald-300" /> 10 languages · 13 currencies · live FX</li>
            </ul>
          </div>

          <div className="text-xs text-white/60">© {new Date().getFullYear()} Mercari Global · All rights reserved.</div>
        </div>

        {/* Right — form pane */}
        <div className="relative flex items-center justify-center p-6 sm:p-10">
          <div className="absolute inset-0 -z-10 lg:hidden" style={{
            background: "radial-gradient(circle at 20% 20%, #FFF7ED 0%, transparent 55%), radial-gradient(circle at 80% 80%, #DBEAFE 0%, transparent 55%), linear-gradient(180deg, #FFFBF6 0%, #F8FAFC 100%)",
          }} />
          <div className="w-full max-w-md">
            <div className="flex justify-center mb-6 lg:hidden">
              <BrandMark size={64} showWordmark animated wordmarkClassName="dark:text-neutral-100" />
            </div>

            <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl p-6 sm:p-8 shadow-xl shadow-neutral-200/50 dark:shadow-black/40">
              <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-800 dark:text-emerald-300">
                <ShieldCheck className="h-3 w-3" /> Secure sign-in
              </div>
              <h1 className="mt-3 text-2xl sm:text-3xl font-extrabold text-neutral-900 dark:text-neutral-100">Welcome back</h1>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">Sign in to continue to your Mercari account.</p>

              <form onSubmit={submit} className="mt-6 space-y-4" data-testid="login-form">
                <div>
                  <Label htmlFor="email" className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Email</Label>
                  <div className="relative mt-1.5">
                    <Mail className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <Input
                      id="email"
                      type="email"
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="pl-9 h-11 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB]"
                      data-testid="login-email"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between">
                    <Label htmlFor="password" className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Password</Label>
                    <Link to="/forgot" className="text-xs text-[#2563EB] dark:text-[#7DD3FC] hover:underline">Forgot?</Link>
                  </div>
                  <div className="relative mt-1.5">
                    <Lock className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2 z-10" />
                    <PasswordInput
                      id="password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="pl-9 h-11 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB]"
                      testIdSuffix="login-password"
                      data-testid="login-password"
                    />
                  </div>
                </div>

                <label className="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400 select-none cursor-pointer">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                    className="h-4 w-4 rounded border-neutral-300 accent-[#2563EB]"
                    data-testid="login-remember"
                  />
                  Keep me signed in on this device
                </label>

                <Button
                  type="submit"
                  disabled={loading || (lockedUntil && Date.now() < lockedUntil)}
                  className="w-full bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] hover:brightness-110 text-white h-11 shadow-sm hover:shadow-md transition-all font-semibold"
                  data-testid="login-submit"
                >
                  {loading ? "Verifying…" : <>Sign in <ArrowRight className="h-4 w-4 ml-1" /></>}
                </Button>
              </form>

              <div className="my-6 flex items-center gap-3">
                <div className="flex-1 h-px bg-neutral-200 dark:bg-neutral-700" />
                <span className="text-[11px] uppercase tracking-widest text-neutral-400 dark:text-neutral-500">or</span>
                <div className="flex-1 h-px bg-neutral-200 dark:bg-neutral-700" />
              </div>

              <GoogleLoginButton label="Continue with Google" testId="login-google-btn" />

              <p className="mt-6 text-sm text-center text-neutral-600 dark:text-neutral-400">
                New to Mercari? <Link to="/register" className="text-[#2563EB] dark:text-[#7DD3FC] font-semibold hover:underline" data-testid="login-to-register">Create your account</Link>
              </p>
            </div>

            <p className="text-[11px] text-center mt-4 text-neutral-400 dark:text-neutral-500">
              Protected by rate-limited authentication. After 5 failed attempts your account is locked for 15 minutes.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
