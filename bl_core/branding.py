"""
Compatibility shim for the TFast Digital brand module.

The authoritative brand data now lives in the dedicated file
:mod:`bl_core.tfast_brand`, and the enforcement engine in
:mod:`bl_core.tfast_guard`.

This shim exists only so older imports (``from bl_core import branding``) keep
working. It deliberately holds **no** brand data of its own: everything is
re-exported from :mod:`bl_core.tfast_brand`. Editing anything here changes
nothing about the copyright, and this file is itself covered by the integrity
seal in ``tfast-brand.json``.

    Copyright (c) 2025-2026 TFast Digital Agency. All rights reserved.
    https://tfastdigital.com/
"""

from __future__ import annotations

from .tfast_brand import (  # noqa: F401
    AGENCY,
    AGENCY_LONG,
    BRAND_ID,
    BRAND_MODULE_REL,
    BRAND_SHIM_REL,
    BUILT_BY,
    CANONICAL_ATTRIBUTION,
    CLI_TITLE,
    COPYRIGHT_LINE,
    COPYRIGHT_YEARS,
    EXPECTED_DIGEST,
    GUARD_MODULE_REL,
    HASHED_FILES,
    ICON_REL,
    LINKS,
    MANIFEST_REL,
    MARKED_FILES,
    NOTICE_REL,
    PRODUCT,
    PRODUCT_EDITION,
    PRODUCT_SHORT,
    PRODUCT_VERSION,
    SOURCE_MARKER,
    SOURCE_MARKER_TAG,
    TAGLINE,
    URL_GITHUB,
    URL_TELEGRAM,
    URL_WEBSITE,
    URL_WHATSAPP,
    WINDOW_TITLE,
    _CANONICAL_ATTRIBUTION,
    _derived_built_by,
    _derived_copyright_line,
    about_text,
    banner_lines,
    digest_of,
    notice_text,
    render_attribution,
    verify,
)

__all__ = [
    "AGENCY",
    "AGENCY_LONG",
    "BRAND_ID",
    "BUILT_BY",
    "CANONICAL_ATTRIBUTION",
    "CLI_TITLE",
    "COPYRIGHT_LINE",
    "COPYRIGHT_YEARS",
    "EXPECTED_DIGEST",
    "LINKS",
    "PRODUCT",
    "PRODUCT_EDITION",
    "PRODUCT_SHORT",
    "PRODUCT_VERSION",
    "SOURCE_MARKER",
    "SOURCE_MARKER_TAG",
    "TAGLINE",
    "URL_GITHUB",
    "URL_TELEGRAM",
    "URL_WEBSITE",
    "URL_WHATSAPP",
    "WINDOW_TITLE",
    "about_text",
    "banner_lines",
    "digest_of",
    "notice_text",
    "render_attribution",
    "verify",
]
