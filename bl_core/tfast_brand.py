"""
TFast Digital - authoritative brand and copyright module.

This is the *dedicated* brand file for the TFast MTK Bootloader Tool. It is the
single source of truth for product identity, copyright and attribution, and it
is one of the files covered by the integrity seal in ``tfast-brand.json``
(verified by :mod:`bl_core.tfast_guard`).

PLEASE READ
-----------
This is a proprietary product of TFast Digital. Removing, obscuring or
altering the copyright and attribution in this file is a breach of the licence
terms under which the software was supplied.

If you legitimately change this file (for example to update the copyright
year), you MUST re-seal the build so the integrity check accepts your change:

    python tools/tfast_seal.py

Until you do, the application refuses to start and reports exactly which file
fails. That refusal is intentional, not a bug.

    Author   : TFast Digital
    Website  : https://tfastdigital.com/
    GitHub   : https://github.com/tfastdigital
    Telegram : https://t.me/tfasthub
    WhatsApp : https://whatsapp.com/channel/0029VaAYznPK5cDIXJa9nW1a
"""

from __future__ import annotations

import hashlib

# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
BRAND_ID = "tfast-digital"

AGENCY = "TFast Digital"
AGENCY_LONG = "TFast Digital Agency"

PRODUCT = "TFast MTK Bootloader Tool"
PRODUCT_SHORT = "TFast BL Tool"
PRODUCT_EDITION = "Desktop Edition"
PRODUCT_VERSION = "2.0.0"

COPYRIGHT_YEARS = "2025-2026"

TAGLINE = "MediaTek / Transsion bootloader unlock, patch and recovery suite"

#: Short machine-readable stamp embedded in protected source files so a guard
#: can confirm the file still belongs to this build.
SOURCE_MARKER = "TFast Digital"
SOURCE_MARKER_TAG = "@brand tfast-digital"

# --------------------------------------------------------------------------- #
# Public links
# --------------------------------------------------------------------------- #
URL_WEBSITE = "https://tfastdigital.com/"
URL_GITHUB = "https://github.com/tfastdigital"
URL_TELEGRAM = "https://t.me/tfasthub"
URL_WHATSAPP = "https://whatsapp.com/channel/0029VaAYznPK5cDIXJa9nW1a"

LINKS: tuple[tuple[str, str], ...] = (
    ("Website", URL_WEBSITE),
    ("GitHub", URL_GITHUB),
    ("Telegram", URL_TELEGRAM),
    ("WhatsApp channel", URL_WHATSAPP),
)

# --------------------------------------------------------------------------- #
# Protected paths (relative to the project root)
# --------------------------------------------------------------------------- #
BRAND_MODULE_REL = "bl_core/tfast_brand.py"
BRAND_SHIM_REL = "bl_core/branding.py"
GUARD_MODULE_REL = "bl_core/tfast_guard.py"
MANIFEST_REL = "tfast-brand.json"
NOTICE_REL = "tfast-NOTICE.txt"
ICON_REL = "assets/tfast.ico"

#: Files whose bytes are hashed into the manifest. Any edit breaks the seal
#: until ``tools/tfast_seal.py`` is run again.
HASHED_FILES: tuple[str, ...] = (
    BRAND_MODULE_REL,
    BRAND_SHIM_REL,
    GUARD_MODULE_REL,
    NOTICE_REL,
    ICON_REL,
)

#: Source files checked for the presence of ``SOURCE_MARKER`` rather than a
#: hash, so ordinary development edits do not break the seal.
MARKED_FILES: tuple[str, ...] = ("bl.py", "gui.py")

# --------------------------------------------------------------------------- #
# Derived strings used by the UI
# --------------------------------------------------------------------------- #
def _derived_copyright_line() -> str:
    return f"\u00a9 {COPYRIGHT_YEARS} {AGENCY_LONG}. All rights reserved."


def _derived_built_by() -> str:
    return f"Built by {AGENCY_LONG}"


COPYRIGHT_LINE = _derived_copyright_line()
BUILT_BY = _derived_built_by()
WINDOW_TITLE = f"{PRODUCT} \u2014 {PRODUCT_EDITION}"
CLI_TITLE = f"{PRODUCT} (CLI Edition v{PRODUCT_VERSION})"

# --------------------------------------------------------------------------- #
# Attribution / integrity
# --------------------------------------------------------------------------- #
#: The exact attribution block that must survive in shipped copies.
CANONICAL_ATTRIBUTION = (
    "© 2025-2026 TFast Digital Agency. All rights reserved. "
    "Built by TFast Digital Agency. "
    "https://tfastdigital.com/ | https://github.com/tfastdigital | "
    "https://t.me/tfasthub | "
    "https://whatsapp.com/channel/0029VaAYznPK5cDIXJa9nW1a"
)

