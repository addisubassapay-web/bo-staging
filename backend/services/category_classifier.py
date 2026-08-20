"""
Category classifier for Apify-scraped listings.

Returns a list of (slug, weight) tuples so a single product can live in
multiple categories (per the product owner's request). The first entry
is always the PRIMARY category (used as `category_id` on the listing);
subsequent entries populate the `secondary_categories` array.

Rules:
- Explicit product-type keywords (electronics/beauty/books/toys/sports/
  home/handmade) beat generic gender keywords, so a "Women's laptop"
  goes to Electronics (primary) with Women as secondary.
- Kids/Men/Women are additive gender tags — they can co-exist with
  Electronics, Beauty, etc.
- If nothing matches → returns [("other", 0.0)] so the caller can
  round-robin over unique slugs instead.
"""

from typing import List, Tuple, Iterable, Dict

# Ordered high → low specificity. Each slug maps to a list of substrings
# that trigger it (already lower-cased, matched via `in`).
PRODUCT_KEYWORDS: Dict[str, List[str]] = {
    "electronics": [
        "electronics", "laptop", "notebook", "computer", "phone", "smartphone",
        "tablet", "ipad", "kindle", "camera", "headphone", "headphones",
        "earbud", "earbuds", "earphone", "speaker", " tv ", "monitor",
        "keyboard", "mouse pad", " mouse", "charger", "cable", "usb-c",
        " usb ", "wireless", "bluetooth", "smart watch", "smartwatch",
        "printer", "console", "gaming", "graphics card", "ssd", "hard drive",
        "router", "modem", "power bank",
    ],
    "beauty": [
        "beauty", "makeup", "make-up", "skincare", "skin care", "cosmetic",
        "perfume", "fragrance", "cologne", "lipstick", "mascara", "eyeliner",
        "eyeshadow", "foundation", "concealer", "shampoo", "conditioner",
        "lotion", "moisturizer", "serum", "hair care", "haircare", "nail polish",
        "manicure", "sunscreen",
    ],
    "books": [
        " book", "novel", "textbook", "paperback", "hardcover", "audiobook",
        "cookbook", "magazine", "encyclopedia", "biography", "self-help",
    ],
    "toys": [
        " toy", "toys", "puzzle", "playset", "lego", "building block",
        "stuffed animal", "plush toy", "board game", "action figure",
        "doll ", "doll house", "rc car",
    ],
    "sports": [
        "fitness", " gym", "yoga", "running shoe", "cycling", "bicycle",
        "outdoor", "camping", "hiking", "athletic", "workout", "exercise",
        "dumbbell", "resistance band", "swim", "tennis", "basketball",
        "soccer", "football", "baseball", "golf",
    ],
    "home": [
        "kitchen", "furniture", "decor", "bedding", "duvet", "pillow",
        "curtain", "lamp", "led light", "led strip", "rug ", "carpet",
        "sofa", "recliner", "table", "storage bin", "organizer", "cookware",
        "utensil", "appliance", "vacuum", "cleaning", "bathroom", "shower",
        "towel", "blanket", "candle", "wall art",
    ],
    "handmade": [
        "handmade", "handcrafted", "artisan", "hand-made", "hand crafted",
    ],
}

# Additive gender / age tags — checked separately, may co-exist with product tags.
GENDER_KEYWORDS: Dict[str, List[str]] = {
    "kids": [
        "kids", "baby", "babies", "toddler", "infant", "children", "childrens",
        "child's", "boys", "girls", "youth", "school", "stroller", "diaper",
        "crib", "nursery", "playpen",
    ],
    "men": [
        "men's", " mens ", "male ", "for men", "gentleman", "boyfriend",
        "father", "husband",
    ],
    "women": [
        "women's", " womens ", " ladies ", "female", "for women", "girlfriend",
        "mother's", "girlfriend", " lady ", "womens ", " her ",
    ],
}


def _hay(item: dict) -> str:
    """Build a lowercased search string from title, description, category and breadcrumbs."""
    parts = [
        str(item.get("title") or ""),
        str(item.get("description") or ""),
        str(item.get("category") or ""),
        str(item.get("breadCrumbs") or item.get("breadcrumbs") or ""),
        str(item.get("productCategory") or ""),
    ]
    return (" ".join(parts)).lower()


def classify(item: dict, available_slugs: Iterable[str]) -> List[str]:
    """Return a de-duplicated list of category slugs for `item`.

    First slug in the list is the PRIMARY category. The classifier prefers
    product-type keywords (electronics, beauty, home, toys, sports, books,
    handmade) as the primary and falls back to gender tags. When nothing
    matches, returns [] so the caller can round-robin.

    `available_slugs` filters the output to slugs the catalog actually has.
    """
    avail = set(available_slugs)
    hay = _hay(item)
    if not hay.strip():
        return []

    primary: List[str] = []
    # Product-type match — take up to 2 to allow rare cross-category items
    for slug, kws in PRODUCT_KEYWORDS.items():
        if slug not in avail:
            continue
        for kw in kws:
            if kw in hay:
                primary.append(slug)
                break

    # Gender/age match — always additive
    genders: List[str] = []
    for slug, kws in GENDER_KEYWORDS.items():
        if slug not in avail:
            continue
        for kw in kws:
            if kw in hay:
                genders.append(slug)
                break

    # Assemble: primary product tag first, then gender tags.
    result: List[str] = []
    for s in primary + genders:
        if s not in result:
            result.append(s)
    return result
