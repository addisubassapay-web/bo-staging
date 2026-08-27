"""Product-category classifier.

Maps a raw Apify product record to one of the 10 marketplace categories:
    Women · Men · Kids · Electronics · Home · Beauty · Sports · Toys · Books · Handmade

Two signals, tried in order:
  1. Apify's `breadCrumbs` string (Amazon's own taxonomy). Highest quality.
  2. Title keyword scoring — the fallback for items missing breadcrumbs.

The output is one of `CANONICAL_CATEGORIES` or None if nothing matched
confidently. `None` products are kept in the catalog but will render
without a category chip.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

CANONICAL_CATEGORIES = [
    "Women", "Men", "Kids", "Electronics", "Home",
    "Beauty", "Sports", "Toys", "Books", "Handmade",
    "Computer", "Phones",
]

# ---------------------------------------------------------------------------
# Rule 1 — Amazon breadcrumb → canonical category
# ---------------------------------------------------------------------------
# We look at (usually) the top 2 breadcrumb segments. The FIRST rule that
# matches wins, so order matters — more specific matches go on top.
_BREADCRUMB_RULES: List[Tuple[re.Pattern, str]] = [
    # Books (must come before generic "Kids' Books" nesting)
    (re.compile(r"^Books\b", re.I), "Books"),
    (re.compile(r"\bKindle\s+eBooks\b", re.I), "Books"),
    (re.compile(r"\bAudible\s+Audiobooks\b", re.I), "Books"),
    (re.compile(r"\bMagazine\s+Subscriptions\b", re.I), "Books"),

    # Handmade first — before any generic Arts / Home overlap
    (re.compile(r"^Handmade\b", re.I), "Handmade"),
    (re.compile(r"\bArts,?\s+Crafts\s*&\s*Sewing\b", re.I), "Handmade"),

    # Beauty — before "Health & Household" (some hair/skin overlaps)
    (re.compile(r"^Beauty\s*&\s*Personal\s+Care\b", re.I), "Beauty"),
    (re.compile(r"^Premium\s+Beauty\b", re.I), "Beauty"),
    (re.compile(r"\bHair\s+Care\b|\bSkin\s+Care\b|\bMakeup\b|\bFragrance\b|\bNail\b|\bOral\s+Care\b", re.I), "Beauty"),

    # Kids — Baby Products & anything under Girls/Boys
    (re.compile(r"^Baby\s+Products?\b", re.I), "Kids"),
    (re.compile(r"^Baby\b", re.I), "Kids"),
    (re.compile(r"\bGirls\b|\bBoys\b|\bInfant\b|\bToddler\b|\bChildren\b|\bBaby\b|\bMaternity\b", re.I), "Kids"),

    # Toys — before Video Games / Kids overlap
    (re.compile(r"^Toys\s*&\s*Games\b", re.I), "Toys"),
    (re.compile(r"\bBoard\s+Games\b|\bPuzzles\b|\bDolls\b|\bAction\s+Figures\b|\bLEGO\b|\bStuffed\s+Animals\b", re.I), "Toys"),

    # Electronics — includes Computers, Cell Phones, Video Games hardware
    (re.compile(r"^Electronics\b", re.I), "Electronics"),
    (re.compile(r"^Computers\s*&\s*Accessories\b", re.I), "Electronics"),
    (re.compile(r"^Cell\s+Phones\s*&\s*Accessories\b", re.I), "Electronics"),
    (re.compile(r"^Video\s+Games\b", re.I), "Electronics"),
    (re.compile(r"^Camera\s*&\s*Photo\b", re.I), "Electronics"),
    (re.compile(r"^Musical\s+Instruments\b", re.I), "Electronics"),

    # Sports & Outdoors — must include shoes context via "Athletic"
    (re.compile(r"^Sports\s*&\s*Outdoors\b", re.I), "Sports"),
    (re.compile(r"^Sports\s+Collectibles\b", re.I), "Sports"),
    (re.compile(r"\bExercise\s*&\s*Fitness\b|\bOutdoor\s+Recreation\b|\bCycling\b|\bYoga\b", re.I), "Sports"),

    # Women — inside Clothing/Shoes/Jewelry
    (re.compile(r"Clothing[^>]*>\s*Women\b", re.I), "Women"),
    (re.compile(r"Shoes[^>]*>\s*Women\b", re.I), "Women"),
    (re.compile(r"\bWomen's\b|\bDresses\b|\bHandbags\b", re.I), "Women"),

    # Men — inside Clothing/Shoes/Jewelry (must come AFTER Women to prevent
    # "Men's & Women's" matches favouring Men)
    (re.compile(r"Clothing[^>]*>\s*Men\b", re.I), "Men"),
    (re.compile(r"Shoes[^>]*>\s*Men\b", re.I), "Men"),
    (re.compile(r"\bMen's\b(?!\s*&\s*Women)", re.I), "Men"),

    # Generic Clothing (bag/wallet without gender) → default to Women
    # (statistically most Amazon "unisex" fashion sells to female shoppers)
    (re.compile(r"^Clothing,\s*Shoes\s*&\s*Jewelry\b", re.I), "Women"),

    # Home & everything homelike
    (re.compile(r"^Home\s*&\s*Kitchen\b", re.I), "Home"),
    (re.compile(r"^Kitchen\s*&\s*Dining\b", re.I), "Home"),
    (re.compile(r"^Appliances\b", re.I), "Home"),
    (re.compile(r"^Furniture\b", re.I), "Home"),
    (re.compile(r"^Tools\s*&\s*Home\s+Improvement\b", re.I), "Home"),
    (re.compile(r"^Patio,?\s*Lawn\s*&\s*Garden\b", re.I), "Home"),
    (re.compile(r"^Grocery\b|^Grocery\s*&\s*Gourmet", re.I), "Home"),
    (re.compile(r"^Health\s*&\s*Household\b", re.I), "Home"),
    (re.compile(r"^Pet\s+Supplies\b", re.I), "Home"),
    (re.compile(r"^Office\s+Products\b", re.I), "Home"),
    (re.compile(r"^Industrial\s*&\s*Scientific\b", re.I), "Home"),
    (re.compile(r"^Automotive\b", re.I), "Home"),
]


def map_breadcrumb_to_category(breadcrumbs: Optional[str]) -> Optional[str]:
    """Best-effort mapping from Amazon's breadcrumb chain to a marketplace category."""
    if not breadcrumbs or not isinstance(breadcrumbs, str):
        return None
    for pattern, category in _BREADCRUMB_RULES:
        if pattern.search(breadcrumbs):
            return category
    return None


