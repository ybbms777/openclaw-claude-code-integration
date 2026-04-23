#!/usr/bin/env python3
"""Generate a cleaner, high-impact GitHub banner for OECK."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
PNG_PATH = ASSETS / "oeck-github-banner.png"
PHILOSOPHY_PATH = ASSETS / "oeck-visual-philosophy.md"

WIDTH = 1280
HEIGHT = 640


def load_font(candidates: list[tuple[str, int | None]], size: int) -> ImageFont.FreeTypeFont:
    search_roots = [
        Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
    ]
    for name, index in candidates:
        for root in search_roots:
            path = root / name
            if path.exists():
                kwargs = {"size": size}
                if index is not None:
                    kwargs["index"] = index
                return ImageFont.truetype(str(path), **kwargs)
    return ImageFont.load_default()


def background() -> Image.Image:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (8, 11, 17, 255))
    pixels = image.load()
    for y in range(HEIGHT):
        blend = y / (HEIGHT - 1)
        top = (7, 10, 16)
        bottom = (17, 22, 32)
        row = tuple(int(top[i] + (bottom[i] - top[i]) * blend) for i in range(3))
        for x in range(WIDTH):
            pixels[x, y] = (*row, 255)
    return image


def add_glow(base: Image.Image, box: tuple[int, int, int, int], color: tuple[int, int, int, int], blur: int) -> None:
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse(box, fill=color)
    overlay = overlay.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(overlay)


def add_column(base: Image.Image) -> None:
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.rounded_rectangle((842, 64, 1186, 576), radius=72, fill=(46, 210, 232, 48))
    draw.rounded_rectangle((874, 104, 1150, 536), radius=56, fill=(20, 116, 132, 82))
    glow = glow.filter(ImageFilter.GaussianBlur(34))
    base.alpha_composite(glow)

    panel = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle((860, 82, 1170, 558), radius=64, fill=(9, 17, 24, 214), outline=(185, 241, 247, 136), width=2)
    draw.rounded_rectangle((892, 120, 1138, 520), radius=52, fill=(14, 39, 48, 216), outline=(101, 219, 233, 82), width=1)
    base.alpha_composite(panel)


def add_slash(base: Image.Image) -> None:
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.polygon(
        [(676, 470), (1020, 246), (1118, 246), (774, 470)],
        fill=(255, 124, 71, 230),
    )
    draw.polygon(
        [(688, 490), (1032, 266), (1086, 266), (742, 490)],
        fill=(255, 207, 174, 102),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(8))
    base.alpha_composite(overlay)


def add_structure(draw: ImageDraw.ImageDraw) -> None:
    for x in range(786, 1200, 62):
        draw.line((x, 96, x, 548), fill=(173, 224, 230, 18), width=1)
    for y in range(112, 548, 62):
        draw.line((816, y, 1200, y), fill=(173, 224, 230, 18), width=1)

    draw.line((94, 516, 724, 516), fill=(255, 255, 255, 42), width=1)
    draw.line((94, 542, 720, 542), fill=(255, 255, 255, 20), width=1)


def add_title(draw: ImageDraw.ImageDraw) -> None:
    eyebrow_font = load_font([("Avenir Next.ttc", 0), ("HelveticaNeue.ttc", 0)], 22)
    kicker_font = load_font([("Avenir Next.ttc", 0), ("HelveticaNeue.ttc", 0)], 28)
    title_font = load_font([("DIN Condensed Bold.ttf", None), ("Arial Black.ttf", None)], 166)
    subtitle_font = load_font([("Avenir Next.ttc", 0), ("HelveticaNeue.ttc", 0)], 26)
    chinese_font = load_font([("Hiragino Sans GB.ttc", 0)], 22)

    draw.text((86, 78), "OPENCLAW / CLAUDE / CODEX", font=eyebrow_font, fill=(255, 211, 179, 255))
    draw.text((86, 116), "OECK", font=title_font, fill=(246, 248, 249, 255))
    draw.text((92, 286), "Enhancement & Compatibility Kit", font=kicker_font, fill=(227, 235, 239, 235))
    draw.text((92, 336), "Unified policy, context, distribution, and observability.", font=subtitle_font, fill=(185, 211, 217, 228))
    draw.text((92, 376), "统一策略 · 统一上下文 · 统一分发 · 统一观测 · 统一适配器", font=chinese_font, fill=(173, 225, 232, 230))


def add_stack(draw: ImageDraw.ImageDraw) -> None:
    label_font = load_font([("Avenir Next.ttc", 0), ("HelveticaNeue.ttc", 0)], 24)
    mono_font = load_font([("Helvetica.ttc", 1), ("Avenir.ttc", 0)], 17)

    draw.text((910, 132), "Runtime Surface", font=label_font, fill=(246, 248, 249, 240))
    items = [
        ("01", "Policy Engine"),
        ("02", "Context Engine"),
        ("03", "Plugin + Bundle"),
        ("04", "Optional Adapters"),
    ]
    y = 200
    for code, label in items:
        draw.rounded_rectangle((908, y - 8, 1124, y + 36), radius=16, fill=(7, 13, 20, 114), outline=(155, 235, 244, 48), width=1)
        draw.text((928, y), code, font=mono_font, fill=(255, 181, 141, 255))
        draw.text((978, y - 1), label, font=label_font, fill=(231, 238, 241, 244))
        y += 76


def add_host_badges(draw: ImageDraw.ImageDraw) -> None:
    font = load_font([("Avenir Next.ttc", 0), ("HelveticaNeue.ttc", 0)], 20)
    badges = [
        ("OpenClaw Native", (255, 129, 84, 230), 92),
        ("Claude Bundle", (60, 201, 221, 226), 314),
        ("Codex Bundle", (79, 118, 255, 230), 516),
    ]
    y = 566
    for text, color, x in badges:
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0] + 32
        draw.rounded_rectangle((x, y - 6, x + width, y + 30), radius=18, fill=(10, 16, 23, 208), outline=color, width=2)
        draw.text((x + 16, y), text, font=font, fill=(246, 248, 249, 250))


def add_texture(base: Image.Image) -> None:
    noise = Image.effect_noise((WIDTH, HEIGHT), 8).convert("L")
    noise = ImageOps.colorize(noise, black=(8, 11, 17), white=(22, 30, 39)).convert("RGBA")
    noise.putalpha(22)
    base.alpha_composite(noise)


def add_ghost_title(draw: ImageDraw.ImageDraw) -> None:
    ghost_font = load_font([("DIN Condensed Bold.ttf", None), ("Arial Black.ttf", None)], 170)
    draw.text((102, 118), "OECK", font=ghost_font, fill=(108, 204, 219, 30), stroke_width=1, stroke_fill=(108, 204, 219, 46))
    draw.text((110, 126), "OECK", font=ghost_font, fill=(255, 140, 92, 16))


def write_philosophy() -> None:
    text = """# Luminous Monolith