#: Backwards-compatible alias (older code referenced the underscore name).
_CANONICAL_ATTRIBUTION = CANONICAL_ATTRIBUTION

#: SHA-256 of ``CANONICAL_ATTRIBUTION`` (UTF-8). Guards against silent edits of
#: the canonical text above.
EXPECTED_DIGEST = "4faf83109d3eb4991950a0c6b6d985ee04e5210bc469499e1843246a3925b967"


def render_attribution() -> str:
    """Reconstruct the canonical attribution from the live primitives.

    Built from ``COPYRIGHT_YEARS`` / ``AGENCY_LONG`` / the URL constants rather
    than from the cached ``COPYRIGHT_LINE``/``BUILT_BY`` strings, so renaming
    the agency or changing the year range is detected as well.
    """
    return (
        f"{_derived_copyright_line()} "
        f"{_derived_built_by()}. "
        f"{URL_WEBSITE} | {URL_GITHUB} | {URL_TELEGRAM} | {URL_WHATSAPP}"
    )


def digest_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify() -> tuple[bool, str]:
    """Check the attribution and copyright constants are intact.

    This is the in-memory half of the protection. The on-disk half (hashes of
    the brand files, manifest seal, source markers) lives in
    :func:`bl_core.tfast_guard.check`.

    Returns ``(ok, message)``. ``ok`` is False when the copyright block has been
    removed or altered, in which case the caller must refuse to start.
    """
    rendered = render_attribution()
    if rendered != CANONICAL_ATTRIBUTION:
        return False, (
            f"The TFast Digital copyright and attribution block has been "
            f"modified or removed from {BRAND_MODULE_REL}.\n\n"
            "This software is proprietary and is licensed on the condition "
            "that the copyright notice is preserved. Restore the original "
            "brand file from https://github.com/tfastdigital to continue."
        )

    # The published strings that the UI actually renders must still match what
    # the primitives derive, so editing them alone is also caught.
    if COPYRIGHT_LINE != _derived_copyright_line() or BUILT_BY != _derived_built_by():
        return False, (
            f"The TFast Digital copyright text has been altered in "
            f"{BRAND_MODULE_REL}.\n\n"
            "Restore the original brand file to continue."
        )

    actual = digest_of(CANONICAL_ATTRIBUTION)
    if actual != EXPECTED_DIGEST:
        return False, (
            "The TFast Digital attribution integrity seal does not match.\n\n"
            f"  expected {EXPECTED_DIGEST}\n"
            f"  actual   {actual}\n\n"
            "Restore the original brand file from "
            "https://github.com/tfastdigital to continue."
        )

    for label, url in LINKS:
        if not url.startswith("https://"):
            return False, f"Branding link '{label}' is not a valid https URL."

    if not SOURCE_MARKER or BRAND_ID != "tfast-digital":
        return False, "The TFast Digital brand identity has been altered."

    return True, "Attribution intact."


def banner_lines() -> list[str]:
    """Short attribution block for terminal / ASCII banners."""
    return [
        f"{PRODUCT}  v{PRODUCT_VERSION}",
        TAGLINE,
        "",
        COPYRIGHT_LINE,
        BUILT_BY,
        f"  Website  : {URL_WEBSITE}",
        f"  GitHub   : {URL_GITHUB}",
        f"  Telegram : {URL_TELEGRAM}",
        f"  WhatsApp : {URL_WHATSAPP}",
    ]


def about_text(edition: str | None = None) -> str:
    """Body text for the About dialog / ``--about`` output."""
    ed = edition or PRODUCT_EDITION
    return (
        f"{PRODUCT}\n"
        f"Version {PRODUCT_VERSION} \u00b7 {ed}\n\n"
        f"{TAGLINE}\n\n"
        f"{COPYRIGHT_LINE}\n\n"
        f"Developed and maintained by {AGENCY_LONG}.\n\n"
        f"Website\n    {URL_WEBSITE}\n"
        f"GitHub\n    {URL_GITHUB}\n"
        f"Telegram\n    {URL_TELEGRAM}\n"
        f"WhatsApp channel\n    {URL_WHATSAPP}\n\n"
        f"This software is proprietary. The copyright notice and attribution "
        f"in {BRAND_MODULE_REL} must remain intact; removing it breaks the "
        f"application by design and is a breach of the licence terms."
    )


def notice_text() -> str:
    """Plain-text NOTICE suitable for writing to disk."""
    return "\n".join(banner_lines()) + "\n"
