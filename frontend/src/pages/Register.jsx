import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";

const Register = () => {
  const navigate = useNavigate();
  const { register } = useAuth();
  const { toast } = useToast();
  const [form, setForm] = useState({ email: "", username: "", password: "" });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (form.password.length < 6) {
      toast({ title: "Password too short", description: "At least 6 characters.", variant: "destructive" });
      return;
    }
    setLoading(true);
    try {
      const u = await register(form.email, form.username, form.password);
      toast({ title: `Welcome, ${u.username}!` });
      navigate("/");
    } catch (err) {
      toast({ title: "Sign up failed", description: err.response?.data?.detail || "Try a different email or username", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto px-4 py-16">
      <div className="bg-white border border-neutral-200 rounded-xl p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-center">Create your account</h1>
        <p className="text-sm text-neutral-500 text-center mt-1">Join Mercari to start buying and selling.</p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <Label>Email</Label>
            <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required className="mt-1" />
          </div>
          <div>
            <Label>Username</Label>
            <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required minLength={3} maxLength={20} className="mt-1" />
          </div>
          <div>
            <Label>Password</Label>
            <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={6} className="mt-1" />
          </div>
          <Button type="submit" disabled={loading} className="w-full bg-[#FF211F] hover:bg-[#e01d1b] h-11">
            {loading ? "Creating…" : "Create account"}
          </Button>
        </form>

        <p className="mt-6 text-sm text-center text-neutral-600">
          Already have an account? <Link to="/login" className="text-[#FF211F] font-medium hover:underline">Log in</Link>
        </p>
      </div>
    </div>
  );
};

export default Register;
