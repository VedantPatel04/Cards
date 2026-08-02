"""
Isolated LLM provider for merchant -> MCC resolution.

Keep the vendor SDK quarantined in this file so swapping ChatGPT <-> Claude
is a one-file change. The public surface is a single function that returns a
*validated* MCC code or None. All cost controls that are per-row live here
(toggle + validation); the per-upload budget cap lives in the pipeline.

Two failure modes, deliberately kept distinct:
  - the model answered but the answer is unusable  -> return None
  - the provider could not be reached at all       -> raise LLMUnavailable

The caller persists None as a durable "known-unknown" so it never pays for the
same merchant twice. Persisting that after a network blip would be wrong: it
would permanently mark a perfectly resolvable merchant as unknown.
"""

import json
import logging
import re

from django.conf import settings
from openai import OpenAI

from services.mcc_resolver import known_mcc_codes

logger = logging.getLogger(__name__)

# The model is told to answer with bare JSON, but wrapping it in a ```json
# fence is the single most common way that instruction gets ignored.
JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class LLMUnavailable(Exception):
    """The provider call failed; we learned nothing about this merchant."""


def _extract_mcc(text: str) -> str | None:
    """Pull {"mcc": "5814"} out of a model reply, fenced or not."""
    match = JSON_OBJECT_RE.search(text or "")
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("mcc")
    return None if raw is None else str(raw)


def llm_lookup_mcc(merchant_key: str) -> str | None:
    """
    Make one cheap, constrained LLM call to guess the Visa MCC for a merchant.

    Returns a code that exists in MCC_Codes, or None when the model gave no
    usable answer. Raises LLMUnavailable if the provider call itself failed.
    """
    if not settings.LLM_ENABLED or not settings.LLM_API_KEY:
        return None

    try:
        client = OpenAI(api_key=settings.LLM_API_KEY, timeout=10)
        response = client.responses.create(
            model=settings.LLM_MODEL,
            input=(
                'Return JSON only, e.g. {"mcc":"5814"}. What is the most likely '
                f"Visa MCC for this merchant? Merchant: {merchant_key}"
            ),
            temperature=0.0,
            max_output_tokens=30,
        )
        text = response.output_text
    except Exception as exc:
        logger.warning("llm lookup unavailable for %r: %s", merchant_key, exc)
        raise LLMUnavailable(str(exc)) from exc

    mcc = _extract_mcc(text)
    if mcc is None:
        logger.warning("llm gave no parseable mcc for %r: %r", merchant_key, text)
        return None

    # Hallucination guard: a code we do not stock would break the FK write and
    # is worse than no answer, because the category fallback is at least honest.
    if mcc not in known_mcc_codes():
        logger.warning("llm returned unknown mcc %r for %r", mcc, merchant_key)
        return None

    return mcc
