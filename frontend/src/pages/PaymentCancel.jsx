import React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { XCircle } from "lucide-react";

const PaymentCancel = () => {
  const [params] = useSearchParams();
  const listingId = params.get("listing_id");
  return (
    <div className="max-w-lg mx-auto px-4 py-16 text-center" data-testid="payment-cancel-page">
      <div className="h-20 w-20 mx-auto rounded-full bg-neutral-100 grid place-items-center">
        <XCircle className="h-10 w-10 text-neutral-500" />
      </div>
      <h1 className="text-2xl sm:text-3xl font-extrabold mt-5 tracking-tight">Payment cancelled</h1>
      <p className="text-neutral-500 mt-2">No card was charged. Your cart is still saved and you can try again any time.</p>
      <div className="mt-6 flex gap-2 justify-center">
        {listingId ? (
          <Link to={`/checkout/${listingId}`}>
            <Button className="bg-[#FF211F] hover:bg-[#e01d1b]" data-testid="payment-cancel-retry">Try again</Button>
          </Link>
        ) : (
          <Link to="/"><Button className="bg-[#FF211F] hover:bg-[#e01d1b]">Back to home</Button></Link>
        )}
        <Link to="/"><Button variant="outline">Keep browsing</Button></Link>
      </div>
    </div>
  );
};

export default PaymentCancel;
