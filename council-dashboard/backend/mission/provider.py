"""Meta Model API (Responses API) transport. One credential name, no fallbacks.

Documented at https://dev.meta.ai/docs/quickstart and https://dev.meta.ai/docs/tool-calling:
  POST https://api.meta.ai/v1/responses, Authorization: Bearer $MODEL_API_KEY,
  flat function tools, tool_choice "auto" only. Follow-up turns are self-contained (state plus tool results so far);
  previous_response_id is not used because the provider's stored conversations failed in live runs (HTTP 400, 503).
Prices from https://dev.meta.ai/docs/pricing-rate-limits (USD per 1M tokens, standard mode).
"""
import hashlib
import os
from pathlib import Path
import httpx
from dotenv import dotenv_values

ENDPOINT = 'https://api.meta.ai/v1/responses'
ENV_FILE = Path(__file__).resolve().parents[1] / '.env'
DIRECTOR_MODEL = 'muse-wonder-1.0'
SPECIALIST_MODEL = 'muse-spark-1.3'
# (input, cached input, output) USD per 1M tokens; retrieved 2026-10-30.
PRICES = {'muse-wonder-1.0': (4.00, 0.20, 20.00), 'muse-spark-1.3': (1.25, 0.15, 4.25)}
PRICE_SOURCE = 'https://dev.meta.ai/docs/pricing-rate-limits (retrieved 2026-10-30)'


class ProviderConfigError(RuntimeError):
    pass


def credential():
    """Return (key, source). backend/.env wins over the process environment; only MODEL_API_KEY is read."""
    file_values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    key = (file_values.get('MODEL_API_KEY') or '').strip()
    source = str(ENV_FILE)
    if not key:
        key = (os.environ.get('MODEL_API_KEY') or '').strip()
        source = 'process environment MODEL_API_KEY'
    if not key:
        legacy = [k for k in ('OPEN_API_KEY', 'WONDER_API_KEY', 'SMART_API_KEY') if (file_values.get(k) or os.environ.get(k))]
        hint = f' Found legacy variable(s) {legacy}; rename the one for your Meta developer account to MODEL_API_KEY.' if legacy else ''
        raise ProviderConfigError('MODEL_API_KEY is not set in ' + str(ENV_FILE) + ' or the environment; no request dispatched.' + hint)
    return key, source


def fingerprint(key):
    """Non-reversible identifier so records show which key was used without storing it."""
    return 'sha256:' + hashlib.sha256(key.encode()).hexdigest()[:16]


def cost_usd(model, usage):
    if model not in PRICES:
        raise ProviderConfigError('No published price recorded for model ' + model)
    price_in, price_cached, price_out = PRICES[model]
    cached = int((usage.get('input_tokens_details') or {}).get('cached_tokens') or 0)
    uncached = usage['input_tokens'] - cached
    if uncached < 0:
        raise ValueError('Provider reported more cached tokens than input tokens')
    return (uncached * price_in + cached * price_cached + usage['output_tokens'] * price_out) / 1e6


def max_cost_usd(model, input_bytes, max_output_tokens):
    """Upper bound used for reservations: every input byte counted as one uncached token."""
    price_in, _, price_out = PRICES[model]
    return (input_bytes * price_in + max_output_tokens * price_out) / 1e6


SAM_MODEL = 'sam-3.1'
# Flat per-call prices from the same pricing page (retrieved 2026-10-31).
SAM_USD_PER_IMAGE = 2.50 / 1000  # sam-3.1: $2.50 per 1,000 images


def retry_wait(retry_after, attempt):
    """Seconds to wait before retrying an HTTP 429: Retry-After (capped at 60 s), else 5, 15, 45 s."""
    try:
        return min(60.0, max(0.0, float(retry_after)))
    except (TypeError, ValueError):
        return 5.0 * 3 ** attempt


def correlation_of(r):
    return {'http_status': r.status_code,
            'response_headers': {k: v for k, v in r.headers.items() if 'request-id' in k.lower() or k.lower() in ('date', 'x-trace-id', 'retry-after')}}


def send(payload, key, transport=None, timeout=120, url=ENDPOINT, max_429_retries=3, sleep=None):
    """One logical request. Returns (response_json, correlation) or raises httpx errors.

    HTTP 429 means the provider refused the request without processing it, so it is retried up to max_429_retries times,
    honouring Retry-After (capped at 60 s; otherwise 5, 15, 45 s). Timeouts and 5xx are never retried here: the request
    may have been processed and charged."""
    import time as _time
    sleep = sleep or _time.sleep
    attempts = []
    for attempt in range(max_429_retries + 1):
        with httpx.Client(timeout=timeout, transport=transport) as client:
            r = client.post(url, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, json=payload)
        attempts.append(correlation_of(r))
        if r.status_code != 429 or attempt == max_429_retries:
            break
        sleep(retry_wait(r.headers.get('retry-after'), attempt))
    # A fresh dict per attempt and a fresh outer dict: the record must be plain JSON (no self-reference).
    correlation = {**correlation_of(r), 'provider_attempts': [dict(a) for a in attempts]}
    r.raise_for_status()
    return r.json(), correlation
