"""
piskel_to_amos.py
-----------------
Converts a Piskel-exported C sprite file into AMOS Pro `Data` statements.

Each pixel is mapped to an index in the standard Amiga palette:
  Palette $000,$00F,$0F0,$F00,$FF0,$0FF,$F0F,$FFF
  Index     0     1     2    3     4     5     6    7
  Name   black  blue green red yellow teal  pink white

Usage:
  python piskel_to_amos.py <sprite.c>           # prints to stdout
  python piskel_to_amos.py <sprite.c> out.txt   # writes to file
"""

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Palette definition
# ---------------------------------------------------------------------------
# AMOS 12-bit hex  -> index, name, 8-bit RGB equivalent
PALETTE = [
    (0, "black",  (0,   0,   0)),    # $000
    (1, "blue",   (0,   0,   255)),  # $00F
    (2, "green",  (0,   255, 0)),    # $0F0
    (3, "red",    (255, 0,   0)),    # $F00
    (4, "yellow", (255, 255, 0)),    # $FF0
    (5, "teal",   (0,   255, 255)),  # $0FF
    (6, "pink",   (255, 0,   255)),  # $F0F
    (7, "white",  (255, 255, 255)),  # $FFF
]

# Fast reverse-lookup: (R,G,B) -> palette index
_RGB_TO_IDX = {rgb: idx for idx, _, rgb in PALETTE}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_piskel_c(filepath: str):
    """
    Read a Piskel C export and return (width, height, frames, pixel_frames).

    pixel_frames is a list of `frames` lists, each containing width*height
    uint32 ARGB values in row-major order.
    """
    text = Path(filepath).read_text()

    def get_define(suffix):
        m = re.search(rf'#define\s+\w+_{suffix}\s+(\d+)', text)
        if not m:
            raise ValueError(f"Missing #define for *_{suffix} in {filepath}")
        return int(m.group(1))

    width  = get_define("FRAME_WIDTH")
    height = get_define("FRAME_HEIGHT")
    frames = get_define("FRAME_COUNT")

    # Collect every 0x... literal — these are exclusively the pixel values
    all_pixels = [int(h, 16) for h in re.findall(r'0x[0-9A-Fa-f]+', text)]

    ppf = width * height  # pixels per frame
    expected = frames * ppf
    if len(all_pixels) < expected:
        raise ValueError(
            f"Expected {expected} pixel values, found {len(all_pixels)}"
        )

    pixel_frames = [all_pixels[f * ppf:(f + 1) * ppf] for f in range(frames)]
    return width, height, frames, pixel_frames


# ---------------------------------------------------------------------------
# Color mapping
# ---------------------------------------------------------------------------
def argb_to_palette_index(argb: int) -> int:
    """
    Map a Piskel pixel value to the nearest palette index.

    Piskel's C export uses 0xAABBGGRR (ABGR) byte order, so R sits in
    the least-significant byte and B in the third byte — the reverse of
    the more common ARGB convention.
    """
    r =  argb        & 0xFF   # R is the least-significant byte
    g = (argb >>  8) & 0xFF   # G is the second byte
    b = (argb >> 16) & 0xFF   # B is the third byte

    # Snap to 4-bit Amiga range (0 or F)
    key = (255 if r >= 128 else 0,
           255 if g >= 128 else 0,
           255 if b >= 128 else 0)

    if key in _RGB_TO_IDX:
        return _RGB_TO_IDX[key]

    # Nearest-neighbour fallback for unusual intermediate colours
    return min(
        range(len(PALETTE)),
        key=lambda i: sum((a - b_) ** 2
                          for a, b_ in zip(PALETTE[i][2], (r, g, b)))
    )


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------
def generate_amos_data(filepath: str, output_path: str | None = None):
    width, height, frames, pixel_frames = parse_piskel_c(filepath)

    pal_hex   = ",".join(f"${idx:X}{r//17:X}{g//17:X}{b//17:X}"
                         for idx, _, (r, g, b) in PALETTE)
    pal_names = ",".join(name for _, name, _ in PALETTE)

    lines = [
        f"' Converted from : {Path(filepath).name}",
        f"' Sprite size    : {width} x {height}  ({frames} frame{'s' if frames != 1 else ''})",
        f"' Palette        : $000,$00F,$0F0,$F00,$FF0,$0FF,$F0F,$FFF",
        f"'                  {pal_names}",
        "",
    ]

    for fi, pixels in enumerate(pixel_frames):
        if frames > 1:
            lines.append(f"' --- Frame {fi + 1} of {frames} ---")

        for row in range(height):
            row_pixels = pixels[row * width:(row + 1) * width]
            indices = ",".join(str(argb_to_palette_index(px)) for px in row_pixels)
            lines.append(f"Data {indices}")

        if fi < frames - 1:
            lines.append("")

    output_text = "\n".join(lines) + "\n"

    if output_path:
        Path(output_path).write_text(output_text)
        print(f"Written to: {output_path}  ({frames * height} Data lines)")
    else:
        print(output_text)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    in_file  = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else None
    generate_amos_data(in_file, out_file)