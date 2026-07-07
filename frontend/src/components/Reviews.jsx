import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";

export const StarRating = ({ value, size = 4, onChange }) => {
  const s = `h-${size} w-${size}`;
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => {
        const filled = value >= n;
        return (
          <button
            key={n}
            type="button"
            onClick={() => onChange && onChange(n)}
            disabled={!onChange}
            className={onChange ? "cursor-pointer" : "cursor-default"}
          >
            <Star className={`${s} ${filled ? "fill-yellow-400 text-yellow-400" : "text-neutral-300"}`} />
          </button>
        );
      })}
    </div>
  );
};

export const ListingReviews = ({ listingId, sellerId }) => {
  const [reviews, setReviews] = useState([]);
  useEffect(() => {
    const url = listingId ? `/reviews/listing/${listingId}` : `/reviews/seller/${sellerId}`;
    api.get(url).then((r) => setReviews(r.data)).catch(() => {});
  }, [listingId, sellerId]);

  const avg = reviews.length ? (reviews.reduce((s, r) => s + r.rating, 0) / reviews.length) : 0;

  if (reviews.length === 0) return null;

  return (
    <div className="mt-8 border-t pt-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-neutral-900">Reviews ({reviews.length})</h2>
        <div className="flex items-center gap-2">
          <StarRating value={avg} />
          <span className="text-sm font-medium">{avg.toFixed(1)}</span>
        </div>
      </div>
      <div className="space-y-3">
        {reviews.slice(0, 6).map((r) => (
          <div key={r.id} className="border border-neutral-200 rounded-lg p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-full bg-neutral-200 grid place-items-center text-xs font-semibold">{r.reviewer_name[0].toUpperCase()}</div>
                <span className="text-sm font-medium">{r.reviewer_name}</span>
              </div>
              <StarRating value={r.rating} />
            </div>
            {r.comment && <p className="mt-2 text-sm text-neutral-700">{r.comment}</p>}
            <div className="mt-1 text-xs text-neutral-400">{new Date(r.created_at).toLocaleDateString()}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export const ReviewOrderCard = ({ order, onReviewed }) => {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(null);
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    api.get(`/reviews/order/${order.id}`).then((r) => setSubmitted(r.data));
  }, [order.id]);

  const submit = async () => {
    if (rating < 1) { toast({ title: "Please select a rating", variant: "destructive" }); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/reviews", { order_id: order.id, rating, comment });
      setSubmitted(data);
      toast({ title: "Thanks for your review!" });
      onReviewed?.();
    } catch (err) {
      toast({ title: "Failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-neutral-200 rounded-lg p-4">
      <Link to={`/listing/${order.listing_id}`} className="font-medium hover:text-[#FF211F]">{order.listing_title}</Link>
      <div className="text-xs text-neutral-500 mb-3">Seller: {order.seller_name}</div>
      {submitted ? (
        <div>
          <div className="flex items-center gap-2 mb-1"><StarRating value={submitted.rating} /><span className="text-sm text-neutral-500">You rated</span></div>
          {submitted.comment && <p className="text-sm text-neutral-700">{submitted.comment}</p>}
        </div>
      ) : (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm text-neutral-600">Your rating:</span>
            <StarRating value={rating} onChange={setRating} size={5} />
          </div>
          <Textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Share your experience (optional)…" />
          <div className="mt-2 flex justify-end">
            <Button size="sm" onClick={submit} disabled={busy} className="bg-[#FF211F] hover:bg-[#e01d1b]">
              {busy ? "Submitting…" : "Submit review"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