# ---------------------------------------------------------------------------
# Rule 2 — Title keyword classifier (fallback)
# ---------------------------------------------------------------------------
# Each entry: (category, list of regex tokens). We score by number of matches.
# Higher-priority categories (e.g. Beauty for "lipstick") appear before lower
# ones (Women), so ties break in the intended direction.
_TITLE_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("Books", [
        r"\bnovel\b", r"\bcookbook\b", r"\bpaperback\b", r"\bhardcover\b",
        r"\btextbook\b", r"\bstory\s+book\b", r"\bencyclopedia\b",
        r"\bbible\b", r"\bmemoir\b", r"\bfiction\b", r"\bmagazine\b",
        r"\bmanga\b", r"\bcomic\s+book\b",
    ]),
    ("Handmade", [
        r"\bhandmade\b", r"\bhand-crafted\b", r"\bhand\s+crafted\b",
        r"\bartisan\b", r"\bcustom\s+made\b", r"\bcrochet\b",
        r"\bknit(?:ted)?\s+gift\b", r"\bhand\s+embroidered\b",
    ]),
    ("Beauty", [
        r"\blipstick\b", r"\bmascara\b", r"\bfoundation\b", r"\beyeliner\b",
        r"\bshampoo\b", r"\bconditioner\b", r"\bperfume\b", r"\bcologne\b",
        r"\bserum\b", r"\bmoisturizer\b", r"\blotion\b", r"\bcosmetic\b",
        r"\bmakeup\b", r"\bskincare\b", r"\bskin\s+care\b", r"\bnail\s+polish\b",
        r"\bmascara\b", r"\bbrow\s+gel\b", r"\btoothpaste\b", r"\btoothbrush\b",
        r"\bdeodorant\b", r"\bhair\s+brush\b", r"\brazor\b", r"\bshaver\b",
        r"\bwaxing\b", r"\btweezer\b", r"\blip\s+balm\b", r"\bblush\b",
        r"\bcleanser\b", r"\bretinol\b", r"\bretinoid\b", r"\bexfoliator\b",
        r"\baftershave\b", r"\bfragrance\b",
    ]),
    ("Toys", [
        r"\btoy\b", r"\blego\b", r"\bpuzzle\b", r"\bplayset\b",
        r"\bboard\s+game\b", r"\bcard\s+game\b", r"\bplush\b", r"\baction\s+figure\b",
        r"\bdoll(?!ar)\b", r"\bfigurine\b", r"\bstuffed\s+animal\b",
        r"\btrading\s+cards?\b", r"\bpokemon\b", r"\brc\s+car\b",
    ]),
    ("Electronics", [
        r"\blaptop\b", r"\bnotebook\s+computer\b", r"\btablet\b", r"\bipad\b",
        r"\bkindle\b", r"\becho\b", r"\balexa\b", r"\bfire\s+stick\b",
        r"\bmonitor\b", r"\bkeyboard\b", r"\bmouse\b", r"\bheadphones?\b",
        r"\bearbuds?\b", r"\bearphones?\b", r"\bspeaker\b", r"\bsoundbar\b",
        r"\bcamera\b", r"\bwebcam\b", r"\bdrone\b", r"\bgps\b",
        r"\bsmartphone\b", r"\bcell\s+phone\b", r"\bcharger\b", r"\bcable\b",
        r"\busb\b", r"\bhdmi\b", r"\brouter\b", r"\bmodem\b", r"\bbluetooth\b",
        r"\bwireless\b", r"\bconsole\b", r"\bplaystation\b", r"\bps[45]\b",
        r"\bxbox\b", r"\bnintendo\b", r"\bcontroller\b", r"\bgaming\b",
        r"\bsmartwatch\b", r"\bapple\s+watch\b", r"\bfitbit\b",
        r"\bhard\s+drive\b", r"\bssd\b", r"\bmemory\s+card\b", r"\bpower\s+bank\b",
        r"\bpower\s+adapter\b", r"\bpower\s+supply\b", r"\btv\b",
        r"\bstreaming\s+device\b", r"\bcapture\s+card\b",
    ]),
    ("Sports", [
        r"\byoga\b", r"\bfitness\b", r"\bworkout\b", r"\bexercise\b",
        r"\bathletic\b", r"\btreadmill\b", r"\bdumbbells?\b",
        r"\bkettlebell\b", r"\bresistance\s+band\b", r"\brunning\s+shoes?\b",
        r"\bhiking\b", r"\bcamping\b", r"\bfishing\b", r"\bbaseball\b",
        r"\bfootball\b", r"\bsoccer\b", r"\bbasketball\b", r"\btennis\b",
        r"\bgolf\b", r"\bswimming\b", r"\bbicycle\b", r"\bcycling\b",
        r"\bskateboard\b", r"\bsnowboard\b", r"\bski\b", r"\bgym\s+bag\b",
        r"\bathletic\s+shorts?\b", r"\btrail\s+running\b",
    ]),
    ("Kids", [
        r"\bbaby\b", r"\binfant\b", r"\btoddler\b", r"\bnewborn\b",
        r"\bdiaper\b", r"\bstroller\b", r"\bcrib\b", r"\bpacifier\b",
        r"\bbibs?\b", r"\bkids\b", r"\bchildren'?s\b", r"\bschool\s+supply\b",
        r"\bboys?\s+watch\b", r"\bgirls?\s+watch\b",
    ]),
    ("Women", [
        r"\bwomen'?s\b", r"\bwomens\b", r"\bdress\b", r"\bskirt\b",
        r"\bblouse\b", r"\bhandbag\b", r"\bpurse\b", r"\bheels\b",
        r"\bbra\b", r"\blingerie\b", r"\btampons?\b",
    ]),
    ("Men", [
        r"\bmen'?s\b", r"\bmens\b", r"\bboxer\s+brief\b", r"\btie\s+(clip|bar)\b",
        r"\bbeard\s+(oil|trimmer)\b", r"\bsuit\s+(jacket|blazer)\b",
    ]),
    ("Home", [
        r"\bkitchen\b", r"\bcookware\b", r"\bmug\b", r"\bpillow\b",
        r"\bblanket\b", r"\bsheet\s+set\b", r"\btowel\b", r"\bcurtain\b",
        r"\brug\b", r"\bvacuum\b", r"\bmop\b", r"\bcleaner\b", r"\bsponge\b",
        r"\bair\s+freshener\b", r"\bcandle\b", r"\bfurniture\b",
        r"\bstorage\b", r"\borganizer\b", r"\bcookbook\b", r"\bfrying\s+pan\b",
        r"\bcutlery\b", r"\bblender\b", r"\btoaster\b", r"\bmicrowave\b",
        r"\bfridge\b", r"\bwashing\s+machine\b", r"\bcleaning\s+wipe\b",
        r"\btoilet\s+paper\b", r"\btrash\s+bag\b", r"\bpaper\s+towel\b",
        r"\bdetergent\b", r"\bdish\s+soap\b", r"\bfood\s+storage\b",
        r"\bcoffee\s+maker\b", r"\bknife\b", r"\bplant\b", r"\bgarden\b",
        r"\btool\b", r"\bpet\s+food\b", r"\bcat\s+litter\b", r"\bdog\s+leash\b",
    ]),
]


