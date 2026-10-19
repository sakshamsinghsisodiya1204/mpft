"""WCAG contrast of the design tokens: 4.5:1 for text pairs, 3:1 for chart colours, in both themes."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent / "web" / "static" / "tokens.css").read_text()


def tokens(block_start):
    i = CSS.index(block_start)
    body = CSS[CSS.index("{", i) + 1:CSS.index("}", i)]
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", body))


LIGHT = tokens(":root {")
DARK = tokens(':root[data-theme="dark"]')


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


TEXT_PAIRS = [("text", "bg"), ("text", "surface"), ("text", "surface-2"), ("text-2", "bg"), ("text-2", "surface"), ("text-2", "surface-2"),
              ("accent", "surface"), ("accent", "accent-soft"), ("on-accent", "accent"), ("on-accent", "accent-hover"), ("ok", "surface"), ("ok", "surface-2"),
              ("warn", "surface"), ("warn", "surface-2"), ("err", "surface"), ("err", "surface-2")]


def test_text_contrast_both_themes():
    for name, t in (("light", LIGHT), ("dark", DARK)):
        for fg, bg in TEXT_PAIRS:
            assert ratio(t[fg], t[bg]) >= 4.5, f"{name}: {fg} on {bg} = {ratio(t[fg], t[bg]):.2f}"


def test_chart_colours_contrast_both_themes():
    for name, t in (("light", LIGHT), ("dark", DARK)):
        for i in range(8):
            assert ratio(t[f"p{i}"], t["surface"]) >= 3.0, f"{name}: path {i} = {ratio(t[f'p{i}'], t['surface']):.2f}"
