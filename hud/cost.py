# Pricing for claude-sonnet-4-6 (model in use as of 2026-03-25).
# All tokens are priced at this rate regardless of actual model used.
# The `~` prefix in the display communicates this is an estimate.
# Update these constants when switching models or when pricing changes.
PRICE_PER_M_IN = 3.0          # $/M input tokens
PRICE_PER_M_OUT = 15.0        # $/M output tokens
PRICE_PER_M_CACHE_WRITE = 3.75  # $/M cache creation tokens
PRICE_PER_M_CACHE_READ = 0.30   # $/M cache read tokens


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * PRICE_PER_M_IN
            + output_tokens / 1_000_000 * PRICE_PER_M_OUT)


def estimate_cost_full(input_tokens: int, cache_write: int, cache_read: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * PRICE_PER_M_IN
            + cache_write / 1_000_000 * PRICE_PER_M_CACHE_WRITE
            + cache_read / 1_000_000 * PRICE_PER_M_CACHE_READ
            + output_tokens / 1_000_000 * PRICE_PER_M_OUT)
