"""
Shared utilities — single source of truth for constants and helpers
used by both app.py and database.py.
"""

# Canonical class order for sorting (Indian K-12 school system)
CLASS_ORDER = {
    "Nursery": 0, "LKG": 1, "UKG": 2,
    "I": 3, "II": 4, "III": 5, "IV": 6, "V": 7,
    "VI": 8, "VII": 9, "VIII": 10, "IX": 11, "X": 12,
    "XI": 13, "XII": 14,
}


def sort_classes(classes):
    """Sort a list of class names by canonical school order."""
    return sorted(classes, key=lambda c: (CLASS_ORDER.get(c, 99), c))


def initials(name: str) -> str:
    """Return up to 2-letter initials from a full name."""
    return "".join(w[0] for w in str(name or "XX").split() if w)[:2].upper()
