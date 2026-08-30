import React, { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { Share2, Copy, Check, Twitter, Facebook, MessageCircle, Send, Link as LinkIcon, Store } from "lucide-react";
import { formatPrice } from "@/lib/api";

/**
 * StorefrontShare — one-tap share of a listing (esp. freshly-published resell items)
 * to the seller's storefront and social channels. Uses standard URL intents (no
 * OAuth needed) so it works everywhere.
 */
const buildUrls = ({ listing, storeSlug }) => {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const listingUrl = `${origin}/listing/${listing.id}?ref=push`;
  const storeUrl = storeSlug ? `${origin}/store/${storeSlug}?ref=push` : null;
  const price = formatPrice(listing.price);
  const caption = `🔥 Just added: ${listing.title} — ${price}. Grab it before it's gone!`;
  const tag = "#BlueOcean #Resell";
  const share = `${caption}\n${listingUrl}\n${tag}`;
  return {
    listingUrl,
    storeUrl,
    caption,
    share,
    twitter: `https://twitter.com/intent/tweet?text=${encodeURIComponent(share)}`,
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(listingUrl)}`,
    whatsapp: `https://api.whatsapp.com/send?text=${encodeURIComponent(share)}`,
    telegram: `https://t.me/share/url?url=${encodeURIComponent(listingUrl)}&text=${encodeURIComponent(caption)}`,
    reddit: `https://www.reddit.com/submit?url=${encodeURIComponent(listingUrl)}&title=${encodeURIComponent(listing.title)}`,
  };
};

const Channel = ({ icon: Icon, label, href, color, onClick, testid }) => {
  const cls = `min-h-[52px] flex-1 min-w-[120px] flex items-center justify-center gap-2 rounded-xl border border-neutral-200 dark:border-neutral-800 hover:border-transparent hover:text-white hover:${color} active:scale-95 transition-all text-sm font-medium bg-white dark:bg-neutral-900`;
  if (href) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={cls} data-testid={testid}>
        <Icon className="h-4 w-4" /> {label}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} className={cls} data-testid={testid}>
      <Icon className="h-4 w-4" /> {label}
    </button>
  );
};

