"""
Merchant name normalizer.

Turns a noisy statement description into a stable, comparable key so that
variants like "MCDONALD'S F31398" and "MCDONALD'S F25696" collapse to the
same token ("MCDONALDS"). Every later tier (rules, cache, DB, LLM) keys off
this value, so it must be deterministic and dependency-free.
"""

import re
def merchant_key(description: str | None) -> str:
    """
    Normalize a raw transaction description into a canonical merchant key.

    Intended algorithm:
      1. uppercase
      2. cut everything after the first '*' or '#' (processor/store noise)
      3. delete digits
      4. replace any non A-Z character with a space
      5. collapse repeated whitespace and strip

    Examples (target behavior — cover these in tests):
      "MCDONALD'S F31398"   -> "MCDONALDS"
      "WAL-MART #2297"      -> "WAL MART"
      "MTA*NYCT PAYGO"      -> "MTA"
      "LYFT   *AIRPORT"     -> "LYFT"

    Returns an uppercase, whitespace-collapsed string (possibly empty).
    """
    if not isinstance(description, str):
        return ""

    key = description.upper()
    key = re.split(r"[*#]", key, maxsplit=1)[0]
    key = re.sub(r"\b[A-Z]\d+\b", " ", key)
    key = re.sub(r"\d+", "", key)
    key = key.replace("'", "").replace("’", "")
    key = re.sub(r"[^A-Z]+", " ", key)


    return " ".join(key.split())