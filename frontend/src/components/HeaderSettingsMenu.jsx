import React from "react";
import { Settings } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import ThemeToggle from "@/components/ThemeToggle";
import { FontSizePicker } from "@/components/FontSizePicker";
import CurrencyPicker from "@/components/CurrencyPicker";
import LanguagePicker from "@/components/LanguagePicker";

/**
 * HeaderSettingsMenu — one gear-icon popover housing every user-preference
 * picker (theme, text size, currency, language). Frees up ~4 slots of
 * horizontal space in the header so the wishlist / cart / auth actions
 * stay in view on medium screens.
 *
 * Each sub-picker keeps its own testid, so existing tests continue to work.
 */
const HeaderSettingsMenu = () => {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Preferences"
          title="Preferences"
          className="h-10 w-10 sm:h-11 sm:w-11 rounded-full border border-neutral-200 hover:border-[#FF7A18] dark:border-neutral-700 dark:hover:border-[#FF7A18] grid place-items-center transition"
          data-testid="header-settings-btn"
        >
          <Settings className="h-5 w-5 text-neutral-600 dark:text-neutral-300" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-72 p-0 rounded-2xl shadow-lg border-neutral-200 dark:border-neutral-800"
        data-testid="header-settings-menu"
      >
        <div className="p-4 border-b border-neutral-100 dark:border-neutral-800">
          <div className="text-xs font-semibold uppercase tracking-wider text-neutral-400">Preferences</div>
        </div>
        <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
          <SettingRow label="Appearance" hint="Light or dark mode">
            <ThemeToggle />
          </SettingRow>
          <SettingRow label="Text size" hint="Compact fits more on screen">
            <FontSizePicker />
          </SettingRow>
          <SettingRow label="Currency" hint="Prices show in your currency">
            <CurrencyPicker variant="prominent" />
          </SettingRow>
          <SettingRow label="Language" hint="Interface language">
            <LanguagePicker variant="prominent" />
          </SettingRow>
        </div>
      </PopoverContent>
    </Popover>
  );
};

const SettingRow = ({ label, hint, children }) => (
  <div className="p-4 flex items-center justify-between gap-3">
    <div className="min-w-0">
      <div className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{label}</div>
      {hint ? <div className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5 truncate">{hint}</div> : null}
    </div>
    <div className="shrink-0">{children}</div>
  </div>
);

export default HeaderSettingsMenu;
