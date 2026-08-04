# =========================================================
# Labor Type categories
# =========================================================
#
# The single source of truth for how hours get bucketed. There are 9
# BUILT-IN categories below -- these are what the app's own matching
# rules (labor_helpers.map_service, estimate_helpers.infer_estimate
# _labor_type) can produce on their own, and they also define the
# default display order.
#
# On top of the built-ins, the master task map CSV (task_map_helpers)
# is allowed to introduce brand new CUSTOM categories -- any Labor
# Type text that doesn't match one of the 9 built-ins below is kept
# as-is instead of being rejected. That's a deliberate trust
# boundary: a typo in the master map ("Enginering") *will* create a
# new stray bucket, but that's the tradeoff for letting the user add
# real new categories without editing this file.

CANONICAL_LABOR_TYPES = [
    "Engineering",
    "Programming",
    "Assembly - Electrical",
    "Assembly - Mechanical",
    "Admin",
    "Installation",
    "Pre-Sale",
    "Non-Project",
    "Other",
]

# "Other" is always the catch-all / unmapped bucket, so it's handled
# on its own everywhere below instead of being treated like a normal
# category.
_OTHER = "Other"

# Lowercased lookup so matching against the built-ins is
# case/whitespace-insensitive.
_NORMALIZED_LOOKUP = {
    canonical.strip().lower(): canonical
    for canonical in CANONICAL_LABOR_TYPES
}

# Built-in categories (excluding Other) in the order they should be
# displayed, e.g. Programming before Admin. Used by sort_labor_types.
_BUILTIN_DISPLAY_RANK = {
    canonical: rank
    for rank, canonical in enumerate(CANONICAL_LABOR_TYPES)
    if canonical != _OTHER
}


def normalize_labor_type(value, allow_new=True):
    """
    Case/whitespace-insensitive match against the built-in Labor Type
    categories, e.g. "engineering" or " Engineering " both resolve to
    "Engineering".

    If the value doesn't match a built-in category:
      - allow_new=True (the default) returns the value's own trimmed
        text, so it becomes a new custom category. This is what lets
        the master task map introduce categories beyond the 9
        built-ins.
      - allow_new=False returns None instead, which is used for
        blank/unusable cells.

    A blank/empty value always returns None either way.
    """
    text = str(value).strip()
    lower = text.lower()

    if lower in _NORMALIZED_LOOKUP:
        return _NORMALIZED_LOOKUP[lower]

    if not text:
        return None

    return text if allow_new else None


def display_label(labor_type):
    """
    The label shown to the user for a given Labor Type. Only the
    "Other" bucket gets renamed for display -- everything else
    (built-in or custom, from the master map) is shown as-is.
    Shared by the website and the PDF so the two never drift apart.
    """
    return "Other/Unmapped" if labor_type == _OTHER else labor_type


def sort_labor_types(labor_types):
    """
    Orders a collection of Labor Types for display:
      1. Built-in categories (other than "Other"), in the fixed order
         defined by CANONICAL_LABOR_TYPES -- this is what keeps
         Programming above Other/Unmapped, for example.
      2. Any custom categories added via the master task map,
         alphabetically.
      3. "Other" always last, since it's the catch-all/unmapped
         bucket.
    """
    def sort_key(labor_type):
        if labor_type == _OTHER:
            return (2, "")

        if labor_type in _BUILTIN_DISPLAY_RANK:
            return (0, _BUILTIN_DISPLAY_RANK[labor_type])

        # Custom category from the master task map.
        return (1, labor_type)

    return sorted(labor_types, key=sort_key)
