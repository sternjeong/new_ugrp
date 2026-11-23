"""Build the 3분커리 logo files.

The orange 3 is drawn here from straight lines. 분커리 is Black Han Sans (SIL Open Font License) converted to
outlines, so the SVG files show the same on any device without the font.

Needs fonttools (not a service dependency) and the font file, which is not kept in this repository:
    python3 -m venv /tmp/logo-venv && /tmp/logo-venv/bin/pip install fonttools
    curl -L -o /tmp/BlackHanSans-Regular.ttf https://raw.githubusercontent.com/google/fonts/main/ofl/blackhansans/BlackHanSans-Regular.ttf
    /tmp/logo-venv/bin/python tools/build_logo.py /tmp/BlackHanSans-Regular.ttf
"""
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
ORANGE, INK, WHITE = '#f6a700', '#1f1e1c', '#ffffff'      # POSTECH Orange, text colour, white
STROKE, BUN_RATIO = .30, .6                                # stroke of the 3 as a share of the height of 커리; 분 is 60% of the 3
# Stacked logo: 3 and a small 분 on top, 커리 below.
WIDTH, MARGIN, THREE_RATIO, GAP = 420, 44, 1.3, .16        # width of 커리, clear space, 3 is 1.3x the height of 커리, gap between blocks
# Horizontal logo for the page header: 3, small 분, 커리 on one line.
LINE_H, LINE_MARGIN, THREE_W, LINE_GAP = 200, 30, .78, .13  # height of the line, clear space, width of the 3 and gap as shares of the height


class Face:
    def __init__(self, path):
        self.font = TTFont(path)
        self.glyphs, self.cmap, self.upm = self.font.getGlyphSet(), self.font.getBestCmap(), self.font['head'].unitsPerEm

    def bounds(self, ch):
        pen = BoundsPen(self.glyphs)
        self.glyphs[self.cmap[ord(ch)]].draw(pen)
        return pen.bounds

    def word(self, text, left, top, k, fill, track=-0.01):
        """Outlined text at its own proportions, ink starting at (left, top). Returns (svg, ink width, ink height)."""
        x0 = self.bounds(text[0])[0]
        ymax, ymin = max(self.bounds(c)[3] for c in text), min(self.bounds(c)[1] for c in text)
        pen_x, parts, right = 0.0, [], 0.0
        for c in text:
            pen = SVGPathPen(self.glyphs)
            self.glyphs[self.cmap[ord(c)]].draw(pen)
            parts.append(f'<path transform="translate({pen_x:.1f} 0)" d="{pen.getCommands()}"/>')
            right = pen_x + self.bounds(c)[2]
            pen_x += self.glyphs[self.cmap[ord(c)]].width + track * self.upm
        svg = f'<g fill="{fill}" transform="translate({left - x0 * k:.2f} {top + ymax * k:.2f}) scale({k:.5f} {-k:.5f})">{"".join(parts)}</g>'
        return svg, (right - x0) * k, (ymax - ymin) * k


def three(x, y, w, h, stroke):
    """The zigzag 3: two bars joined by two diagonals, one closed outline of twelve points."""
    t, tx = stroke, min(stroke * 1.55, w * .45)
    points = [(0, 0), (w, 0), (w, t), (w * .62, h / 2), (w, h - t), (w, h), (0, h), (0, h - t), (w - tx, h - t), (w * .62 - tx, h / 2), (w - tx, t), (0, t)]
    return f'<path fill="{ORANGE}" d="M' + ' L'.join(f'{x + px:.2f} {y + py:.2f}' for px, py in points) + ' Z"/>'


def svg(w, h, body, background=None):
    rect = f'<rect width="{w:.0f}" height="{h:.0f}" fill="{background}"/>' if background else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}" role="img" aria-label="3분커리">'
            f'<title>3분커리</title>{rect}{body}</svg>\n')


def stacked(face, letters, background=None, margin=MARGIN):
    _, w1, h1 = face.word('커리', 0, 0, 1, letters)
    k = WIDTH / w1
    hk = h1 * k
    top_h, gap = hk * THREE_RATIO, hk * GAP
    _, bw1, bh1 = face.word('분', 0, 0, 1, letters)
    kb = top_h * BUN_RATIO / bh1
    bun_w, bun_h = bw1 * kb, bh1 * kb
    body = three(margin, margin, WIDTH - gap - bun_w, top_h, hk * STROKE)
    body += face.word('분', margin + WIDTH - bun_w, margin + top_h - bun_h, kb, letters)[0]
    body += face.word('커리', margin, margin + top_h + gap, k, letters)[0]
    return svg(WIDTH + 2 * margin, top_h + gap + hk + 2 * margin, body, background)


def horizontal(face, letters, background=None, margin=LINE_MARGIN):
    _, _, h1 = face.word('커리', 0, 0, 1, letters)
    k = LINE_H / h1
    kb = k * BUN_RATIO
    three_w, gap = LINE_H * THREE_W, LINE_H * LINE_GAP
    _, bun_w, bun_h = face.word('분', 0, 0, kb, letters)
    _, name_w, _ = face.word('커리', 0, 0, k, letters)
    x_bun = margin + three_w + gap * .7
    body = three(margin, margin, three_w, LINE_H, LINE_H * STROKE)
    body += face.word('분', x_bun, margin + LINE_H - bun_h, kb, letters)[0]
    body += face.word('커리', x_bun + bun_w + gap, margin, k, letters)[0]
    return svg(x_bun + bun_w + gap + name_w + margin, LINE_H + 2 * margin, body, background)


def mark(size=512):
    """Square symbol for the browser tab and profile pictures: the 3 alone on the dark ground."""
    box_w, box_h = size * .50, size * .62
    body = f'<rect width="{size}" height="{size}" rx="{size * .14:.0f}" fill="{INK}"/>' + three((size - box_w) / 2, (size - box_h) / 2, box_w, box_h, size * .135)
    return svg(size, size, body)


def main():
    face = Face(sys.argv[1])
    static, docs = ROOT / 'curri' / 'static' / 'brand', ROOT / 'docs' / 'brand'
    static.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    files = {
        static / 'logo.svg': horizontal(face, INK, margin=0),                  # page header: no ground, no margin
        static / 'logo-dark.svg': horizontal(face, WHITE, margin=0),           # page header in the dark theme
        static / 'favicon.svg': mark(),
        docs / 'logo-horizontal.svg': horizontal(face, INK, WHITE),            # for documents: ground and clear space included
        docs / 'logo-horizontal-dark.svg': horizontal(face, WHITE, INK),
        docs / 'logo-stacked.svg': stacked(face, INK, WHITE),
        docs / 'logo-stacked-dark.svg': stacked(face, WHITE, INK),
        docs / 'mark.svg': mark(),
    }
    for path, text in files.items():
        path.write_text(text)
    print('written:', ', '.join(str(p.relative_to(ROOT)) for p in files))


if __name__ == '__main__':
    main()
