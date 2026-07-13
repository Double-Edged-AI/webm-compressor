"""
Themed replacements for tkinter.messagebox that match the app's design system
(dark two-sheet theme, rounded frameless dialogs, Poppins/Montserrat/Open Sans).

Drop-in compatible with the call sites used in app.py:
    showinfo(title, message)     showwarning(title, message)
    showerror(title, message)    askyesno(title, message) -> bool
"""
import sys
import tkinter as tk
import customtkinter as ctk

_KINDS = {
    "info":     {"glyph": "i",  "color": "#8E8EDD"},
    "warning":  {"glyph": "!",  "color": "#BFA378"},
    "error":    {"glyph": "✕",  "color": "#E8574A"},
    "question": {"glyph": "?",  "color": "#4EB18C"},
}


def _beep(kind):
    if sys.platform != "win32":
        return
    try:
        import winsound
        sounds = {
            "info": winsound.MB_ICONASTERISK,
            "warning": winsound.MB_ICONEXCLAMATION,
            "error": winsound.MB_ICONHAND,
            "question": winsound.MB_ICONQUESTION,
        }
        winsound.MessageBeep(sounds.get(kind, winsound.MB_OK))
    except Exception:
        pass


class _ThemedDialog(ctk.CTkToplevel):
    def __init__(self, title, message, kind="info", buttons=("OK",)):
        master = tk._default_root
        super().__init__(master)
        self.result = None
        spec = _KINDS.get(kind, _KINDS["info"])

        # Frameless rounded shell, same construction as the main window
        self.overrideredirect(True)
        self.configure(fg_color="#010101")
        try:
            self.attributes("-transparentcolor", "#010101")
        except Exception:
            self.configure(fg_color="#1B1B26")
        self.attributes("-topmost", True)

        shell = ctk.CTkFrame(
            self, fg_color="#1B1B26",
            border_width=1, border_color="#31313F",
            corner_radius=14
        )
        shell.pack(fill="both", expand=True)

        # Header: colored icon chip + title, draggable
        head = ctk.CTkFrame(shell, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(16, 4))
        chip = ctk.CTkLabel(
            head, text=spec["glyph"], width=32, height=32,
            fg_color=spec["color"], corner_radius=16,
            font=ctk.CTkFont(family="Montserrat", size=15, weight="bold"),
            text_color="#15151D"
        )
        chip.pack(side="left")
        title_lbl = ctk.CTkLabel(
            head, text=title,
            font=ctk.CTkFont(family="Montserrat", size=13, weight="bold"),
            text_color="#F2F2F4"
        )
        title_lbl.pack(side="left", padx=12)

        for w in (head, chip, title_lbl):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        # Message body
        ctk.CTkLabel(
            shell, text=message,
            font=ctk.CTkFont(family="Open Sans", size=13),
            text_color="#C9C9D1",
            justify="left", wraplength=360, anchor="w"
        ).pack(fill="x", padx=20, pady=(6, 4))

        # Buttons
        btn_row = ctk.CTkFrame(shell, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(8, 16))

        if buttons == ("Yes", "No"):
            ctk.CTkButton(
                btn_row, text="No", width=90, height=32,
                fg_color="transparent", hover_color="#2A2A36",
                border_width=1, border_color="#3A3A48",
                text_color="#C9C9D1", corner_radius=8,
                font=ctk.CTkFont(family="Open Sans", size=13, weight="bold"),
                command=lambda: self._close(False)
            ).pack(side="right", padx=(8, 0))
            ctk.CTkButton(
                btn_row, text="Yes", width=90, height=32,
                fg_color="#4EB18C", hover_color="#3F9273",
                text_color="#000000", corner_radius=8,
                font=ctk.CTkFont(family="Open Sans", size=13, weight="bold"),
                command=lambda: self._close(True)
            ).pack(side="right")
        else:
            ctk.CTkButton(
                btn_row, text="OK", width=96, height=32,
                fg_color=spec["color"], hover_color=spec["color"],
                text_color="#15151D", corner_radius=8,
                font=ctk.CTkFont(family="Open Sans", size=13, weight="bold"),
                command=lambda: self._close(True)
            ).pack(side="right")

        self.bind("<Return>", lambda e: self._close(True))
        self.bind("<Escape>", lambda e: self._close(False))

        # Size to content, center over parent (or screen)
        self.update_idletasks()
        w = max(420, self.winfo_reqwidth())
        h = self.winfo_reqheight()
        if master and master.winfo_viewable():
            x = master.winfo_x() + (master.winfo_width() - w) // 2
            y = master.winfo_y() + (master.winfo_height() - h) // 2
        else:
            x = (self.winfo_screenwidth() - w) // 2
            y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

        _beep(kind)
        try:
            self.grab_set()
        except Exception:
            pass
        self.focus_force()

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _close(self, result):
        self.result = result
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def themed_toplevel(title, width=420, height=None, modal=False):
    """
    Frameless rounded toplevel in the app's design system.
    Returns (window, body_frame): put content in body_frame; the header
    (draggable, with title + ✕) is already built.
    """
    master = tk._default_root
    win = ctk.CTkToplevel(master)
    win.overrideredirect(True)
    win.configure(fg_color="#010101")
    try:
        win.attributes("-transparentcolor", "#010101")
    except Exception:
        win.configure(fg_color="#1B1B26")
    win.attributes("-topmost", True)

    shell = ctk.CTkFrame(
        win, fg_color="#1B1B26",
        border_width=1, border_color="#31313F",
        corner_radius=14
    )
    shell.pack(fill="both", expand=True)

    head = ctk.CTkFrame(shell, fg_color="transparent")
    head.pack(fill="x", padx=16, pady=(12, 2))
    title_lbl = ctk.CTkLabel(
        head, text=title,
        font=ctk.CTkFont(family="Montserrat", size=13, weight="bold"),
        text_color="#F2F2F4"
    )
    title_lbl.pack(side="left")
    ctk.CTkButton(
        head, text="✕", width=30, height=22,
        fg_color="transparent", hover_color="#E8574A",
        text_color="#8E8E9C", corner_radius=6,
        font=ctk.CTkFont(size=12), command=win.destroy
    ).pack(side="right")

    def _ds(e):
        win._dx, win._dy = e.x_root - win.winfo_x(), e.y_root - win.winfo_y()
    def _dm(e):
        win.geometry(f"+{e.x_root - win._dx}+{e.y_root - win._dy}")
    for w in (head, title_lbl):
        w.bind("<Button-1>", _ds)
        w.bind("<B1-Motion>", _dm)

    body = ctk.CTkFrame(shell, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=16, pady=(4, 14))

    win.update_idletasks()
    w = width
    h = height or win.winfo_reqheight()
    if master and master.winfo_viewable():
        x = master.winfo_x() + (master.winfo_width() - w) // 2
        y = master.winfo_y() + (master.winfo_height() - h) // 2
    else:
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    if modal:
        try:
            win.grab_set()
        except Exception:
            pass
    win.focus_force()
    return win, body


