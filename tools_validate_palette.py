"""
Palette validator - Python port of the dataviz skill's validate_palette.js.
Node is not installed in this environment, and the skill requires the colour
checks be computed rather than eyeballed, so the same six checks are
reimplemented here.

Checks: lightness band, chroma floor, adjacent-pair CVD separation,
normal-vision floor, and contrast against the chart surface.
"""
import sys
import math

# Machado et al. (2009) CVD matrices, severity 1.0, applied to linear sRGB
CVD = {
    "protanopia": [[0.152286, 1.052583, -0.204868],
                   [0.114503, 0.786281, 0.099216],
                   [-0.003882, -0.048116, 1.051998]],
    "deuteranopia": [[0.367322, 0.860646, -0.227968],
                     [0.280085, 0.672501, 0.047413],
                     [-0.011820, 0.042940, 0.968881]],
    "tritanopia": [[1.255528, -0.076749, -0.178779],
                   [-0.078411, 0.930809, 0.147602],
                   [0.004733, 0.691367, 0.303900]],
}


def hex_to_srgb(h):
    h = h.strip().lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_rgb(hexcode):
    return tuple(to_linear(c) for c in hex_to_srgb(hexcode))


def oklab(rgb_lin):
    r, g, b = rgb_lin
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (max(v, 0) ** (1 / 3) for v in (l, m, s))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def apply_cvd(rgb_lin, kind):
    M = CVD[kind]
    return tuple(
        max(0.0, min(1.0, sum(M[i][j] * rgb_lin[j] for j in range(3))))
        for i in range(3)
    )


def dE(c1, c2):
    """OKLab delta-E x100."""
    return 100 * math.dist(c1, c2)


def rel_lum(rgb_lin):
    r, g, b = rgb_lin
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(hex1, hex2):
    a, b = rel_lum(linear_rgb(hex1)), rel_lum(linear_rgb(hex2))
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def validate(palette, surface="#FFFFFF", ordinal=False, label=""):
    print(f"\n{'=' * 74}")
    print(f"{label}  ({len(palette)} colours, surface {surface})")
    print("=" * 74)
    fails = warns = 0

    labs = [oklab(linear_rgb(h)) for h in palette]

    # 1-2. Lightness band + chroma floor
    print("\n  lightness (L) and chroma (C):")
    for h, lab in zip(palette, labs):
        L = lab[0]
        C = math.hypot(lab[1], lab[2])
        flag = ""
        if not (0.35 <= L <= 0.90):
            flag += "  <- L outside 0.35-0.90"
            warns += 1
        if C < 0.02:
            flag += "  <- chroma below floor"
            warns += 1
        print(f"    {h}   L={L:.3f}  C={C:.3f}{flag}")

    # 3-4. Pair separation: adjacent for ordinal ramps, all pairs otherwise
    pairs = ([(i, i + 1) for i in range(len(palette) - 1)] if ordinal
             else [(i, j) for i in range(len(palette)) for j in range(i + 1, len(palette))])
    kind = "adjacent pairs (ordinal ramp)" if ordinal else "all pairs"
    print(f"\n  separation, {kind}:")
    print(f"    {'pair':<20}{'normal':>9}{'deuter':>9}{'protan':>9}{'tritan':>9}   verdict")
    for i, j in pairs:
        n = dE(labs[i], labs[j])
        cvd = {}
        for k in CVD:
            cvd[k] = dE(oklab(apply_cvd(linear_rgb(palette[i]), k)),
                        oklab(apply_cvd(linear_rgb(palette[j]), k)))
        worst = min(cvd.values())
        if n < 15:
            v, bad = "FAIL normal<15", True
        elif worst < 6:
            v, bad = "FAIL cvd<6", True
        elif worst < 8:
            v, bad = "WARN cvd 6-8 (needs 2nd encoding)", False
        else:
            v, bad = "pass", False
        fails += bad
        warns += (v.startswith("WARN"))
        print(f"    {palette[i]}/{palette[j]}  {n:>8.1f}{cvd['deuteranopia']:>9.1f}"
              f"{cvd['protanopia']:>9.1f}{cvd['tritanopia']:>9.1f}   {v}")

    # 5. Contrast against surface
    print("\n  contrast vs surface:")
    for h in palette:
        c = contrast(h, surface)
        flag = "" if c >= 3.0 else "  <- WARN below 3:1, needs visible label/table"
        if c < 3.0:
            warns += 1
        print(f"    {h}   {c:.2f}:1{flag}")

    print(f"\n  RESULT: {fails} FAIL, {warns} WARN")
    return fails


if __name__ == "__main__":
    quality = ["#B2182B", "#EF8A62", "#FDBF93", "#92C5DE", "#4393C3", "#2166AC"]
    f1 = validate(quality, ordinal=True,
                  label="Quality class ramp (RdBu-6: Stub -> FA), dashboard palette")

    ident = ["#08519C", "#6BAED6", "#BDD7E7"]
    f2 = validate(ident, ordinal=True,
                  label="Cancer identification method (3 categories, confidence-ordered)")

    print("\n" + "=" * 74)
    print(f"TOTAL FAILURES: {f1 + f2}")
    sys.exit(0)
