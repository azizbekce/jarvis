from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter


def _render_base(size: int = 512) -> Image.Image:
    root = Path(__file__).resolve().parent.parent
    src_path = root / "assets" / "arc_reactor_source.png"
    if not src_path.is_file():
        raise FileNotFoundError(f"Missing photorealistic icon source: {src_path}")

    raw = Image.open(src_path).convert("RGBA")
    hi_size = 1024
    raw = raw.resize((hi_size, hi_size), Image.Resampling.LANCZOS)

    # Create a supersampled circular alpha mask matching the outer titanium bezel
    mask = Image.new("L", (hi_size, hi_size), 0)
    mdraw = ImageDraw.Draw(mask)
    cx = cy = hi_size / 2.0
    radius = hi_size * 0.462
    mdraw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill=255,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1.8))

    out = Image.new("RGBA", (hi_size, hi_size), (0, 0, 0, 0))
    out.paste(raw, (0, 0), mask)

    if size != hi_size:
        out = out.resize((size, size), Image.Resampling.LANCZOS)
    return out


def main():
    root = Path(__file__).resolve().parent.parent
    out = root / "assets" / "JARVIS.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    base = _render_base(512)
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    base.save(out, format="ICO", sizes=sizes)
    print(f"Wrote photorealistic {out}")


if __name__ == "__main__":
    main()
