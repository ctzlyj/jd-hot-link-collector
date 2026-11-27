"""Use the original price only when this batch recorded the user decision."""


def attach_fallback(package_live):
    if not package_live.fallback_marker():
        raise RuntimeError("ORIGINAL_PRICE_FALLBACK_AUTHORIZATION_REQUIRED")
    return package_live.live_data


# Kept for legacy imports. Only the current batch receipt carries authorization.
FALLBACK_PRICE_SOURCE = None
