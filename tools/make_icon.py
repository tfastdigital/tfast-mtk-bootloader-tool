#!/usr/bin/env python3
"""
Generate the TFast Digital branded application icon - no third-party deps.

The runtime bundled in ``py314_runtime/lib`` ships a stripped Pillow (the
``_imaging`` extension is absent), so this script implements its own tiny
software rasteriser, PNG encoder and ICO container writer using only the
standard library (``zlib`` + ``struct``).

Output (in ``BL/assets/``):

    tfast.ico         Windows icon, 16/24/32/48/64/128/256
    tfast_512.png     large PNG for the About panel / storefront art
    tfast_256.png     256px PNG
    tfast_64.png      64px PNG for the in-app header

Run once; the generated files are committed so the app never needs this at
runtime:

    python tools/make_icon.py
"""

from __future__ import annotations

import math
import struct
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

MASTER = 256          # master render size
SS = 2                # supersampling factor per axis on the master
ICO_SIZES = [256, 128, 64, 48, 32, 24, 16]

# --------------------------------------------------------------------------- #
# Brand palette - deep violet to electric blue. Deliberately high-contrast so
# the mark stays readable at 16px in the taskbar and window title bar.
# --------------------------------------------------------------------------- #
VIOLET_DARK = (24, 12, 64)
VIOLET = (88, 44, 190)
BLUE = (36, 132, 245)
WHITE = (255, 255, 255)

# ---- Normalised geometry (0..1 of the icon box) --------------------------- #
CORNER_R = 0.235

BODY_X0, BODY_Y0, BODY_X1, BODY_Y1, BODY_R = 0.265, 0.470, 0.735, 0.850, 0.075

SH_CX, SH_CY = 0.5, 0.415
SH_R_OUT = 0.1725
SH_R_IN = 0.1175

LEG_X = SH_CX - SH_R_OUT + (SH_R_OUT - SH_R_IN) / 2     # centre of left leg
LEG_Y_TOP = SH_CY
LEG_Y_BOT = BODY_Y0 + 0.030

T_X0, T_X1 = 0.3875, 0.6125
T_TOP = 0.585
T_BAR_H = 0.050
T_STEM_W = 0.046
T_STEM_BOT = 0.780

SHEEN_CX, SHEEN_CY, SHEEN_RX, SHEEN_RY = 0.30, 0.10, 0.56, 0.46


def _lerp(a: tuple, b: tuple, t: float) -> tuple:
    return (
        int(round(a[0] + (b[0] - a[0]) * t)),
        int(round(a[1] + (b[1] - a[1]) * t)),
        int(round(a[2] + (b[2] - a[2]) * t)),
    )


def _gradient(u: float, v: float) -> tuple:
    t = (u + v) * 0.5
    if t <= 0.55:
        return _lerp(VIOLET_DARK, VIOLET, t / 0.55)
    return _lerp(VIOLET, BLUE, (t - 0.55) / 0.45)


# --------------------------------------------------------------------------- #
# Geometry predicates
# --------------------------------------------------------------------------- #
def _rrect(u, v, x0, y0, x1, y1, r) -> bool:
    """Point-in-rounded-rectangle via signed distance."""
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    hw, hh = (x1 - x0) * 0.5 - r, (y1 - y0) * 0.5 - r
    qx = abs(u - cx) - hw
    qy = abs(v - cy) - hh
    mx, my = max(qx, 0.0), max(qy, 0.0)
    return math.sqrt(mx * mx + my * my) + min(max(qx, qy), 0.0) - r <= 0.0


def _ellipse(u, v, cx, cy, rx, ry) -> bool:
    dx = (u - cx) / rx
    dy = (v - cy) / ry
    return dx * dx + dy * dy <= 1.0


def _annulus_upper(u, v, cx, cy, r_in, r_out, a0=0.0, a1=180.0) -> bool:
    dx, dy = u - cx, cy - v          # y up, so standard maths orientation
    d2 = dx * dx + dy * dy
    if d2 > r_out * r_out or d2 < r_in * r_in:
        return False
    ang = math.degrees(math.atan2(dy, dx)) % 360.0
    return a0 <= ang <= a1


def _capsule(u, v, x0, y0, x1, y1, r) -> bool:
    vx, vy = x1 - x0, y1 - y0
    wx, wy = u - x0, v - y0
    seg = vx * vx + vy * vy
    t = 0.0 if seg == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / seg))
    px, py = x0 + vx * t - u, y0 + vy * t - v
    return px * px + py * py <= r * r


