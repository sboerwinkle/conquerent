import os
import pygame as pg

if not pg.image.get_extended():
    raise SystemExit("Extended image module req'd, aborting")

teamed_colors=[(255, 0, 0, 255), (0xFF, 0x8f, 0x26, 255), (0x03, 0xC2, 0xFC, 255), (128, 128, 128, 255), (0x84, 0x03, 0xFC, 255), (0xFA, 0xAA, 0xF3, 255)]

def load(*segments):
    return pg.image.load(os.path.join("assets", *segments)).convert_alpha()

def load_spun(*segments):
    img = load(*segments)
    return [img] + [rotate(img, deg) for deg in [60, 120, 180, -120, -60]]

def load_teamed(*segments):
    img = load(*segments)
    return [dye(img, c) for c in teamed_colors]

def load_teamed_anim(name, frames):
    teamed_anim = [load_teamed("units", name+str(x)+".png") for x in range(frames)]
    # Transpose, so first index is team
    return list(zip(*teamed_anim))

def rotate(img, degrees):
    "A wrapper around pygame's rotate that rotates about the center and keeps the dimensions the same"
    dest = pg.Surface(img.get_size(), pg.SRCALPHA, img)
    dest.fill(0)
    rotated = pg.transform.rotate(img, degrees)
    (dx, dy) = dest.get_rect().center
    (rx, ry) = rotated.get_rect().center
    dest.blit(rotated, (dx-rx, dy-ry))
    return dest

def dye(img, color):
    copy = img.copy()
    copy.fill(color, special_flags=pg.BLEND_RGBA_MULT)
    return copy
