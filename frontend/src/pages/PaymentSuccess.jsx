import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import confetti from "canvas-confetti";

const MAX_ATTEMPTS = 8;
const INTERVAL_MS = 2000;

const PaymentSuccess = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const sessionId = params.get("session_id");
  const [state, setState] = useState({ phase: "polling", status: null, order_id: null, error: "" });
  const attemptsRef = useRef(0);
  const timerRef = useRef(null);
  const firedConfettiRef = useRef(false);

  useEffect(() => {
    if (!sessionId) {
      setState({ phase: "error", error: "Missing session id" });
      return;
    }
    let cancelled = false;
    const poll = async () => {
      attemptsRef.current += 1;
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (cancelled) return;
        if (data.payment_status === "paid" && data.order_id) {
          setState({ phase: "success", status: data, order_id: data.order_id });
          if (!firedConfettiRef.current) {
            firedConfettiRef.current = true;
            const colors = ["#FF211F", "#FF7A18", "#FFD166", "#06D6A0", "#118AB2"];
            const end = Date.now() + 1500;
            (function frame() {
              confetti({ particleCount: 5, angle: 60, spread: 55, startVelocity: 55, origin: { x: 0, y: 0.7 }, colors });
              confetti({ particleCount: 5, angle: 120, spread: 55, startVelocity: 55, origin: { x: 1, y: 0.7 }, colors });
              if (Date.now() < end) requestAnimationFrame(frame);
            })();
          }
          return;
        }
        if (data.payment_status === "failed" || data.payment_status === "expired") {
          setState({ phase: "failed", status: data, error: "Payment was not completed." });
          return;
        }
        if (attemptsRef.current >= MAX_ATTEMPTS) {
          setState({ phase: "timeout", status: data, error: "Still processing — we'll email you as soon as it's confirmed." });
          return;
        }
        timerRef.current = setTimeout(poll, INTERVAL_MS);
      } catch (e) {
        if (attemptsRef.current >= MAX_ATTEMPTS) {
          setState({ phase: "timeout", error: e?.response?.data?.detail || "Could not confirm status." });
        } else {
          timerRef.current = setTimeout(poll, INTERVAL_MS);
        }
      }
    };
    poll();
    return () => { cancelled = true; if (timerRef.current) clearTimeout(timerRef.current); };
  }, [sessionId]);

  return (
    <div className="max-w-lg mx-auto px-4 py-16 text-center" data-testid="payment-success-page">
      {state.phase === "polling" && (
        <>
          <div className="h-20 w-20 mx-auto rounded-full bg-gradient-to-br from-sky-400 to-sky-600 grid place-items-center shadow-xl">
            <Loader2 className="h-10 w-10 text-white animate-spin" />
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold mt-5 tracking-tight" data-testid="payment-status-heading">Confirming your payment…</h1>
          <p className="text-neutral-500 mt-2">Stripe is processing your card. This usually takes a couple of seconds.</p>
        </>
      )}

      {state.phase === "success" && (
        <>
          <div className="relative inline-block">
            <div className="absolute inset-0 rounded-full bg-emerald-500/20 blur-2xl scale-125" />
            <div className="relative h-20 w-20 mx-auto rounded-full bg-gradient-to-br from-emerald-400 to-emerald-600 grid place-items-center shadow-xl">
              <CheckCircle2 className="h-10 w-10 text-white" />
            </div>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold mt-5 tracking-tight" data-testid="payment-success-heading">Payment received 🎉</h1>
          <p className="text-neutral-500 mt-2">
            Your order is confirmed. Track it any time from your profile.
          </p>
          <div className="mt-6 rounded-2xl border border-neutral-200 bg-white p-4 text-left text-sm space-y-1.5">
            <div className="flex justify-between text-neutral-700">
              <span>Order ID</span>
              <span className="font-mono text-xs" data-testid="payment-success-order-id">{state.order_id?.slice(0, 8)}</span>
            </div>
            <div className="flex justify-between text-neutral-700">
              <span>Amount</span>
              <span className="tabular-nums font-semibold">${Number(state.status?.amount || 0).toFixed(2)}</span>
            </div>
          </div>
          <div className="mt-6 flex gap-2 justify-center">
            <Button onClick={() => navigate("/profile?tab=orders")} className="bg-[#FF211F] hover:bg-[#e01d1b]" data-testid="payment-success-track">
              Track my order
            </Button>
            <Button variant="outline" onClick={() => navigate("/")}>Keep shopping</Button>
          </div>
        </>
      )}

      {(state.phase === "failed" || state.phase === "timeout" || state.phase === "error") && (
        <>
          <div className="h-20 w-20 mx-auto rounded-full bg-gradient-to-br from-red-400 to-red-600 grid place-items-center shadow-xl">
            <XCircle className="h-10 w-10 text-white" />
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold mt-5">
            {state.phase === "timeout" ? "Still processing…" : "Payment issue"}
          </h1>
          <p className="text-neutral-500 mt-2">{state.error}</p>
          <div className="mt-6 flex gap-2 justify-center">
            <Link to="/"><Button variant="outline">Back to home</Button></Link>
            <Link to="/profile?tab=orders"><Button className="bg-[#FF211F] hover:bg-[#e01d1b]">Check my orders</Button></Link>
          </div>
        </>
      )}
    </div>
  );
};

export default PaymentSuccess;
