"""Slice lastochka.png into the layered rig `components/mascot/lastochka.tsx` animates.

Run with:  python3 scripts/build-mascot-rig.py
Requires:  pillow, numpy


Every layer is exported on the same 1024x1024 canvas, so the runtime can stack
them with `absolute inset-0` and only vary transform-origin. Overlay layers sit
on top of an intact base, so small rotations never expose a hole.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import numpy as np, os, math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets/mascot/lastochka.png")   # pristine 1024px art
OUT = os.path.join(ROOT, "public/mascot")
N = 1024
EXPORT = 640   # the rig renders at ~260px; 640 is comfortably retina

im = Image.open(SRC).convert("RGBA")
arr = np.array(im).astype(np.int16)
rgb, alpha = arr[..., :3], arr[..., 3]
R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
lum = 0.2126 * R + 0.7152 * G + 0.0722 * B
solid = alpha > 128

print("catchlight probe: rgba(429,379) =", im.getpixel((429, 379)),
      " rgba(430,376) =", im.getpixel((430, 376)))

# ---------------------------------------------------------------- helpers
def blank():
    return Image.new("L", (N, N), 0)

def mask_from(np_bool):
    m = blank()
    m.putdata((np_bool.astype(np.uint8) * 255).flatten().tolist())
    return m

def feather(mask, radius):
    return mask.filter(ImageFilter.GaussianBlur(radius)) if radius else mask

def cut(mask):
    """Original pixels wherever `mask` is opaque, shadow excluded."""
    layer = im.copy()
    layer.putalpha(ImageChops.multiply(body_alpha, mask))
    return layer

def save(img, name):
    bb = img.split()[3].getbbox()
    out = img.resize((EXPORT, EXPORT), Image.LANCZOS)
    out.save(os.path.join(OUT, name), optimize=True)
    kb = os.path.getsize(os.path.join(OUT, name)) / 1024
    print(f"  {name:22s} bbox={str(bb):26s} {kb:6.1f} KB")

# ---------------------------------------------------------------- landmarks
EYE = (429, 389, 22, 26)              # cx, cy, rx, ry
BEAK_TIP = (294, 398)
MOUTH_LINE = [(292, 399), (322, 404), (348, 408), (372, 413)]
HEAD_ELLIPSE = (430, 400, 178, 128)   # cx, cy, rx, ry
NECK_PIVOT = (523, 468)
WING_ELLIPSE = (604, 553, 214, 92, -14)
SHOULDER_PIVOT = (437, 516)

yellow = solid & (R > 190) & (G > 128) & (G < 220) & (B < 115)

# ---------------------------------------------------------------- 0. shadow
# The art has a soft drop shadow baked in. Split it off so the body can float
# while its shadow stays put and softens. Anything with alpha but far from the
# silhouette is shadow; a 3px band keeps the body's own anti-aliasing intact.
solid_m = mask_from(solid)
near = solid_m.filter(ImageFilter.MaxFilter(7))          # dilate ~3px
shadow_m = ImageChops.subtract(im.split()[3], near)
# The ring has a bird-shaped hole in it, and blurring the ring inward only
# reaches alpha ~5 in the middle — so a floating body exposes bare paper as a
# bright band. Fill the interior from the silhouette instead, matched to the
# rim's own density, and it becomes a proper contact shadow.
core = solid_m.filter(ImageFilter.GaussianBlur(30)).point(lambda v: int(v * 0.21))
filled = ImageChops.lighter(shadow_m, core)
filled = filled.filter(ImageFilter.GaussianBlur(4))
shadow_layer = Image.new("RGBA", (N, N), (44, 40, 34, 255))
shadow_layer.putalpha(filled.point(lambda v: int(v * 0.92)))
save(shadow_layer, "part-shadow.png")
body_alpha = ImageChops.multiply(im.split()[3], near)

# ---------------------------------------------------------------- 1. eye
eye_m = blank()
ImageDraw.Draw(eye_m).ellipse(
    [EYE[0] - EYE[2], EYE[1] - EYE[3], EYE[0] + EYE[2], EYE[1] + EYE[3]], fill=255)
# The catchlight is a hole punched through the artwork. Fill it so the eye is
# self-contained and keeps its highlight on any background.
catch = Image.new("RGBA", (N, N), (247, 244, 237, 255))
catch_m = ImageChops.subtract(mask_from(np.ones((N, N), bool)), im.split()[3])
catch_only = blank()
ImageDraw.Draw(catch_only).ellipse(
    [EYE[0] - EYE[2], EYE[1] - EYE[3], EYE[0] + EYE[2], EYE[1] + EYE[3]], fill=255)
catch.putalpha(ImageChops.multiply(catch_m, catch_only))
eye_src = Image.alpha_composite(im, catch)
eye_layer = eye_src.copy()
eye_layer.putalpha(ImageChops.multiply(
    ImageChops.lighter(im.split()[3], catch.split()[3]), feather(eye_m, 0.6)))
save(eye_layer, "part-eye.png")

# Heal the eye out of the head: sample slate from a ring around it and paint over.
# Sample per-row so the patch follows the head's vertical gradient instead of
# sitting on it as one flat disc.
patch = Image.new("RGBA", (N, N), (0, 0, 0, 0))
pdraw = ImageDraw.Draw(patch)
y0, y1 = EYE[1] - EYE[3] - 8, EYE[1] + EYE[3] + 8
for y in range(y0, y1 + 1):
    band = [rgb[y, x] for x in (list(range(EYE[0] - EYE[2] - 26, EYE[0] - EYE[2] - 8)) +
                                list(range(EYE[0] + EYE[2] + 8, EYE[0] + EYE[2] + 26)))
            if 0 <= x < N and solid[y, x] and lum[y, x] > 45]
    if not band:
        continue
    c = tuple(int(v) for v in np.median(np.array(band), axis=0))
    pdraw.line([(EYE[0] - EYE[2] - 8, y), (EYE[0] + EYE[2] + 8, y)], fill=c + (255,))
patch = patch.filter(ImageFilter.GaussianBlur(3))
print("  healed eye skin (mid row):", patch.getpixel((EYE[0], EYE[1]))[:3])

healed = im.copy()
patch_m = blank()
ImageDraw.Draw(patch_m).ellipse(
    [EYE[0] - EYE[2] - 5, EYE[1] - EYE[3] - 5, EYE[0] + EYE[2] + 5, EYE[1] + EYE[3] + 5], fill=255)
patch_m = feather(patch_m, 5)
patch.putalpha(patch_m)
healed = Image.alpha_composite(healed, patch)
# Keep the silhouette, but make the healed patch opaque so the catchlight hole
# under the eye does not show through once the eye blinks shut.
healed.putalpha(ImageChops.lighter(body_alpha, patch_m))

# ---------------------------------------------------------------- 2. beak
def below_mouth_line(px, py):
    pts = MOUTH_LINE
    if px <= pts[0][0]:
        return py > pts[0][1]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        if ax <= px <= bx:
            t = (px - ax) / max(1, bx - ax)
            return py > ay + t * (by - ay)
    return py > pts[-1][1]

beak_zone = np.zeros((N, N), bool)
for y in range(370, 430):
    for x in range(280, 380):
        if solid[y, x] and not yellow[y, x] and below_mouth_line(x, y):
            beak_zone[y, x] = True
beak_m = feather(mask_from(beak_zone), 1.2)
save(cut(beak_m), "part-beak-lower.png")

# Mouth interior: a dark sliver revealed when the lower mandible drops. Kept
# inside the closed beak's own footprint so it can never smear past the tip.
mouth = Image.new("RGBA", (N, N), (0, 0, 0, 0))
ImageDraw.Draw(mouth).polygon(
    [(306, 400), (372, 412), (368, 421), (312, 407)], fill=(31, 20, 17, 255))
mouth = mouth.filter(ImageFilter.GaussianBlur(1.1))
mouth.putalpha(ImageChops.multiply(mouth.split()[3], feather(mask_from(beak_zone), 3)))
save(mouth, "part-mouth.png")

# ---------------------------------------------------------------- 3. throat
throat_m = feather(mask_from(yellow), 2.2)
save(cut(throat_m), "part-throat.png")

# ---------------------------------------------------------------- 4. head
head_hard = blank()
cx, cy, rx, ry = HEAD_ELLIPSE
ImageDraw.Draw(head_hard).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
ImageDraw.Draw(head_hard).polygon([(280, 380), (280, 425), (390, 440), (390, 370)], fill=255)
head_m = feather(head_hard, 9)
head_src = healed.copy()
head_src.putalpha(ImageChops.multiply(healed.split()[3], head_m))
save(head_src, "part-head.png")

# ---------------------------------------------------------------- 5. wing
wcx, wcy, wrx, wry, wrot = WING_ELLIPSE
wm = Image.new("L", (wrx * 2 + 40, wry * 2 + 40), 0)
ImageDraw.Draw(wm).ellipse([20, 20, wrx * 2 + 20, wry * 2 + 20], fill=255)
wm = wm.rotate(wrot, expand=True, resample=Image.BICUBIC)
wing_hard = blank()
wing_hard.paste(wm, (wcx - wm.width // 2, wcy - wm.height // 2))
wing_m = feather(wing_hard, 11)
save(cut(wing_m), "part-wing.png")

# ---------------------------------------------------------------- 6. base
# The base must not keep its own copy of anything that moves, or a rotated part
# leaves the original's outline ghosting behind it. Cut each moving part out,
# eroded, so the part still covers the base's hard cut edge at full deflection.
def erode(mask, px):
    for _ in range(px // 2):
        mask = mask.filter(ImageFilter.MinFilter(5))
    return mask

base = healed.copy()
ba = base.split()[3]
for m, px in ((head_hard, 16), (wing_hard, 18)):
    ba = ImageChops.multiply(ba, ImageChops.invert(feather(erode(m, px), 4)))
ba = ImageChops.multiply(ba, ImageChops.invert(beak_m))
base.putalpha(ba)
base = Image.alpha_composite(mouth, base)
save(base, "part-base.png")

# No flattened copy is emitted: the runtime stacks the part-*.png layers and
# nothing references a combined image. The pristine source stays in assets/.

print("\nrig written to", OUT)
