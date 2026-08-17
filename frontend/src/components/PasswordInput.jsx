import React, { useState, forwardRef } from "react";
import { Input } from "@/components/ui/input";
import { Eye, EyeOff } from "lucide-react";

/**
 * PasswordInput — an <Input> with an inline eye/eye-off toggle.
 * Accepts every prop the shadcn Input accepts. `testIdSuffix` powers
 * `password-toggle-{suffix}` for stable e2e selectors.
 */
const PasswordInput = forwardRef(function PasswordInput(
  { className = "", testIdSuffix = "password", ...rest },
  ref,
) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <Input
        ref={ref}
        type={visible ? "text" : "password"}
        className={`pr-10 ${className}`}
        data-testid={rest["data-testid"] || `input-${testIdSuffix}`}
        {...rest}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        tabIndex={-1}
        className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 grid place-items-center text-neutral-400 hover:text-[#2563EB] focus:outline-none focus:text-[#2563EB] transition"
        data-testid={`password-toggle-${testIdSuffix}`}
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
});

export default PasswordInput;
