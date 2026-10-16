"""Genera el icono de Rubencho AI (rubencho.ico y rubencho.png) a partir de código."""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).parent
S = 1024                                # se dibuja grande y se reduce (bordes suaves)


def radial(size, inner, outer, center, radius):
    """Degradado radial (de inner en el centro a outer en el radio)."""
    img = Image.new("RGBA", (size, size))
    px = img.load()
    cx, cy = center
    for y in range(size):
        for x in range(size):
            t = min(1.0, math.hypot(x - cx, y - cy) / radius)
            t = t ** 1.15
            px[x, y] = tuple(int(inner[i] + (outer[i] - inner[i]) * t) for i in range(4))
    return img


def build(small: bool = False) -> Image.Image:
    """small=True: sin halo y casi sin margen (para 16–48 px: barra de tareas y bandeja)."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m = S * (0.02 if small else 0.07)   # margen
    box = [m, m, S - m, S - m]

    if not small:
        # Halo exterior suave
        glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([m * 0.55, m * 0.55, S - m * 0.55, S - m * 0.55],
                                     fill=(64, 140, 255, 150))
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(S * 0.03)))

    # Esfera: degradado azul con la luz arriba a la izquierda
    sphere = radial(S, (150, 205, 255, 255), (16, 52, 170, 255), (S * 0.38, S * 0.34), S * 0.62)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    img.paste(sphere, (0, 0), mask)

    # Barras de voz (ecualizador) en el centro
    waves = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(waves)
    cx, cy = S * 0.5, S * 0.53
    bars = [0.18, 0.34, 0.52, 0.34, 0.18] if small else [0.16, 0.30, 0.46, 0.30, 0.16]
    bw, gap = (S * 0.085, S * 0.05) if small else (S * 0.062, S * 0.045)
    total = len(bars) * bw + (len(bars) - 1) * gap
    x = cx - total / 2
    for h in bars:
        hh = S * h
        d.rounded_rectangle([x, cy - hh / 2, x + bw, cy + hh / 2], radius=bw / 2,
                            fill=(255, 255, 255, 245))
        x += bw + gap
    shadow = waves.copy()
    shadow.putalpha(shadow.getchannel("A").point(lambda a: int(a * 0.35)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(S * 0.012))
    tinted = Image.new("RGBA", (S, S), (8, 30, 110, 0))
    tinted.putalpha(shadow.getchannel("A"))
    img.alpha_composite(tinted, (int(S * 0.008), int(S * 0.014)))
    img = Image.alpha_composite(img, waves)

    # Brillo especular arriba a la izquierda
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([S * 0.22, S * 0.13, S * 0.62, S * 0.36], fill=(255, 255, 255, 105))
    hl = hl.filter(ImageFilter.GaussianBlur(S * 0.03))
    hl_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hl_mask).ellipse(box, fill=255)
    hl.putalpha(Image.composite(hl.getchannel("A"), Image.new("L", (S, S), 0), hl_mask))
    img = Image.alpha_composite(img, hl)

    # Borde fino más claro
    ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse(box, outline=(190, 225, 255, 160), width=int(S * 0.012))
    img = Image.alpha_composite(img, ring)
    return img


if __name__ == "__main__":
    big, small = build(), build(small=True)
    big.resize((256, 256), Image.LANCZOS).save(HERE / "rubencho.png")
    big.resize((512, 512), Image.LANCZOS).save(HERE / "rubencho_512.png")
    small.resize((64, 64), Image.LANCZOS).save(HERE / "rubencho_bandeja.png")
    frames = ([big.resize((n, n), Image.LANCZOS) for n in (256, 128, 64)] +
              [small.resize((n, n), Image.LANCZOS) for n in (48, 40, 32, 24, 20, 16)])
    frames[0].save(HERE / "rubencho.ico", format="ICO", sizes=[f.size for f in frames],
                   append_images=frames[1:])

    # Imágenes del asistente de instalación (Inno Setup): normal y para pantallas con zoom
    for k in (1, 2):
        w, h = 164 * k, 314 * k                  # panel izquierdo de la bienvenida
        side = Image.new("RGB", (w, h))
        px = side.load()
        for y in range(h):
            t = y / (h - 1)
            for x in range(w):
                px[x, y] = (int(13 + 10 * t), int(27 + 30 * t), int(64 + 90 * t))
        orb = big.resize((int(w * 0.8), int(w * 0.8)), Image.LANCZOS)
        side.paste(orb, ((w - orb.width) // 2, int(h * 0.30)), orb)
        side.save(HERE / f"instalador_lateral_{k}x.bmp")
        n = 55 * k                               # icono pequeño de la cabecera
        sm = Image.new("RGB", (n, n), (255, 255, 255))
        o = small.resize((n, n), Image.LANCZOS)
        sm.paste(o, (0, 0), o)
        sm.save(HERE / f"instalador_cabecera_{k}x.bmp")
    print("ok")
