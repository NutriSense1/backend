"""
Keep-alive pinger.

Render's free web service instances spin down after ~15 minutes with no
inbound HTTP traffic. This background task wakes up every
`interval_seconds` (default 12 minutes) and makes a real HTTP request to
this service's own public health endpoint, which counts as inbound
traffic and resets Render's idle timer.

It only runs against the service's *public* URL — Render sets
RENDER_EXTERNAL_URL automatically for every web service at runtime, so
there's nothing to configure. If that env var isn't present (e.g. running
locally, or on a non-Render host), the loop logs once and exits instead
of looping forever for no reason.

Note: paid Render instance types (Starter and above) don't spin down due
to inactivity in the first place, so this is mainly a safety net for free
instances or in case the plan changes later — it's harmless either way.
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)


async def keep_alive_loop(interval_seconds: int = 720) -> None:
    base_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not base_url:
        logger.info(
            "RENDER_EXTERNAL_URL not set — keep-alive pinger is a no-op "
            "(not running on Render, or running locally)."
        )
        return

    url = f"{base_url.rstrip('/')}/health"
    logger.info(f"Keep-alive pinger started: hitting {url} every {interval_seconds}s")

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                response = await client.get(url)
                logger.info(f"Keep-alive ping -> {response.status_code}")
            except asyncio.CancelledError:
                logger.info("Keep-alive pinger stopped.")
                raise
            except Exception as exc:
                # Never let a failed ping take down the loop — just log and
                # try again on the next interval.
                logger.warning(f"Keep-alive ping failed: {exc!r}")