def classify_by_title(title: Optional[str]) -> Optional[str]:
    """Score keyword hits per category and return the top-scoring one."""
    if not title:
        return None
    scores: Dict[str, int] = {}
    lower = title.lower()
    for category, tokens in _TITLE_KEYWORDS:
        for tok in tokens:
            if re.search(tok, lower):
                scores[category] = scores.get(category, 0) + 1
    if not scores:
        return None
    # Highest score wins. If two tie, respect the order in _TITLE_KEYWORDS by
    # picking the first one to reach the max.
    top = max(scores.values())
    for category, _ in _TITLE_KEYWORDS:
        if scores.get(category) == top:
            return category
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def classify_product(item: Dict) -> Optional[str]:
    """Given a raw Apify item (or a DB doc), return the best canonical category
    or None if nothing matched. Breadcrumbs beat title-keyword fallback."""
    # Apify raw items use "breadCrumbs"; DB docs may carry "breadcrumbs".
    bc = item.get("breadCrumbs") or item.get("breadcrumbs")
    fromCrumb = map_breadcrumb_to_category(bc)
    if fromCrumb:
        return fromCrumb
    # Existing `category` value takes precedence over blind title-keyword
    # classification — normalise case and validate against canonical set.
    existing = item.get("category")
    if isinstance(existing, str):
        norm = existing.strip().title()
        if norm in CANONICAL_CATEGORIES:
            return norm
    return classify_by_title(item.get("title"))
