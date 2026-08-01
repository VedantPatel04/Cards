"""
Phase 5 — Isolated LLM provider for merchant -> MCC resolution.

Keep the vendor SDK quarantined in this file so swapping ChatGPT <-> Claude
is a one-file change. The public surface is a single function that returns a
*validated* MCC code or None. All cost controls that are per-row live here
(toggle + validation); the per-upload budget cap lives in the pipeline.
"""

from django.conf import settings
from openai import OpenAI
import json
from services.mcc_resolver import known_mcc_codes


def llm_lookup_mcc(merchant_key: str) -> str | None:
    """
    Make one cheap, constrained LLM call to guess the Visa MCC for a merchant.

    Implementation notes:
      - Guard: if not settings.LLM_ENABLED or not settings.LLM_API_KEY -> None
      - Prompt: force JSON only, e.g. {"mcc": "5814"}; small max_tokens (~30),
        low temperature.
      - Validate HARD: parse JSON and, if the code is not in
        mcc_resolver.known_mcc_codes(), return None (kills hallucinations so
        they fall through to the category fallback tier).
      - Fail open: wrap network/JSON parsing in try/except -> None, short
        timeout.

    Returns a valid MCC code string, or None.
    """
    if not settings.LLM_ENABLED or not settings.LLM_API_KEY:
      return None
    try:
      client = OpenAI(api_key = settings.LLM_API_KEY, timeout = 10)
      response = client.responses.create(
      model = settings.LLM_MODEL,
      input = f'Return JSON only, e.g. {{"mcc":"5814"}}. What is the most likely Visa MCC for this merchant? Merchant: {merchant_key}',
      temperature = 0.0,
      max_output_tokens=30
      )
      text = response.output_text

      data = json.loads(text) # dict {"mcc": "4111"}
      mcc = str(data.get("mcc"))

      if mcc and mcc in known_mcc_codes():
        return mcc
        
    except Exception:
      return None