Luminous Monolith treats software infrastructure as a single engineered object rather than a collage of features. The composition should feel carved, not assembled: one dominant form, one dominant gesture, and enough restraint that every decision reads as deliberate. The final image must look meticulously crafted and reduced until only the strongest visual signals remain.

Color should work like energy under pressure. The palette stays dark and controlled, then allows only a few calibrated emissions: a cold cyan glow for continuity, context, and system surface; a hotter ember slash for intervention, compatibility, and decisive routing. This contrast should feel expensive and precise, the product of deep expertise rather than decorative contrast.

Scale is the main communication system. One oversized typographic mass should anchor the entire piece and create immediate recognition from a distance. Supporting information must stay secondary, carefully spaced, and surgically sparse. The work should look like it was refined for countless hours by someone operating at master level, with no line, margin, or proportion left accidental.

Geometry should suggest containment and transfer. A monolithic vertical volume holds the system surface, while a single diagonal vector cuts across it to imply activation and host-to-host movement. These forms should feel structural, as if the image were documenting a protocol artifact from an imaginary discipline. The result must be painstakingly tuned, with silence doing as much work as detail.

Typography is forceful but disciplined. Words act as visual architecture first and explanation second. The hierarchy should be unmistakable: a monumental mark, a restrained descriptor, and a few precisely placed labels. The finished artifact must read as premium, confident, and unmistakably product-grade, with craftsmanship visible in every interval and edge.
"""
    PHILOSOPHY_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    write_philosophy()

    image = background()
    add_glow(image, (-120, 220, 560, 880), (255, 125, 78, 64), 90)
    add_glow(image, (720, -40, 1310, 620), (52, 206, 230, 84), 110)
    add_glow(image, (786, 96, 1242, 558), (52, 206, 230, 46), 34)
    add_texture(image)
    add_column(image)
    add_slash(image)

    draw = ImageDraw.Draw(image, "RGBA")
    add_structure(draw)
    add_ghost_title(draw)
    add_title(draw)
    add_stack(draw)
    add_host_badges(draw)

    image = image.convert("RGB")
    image.save(PNG_PATH, optimize=True)
    print(PNG_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
