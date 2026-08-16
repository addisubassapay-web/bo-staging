import React, { useState, useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import api from "@/lib/api";
import BrandMark from "@/components/BrandMark";

const Register = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { toast } = useToast();
  const [form, setForm] = useState({ email: "", username: "", password: "", referral_code: "" });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const ref = searchParams.get("ref");
    if (ref) setForm((f) => ({ ...f, referral_code: ref.toUpperCase() }));
  }, [searchParams]);

  const submit = async (e) => {
    e.preventDefault();
    if (form.password.length < 6) {
      toast({ title: "Password too short", description: "At least 6 characters.", variant: "destructive" });
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/register", {
        email: form.email,
        username: form.username,
        password: form.password,
        referral_code: form.referral_code || null,
      });
      localStorage.setItem("mercari_token", data.token);
      toast({ title: `Welcome, ${data.user.username}!` });
      window.location.href = "/";
    } catch (err) {
      toast({ title: "Sign up failed", description: err.response?.data?.detail || "Try a different email or username", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] px-4 py-16 relative overflow-hidden">
      {/* Soft gradient background — light + dark variants */}
      <div className="absolute inset-0 -z-10 dark:hidden" style={{
        background: "radial-gradient(circle at 20% 20%, #FFF7ED 0%, transparent 55%), radial-gradient(circle at 80% 80%, #DBEAFE 0%, transparent 55%), linear-gradient(180deg, #FFFBF6 0%, #F8FAFC 100%)",
      }} />
      <div className="absolute inset-0 -z-10 hidden dark:block" style={{
        background: "radial-gradient(circle at 20% 20%, rgba(255,122,24,0.18) 0%, transparent 55%), radial-gradient(circle at 80% 80%, rgba(37,99,235,0.22) 0%, transparent 55%), linear-gradient(180deg, #0B0D10 0%, #111318 100%)",
      }} />
      <div className="absolute -top-24 -right-24 h-72 w-72 rounded-full bg-[#7DD3FC] opacity-20 dark:opacity-25 blur-3xl -z-10" />
      <div className="absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-[#FF7A18] opacity-15 dark:opacity-20 blur-3xl -z-10" />

      <div className="max-w-md mx-auto">
        <div className="flex justify-center mb-6">
          <BrandMark size={80} showWordmark animated wordmarkClassName="dark:text-neutral-100" data-testid="register-logo" />
        </div>
        <div className="bg-white/80 dark:bg-neutral-900/70 backdrop-blur border border-white/60 dark:border-neutral-800 rounded-2xl p-8 shadow-xl shadow-orange-100/40 dark:shadow-blue-950/40 ring-1 ring-neutral-100 dark:ring-neutral-800">
          <h1 className="text-2xl font-bold text-center dark:text-neutral-100">Create your account</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 text-center mt-1">Join Mercari to start buying and selling.</p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <Label>Email</Label>
            <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required className="mt-1 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB] transition" />
          </div>
          <div>
            <Label>Username</Label>
            <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required minLength={3} maxLength={20} className="mt-1 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB] transition" />
          </div>
          <div>
            <Label>Password</Label>
            <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={6} className="mt-1 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB] transition" />
          </div>
          <div>
            <Label>Referral code <span className="text-xs text-neutral-400">(optional)</span></Label>
            <Input value={form.referral_code} onChange={(e) => setForm({ ...form, referral_code: e.target.value.toUpperCase() })} placeholder="Have a friend's code?" className="mt-1 font-mono uppercase focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB] transition" maxLength={12} />
          </div>
          <Button type="submit" disabled={loading} className="w-full bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] hover:brightness-110 text-white h-11 shadow-sm hover:shadow-md transition-all">
            {loading ? "Creating…" : "Create account"}
          </Button>
        </form>

        <p className="mt-6 text-sm text-center text-neutral-600 dark:text-neutral-400">
          Already have an account? <Link to="/login" className="text-[#2563EB] dark:text-[#7DD3FC] font-medium hover:underline">Log in</Link>
        </p>
        </div>
      </div>
    </div>
  );
};

export default Register;
