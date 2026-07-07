import React, { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";

const AffiliateRedirect = () => {
  const { code } = useParams();
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/affiliate/track/${code}`);
        // Save code so checkout can attach it and reward the affiliate
        sessionStorage.setItem("affiliate_code", code);
        if (data.listing_id) {
          navigate(`/listing/${data.listing_id}`, { replace: true });
        } else {
          navigate("/", { replace: true });
        }
      } catch {
        navigate("/", { replace: true });
      }
    })();
  }, [code, navigate]);

  return <div className="max-w-2xl mx-auto px-4 py-16 text-center text-neutral-600">Redirecting…</div>;
};

export default AffiliateRedirect;
