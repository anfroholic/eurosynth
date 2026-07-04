# SPDX-FileCopyrightText: © 2024 Leo Moser <leo.moser@pm.me>
# SPDX-License-Identifier: Apache-2.0

import math
import klayout.db as db
import argparse
from PIL import Image, ImageFilter, ImageChops


def _open2(img):
    """2x2 morphological opening on an 'L' image where metal=0 (black).
    Removes sub-2px slivers (e.g. where a screen line meets a curved edge)
    so the halftone stays above min-width/min-space with no acute angles."""
    def off(i, dx, dy):
        return ImageChops.offset(i, dx, dy)
    e = img
    for dx, dy in [(-1, 0), (0, -1), (-1, -1)]:      # erode metal
        e = ImageChops.lighter(e, off(img, dx, dy))
    d = e
    for dx, dy in [(1, 0), (0, 1), (1, 1)]:          # dilate back
        d = ImageChops.darker(d, off(e, dx, dy))
    return d


def _declobber(img):
    """Break diagonal corner-touches (checkerboard 2x2) that arise where a
    dot/mesh screen meets a curved, anti-aliased edge. A metal-metal diagonal
    contact is a zero-width pinch (min-width) and the complementary empty-empty
    diagonal is a zero-space pinch (min-space); filling one corner removes both."""
    px = img.load()
    W, H = img.size
    for _ in range(2):
        for y in range(H - 1):
            for x in range(W - 1):
                a, b = px[x, y], px[x + 1, y]
                c, d = px[x, y + 1], px[x + 1, y + 1]
                if a == 0 and d == 0 and b != 0 and c != 0:
                    px[x + 1, y] = 0
                elif b == 0 and c == 0 and a != 0 and d != 0:
                    px[x, y] = 0
    return img


def _feat(density, screen):
    """Map density 0..1 to an on-grid feature width in [2, screen-2] px.
    Both the feature and its gap stay >=2px so they survive the 2x2 open and
    clear min-width/min-space; never fully solid (leaves grid gaps = slotting)."""
    lo, hi = 2, max(2, screen - 2)
    return max(lo, min(hi, int(round(lo + density * (hi - lo)))))


def _dot_cell(x, y, P, w):
    """Square dot of side w centred in each PxP cell (flat-tone 'dot' style)."""
    lo = (P - w) // 2
    cx, cy = x % P, y % P
    return lo <= cx < lo + w and lo <= cy < lo + w


