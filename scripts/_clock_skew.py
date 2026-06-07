"""
Shared clock-skew correction for Google Auth JWT generation.

Usage (add near top of any script that needs it, after sys.path setup):

    from _clock_skew import apply_google_clock_skew
    apply_google_clock_skew()

Why this exists (M33):
  If the local system clock differs from Google's servers by >10 s, JWT
  authentication will fail with "invalid_grant".  We probe the Date header
  from https://accounts.google.com and, when skew is significant, temporarily
  patch google.auth._helpers.utcnow() so generated JWTs carry correct iat/exp.

  The two setup scripts previously had duplicate but inconsistent versions of
  this logic — one computed skew with naive datetimes, the other with aware
  datetimes, causing a TypeError when offsets were added.  This module is the
  single authoritative implementation using timezone-aware UTC throughout.
"""
from __future__ import annotations

import datetime
import email.utils
import logging
import urllib.request

log = logging.getLogger(__name__)

_SKEW_THRESHOLD_SECONDS = 10.0


def apply_google_clock_skew(url: str = "https://accounts.google.com") -> None:
    """
    Probe Google's clock and patch google.auth._helpers.utcnow if skew > 10 s.

    Best-effort: any network or parse error is swallowed; if the patch cannot
    be applied, auth will proceed normally and fail with the server's own error.
    """
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            date_header: str = resp.headers.get("Date", "")
    except Exception as exc:
        log.debug("[clock-fix] Could not reach %s to probe clock skew: %s", url, exc)
        return

    if not date_header:
        return

    try:
        # Use timezone-aware UTC on both sides to avoid aware/naive TypeError
        server_dt: datetime.datetime = email.utils.parsedate_to_datetime(date_header)
        local_dt: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
        # Ensure server_dt is also tz-aware (RFC 2822 dates always carry offset)
        if server_dt.tzinfo is None:
            server_dt = server_dt.replace(tzinfo=datetime.timezone.utc)
        skew: datetime.timedelta = server_dt - local_dt
    except Exception as exc:
        log.debug("[clock-fix] Could not parse Date header %r: %s", date_header, exc)
        return

    if abs(skew.total_seconds()) <= _SKEW_THRESHOLD_SECONDS:
        log.debug("[clock-fix] Clock skew %.1f s — within threshold, no patch needed",
                  skew.total_seconds())
        return

    try:
        import google.auth._helpers as _gah  # type: ignore[import]
    except ImportError:
        return

    if not hasattr(_gah, "utcnow"):
        log.debug("[clock-fix] google.auth._helpers.utcnow not found; skipping patch")
        return

    _orig = _gah.utcnow
    _gah.utcnow = lambda: _orig() + skew  # type: ignore[assignment]
    print(
        f"[clock-fix] Adjusted Google Auth JWT clock by {skew.total_seconds():.0f} s "
        f"to match server"
    )
