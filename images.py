import os
import pygame as pg

if not pg.image.get_extended():
    raise SystemExit("Extended image module req'd, aborting")

#You can't convert() / convert_alpha() until the display is set up,
#but that doesn't happen until we're ready to start the game.
#So, we just store references to objects here, and assign them an "image" attribute when it's time to do the image loading.
#Because of how Python works, this also works to create class-level "image" attributes after the fact if desired.

to_load=[]
teamed_colors=[(255, 0, 0, 255), (0xFF, 0x8f, 0x26, 255), (0x03, 0xC2, 0xFC, 255), (128, 128, 128, 255), (0x84, 0x03, 0xFC, 255), (0xFA, 0xAA, 0xF3, 255)]

class QueuedSpec:
    def __init__(self, item, segments, mode):
        self.item = item
        self.path = os.path.join("assets", *segments)
        self.mode = mode
def _queue(item, segments, mode):
    to_load.append(QueuedSpec(item, segments, mode))

def queue(item, *segments):
    _queue(item, segments, 'normal')
def queue_spun(item, *segments):
    _queue(item, segments, 'spun')
def queue_teamed(item, *segments):
    _queue(item, segments, 'teamed')
def load_queued():
    global to_load
    for spec in to_load:
        img = pg.image.load(spec.path).convert_alpha()
        item = spec.item
        if spec.mode == 'normal':
            item.image = img
        elif spec.mode == 'spun':
            item.spun_images = [img] + [rotate(img, deg) for deg in [60, 120, 180, -120, -60]]
        elif spec.mode == 'teamed':
            item.teamed_images = [dye(img, c) for c in teamed_colors]
    to_load = []
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