# --------------------------------------------------------------------------- #
# Shading
# --------------------------------------------------------------------------- #
def _over(dst, src_rgb, src_a):
    """Source-over composite of a layer onto dst (dst is opaque here)."""
    dr, dg, db, da = dst
    if src_a >= 1.0:
        return (src_rgb[0], src_rgb[1], src_rgb[2], 255)
    if src_a <= 0.0:
        return dst
    out_a = src_a + da / 255.0 * (1.0 - src_a)
    if out_a <= 0.0:
        return (0, 0, 0, 0)
    oa = 1.0 / out_a
    r = (src_rgb[0] / 255.0 * src_a + dr / 255.0 * (da / 255.0) * (1.0 - src_a)) * oa
    g = (src_rgb[1] / 255.0 * src_a + dg / 255.0 * (da / 255.0) * (1.0 - src_a)) * oa
    b = (src_rgb[2] / 255.0 * src_a + db / 255.0 * (da / 255.0) * (1.0 - src_a)) * oa
    return (int(r * 255), int(g * 255), int(b * 255), int(out_a * 255))


def shade(u: float, v: float):
    """Composite colour at normalised coords, or None when transparent."""
    # --- background badge: rounded square with gradient -------------------
    if not _rrect(u, v, 0.0, 0.0, 1.0, 1.0, CORNER_R):
        return None
    g = _gradient(u, v)
    col = (g[0], g[1], g[2], 255)

    # --- soft sheen in the upper-left -------------------------------------
    if _ellipse(u, v, SHEEN_CX, SHEEN_CY, SHEEN_RX, SHEEN_RY):
        col = _over(col, WHITE, 0.085)

    # --- padlock shackle: open on the right -------------------------------
    if _annulus_upper(u, v, SH_CX, SH_CY, SH_R_IN, SH_R_OUT):
        col = _over(col, WHITE, 1.0)

    stroke = (SH_R_OUT - SH_R_IN) * 0.5
    if _capsule(u, v, LEG_X, LEG_Y_TOP, LEG_X, LEG_Y_BOT, stroke):
        col = _over(col, WHITE, 1.0)

    # --- padlock body (after the shackle so the leg merges in) ------------
    if _rrect(u, v, BODY_X0, BODY_Y0, BODY_X1, BODY_Y1, BODY_R):
        col = _over(col, WHITE, 1.0)

        # --- 'T' monogram inset into the body ----------------------------
        if _rrect(u, v, T_X0, T_TOP, T_X1, T_TOP + T_BAR_H, T_BAR_H * 0.35):
            col = _over(col, VIOLET_DARK, 1.0)
        elif _rrect(u, v, SH_CX - T_STEM_W / 2, T_TOP,
                    SH_CX + T_STEM_W / 2, T_STEM_BOT, T_STEM_W * 0.30):
            col = _over(col, VIOLET_DARK, 1.0)

    return col


# --------------------------------------------------------------------------- #
# Render + resample
# --------------------------------------------------------------------------- #
def render_master() -> bytearray:
    """Return a MASTER-sized RGBA bytearray, rows top-down."""
    n = MASTER
    step = 1.0 / (n * SS)
    inv = 1.0 / (SS * SS)
    out = bytearray(n * n * 4)
    for y in range(n):
        row_off = y * n * 4
        base_v = y * SS * step
        for x in range(n):
            base_u = x * SS * step
            r = g = b = a = 0.0
            for sy in range(SS):
                v = base_v + (sy + 0.5) * step
                for sx in range(SS):
                    u = base_u + (sx + 0.5) * step
                    c = shade(u, v)
                    if c is not None:
                        al = c[3] / 255.0
                        r += c[0] * al
                        g += c[1] * al
                        b += c[2] * al
                        a += c[3]
            if a <= 0.0:
                continue
            # Un-premultiply once (a already holds the summed 0..255 alphas),
            # then average the alpha by the sample count.
            scale_c = 255.0 / a
            o = row_off + x * 4
            out[o] = min(255, int(r * scale_c + 0.5))
            out[o + 1] = min(255, int(g * scale_c + 0.5))
            out[o + 2] = min(255, int(b * scale_c + 0.5))
            out[o + 3] = min(255, int(a * inv + 0.5))
    return out