# Per-style on-grid boolean generators (Halftone Studio v1.1, studio.js STYLES).
# Manhattan modulo forms; python's % is already non-negative so d135/xmesh match
# the JS ((x-y)%P + P)%P. All keep feature + gap >= 2px via _feat's clamp.
_STYLES = {
    "hline": lambda x, y, P, w: (y % P) < w,                     # 0 deg
    "vline": lambda x, y, P, w: (x % P) < w,                     # 90 deg
    "d45":   lambda x, y, P, w: ((x + y) % P) < w,               # 45 deg /
    "d135":  lambda x, y, P, w: ((x - y) % P) < w,               # 135 deg \
    "mesh":  lambda x, y, P, w: ((y % P) < w) or ((x % P) < w),  # H+V grid #
    "xmesh": lambda x, y, P, w: (((x + y) % P) < w) or (((x - y) % P) < w),
    "dot":   _dot_cell,
    # running-bond brick: courses w tall, mortar P-w, head joints offset half a
    # brick every other course
    "brick": lambda x, y, P, w: ((y % P) < w) and
        (((x + (P if (y // P) % 2 else 0)) % (2 * P)) < (2 * P - (P - w))),
    # basket weave: cells checker between vertical and horizontal stripes
    "weave": lambda x, y, P, w: ((x % P) < w) if (((x // P) + (y // P)) % 2)
        else ((y % P) < w),
}


def _hue_style(hd):
    """Hue (degrees) -> screen style. Halftone Studio v1.1 8-band registry."""
    if hd >= 340 or hd < 20:
        return "xmesh"                               # red   -> X crosshatch
    if hd < 45:
        return "brick"                               # orange-> running bond
    if hd < 75:
        return "d45"                                 # yellow-> 45 deg
    if hd < 150:
        return "mesh"                                # green -> grid
    if hd < 200:
        return "d135"                                # cyan  -> 135 deg
    if hd < 250:
        return "hline"                               # blue  -> horizontal
    if hd < 290:
        return "weave"                               # violet-> basket weave
    return "vline"                                   # magenta-> vertical


def _dot_matrix(P):
    """Clustered-dot threshold matrix (v1.1). Cell positions ranked by distance
    from a quarter-pixel-offset centre so ranks 0-3 form a 2x2 seed block (the
    smallest dot then survives _open2); ~P^2 tone levels. metal = density > T."""
    c = (P - 1) / 2.0 - 0.25
    ranked = sorted((math.hypot(x - c, y - c), y * P + x)
                    for y in range(P) for x in range(P))
    T = [0.0] * (P * P)
    for rank, (_, idx) in enumerate(ranked):
        T[idx] = (rank + 0.5) / (P * P)
    return T


def _classify(h, s, v):
    """v1.1 control-map classification (ports studio.js classify()). HSV 0..255.
        black -> solid                 white -> empty
        grey  -> clustered dots 'dotm' (density = darkness, floor 0.15)
        colour-> hue-selected style    (density = clamp(S/0.55, 0.2, 1))
    Grey now renders as clustered dots via the threshold matrix (not lines), for
    ~P^2 tone levels; hue registry: red=xmesh orange=brick yellow=d45 green=mesh
    cyan=d135 blue=hline violet=weave magenta=vline."""
    S, V = s / 255.0, v / 255.0
    if V < 0.28 and S < 0.35:
        return ("solid", 1.0)
    if V > 0.90 and S < 0.12:
        return ("empty", 0.0)
    if S < 0.12 and 0.28 <= V <= 0.90:                # grey -> clustered dots
        return ("dotm", max(0.15, (0.90 - V) / (0.90 - 0.28)))
    if S >= 0.12 and V >= 0.28:                       # colour -> hue style
        return (_hue_style(h * 360.0 / 255.0), min(1.0, max(0.20, S / 0.55)))
    return ("solid", 1.0)                             # dark-but-saturated = metal


def _control_halftone(img_rgb, width, height, screen, solid_screen=0, color_style=""):
    """Color-control halftone: pixel hue picks the style, saturation/value the
    density, per region. Synthesised on-grid, then a 2x2 open cleans slivers.

    solid_screen>0 : render 'solid' (black) regions as a dense horizontal line
    screen at that pitch (feature = pitch-2, gap 2px) instead of flat metal. A
    thick blackletter stroke then becomes fine hairline strips, each thin in the
    vertical dimension, so it clears MSLOT.1 (solid metal >30um needs slots)
    while still reading nearly black. 0 = fully solid (locked-spec default).

    color_style : if set, force every COLOUR region to this texture instead of
    its hue-selected one ('dots' = clustered-dot matrix; else a key in _STYLES).
    density still comes from saturation. Lets a lone colour region (e.g. the
    logo's drop-shadow) carry a texture distinct from the solid_screen letters."""
    g = (img_rgb.resize((width, height), Image.LANCZOS) if (width and height)
         else img_rgb).convert("HSV")
    px = g.load()
    W, H = g.size
    out = Image.new("L", (W, H), 255)
    o = out.load()
    Tm = _dot_matrix(screen)                          # grey clustered-dot matrix
    for y in range(H):
        for x in range(W):
            h, s, v = px[x, y]
            style, d = _classify(h, s, v)
            if style == "empty":
                metal = False
            elif style == "solid":
                metal = (True if solid_screen <= 0
                         else (y % solid_screen) < (solid_screen - 2))
            elif style == "dotm":                     # grey: dither vs the matrix
                metal = d > Tm[(y % screen) * screen + (x % screen)]
            else:                                     # colour region
                cs = color_style or style
                if cs == "dots":
                    metal = d > Tm[(y % screen) * screen + (x % screen)]
                else:
                    metal = _STYLES[cs](x, y, screen, _feat(d, screen))
            if metal:
                o[x, y] = 0
    return _declobber(_open2(out)).convert("1")


def _halftone(gray, width, height, mode, screen, line_width, solid_below, shade_below):
    """Turn a continuous-tone greyscale into an on-grid 1-bit stencil:
    v < solid_below         -> solid metal (crisp line-art)
    solid_below..shade_below-> screened (dot/line/mesh) metal
    >= shade_below          -> empty.
    Screen is synthesised AT the metal grid (resize first) so features land
    on-grid; then a 2x2 open cleans edge slivers. Returns a mode '1' image
    with metal = 0 (black)."""
    g = gray.resize((width, height), Image.LANCZOS) if (width and height) else gray
    W, H = g.size
    px = g.load()
    out = Image.new("L", (W, H), 255)
    o = out.load()

    T = None
    if mode == "dot":                                 # clustered-dot thresholds
        cx = cy = (screen - 1) / 2.0
        cells = sorted((((i - cy) ** 2 + (j - cx) ** 2), i, j)
                       for i in range(screen) for j in range(screen))
        T = [[0.0] * screen for _ in range(screen)]
        for r, (_, i, j) in enumerate(cells):
            T[i][j] = 1.0 - (r + 0.5) / (screen * screen)

    for y in range(H):
        for x in range(W):
            v = px[x, y]
            metal = v < solid_below
            if not metal and v < shade_below:
                if mode == "line":
                    metal = (y % screen) < line_width
                elif mode == "mesh":
                    metal = ((y % screen) < line_width) or ((x % screen) < line_width)
                elif mode == "dot":
                    metal = v < T[y % screen][x % screen] * 255
            if metal:
                o[x, y] = 0
    return _declobber(_open2(out)).convert("1")


def convert_to_gds(
    input_filepath,
    output_filepath,
    cellname="TOP",
    scale=1.0,
    width=None,
    height=None,
    threshold=128,
    invert=False,
    invert_alpha=False,
    merge=False,
    smooth=False,
    blur=0.0,
    halftone="none",
    screen=6,
    solid_screen=0,
    color_style="",
    line_width=2,
    solid_below=96,
    shade_below=210,
    pixel_size=6,
    foregrounds=["1/0"],
    boundaries=["0/0"],
):

    ly = db.Layout()
    ly.dbu = 0.001

    top = ly.create_cell(cellname)
    to_um = db.CplxTrans(ly.dbu)
    from_um = to_um.inverted()

    # Open the image
    img = Image.open(input_filepath)

    # Add the foregrounds
    foreground_layers = []
    for foreground in foregrounds:
        layer, datatype = foreground.split('/')
        foreground_layer = db.LayerInfo(int(layer), int(datatype))
        foreground_layers.append(foreground_layer)

    if not invert_alpha:
        # Create a white rgba background
        new_image = Image.new("RGBA", img.size, "WHITE")
    else:
        # Create a black rgba background
        new_image = Image.new("RGBA", img.size, "BLACK")

    # Paste the image on the background
    new_image.paste(img, (0, 0), img)

    # Convert the image to grayscale
    new_image_grayscale = new_image.convert("L")

    # Optional pre-threshold Gaussian blur. Melts halftone/dithered fills
    # (e.g. the gray gear) into mid-gray so they drop out at threshold, while
    # solid line-art stays dark. Keeps the 1-bit stencil DRC-clean.
    if blur and blur > 0.0:
        new_image_grayscale = new_image_grayscale.filter(ImageFilter.GaussianBlur(blur))

    # new_image_grayscale.show()

    # Convert the image to binary. In halftone mode the greys become an on-grid
    # dot/line/mesh screen (line-art stays solid); otherwise a plain threshold.
    if halftone == "control":
        new_image_binary = _control_halftone(
            new_image.convert("RGB"), width, height, screen, solid_screen, color_style,
        )
    elif halftone and halftone != "none":
        new_image_binary = _halftone(
            new_image_grayscale, width, height, halftone,
            screen, line_width, solid_below, shade_below,
        )
    else:
        new_image_binary = new_image_grayscale.point(lambda x: 255 if x > threshold else 0)
        new_image_binary = new_image_binary.convert("1")

    # new_image_binary.show()

    # Scale down the image
    if scale != 1.0:
        new_image_binary.thumbnail(
            (new_image_binary.width * scale, new_image_binary.height * scale),
            Image.LANCZOS,
        )

    if width or height:
        new_image_binary.thumbnail(
            (width, height),
            Image.LANCZOS,
        )

    # Use a region to merge pixels together
    if merge:
        top_region = db.Region()

    for y in range(new_image_binary.height):
        for x in range(new_image_binary.width):
            # If pixel is set
            pixel = new_image_binary.getpixel((x, y))

            if pixel and not invert or not pixel and invert:
                pixel = db.DBox(0.0, 0.0, pixel_size, pixel_size).moved(
                    x * pixel_size, (new_image_binary.height - y - 1) * pixel_size
                )

                if merge:
                    pixel_polygon = db.DPolygon(pixel)
                    top_region.insert(from_um * pixel_polygon)
                else:
                    for foreground_layer in foreground_layers:
                        top.shapes(foreground_layer).insert(pixel)

    if merge:
        top_region.merge()

        if smooth:
            top_region = top_region.smoothed(from_um * pixel_size * 0.99)

        for foreground_layer in foreground_layers:
            top.shapes(foreground_layer).insert(top_region)

    # Add the boundaries
    for boundary in boundaries:
        layer, datatype = boundary.split('/')
        boundary_layer = db.LayerInfo(int(layer), int(datatype))
        top.shapes(boundary_layer).insert(db.DBox.new(0, 0, new_image_binary.width * pixel_size, new_image_binary.height * pixel_size))

    # Save the layout to a file
    ly.write(output_filepath)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        prog="img2gds", description="Convert an image to GDS format"
    )

    parser.add_argument("image_path")
    parser.add_argument("gds_path")
    parser.add_argument("--cellname", default="TOP", help="top cellname")
    parser.add_argument(
        "--pixel-size", type=float, default=0.3, help="pixel size in um"
    )
    parser.add_argument(
        "--scale", type=float, default=1.0, help="downscale the image, e.g. 0.5"
    )
    parser.add_argument(
        "--width", type=int, default=None, help="scale to image width"
    )
    parser.add_argument(
        "--height", type=int, default=None, help="scale to image height"
    )
    parser.add_argument(
        "--threshold", type=int, default=128, help="threshold to compare against"
    )
    parser.add_argument("--invert", action="store_true", help="invert the pixels")
    parser.add_argument(
        "--invert-alpha", action="store_true", help="invert the alpha pixels"
    )
    parser.add_argument("--merge", action="store_true", help="merge polygons")
    parser.add_argument(
        "--foreground",
        nargs="*",
        type=str,
        help="gds layer/datatype pair for foreground pixels e.g. 0/0",
    )
    parser.add_argument(
        "--boundary",
        nargs="*",
        type=str,
        help="gds layer/datatype pairs for boundary e.g. 0/0",
    )
    parser.add_argument("--smooth", action="store_true", help="smooth the edges")
    parser.add_argument(
        "--blur", type=float, default=0.0,
        help="Gaussian blur radius (px) applied before threshold; drops halftone fills",
    )
    parser.add_argument(
        "--halftone", choices=["none", "line", "mesh", "dot", "control"], default="none",
        help="screen greys into an on-grid halftone (line-art stays solid); "
             "'control' = colour picks style per region (black=solid, grey=line, "
             "green=mesh, blue=dots; saturation/darkness = density)",
    )
    parser.add_argument("--screen", type=int, default=6, help="halftone screen pitch (px)")
    parser.add_argument("--solid-screen", type=int, default=0,
                        help="control-mode: render 'solid' (black) as a dense hline screen "
                             "at this pitch (feature=pitch-2) so thick strokes clear MSLOT; 0=flat solid")
    parser.add_argument("--color-style", type=str, default="",
                        help="control-mode: force all colour regions to this texture "
                             "('dots' or an _STYLES key e.g. d45/d135/mesh/vline); '' = hue-selected")
    parser.add_argument("--line-width", type=int, default=2, help="halftone line/mesh width (px)")
    parser.add_argument("--solid-below", type=int, default=96, help="grey < this -> solid metal")
    parser.add_argument("--shade-below", type=int, default=210, help="grey < this -> screened; else empty")

    args = parser.parse_args()

    convert_to_gds(
        args.image_path,
        args.gds_path,
        cellname=args.cellname,
        scale=args.scale,
        width=args.width,
        height=args.height,
        threshold=args.threshold,
        invert=args.invert,
        invert_alpha=args.invert_alpha,
        merge=args.merge,
        smooth=args.smooth,
        blur=args.blur,
        halftone=args.halftone,
        screen=args.screen,
        solid_screen=args.solid_screen,
        color_style=args.color_style,
        line_width=args.line_width,
        solid_below=args.solid_below,
        shade_below=args.shade_below,
        pixel_size=args.pixel_size,
        foregrounds=args.foreground,
        boundaries=args.boundary,
    )
