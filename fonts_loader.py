"""
Loads the bundled Poppins / Montserrat / Open Sans TTFs into this process
(Windows GDI, FR_PRIVATE) so the app's typography renders identically on
machines that don't have the fonts installed. All three families are
Google Fonts under the SIL Open Font License — bundling is permitted
(license texts: https://fonts.google.com).

Call load_bundled_fonts() once, before any Tk widgets are created.
"""
import os
import sys


def _resource_path(relative):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def load_bundled_fonts():
    """Register every TTF in assets/fonts for this process. Silent no-op on failure."""
    if sys.platform != "win32":
        return 0
    loaded = 0
    try:
        import ctypes
        FR_PRIVATE = 0x10
        fonts_dir = _resource_path(os.path.join("assets", "fonts"))
        if not os.path.isdir(fonts_dir):
            return 0
        for name in os.listdir(fonts_dir):
            if name.lower().endswith((".ttf", ".otf")):
                path = os.path.join(fonts_dir, name)
                if ctypes.windll.gdi32.AddFontResourceExW(path, FR_PRIVATE, 0):
                    loaded += 1
    except Exception:
        pass
    return loaded
