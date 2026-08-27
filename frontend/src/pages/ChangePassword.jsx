import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import api from "@/lib/api";
import { ShieldAlert, Lock, ArrowRight } from "lucide-react";
import PasswordStrengthMeter, { scorePassword } from "@/components/PasswordStrengthMeter";

/**
 * ChangePassword page — reached in two ways:
 *  1) User is force-redirected here right after login when the server
 *     flags them with `password_change_required: true` (admin reset or
 *     legacy-user migration). In this mode we hide the "old password"
 *     field because the backend accepts a change without it while the
 *     flag is set.
 *  2) User walks in manually from Profile → Change Password. In that
 *     mode the current password IS required.
 */
const ChangePassword = () => {
  const navigate = useNavigate();
  const { user, refresh } = useAuth();
  const { toast } = useToast();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const forced = !!(user && user.must_change_password);

  const submit = async (e) => {
    e.preventDefault();
    if (newPassword.length < 6) {
      toast({ title: "Password too short", description: "Use at least 6 characters.", variant: "destructive" });
      return;
    }
    if (scorePassword(newPassword).level < 1) {
      toast({ title: "Password too weak", description: "Pick something a little stronger.", variant: "destructive" });
      return;
    }
    if (newPassword !== confirmPassword) {
      toast({ title: "Passwords don't match", variant: "destructive" });
      return;
    }
    setLoading(true);
    try {
      const body = { new_password: newPassword };
      if (!forced) body.old_password = oldPassword;
      await api.post("/auth/change-password", body);
      await refresh();
      toast({ title: "Password updated", description: "You're all set." });
      navigate("/");
    } catch (err) {
      toast({
        title: "Change failed",
        description: err.response?.data?.detail || "Please try again.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto px-4 py-8 sm:py-14" data-testid="change-password-page">
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6 sm:p-8 shadow-sm">
        {forced && (
          <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/30 p-3 flex gap-2">
            <ShieldAlert className="h-5 w-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div className="text-sm text-amber-800 dark:text-amber-200">
              For your security, please pick a new password before continuing.
              An admin recently issued you a temporary one.
            </div>
          </div>
        )}
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
          {forced ? "Set your password" : "Change password"}
        </h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Choose something at least 6 characters long.
        </p>
        <form onSubmit={submit} className="mt-6 space-y-4" data-testid="change-password-form">
          {!forced && (
            <div>
              <Label htmlFor="cp-old">Current password</Label>
              <div className="relative mt-1">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
                <Input
                  id="cp-old"
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  required
                  className="pl-9 min-h-[44px]"
                  data-testid="cp-old-input"
                />
              </div>
            </div>
          )}
          <div>
            <Label htmlFor="cp-new">New password</Label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
              <Input
                id="cp-new"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={6}
                className="pl-9 min-h-[44px]"
                data-testid="cp-new-input"
              />
            </div>
            <PasswordStrengthMeter password={newPassword} />
          </div>
          <div>
            <Label htmlFor="cp-confirm">Confirm new password</Label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
              <Input
                id="cp-confirm"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={6}
                className="pl-9 min-h-[44px]"
                data-testid="cp-confirm-input"
              />
            </div>
          </div>
          <Button
            type="submit"
            disabled={loading}
            className="w-full min-h-[44px] bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] hover:brightness-110"
            data-testid="cp-submit-btn"
          >
            {loading ? "Updating…" : <>Update password <ArrowRight className="h-4 w-4 ml-1" /></>}
          </Button>
        </form>
      </div>
    </div>
  );
};

export default ChangePassword;
