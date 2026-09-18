"""Cosmetic version info for the dropdown. Display-only — real version IDs
always come from Mojang's live manifest, so nothing here can break a launch."""

VERSION_NAMES = {
    # modern year-based drops (2026+)
    "1.26": "Technical Macro era",
    # sequential version era
    "1.21": "Tricky Trials",        "1.20": "Trails & Tales",
    "1.19": "The Wild Update",       "1.18": "Caves & Cliffs II",
    "1.17": "Caves & Cliffs I",      "1.16": "Nether Update",
    "1.15": "Buzzy Bees",            "1.14": "Village & Pillage",
    "1.13": "Update Aquatic",        "1.12": "World of Color",
    "1.11": "Exploration Update",    "1.10": "Frostburn Update",
    "1.9":  "Combat Update",         "1.8":  "Bountiful Update",
    "1.7":  "The Update that Changed the World",
    "1.6":  "Horse Update",          "1.5":  "Redstone Update",
}

# specific patch names where the log gives them
PATCH_NAMES = {
    "1.26.50": "Wilderness Bound",
    "1.26.20": "Chaos Cubed",
    "1.26.10": "Tiny Takeover",
    "1.26.00": "Technical Macro Update",
}

def pretty(v):
    """'1.26.50' -> '1.26.50 — Wilderness Bound' (falls back to plain id)."""
    if v in PATCH_NAMES:
        return f"{v} — {PATCH_NAMES[v]}"
    base = ".".join(v.split(".")[:2])
    if base in VERSION_NAMES:
        return f"{v} — {VERSION_NAMES[base]}"
    return v
