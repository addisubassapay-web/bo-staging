import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import BrandMark from "@/components/BrandMark";

const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const { toast } = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const u = await login(email, password);
      toast({ title: `Welcome back, ${u.username}!` });
      const next = location.state?.from || "/";
      navigate(next);
    } catch (err) {
      toast({ title: "Log in failed", description: err.response?.data?.detail || "Check your credentials", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = (kind) => {
    if (kind === "admin") {
      setEmail("admin@mercari.local");
      setPassword("admin123");
    } else {
      setEmail("sophia_style@demo.local");
      setPassword("demo1234");
    }
  };

  return (
    <div className="max-w-md mx-auto px-4 py-16">
      <div className="flex justify-center mb-6">
        <BrandMark size={80} showWordmark animated data-testid="login-logo" />
      </div>
      <div className="bg-white border border-neutral-200 rounded-xl p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-center">Log in to Mercari</h1>
        <p className="text-sm text-neutral-500 text-center mt-1">Buy, sell, and save your favorites.</p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <Label>Email</Label>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="mt-1" />
          </div>
          <div>
            <Label>Password</Label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required className="mt-1" />
          </div>
          <Button type="submit" disabled={loading} className="w-full bg-[#FF211F] hover:bg-[#e01d1b] h-11">
            {loading ? "Logging in…" : "Log in"}
          </Button>
        </form>

        <div className="mt-4 flex gap-2">
          <Button type="button" variant="outline" size="sm" className="flex-1" onClick={() => fillDemo("user")}>Demo user</Button>
          <Button type="button" variant="outline" size="sm" className="flex-1" onClick={() => fillDemo("admin")}>Demo admin</Button>
        </div>

        <p className="mt-6 text-sm text-center text-neutral-600">
          New here? <Link to="/register" className="text-[#FF211F] font-medium hover:underline">Create an account</Link>
        </p>
      </div>
    </div>
  );
};

export default Login;
