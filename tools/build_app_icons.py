"""Home screen icons (PNG) from the tab icon's shape (curri/static/brand/favicon.svg), standard library only.

iOS and Android round or mask the corners themselves, so these are full squares: the orange 3 on the ink
background. The 3 spans the middle half of the square, inside Android's maskable safe zone (the middle 80%).
    python3 tools/build_app_icons.py      # writes curri/static/brand/icon-{180,192,512}.png
"""
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INK, ORANGE = (0x1f, 0x1e, 0x1c), (0xf6, 0xa7, 0x00)
# The 3 in favicon.svg, on its 512 x 512 grid
THREE = [(128.00, 97.28), (384.00, 97.28), (384.00, 166.40), (286.72, 256.00), (384.00, 345.60), (384.00, 414.72),
         (128.00, 414.72), (128.00, 345.60), (276.86, 345.60), (179.58, 256.00), (276.86, 166.40), (128.00, 166.40)]
SAMPLES = 4  # per pixel side; 16 samples smooth the slanted edges


def coverage(size):
    """Share of each pixel inside the 3, from SAMPLES x SAMPLES scanline samples (even-odd rule)."""
    scale = size / 512
    poly = [(x * scale, y * scale) for x, y in THREE]
    edges = list(zip(poly, poly[1:] + poly[:1]))
    cover = [[0.0] * size for _ in range(size)]
    step = 1 / SAMPLES
    for row in range(size * SAMPLES):
        y = (row + .5) * step
        xs = sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in edges if (y0 <= y < y1) or (y1 <= y < y0))
        line = cover[row // SAMPLES]
        for a, b in zip(xs[::2], xs[1::2]):
            for col in range(int(a * SAMPLES + .5 - 1e-9), int(b * SAMPLES + .5 - 1e-9)):
                if 0 <= col < size * SAMPLES:
                    line[col // SAMPLES] += 1 / (SAMPLES * SAMPLES)
    return cover


def png(size):
    cover = coverage(size)
    rows = bytearray()
    for line in cover:
        rows.append(0)
        for c in line:
            c = min(1.0, c)
            rows += bytes(round(i + (o - i) * c) for i, o in zip(INK, ORANGE))
    chunk = lambda tag, data: struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b''))


if __name__ == '__main__':
    for size in (180, 192, 512):
        path = ROOT / 'curri' / 'static' / 'brand' / f'icon-{size}.png'
        path.write_bytes(png(size))
        print(path.relative_to(ROOT), path.stat().st_size, 'bytes')
