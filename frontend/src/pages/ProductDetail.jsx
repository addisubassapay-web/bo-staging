import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Package, ExternalLink, ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";

const formatMoney = (amount, currency = "USD") => {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `$${Number(amount).toFixed(2)}`;
  }
};

const ProductDetail = () => {
  const { id } = useParams();
  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeImg, setActiveImg] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const { data } = await api.get(`/products/${id}`);
        if (!cancelled) {
          setProduct(data);
          setActiveImg(0);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.status === 404 ? "not-found" : "error");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12">
        <div className="grid md:grid-cols-2 gap-8 animate-pulse">
          <div className="aspect-square bg-neutral-100 dark:bg-neutral-800 rounded-2xl" />
          <div className="space-y-3">
            <div className="h-8 bg-neutral-100 dark:bg-neutral-800 rounded w-3/4" />
            <div className="h-6 bg-neutral-100 dark:bg-neutral-800 rounded w-1/3" />
            <div className="h-24 bg-neutral-100 dark:bg-neutral-800 rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (error === "not-found" || !product) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center" data-testid="product-not-found">
        <Package className="h-12 w-12 text-neutral-300 mx-auto mb-3" />
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
          Product not found
        </h1>
        <p className="text-neutral-500 mt-2">
          This product may have been removed or the link is incorrect.
        </p>
        <Link to="/products" className="inline-block mt-6">
          <Button variant="outline">
            <ArrowLeft className="h-4 w-4 mr-1" /> Back to catalog
          </Button>
        </Link>
      </div>
    );
  }

  const images = product.images?.length ? product.images : [];
  const currentImg = images[activeImg];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8" data-testid="product-detail-page">
      <Link
        to="/products"
        className="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-[#FF211F] mb-4"
        data-testid="product-back-link"
      >
        <ArrowLeft className="h-4 w-4" /> Back to catalog
      </Link>

      <div className="grid md:grid-cols-2 gap-8">
        {/* Gallery */}
        <div>
          <div className="aspect-square bg-neutral-100 dark:bg-neutral-800 rounded-2xl overflow-hidden relative">
            {currentImg ? (
              <img
                src={currentImg}
                alt={product.title}
                className="w-full h-full object-contain"
                data-testid="product-main-image"
              />
            ) : (
              <div className="w-full h-full grid place-items-center text-neutral-400">
                <Package className="h-16 w-16" />
              </div>
            )}
            {images.length > 1 && (
              <>
                <button
                  onClick={() => setActiveImg((i) => (i - 1 + images.length) % images.length)}
                  className="absolute left-2 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-white/90 hover:bg-white grid place-items-center shadow"
                  aria-label="Previous image"
                  data-testid="product-img-prev"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button
                  onClick={() => setActiveImg((i) => (i + 1) % images.length)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-white/90 hover:bg-white grid place-items-center shadow"
                  aria-label="Next image"
                  data-testid="product-img-next"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              </>
            )}
          </div>
          {images.length > 1 && (
            <div className="mt-3 flex gap-2 overflow-x-auto scrollbar-hide">
              {images.map((src, i) => (
                <button
                  key={i}
                  onClick={() => setActiveImg(i)}
                  className={`h-16 w-16 shrink-0 rounded-lg overflow-hidden border-2 transition ${
                    i === activeImg
                      ? "border-[#FF211F]"
                      : "border-transparent hover:border-neutral-300"
                  }`}
                  data-testid={`product-thumb-${i}`}
                >
                  <img src={src} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Info */}
        <div>
          {product.category ? (
            <Badge variant="outline" className="mb-3 uppercase text-[10px] tracking-wide">
              {product.category}
            </Badge>
          ) : null}
          <h1
            className="text-2xl md:text-3xl font-bold text-neutral-900 dark:text-neutral-100"
            data-testid="product-title"
          >
            {product.title}
          </h1>

          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-[#FF211F]" data-testid="product-price">
              {formatMoney(product.price, product.currency)}
            </span>
            <span className="text-sm text-neutral-400">{product.currency}</span>
          </div>

          {product.description ? (
            <p
              className="mt-6 text-neutral-700 dark:text-neutral-300 whitespace-pre-line leading-relaxed"
              data-testid="product-description"
            >
              {product.description}
            </p>
          ) : null}

          <dl className="mt-8 grid grid-cols-2 gap-3 text-sm border-t border-neutral-200 dark:border-neutral-800 pt-6">
            {product.sku ? (
              <>
                <dt className="text-neutral-500">SKU</dt>
                <dd className="font-mono text-xs text-neutral-800 dark:text-neutral-200 break-all">
                  {product.sku}
                </dd>
              </>
            ) : null}
            <dt className="text-neutral-500">Listed</dt>
            <dd className="text-neutral-800 dark:text-neutral-200">
              {new Date(product.created_at).toLocaleDateString()}
            </dd>
            {product.updated_at ? (
              <>
                <dt className="text-neutral-500">Updated</dt>
                <dd className="text-neutral-800 dark:text-neutral-200">
                  {new Date(product.updated_at).toLocaleDateString()}
                </dd>
              </>
            ) : null}
            <dt className="text-neutral-500">Status</dt>
            <dd>
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                  product.is_active
                    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                    : "bg-neutral-200 text-neutral-600"
                }`}
              >
                {product.is_active ? "Available" : "Unavailable"}
              </span>
            </dd>
          </dl>

          {product.source_url ? (
            <a
              href={product.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-6 inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-[#FF211F]"
              data-testid="product-source-link"
            >
              View original source <ExternalLink className="h-3.5 w-3.5" />
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default ProductDetail;