export const StorefrontShareDialog = ({ open, onOpenChange, listing, storeSlug, headline = "Share to boost your first sale" }) => {
  const { toast } = useToast();
  const [copied, setCopied] = useState("");
  const urls = useMemo(() => (listing ? buildUrls({ listing, storeSlug }) : null), [listing, storeSlug]);
  if (!listing || !urls) return null;

  const copy = async (text, key) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      toast({ title: "Copied" });
      setTimeout(() => setCopied(""), 1500);
    } catch (e) { /* ignore */ }
  };

  const nativeShare = async () => {
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ title: listing.title, text: urls.caption, url: urls.listingUrl });
      } catch (e) { /* user cancelled */ }
    } else {
      copy(urls.share, "share");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="storefront-share-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Share2 className="h-5 w-5 text-[#DC2626]" />{headline}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Preview */}
          <div className="flex gap-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-3">
            {listing.images?.[0] || listing.image ? (
              <img src={listing.images?.[0] || listing.image} alt="" className="h-16 w-16 rounded-lg object-cover shrink-0" />
            ) : null}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 line-clamp-2">{listing.title}</div>
              <div className="text-sm text-[#DC2626] font-bold mt-0.5 tabular-nums">{formatPrice(listing.price)}</div>
            </div>
          </div>

          {/* Storefront link */}
          {urls.storeUrl && (
            <div>
              <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold mb-1.5 flex items-center gap-1"><Store className="h-3.5 w-3.5" /> Your storefront</div>
              <div className="flex gap-2">
                <input
                  readOnly
                  value={urls.storeUrl}
                  className="flex-1 min-w-0 h-11 px-3 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-sm font-mono truncate"
                  data-testid="storefront-store-url"
                />
                <button
                  type="button"
                  onClick={() => copy(urls.storeUrl, "store")}
                  className="min-h-[44px] min-w-[44px] px-3 rounded-lg border border-neutral-200 dark:border-neutral-800 hover:border-[#DC2626] hover:text-[#DC2626] active:scale-95 transition-all flex items-center gap-1.5 text-sm font-medium"
                  data-testid="storefront-copy-store"
                >
                  {copied === "store" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  <span className="hidden sm:inline">Copy</span>
                </button>
              </div>
            </div>
          )}

          {/* Listing link */}
          <div>
            <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold mb-1.5 flex items-center gap-1"><LinkIcon className="h-3.5 w-3.5" /> Listing link</div>
            <div className="flex gap-2">
              <input
                readOnly
                value={urls.listingUrl}
                className="flex-1 min-w-0 h-11 px-3 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-sm font-mono truncate"
                data-testid="storefront-listing-url"
              />
              <button
                type="button"
                onClick={() => copy(urls.listingUrl, "listing")}
                className="min-h-[44px] min-w-[44px] px-3 rounded-lg border border-neutral-200 dark:border-neutral-800 hover:border-[#DC2626] hover:text-[#DC2626] active:scale-95 transition-all flex items-center gap-1.5 text-sm font-medium"
                data-testid="storefront-copy-listing"
              >
                {copied === "listing" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                <span className="hidden sm:inline">Copy</span>
              </button>
            </div>
          </div>

          {/* Ready-to-post caption */}
          <div>
            <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold mb-1.5">Ready-to-post caption</div>
            <textarea
              readOnly
              value={urls.share}
              rows={3}
              className="w-full rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-sm p-2.5 resize-none"
              data-testid="storefront-caption"
            />
            <button
              type="button"
              onClick={() => copy(urls.share, "caption")}
              className="mt-2 min-h-[44px] px-4 rounded-full border border-neutral-200 dark:border-neutral-800 hover:border-[#DC2626] hover:text-[#DC2626] active:scale-95 transition-all flex items-center gap-1.5 text-sm font-medium"
              data-testid="storefront-copy-caption"
            >
              {copied === "caption" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copied === "caption" ? "Copied caption" : "Copy caption"}
            </button>
          </div>

          {/* Channel buttons */}
          <div>
            <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-semibold mb-2">Post it in one tap</div>
            <div className="flex flex-wrap gap-2">
              <Channel testid="storefront-share-twitter" icon={Twitter} label="Twitter/X" href={urls.twitter} color="bg-sky-500" />
              <Channel testid="storefront-share-facebook" icon={Facebook} label="Facebook" href={urls.facebook} color="bg-blue-700" />
              <Channel testid="storefront-share-whatsapp" icon={MessageCircle} label="WhatsApp" href={urls.whatsapp} color="bg-emerald-600" />
              <Channel testid="storefront-share-telegram" icon={Send} label="Telegram" href={urls.telegram} color="bg-sky-600" />
              <Channel testid="storefront-share-native" icon={Share2} label="More…" onClick={nativeShare} color="bg-[#DC2626]" />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={() => onOpenChange(false)}
            className="min-h-[44px] w-full sm:w-auto bg-[#DC2626] hover:bg-[#e01d1b] text-white"
            data-testid="storefront-share-close"
          >Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

/**
 * Trigger button — pill-shaped, high-contrast. Use anywhere.
 */
export const StorefrontShareButton = ({ listing, storeSlug, label = "Share to storefront", testid = "storefront-share-btn", className = "" }) => {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        type="button"
        onClick={() => setOpen(true)}
        className={`min-h-[44px] rounded-full gap-1.5 bg-gradient-to-r from-[#5459E8] to-[#818CF8] hover:brightness-110 text-white ${className}`}
        data-testid={testid}
      >
        <Share2 className="h-4 w-4" /> {label}
      </Button>
      <StorefrontShareDialog open={open} onOpenChange={setOpen} listing={listing} storeSlug={storeSlug} />
    </>
  );
};

export default StorefrontShareButton;
