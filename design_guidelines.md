# Merchari-global — Design Guidelines

## Brand
- **Primary red**: `#FF211F` (CTAs, active states, dispute severity)
- **Warm orange**: `#FF7A18` (accents, secondary badges, hover)
- **Gradient**: `bg-gradient-to-br from-[#FF7A18] to-[#FF211F]` (logo, hero banners, refund CTAs)

## Surfaces
- **Cards**: `rounded-2xl`, `border border-neutral-200 dark:border-neutral-800`, `bg-white dark:bg-neutral-900`
- **Hover lift**: `hover:-translate-y-0.5 hover:shadow-[0_12px_28px_-16px_rgba(255,33,31,0.25)] transition-all duration-300`
- **Rings**: `ring-1 ring-black/[0.04] dark:ring-white/10` for extra depth on media surfaces

## Typography
- **H1 (page)**: `text-2xl sm:text-4xl font-extrabold tracking-tight`
- **H2 (section)**: `text-2xl sm:text-3xl font-extrabold tracking-tight`
- **Kicker chip**: `text-[10px] uppercase tracking-[0.2em] font-semibold` inside a warm rounded-full pill
- **Body**: `text-sm text-neutral-500 dark:text-neutral-400`
- **Numbers**: append `tabular-nums` to prices, counts, page indicators

## Spacing rhythm
- Section top margin: `mt-16 sm:mt-20`
- Card grid gaps: `gap-3 sm:gap-4`
- Container padding: `px-3 sm:px-4`

## Interactions
- Hearts, arrows in "See all" links reveal on hover with `translate-x-0.5` slide
- Buttons: pill-shaped (`rounded-full`), `h-11`, `px-5 sm:px-6`
- Focus ring: `focus-visible:ring-2 focus-visible:ring-[#FF7A18]/60 focus-visible:ring-offset-2`

## Dark mode
- Always pair light + dark variants for surfaces, borders, and text
- Brand red/orange retain hue in dark mode (do not desaturate)

## Product Card
- Aspect square media, image zooms to 1.06 on hover with `ease-out duration-500`
- Favorite button: fades in on card hover; when active stays visible with red fill
- Sold state: gradient overlay + white pill ("Sold")
- Price: `font-extrabold`, previous strikethrough `text-neutral-400`
