import React from "react";
import { useFontSize } from "@/context/FontSizeContext";

/**
 * FontSizePicker — three-button A-/A/A+ toggle for UI density.
 * Rendered inside the header's utility row. Uses `rem` scaling so the whole
 * layout expands/contracts proportionally; on mobile, tapping "A-" packs
 * more desktop features into the same viewport.
 */
export const FontSizePicker = ({ variant = "row" }) => {
  const { size, setSize } = useFontSize();
  const options = [
    { value: "sm", label: "A", cls: "text-[11px]", title: "Compact — fit more on screen" },
    { value: "md", label: "A", cls: "text-sm",     title: "Standard" },
    { value: "lg", label: "A", cls: "text-base",   title: "Large — easier to read" },
  ];
  const containerCls = variant === "row"
    ? "inline-flex items-center gap-0.5 rounded-full border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-0.5"
    : "flex items-center gap-1";
  return (
    <div
      className={containerCls}
      role="group"
      aria-label="Adjust text size"
      data-testid="font-size-picker"
    >
      {options.map((o) => {
        const active = size === o.value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => setSize(o.value)}
            title={o.title}
            aria-pressed={active}
            aria-label={`Text size ${o.value === "sm" ? "small" : o.value === "md" ? "medium" : "large"}`}
            data-testid={`font-size-${o.value}`}
            className={`min-h-[32px] min-w-[32px] rounded-full font-semibold leading-none transition ${o.cls} ${
              active
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-500 hover:text-neutral-900 hover:bg-neutral-100 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
};

export default FontSizePicker;
