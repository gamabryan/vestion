"""Ícone da Lia perto do relógio do Windows."""
from pathlib import Path
from typing import Callable

import pystray
from PIL import Image, ImageDraw

ICON_PATH = Path(__file__).with_name("ui") / "lia.ico"


def draw_icon(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.ellipse((2 * s, 2 * s, 62 * s, 62 * s), fill=(3, 7, 13, 255), outline=(41, 217, 255, 255), width=max(1, int(3 * s)))
    d.arc((12 * s, 12 * s, 52 * s, 52 * s), 20, 160, fill=(41, 217, 255, 255), width=max(1, int(5 * s)))
    d.arc((12 * s, 12 * s, 52 * s, 52 * s), 200, 340, fill=(41, 217, 255, 255), width=max(1, int(5 * s)))
    d.ellipse((24 * s, 24 * s, 40 * s, 40 * s), fill=(220, 250, 255, 255))
    return img


def save_ico(path: Path = ICON_PATH) -> Path:
    draw_icon(256).save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
    return path


def start_tray(on_open: Callable[[], None], on_quit: Callable[[], None],
               on_connect_google: Callable[[], None] | None = None) -> pystray.Icon:
    items = [pystray.MenuItem("Abrir central", lambda icon, item: on_open(), default=True)]
    if on_connect_google:
        items.append(pystray.MenuItem("Conectar Google", lambda icon, item: on_connect_google()))
    items.append(pystray.MenuItem("Sair", lambda icon, item: on_quit()))
    menu = pystray.Menu(*items)
    icon = pystray.Icon("vestion", draw_icon(), "Vestion", menu)
    icon.run_detached()
    return icon