def _weights(src: int, dst: int) -> list:
    """Area-average weights mapping dst index -> list of (src_index, weight)."""
    scale = src / dst
    table = []
    for i in range(dst):
        start = i * scale
        end = start + scale
        acc = {}
        j = int(math.floor(start))
        while j < end and j < src:
            lo = max(start, j)
            hi = min(end, j + 1)
            w = hi - lo
            if w > 0:
                acc[j] = acc.get(j, 0.0) + w
            j += 1
        total = sum(acc.values()) or 1.0
        table.append([(k, w / total) for k, w in acc.items()])
    return table


def resample(src: list, src_size: int, dst_size: int) -> bytearray:
    if src_size == dst_size:
        return bytearray(src)

    wx = _weights(src_size, dst_size)
    wy = _weights(src_size, dst_size)

    # horizontal pass -> float rows
    tmp = [[0.0] * (dst_size * 4) for _ in range(src_size)]
    for y in range(src_size):
        srow = y * src_size * 4
        trow = tmp[y]
        for x in range(dst_size):
            wr = wg = wb = wa = 0.0
            for sx, w in wx[x]:
                o = srow + sx * 4
                wr += src[o] * w
                wg += src[o + 1] * w
                wb += src[o + 2] * w
                wa += src[o + 3] * w
            o = x * 4
            trow[o] = wr
            trow[o + 1] = wg
            trow[o + 2] = wb
            trow[o + 3] = wa

    # vertical pass -> bytes
    out = bytearray(dst_size * dst_size * 4)
    for y in range(dst_size):
        o2 = y * dst_size * 4
        acc = [0.0] * (dst_size * 4)
        for sy, w in wy[y]:
            srow = tmp[sy]
            for x in range(dst_size * 4):
                acc[x] += srow[x] * w
        for x in range(dst_size * 4):
            v = int(acc[x] + 0.5)
            out[o2 + x] = 255 if v > 255 else v
    return out


# --------------------------------------------------------------------------- #
# Encoders
# --------------------------------------------------------------------------- #
def encode_png(w: int, h: int, rgba: list) -> bytes:
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)                      # filter type 0 (None)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def encode_bmp_ico(w: int, h: int, rgba: list) -> bytes:
    """32bpp bottom-up DIB with the mandatory 1bpp AND mask."""
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    px = bytearray()
    stride = w * 4
    for y in range(h - 1, -1, -1):
        row = rgba[y * stride:(y + 1) * stride]
        for x in range(w):
            o = x * 4
            px += bytes((row[o + 2], row[o + 1], row[o], row[o + 3]))

    mask_stride = ((w + 31) // 32) * 4
    mask = b"\x00" * (h * mask_stride)
    return header + bytes(px) + mask


def write_ico(path: Path, frames: dict) -> None:
    sizes = sorted(frames, reverse=True)
    blobs = []
    for s in sizes:
        data = frames[s]
        blob = encode_png(s, s, data) if s >= 256 else encode_bmp_ico(s, s, data)
        blobs.append((s, blob))

    count = len(blobs)
    header = struct.pack("<HHH", 0, 1, count)
    offset = len(header) + 16 * count
    entries = b""
    body = b""
    for s, blob in blobs:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        body += blob
        offset += len(blob)
    path.write_bytes(header + entries + body)


# --------------------------------------------------------------------------- #
def main() -> int:
    t0 = time.time()
    ASSETS.mkdir(parents=True, exist_ok=True)

    print(f"[*] Rendering {MASTER}x{MASTER} master at {SS}x supersampling...")
    master = render_master()

    frames = {}
    for s in ICO_SIZES:
        frames[s] = master if s == MASTER else resample(master, MASTER, s)

    ico = ASSETS / "tfast.ico"
    write_ico(ico, frames)

    (ASSETS / "tfast_512.png").write_bytes(
        encode_png(512, 512, resample(master, MASTER, 512))
    )
    (ASSETS / "tfast_256.png").write_bytes(encode_png(MASTER, MASTER, master))
    (ASSETS / "tfast_64.png").write_bytes(
        encode_png(64, 64, resample(master, MASTER, 64))
    )

    for p in sorted(ASSETS.glob("tfast*")):
        print(f"  {p.name:18s} {p.stat().st_size:>9,} bytes")
    print(f"[+] Icon written to {ico}  ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
