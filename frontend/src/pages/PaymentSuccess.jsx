import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Info } from "lucide-react";

/**
 * PaymentSuccess — the Stripe card-checkout landing page has been retired
 * alongside the Stripe integration. If someone follows a stale bookmark or
 * an old email link here, we surface a simple retro-friendly message + a
 * link back to their orders instead of a broken polling spinner.
 */
const PaymentSuccess = () => (
  <div className="max-w-md mx-auto px-4 py-16 text-center" data-testid="payment-success-page">
    <div className="mx-auto h-14 w-14 rounded-full bg-neutral-100 grid place-items-center mb-4">
      <Info className="h-6 w-6 text-neutral-500" />
    </div>
    <h1 className="text-xl font-semibold">Card payments are offline</h1>
    <p className="text-neutral-600 mt-2 text-sm">
      Card checkout has been retired. Please pay from your wallet, crypto, or
      bank transfer at checkout. If you were charged and don&apos;t see your
      order, contact support and we&apos;ll sort it out right away.
    </p>
    <div className="mt-6 flex gap-2 justify-center">
      <Link to="/profile?tab=orders">
        <Button className="bg-[#DC2626] hover:bg-[#e01d1b]" data-testid="ps-view-orders">
          View my orders
        </Button>
      </Link>
      <Link to="/">
        <Button variant="outline" data-testid="ps-back-home">Back home</Button>
      </Link>
    </div>
  </div>
);

export default PaymentSuccess;