def _show(title, message, kind, buttons=("OK",)):
    try:
        dlg = _ThemedDialog(title, message, kind, buttons)
        dlg.wait_window()
        return dlg.result
    except Exception:
        # Absolute fallback: never lose a message because theming failed
        from tkinter import messagebox as _mb
        fn = {"info": _mb.showinfo, "warning": _mb.showwarning,
              "error": _mb.showerror, "question": _mb.askyesno}[kind]
        return fn(title, message)


def show_link_info(title, message, link_text, url, kind="info"):
    """
    Info dialog with a clickable hyperlink under the message. The link opens
    in the default browser. Falls back to a plain dialog if theming fails.
    """
    import webbrowser
    try:
        dlg = _ThemedDialog(title, message, kind)
        try:
            shell = dlg.winfo_children()[0]
            btn_row = shell.winfo_children()[-1]
            link = ctk.CTkLabel(
                shell, text=link_text,
                font=ctk.CTkFont(family="Open Sans", size=13, underline=True),
                text_color="#8E8EDD", cursor="hand2",
                justify="left", wraplength=360, anchor="w"
            )
            link.pack(fill="x", padx=20, pady=(0, 2), before=btn_row)
            link.bind("<Button-1>", lambda e: webbrowser.open(url))
            dlg.update_idletasks()
            w = max(420, dlg.winfo_reqwidth())
            h = dlg.winfo_reqheight()
            dlg.geometry(f"{w}x{h}")
        except Exception:
            pass  # dialog still works without the styled link
        dlg.wait_window()
        return dlg.result
    except Exception:
        return _show(title, f"{message}\n\n{link_text}: {url}", kind)


def showinfo(title, message, **kw):
    return _show(title, message, "info")


def showwarning(title, message, **kw):
    return _show(title, message, "warning")


def showerror(title, message, **kw):
    return _show(title, message, "error")


def askyesno(title, message, **kw):
    return bool(_show(title, message, "question", buttons=("Yes", "No")))
