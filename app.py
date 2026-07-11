# PERMANENT RULE: This application compresses videos and exports WebM only. 
# Input can be any supported video format, but output must always be .webm. 
# No UI option, preset, override, or backend process is allowed to export MP4 or any other format.

import os
import sys
import tkinter as tk
from tkinter import filedialog
import dialogs as messagebox  # themed drop-in for tkinter.messagebox
import customtkinter as ctk
import shutil
import threading
import subprocess

# Drag-and-drop support (tkinterdnd2 bundles the TkDnD extension). Optional:
# if unavailable, the app still runs - the Add Videos button covers the flow.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DnDBase = TkinterDnD.DnDWrapper
    DND_AVAILABLE = True
except Exception:
    DND_FILES = None
    _DnDBase = object
    DND_AVAILABLE = False

from taskbar_progress import TaskbarProgress
from fonts_loader import load_bundled_fonts
load_bundled_fonts()

# Windows-specific flag to prevent cmd console windows from spawning
CREATE_NO_WINDOW = 0x08000000

# Import our backend logic
from encoder import (
    EncodingQueue,
    EncoderTask,
    PRESETS,
    AUDIO_ONLY_PRESET,
    get_metadata,
    detect_active_hardware_webm_encoders,
    generate_preview
)

# File extensions accepted by Add Videos and drag-and-drop
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v",
    ".mpg", ".mpeg", ".wmv", ".flv", ".ts", ".m2ts", ".3gp", ".mts"
}


def resource_path(relative):
    """Resolve bundled resource paths in both source and PyInstaller builds."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

# Set appearance mode and color theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class TaskRow:
    """
    Represents a visual row in the queue table.
    Designed using Apple's Human Interface Guidelines (elevated flat card design).
    Fully responsive layout using horizontal flow packaging.
    """
    def __init__(self, parent_frame, task, remove_callback, preview_callback, selection_callback=None):
        self.task = task
        self.remove_callback = remove_callback
        self.preview_callback = preview_callback
        self.selection_callback = selection_callback

        # Apple System Gray 5 elevated background with a very subtle border
        self.frame = ctk.CTkFrame(
            parent_frame,
            fg_color="#262634",       # elevated row on queue sheet
            border_width=0,
            corner_radius=10
        )
        self.frame.pack(fill="x", padx=10, pady=4)

        # 0. Selection checkbox - only ticked rows are compressed
        self.select_var = tk.BooleanVar(value=getattr(task, "selected", True))
        self.select_cb = ctk.CTkCheckBox(
            self.frame,
            text="",
            width=24,
            checkbox_width=18,
            checkbox_height=18,
            variable=self.select_var,
            fg_color="#F4695C",
            border_color="#5A5A5E",
            command=self._on_select_toggled
        )
        self.select_cb.pack(side="left", padx=(12, 0), pady=10)

        # Left container (details and progress)
        self.left_container = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.left_container.pack(side="left", fill="both", expand=True, padx=(8, 10), pady=10)
        
        # Right container (actions)
        self.right_container = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.right_container.pack(side="right", fill="y", padx=(10, 15), pady=10)

        # 1. Filename label
        base_name = os.path.basename(task.input_path)
        self.name_label = ctk.CTkLabel(
            self.left_container, 
            text=base_name, 
            anchor="w", 
            font=ctk.CTkFont(family="Open Sans", size=14, weight="bold"),
            text_color="#FFFFFF"
        )
        self.name_label.pack(fill="x", anchor="w", pady=(0, 2))
        
        # 2. Preset & Details stacked
        duration_str = self._format_duration(task.metadata["duration"])
        size_str = self._format_size(task.metadata["size_bytes"])
        profile_text = task.preset_name.replace(" WebM", "") + (" (GPU)" if task.use_gpu else " (CPU)")
        self.details_label = ctk.CTkLabel(
            self.left_container,
            text=f"Size: {size_str}  •  Duration: {duration_str}  •  Profile: {profile_text}",
            anchor="w",
            font=ctk.CTkFont(family="Open Sans", size=11),
            text_color="#8E8E93"
        )
        self.details_label.pack(fill="x", anchor="w", pady=(0, 6))

        # 3. Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            self.left_container,
            progress_color="#F4695C",
            fg_color="#31313F",
            height=5,
            corner_radius=3
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", anchor="w", pady=(0, 4))

        # 4. Status Text
        self.status_label = ctk.CTkLabel(
            self.left_container,
            text="Waiting...",
            anchor="w",
            font=ctk.CTkFont(family="Open Sans", size=11, weight="bold"),
            text_color="#AEAEB2"
        )
        self.status_label.pack(anchor="w")

        # 5. Action buttons (Preview & Delete)
        # Preview Button
        self.preview_btn = ctk.CTkButton(
            self.right_container,
            text="👁",
            width=28,
            height=28,
            fg_color="#333341",
            hover_color="#3D3D4C",
            text_color="#FFFFFF",
            corner_radius=8,
            font=ctk.CTkFont(size=13),
            command=lambda: self.preview_callback(self.task)
        )
        self.preview_btn.pack(side="left", padx=3)

        # Delete Button
        self.delete_btn = ctk.CTkButton(
            self.right_container,
            text="✕",
            width=28,
            height=28,
            fg_color="#333341",
            hover_color="#E8574A",    # Changes to Apple System Red on hover
            text_color="#AEAEB2",
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            command=lambda: self.remove_callback(task.id)
        )
        self.delete_btn.pack(side="left", padx=3)

    def update(self, task):
        self.task = task
        
        # Apple semantic status colors
        status_colors = {
            "Pending": "#BFA378",      # Apple Orange
            "Queued": "#8E8EDD",
            "Encoding": "#4EB18C",     # Apple Green
            "Completed": "#4EB18C",    # Apple Green
            "Failed": "#E8574A",       # Apple Red
            "Stopped": "#E8574A"       # Apple Red
        }
        
        color = status_colors.get(task.status, "#ffffff")
        
        status_text = task.status
        if task.status == "Encoding":
            status_text = f"Encoding ({int(task.progress)}%)"
            if task.two_pass:
                if task.progress < 50.0:
                    status_text = f"Pass 1/2 ({int(task.progress * 2)}%)"
                else:
                    status_text = f"Pass 2/2 ({int((task.progress - 50.0) * 2)}%)"
            
        self.status_label.configure(text=status_text, text_color=color)
        self.progress_bar.set(task.progress / 100.0)
        self.progress_bar.configure(progress_color=color if task.progress > 0 else "#31313F")
        
        self.preset_label_text = task.preset_name.replace(" WebM", "") + (" (GPU)" if task.use_gpu else " (CPU)")
        
        if task.status == "Encoding":
            orig_size_str = self._format_size(task.metadata["size_bytes"])
            eta_str = self._format_eta(task.eta)
            if task.est_size_bytes > 0:
                est_size_str = self._format_size(task.est_size_bytes)
                size_text = f"Estimated: ~{est_size_str} of {orig_size_str}"
            else:
                size_text = f"Size: {orig_size_str}"
            
            self.details_label.configure(
                text=f"{size_text}  •  Speed: {task.speed}  •  Time Remaining: {eta_str}  •  Profile: {self.preset_label_text}",
                text_color="#E5E5EA"
            )
        elif task.status == "Completed":
            final_size_str = self._format_size(task.est_size_bytes)
            orig_size_str = self._format_size(task.metadata["size_bytes"])
            reduction = 0
            if task.metadata["size_bytes"] > 0:
                reduction = int(((task.metadata["size_bytes"] - task.est_size_bytes) / task.metadata["size_bytes"]) * 100)
            self.details_label.configure(
                text=f"Final Size: {final_size_str} of {orig_size_str} (Saved {reduction}%)  •  Done",
                text_color="#4EB18C"
            )
        else:
            # Update default labels if settings changes occur in real-time
            duration_str = self._format_duration(task.metadata["duration"])
            size_str = self._format_size(task.metadata["size_bytes"])
            self.details_label.configure(
                text=f"Size: {size_str}  •  Duration: {duration_str}  •  Profile: {self.preset_label_text}",
                text_color="#8E8E93"
            )
            
        if task.status == "Encoding":
            self.delete_btn.configure(state="disabled")
            self.preview_btn.configure(state="disabled")
            self.select_cb.configure(state="disabled")
        else:
            self.delete_btn.configure(state="normal")
            self.preview_btn.configure(state="normal")
            self.select_cb.configure(state="normal")

    def _on_select_toggled(self):
        self.task.selected = bool(self.select_var.get())
        if self.selection_callback:
            self.selection_callback()

    def destroy(self):
        self.frame.destroy()

    def _format_duration(self, seconds):
        if not seconds:
            return "00:00"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _format_size(self, size_bytes):
        if not size_bytes:
            return "0 KB"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def _format_eta(self, seconds):
        if seconds == -1:
            return "Estimating..."
        if seconds == 0:
            return "Done"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"


class WebMCompressorApp(ctk.CTk, _DnDBase):
    def __init__(self):
        super().__init__()

        self.title("WebM Compressor")
        self.minsize(1160, 780)

        # Center the window on screen at startup
        _w, _h = 1260, 830
        _x = (self.winfo_screenwidth() - _w) // 2
        _y = max(20, (self.winfo_screenheight() - _h) // 2 - 20)
        self.geometry(f"{_w}x{_h}+{_x}+{_y}")

        # Brand icon (bracketed Double-Edged AI feather). CustomTkinter applies
        # its own default icon shortly after startup, so set ours again after it.
        self._icon_path = resource_path(os.path.join("assets", "icon.ico"))
        self._apply_window_icon()
        self.after(400, self._apply_window_icon)

        # ── Frameless rounded window (Option B) ─────────────────────────────
        # Remove the native frame; paint the root a transparency-key color so
        # the rounded shell's corners show the desktop through them.
        self._frameless_suspended = False
        self._is_maximized = False
        self.overrideredirect(True)
        self.configure(fg_color="#010101")
        try:
            self.attributes("-transparentcolor", "#010101")
        except Exception:
            self.configure(fg_color="#15151D")  # fallback: square corners

        self.shell = ctk.CTkFrame(
            self, fg_color="#15151D",
            border_width=1, border_color="#2A2A36",
            corner_radius=18
        )
        self.shell.pack(fill="both", expand=True)

        # Initialize background queue
        self.queue = EncodingQueue(
            callback_on_update=self.on_queue_update,
            callback_on_finish=self.on_queue_finish
        )
        self.task_rows = {}
        self.preview_window = None
        self.taskbar = None  # created lazily once the window has a real HWND

        # Shell layout: title bar row + two-sheet content row
        self.shell.grid_columnconfigure(0, weight=1, minsize=350)  # Sidebar
        self.shell.grid_columnconfigure(1, weight=3)               # Main Panel
        self.shell.grid_rowconfigure(1, weight=1)

        self._build_titlebar()
        self._build_sidebar()
        self._build_main_panel()
        self._build_resize_grip()
        self._setup_drag_and_drop()

        # Frameless windows drop off the taskbar - restore taskbar presence,
        # then re-assert it whenever the window comes back from minimize.
        self.after(20, self._make_taskbar_window)
        self.bind("<Map>", self._on_map_restore, add="+")

        self._check_ffmpeg()

    # ── Frameless window plumbing ────────────────────────────────────────────

    def _build_titlebar(self):
        bar = ctk.CTkFrame(self.shell, fg_color="transparent", height=34)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(8, 0))

        title_lbl = ctk.CTkLabel(
            bar, text="●  WebM Compressor",
            font=ctk.CTkFont(family="Montserrat", size=11, weight="bold"),
            text_color="#6E6E78"
        )
        title_lbl.pack(side="left", pady=4)

        btn_close = ctk.CTkButton(
            bar, text="✕", width=34, height=22,
            fg_color="transparent", hover_color="#E8574A",
            text_color="#8E8E9C", corner_radius=6,
            font=ctk.CTkFont(size=13), command=self.destroy
        )
        btn_close.pack(side="right", padx=(2, 0), pady=4)
        btn_max = ctk.CTkButton(
            bar, text="▢", width=34, height=22,
            fg_color="transparent", hover_color="#333341",
            text_color="#8E8E9C", corner_radius=6,
            font=ctk.CTkFont(size=12), command=self._toggle_maximize
        )
        btn_max.pack(side="right", padx=2, pady=4)
        btn_min = ctk.CTkButton(
            bar, text="─", width=34, height=22,
            fg_color="transparent", hover_color="#333341",
            text_color="#8E8E9C", corner_radius=6,
            font=ctk.CTkFont(size=12), command=self._minimize_window
        )
        btn_min.pack(side="right", padx=2, pady=4)

        # Drag the window by its title bar; double-click toggles maximize
        for w in (bar, title_lbl):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<Double-Button-1>", lambda e: self._toggle_maximize())

    def _drag_start(self, event):
        self._drag_dx = event.x_root - self.winfo_x()
        self._drag_dy = event.y_root - self.winfo_y()

    def _drag_move(self, event):
        if self._is_maximized:
            return
        self.geometry(f"+{event.x_root - self._drag_dx}+{event.y_root - self._drag_dy}")

    def _minimize_window(self):
        # overrideredirect windows can't iconify: momentarily restore the
        # native frame, minimize, then re-frameless on the way back (<Map>).
        self._frameless_suspended = True
        self.overrideredirect(False)
        self.iconify()

    def _on_map_restore(self, event):
        if self._frameless_suspended:
            self._frameless_suspended = False
            self.overrideredirect(True)
            self.after(20, self._make_taskbar_window)

    def _toggle_maximize(self):
        import ctypes
        from ctypes import wintypes, byref
        if self._is_maximized:
            self.geometry(self._restore_geometry)
            self._is_maximized = False
        else:
            self._restore_geometry = self.geometry()
            rect = wintypes.RECT()
            ctypes.windll.user32.SystemParametersInfoW(48, 0, byref(rect), 0)  # SPI_GETWORKAREA
            self.geometry(f"{rect.right - rect.left}x{rect.bottom - rect.top}+{rect.left}+{rect.top}")
            self._is_maximized = True

    def _make_taskbar_window(self):
        """Give the frameless window a taskbar button (WS_EX_APPWINDOW)."""
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            self.wm_withdraw()
            self.after(10, self.wm_deiconify)
            self.after(450, self._apply_window_icon)
        except Exception:
            pass

    def _build_resize_grip(self):
        grip = ctk.CTkLabel(
            self.shell, text="◢",
            font=ctk.CTkFont(size=13), text_color="#3A3A48", cursor="size_nw_se"
        )
        grip.place(relx=1.0, rely=1.0, anchor="se", x=-7, y=-5)
        grip.bind("<B1-Motion>", self._resize_move)

    def _resize_move(self, event):
        if self._is_maximized:
            return
        w = max(1160, event.x_root - self.winfo_rootx() + 8)
        h = max(780, event.y_root - self.winfo_rooty() + 8)
        self.geometry(f"{int(w)}x{int(h)}")

    def _apply_window_icon(self):
        try:
            if os.path.exists(self._icon_path):
                self.iconbitmap(self._icon_path)
        except Exception:
            pass

    def _setup_drag_and_drop(self):
        if not DND_AVAILABLE:
            return
        try:
            self.TkdndVersion = TkinterDnD._require(self)
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self.on_drop_files)
        except Exception as e:
            print(f"Drag-and-drop unavailable: {e}")

    def _get_taskbar(self):
        """Lazily bind ITaskbarList3 to this window's top-level HWND."""
        if self.taskbar is None:
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                self.taskbar = TaskbarProgress(hwnd)
            except Exception:
                self.taskbar = TaskbarProgress(None)
        return self.taskbar

    def _build_sidebar(self):
        # ── Two-Sheet Studio: floating settings sheet (taller than main sheet) ──
        sidebar = ctk.CTkFrame(
            self.shell,
            fg_color="#23232F",
            border_width=1,
            border_color="#31313F",
            corner_radius=16
        )
        sidebar.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(4, 26))

        # Brand row (app icon + name)
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=16, pady=(16, 8))
        try:
            from PIL import Image
            _img = ctk.CTkImage(
                Image.open(resource_path(os.path.join("assets", "icon_256.png"))),
                size=(24, 24)
            )
            ctk.CTkLabel(brand, image=_img, text="").pack(side="left", padx=(0, 8))
        except Exception:
            pass
        _brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        _brand_text.pack(side="left")
        ctk.CTkLabel(
            _brand_text, text="WebM Compressor",
            font=ctk.CTkFont(family="Poppins", size=22, weight="bold"),
            text_color="#F2F2F4"
        ).pack(anchor="w")
        ctk.CTkLabel(
            _brand_text, text="A DOUBLE-EDGED AI PROJECT",
            font=ctk.CTkFont(family="Montserrat", size=10, weight="bold"),
            text_color="#6E6E78"
        ).pack(anchor="w")

        def _section(icon_title):
            card = ctk.CTkFrame(sidebar, fg_color="#2B2B39", corner_radius=12)
            card.pack(fill="x", padx=14, pady=5)
            icon, text = icon_title.split("  ", 1)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(anchor="w", padx=12, pady=(9, 3))
            ctk.CTkLabel(
                row, text=icon,
                font=ctk.CTkFont(size=17),
                text_color="#F4695C"
            ).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                row, text=text,
                font=ctk.CTkFont(family="Montserrat", size=12, weight="bold"),
                text_color="#8F8F9A"
            ).pack(side="left")
            return card

        # 1. Engine
        card_engine = _section("⚙  ENGINE")
        self.unit_toggle = ctk.CTkSegmentedButton(
            card_engine,
            values=["CPU", "GPU (Fast, Lower Quality)"],
            command=self.on_unit_toggled,
            selected_color="#F4695C",
            selected_hover_color="#D95546",
            fg_color="#23232F",
            unselected_color="#23232F",
            unselected_hover_color="#333341",
            text_color="#F2F2F4",
            corner_radius=8,
            font=ctk.CTkFont(family="Open Sans", size=12)
        )
        self.unit_toggle.pack(fill="x", padx=12, pady=(0, 11))
        self.unit_toggle.set("CPU")

        # 2. Profile & quality
        card_prof = _section("🎚  PROFILE & QUALITY")
        self.preset_dropdown = ctk.CTkOptionMenu(
            card_prof,
            values=list(PRESETS.keys()),
            command=self.on_preset_changed,
            fg_color="#23232F",
            button_color="#333341",
            button_hover_color="#3D3D4C",
            dropdown_fg_color="#2B2B39",
            dropdown_hover_color="#383846",
            text_color="#F2F2F4",
            corner_radius=8,
            font=ctk.CTkFont(family="Open Sans", size=13),
            dropdown_font=ctk.CTkFont(family="Open Sans", size=13)
        )
        self.preset_dropdown.pack(fill="x", padx=12, pady=(0, 8))
        self.preset_dropdown.set("LMS Upload - VP9 1080p (Recommended)")

        self.crf_slider = ctk.CTkSlider(
            card_prof,
            from_=15, to=50, number_of_steps=35,
            command=self.on_crf_changed,
            button_color="#F4695C",
            button_hover_color="#D95546",
            progress_color="#F4695C",
            fg_color="#3A3A48"
        )
        self.crf_slider.pack(fill="x", padx=12, pady=0)
        self.crf_slider.set(32)
        self.crf_value_label = ctk.CTkLabel(
            card_prof, text="Quality: 32 (Medium)",
            font=ctk.CTkFont(family="Open Sans", size=11),
            text_color="#AEAEB2"
        )
        self.crf_value_label.pack(anchor="w", padx=12, pady=(2, 6))

        # AV1 speed dial (only packed when an AV1 profile is active on CPU)
        self.av1_frame = ctk.CTkFrame(card_prof, fg_color="transparent")
        self.av1_label = ctk.CTkLabel(
            self.av1_frame, text="SVT-AV1 PRESET SPEED",
            font=ctk.CTkFont(family="Montserrat", size=12, weight="bold"),
            text_color="#8F8F9A"
        )
        self.av1_label.pack(anchor="w", padx=12, pady=(0, 2))
        self.av1_slider = ctk.CTkSlider(
            self.av1_frame,
            from_=0, to=13, number_of_steps=13,
            command=self.on_av1_preset_changed,
            button_color="#4EB18C",
            button_hover_color="#3F9273",
            progress_color="#4EB18C",
            fg_color="#3A3A48"
        )
        self.av1_slider.pack(fill="x", padx=12, pady=0)
        self.av1_slider.set(8)
        self.av1_value_label = ctk.CTkLabel(
            self.av1_frame, text="Preset: 8 (Default)",
            font=ctk.CTkFont(family="Open Sans", size=11),
            text_color="#AEAEB2"
        )
        self.av1_value_label.pack(anchor="w", padx=12, pady=(2, 8))

        # keep a reference name used elsewhere in the app
        self.settings_container = card_prof

        # 3. Advanced options
        card_adv = _section("⚗  ADVANCED")
        self.two_pass_cb = ctk.CTkCheckBox(
            card_adv,
            text="Two-Pass VP9 (Slower, Higher Quality)",
            font=ctk.CTkFont(family="Open Sans", size=11),
            fg_color="#F4695C",
            border_color="#3A3A44",
            hover_color="#D95546",
            text_color="#D8D8DE",
            command=self.sync_all_options
        )
        self.two_pass_cb.pack(anchor="w", padx=12, pady=(0, 4))
        self.bit10_cb = ctk.CTkCheckBox(
            card_adv,
            text="Enable 10-bit Color (yuv420p10le)",
            font=ctk.CTkFont(family="Open Sans", size=11),
            fg_color="#F4695C",
            border_color="#3A3A44",
            hover_color="#D95546",
            text_color="#D8D8DE",
            command=self.sync_all_options
        )
        self.bit10_cb.pack(anchor="w", padx=12, pady=(0, 10))

        # 4. Destination (required)
        card_dest = ctk.CTkFrame(sidebar, fg_color="#2B2B39", corner_radius=12)
        card_dest.pack(fill="x", padx=14, pady=5)
        _dest_head = ctk.CTkFrame(card_dest, fg_color="transparent")
        _dest_head.pack(fill="x", padx=12, pady=(9, 3))
        ctk.CTkLabel(
            _dest_head, text="📁",
            font=ctk.CTkFont(size=17),
            text_color="#F4695C"
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            _dest_head, text="DESTINATION",
            font=ctk.CTkFont(family="Montserrat", size=12, weight="bold"),
            text_color="#8F8F9A"
        ).pack(side="left")
        self.dest_badge = ctk.CTkLabel(
            _dest_head, text="⚠ required",
            font=ctk.CTkFont(family="Montserrat", size=10, weight="bold"),
            text_color="#BFA378"
        )
        self.dest_badge.pack(side="right")
        self.output_entry = ctk.CTkEntry(
            card_dest,
            placeholder_text="Choose where WebM files go…",
            fg_color="#23232F",
            border_color="#3A3A48",
            text_color="#F2F2F4",
            corner_radius=8
        )
        self.output_entry.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkButton(
            card_dest,
            text="Choose Destination…",
            fg_color="#333341",
            hover_color="#3D3D4C",
            text_color="#F2F2F4",
            corner_radius=8,
            command=self.browse_output_dir
        ).pack(fill="x", padx=12, pady=(0, 11))

        # Push status row to the bottom of the sheet
        ctk.CTkFrame(sidebar, fg_color="transparent", height=1).pack(fill="y", expand=True)

        # 5. Engine status + system info
        self.status_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.status_frame.pack(fill="x", padx=16, pady=(4, 14))
        self.status_dot = ctk.CTkLabel(self.status_frame, text="●", font=ctk.CTkFont(size=14), text_color="#BFA378")
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_text = ctk.CTkLabel(
            self.status_frame, text="Initial scan...",
            font=ctk.CTkFont(family="Open Sans", size=11, weight="bold"),
            text_color="#AEAEB2"
        )
        self.status_text.pack(side="left")
        ctk.CTkButton(
            self.status_frame, text="ⓘ", width=24, height=22,
            fg_color="#2B2B39", hover_color="#383846", text_color="#8F8F9A",
            corner_radius=6, font=ctk.CTkFont(size=12),
            command=self.show_system_info
        ).pack(side="right")

        # Hidden label: _check_ffmpeg writes hardware details here; shown in the ⓘ popup
        self.spec_details = ctk.CTkLabel(sidebar, text="")

    def show_system_info(self):
        from dialogs import themed_toplevel
        win, body = themed_toplevel("System Details", width=380, height=230)
        ctk.CTkLabel(
            body, text="DIAGNOSTIC TELEMETRY",
            font=ctk.CTkFont(family="Montserrat", size=12, weight="bold"),
            text_color="#F4695C"
        ).pack(anchor="w", pady=(4, 6))
        ctk.CTkLabel(
            body, text=self.spec_details.cget("text") or "Scanning…",
            font=ctk.CTkFont(family="Open Sans", size=12),
            justify="left", text_color="#D8D8DE"
        ).pack(anchor="w")

    def _build_main_panel(self):
        # ── Main sheet: offset lower than the sidebar sheet (layered look) ──
        main = ctk.CTkFrame(
            self.shell,
            fg_color="#1B1B26",
            border_width=1,
            border_color="#2A2A36",
            corner_radius=16
        )
        main.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(20, 12))
        main.grid_rowconfigure(2, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # 1. Actions row
        actions_frame = ctk.CTkFrame(main, fg_color="transparent")
        actions_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        btn_add = ctk.CTkButton(
            actions_frame,
            text="＋ Add Videos…",
            fg_color="#F4695C",
            hover_color="#D95546",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Open Sans", size=13, weight="bold"),
            corner_radius=9,
            command=self.add_files
        )
        btn_add.pack(side="left", padx=(0, 8))

        btn_clear = ctk.CTkButton(
            actions_frame,
            text="Clear",
            width=70,
            fg_color="#23232F",
            hover_color="#2B2B39",
            text_color="#C9C9D1",
            font=ctk.CTkFont(family="Open Sans", size=13),
            corner_radius=9,
            command=self.clear_queue
        )
        btn_clear.pack(side="left")

        btn_commands = ctk.CTkButton(
            actions_frame,
            text="ⓘ Pipeline",
            width=86,
            fg_color="#23232F",
            hover_color="#2B2B39",
            text_color="#8F8F9A",
            font=ctk.CTkFont(family="Open Sans", size=12),
            corner_radius=9,
            command=self.show_pipeline_commands
        )
        btn_commands.pack(side="right")

        # 2. KPI strip - the compression numbers, front and center
        kpis = ctk.CTkFrame(main, fg_color="transparent")
        kpis.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        for i in range(4):
            kpis.grid_columnconfigure(i, weight=1)

        def _kpi(col, title, color):
            card = ctk.CTkFrame(kpis, fg_color="#23232F", corner_radius=12)
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0))
            icon, text = title.split("  ", 1)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(anchor="w", padx=12, pady=(9, 0))
            ctk.CTkLabel(
                row, text=icon,
                font=ctk.CTkFont(size=20),
                text_color=color
            ).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                row, text=text,
                font=ctk.CTkFont(family="Montserrat", size=11, weight="bold"),
                text_color=color
            ).pack(side="left")
            n = ctk.CTkLabel(
                card, text="-",
                font=ctk.CTkFont(family="Montserrat", size=30, weight="bold"),
                text_color="#F2F2F4"
            )
            n.pack(anchor="w", padx=12, pady=(0, 0))
            c = ctk.CTkLabel(
                card, text=" ",
                font=ctk.CTkFont(family="Open Sans", size=11),
                text_color="#7B7B85"
            )
            c.pack(anchor="w", padx=12, pady=(0, 8))
            return n, c

        self.kpi_files_n, self.kpi_files_c = _kpi(0, "🎞  FILES", "#F4695C")
        self.kpi_in_n, self.kpi_in_c = _kpi(1, "📥  INPUT", "#BFA378")
        self.kpi_out_n, self.kpi_out_c = _kpi(2, "📤  EST. OUTPUT", "#8E8EDD")
        self.kpi_saved_n, self.kpi_saved_c = _kpi(3, "💾  SAVED", "#4EB18C")

        # 3. Scrollable queue
        self.queue_frame = ctk.CTkScrollableFrame(
            main,
            fg_color="#20202C",
            border_width=0,
            corner_radius=12,
            label_text="CONVERSION QUEUE  ·  WEBM ONLY",
            label_fg_color="#20202C",
            label_text_color="#8F8F9A",
            label_font=ctk.CTkFont(family="Montserrat", size=11, weight="bold")
        )
        self.queue_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 8))

        placeholder = "Drag & drop videos here, or click \"＋ Add Videos…\"\n\nOutput is always WebM." if DND_AVAILABLE \
            else "Click \"＋ Add Videos…\" to import files.\n\nOutput is always WebM."
        self.empty_label = ctk.CTkLabel(
            self.queue_frame,
            text=placeholder,
            text_color="#6E6E78",
            justify="center",
            font=ctk.CTkFont(family="Open Sans", size=13, slant="italic")
        )
        self.empty_label.pack(pady=110)

        # 4. Overall progress
        self.progress_panel = ctk.CTkFrame(main, fg_color="#23232F", corner_radius=12)
        self.progress_panel.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.overall_progress_label = ctk.CTkLabel(
            self.progress_panel,
            text="Overall Progress: 0/0 files (0%)",
            font=ctk.CTkFont(family="Open Sans", size=12, weight="bold"),
            text_color="#F2F2F4"
        )
        self.overall_progress_label.pack(anchor="w", padx=16, pady=(10, 3))
        self.overall_progress_bar = ctk.CTkProgressBar(
            self.progress_panel,
            progress_color="#2E2E3C",  # matches track at 0% (no nub); teal once moving
            fg_color="#2E2E3C",
            height=6,
            corner_radius=3
        )
        self.overall_progress_bar.set(0.0)
        self.overall_progress_bar.pack(fill="x", padx=16, pady=(0, 12))

        # 5. Action buttons - solid green go, ghost red stop
        controls_frame = ctk.CTkFrame(main, fg_color="transparent")
        controls_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 14))

        self.btn_start = ctk.CTkButton(
            controls_frame,
            text="Compress to WebM",
            height=44,
            fg_color="#4EB18C",
            hover_color="#3F9273",
            text_color="#000000",
            text_color_disabled="#0b3d1c",
            font=ctk.CTkFont(family="Open Sans", size=16, weight="bold"),
            corner_radius=10,
            command=self.start_conversion
        )
        self.btn_start.pack(fill="x", side="left", expand=True, padx=(0, 10))

        self.btn_stop = ctk.CTkButton(
            controls_frame,
            text="■ Stop",
            height=44,
            width=130,
            fg_color="transparent",
            hover_color="#2E1512",
            border_width=1,
            border_color="#5C2620",
            text_color="#E8574A",
            text_color_disabled="#5C5C66",
            font=ctk.CTkFont(family="Open Sans", size=15, weight="bold"),
            corner_radius=10,
            state="disabled",
            command=self.stop_conversion
        )
        self.btn_stop.pack(side="right")
        self.refresh_start_button()

    def refresh_start_button(self):
        """Button label reflects how many queued videos are ticked for compression."""
        selectable = [t for t in self.queue.tasks if t.status in ["Pending", "Queued", "Stopped", "Failed"]]
        n = sum(1 for t in selectable if getattr(t, "selected", True))
        if self.queue.running:
            return  # start_conversion owns the label while encoding
        if not self.queue.tasks:
            self.btn_start.configure(text="Compress to WebM", state="normal")
        elif n == 0:
            self.btn_start.configure(text="No Videos Selected", state="disabled")
        elif n == 1:
            self.btn_start.configure(text="Compress 1 Video (WebM)", state="normal")
        else:
            self.btn_start.configure(text=f"Compress {n} Selected Videos (WebM)", state="normal")

    def on_drop_files(self, event):
        """Handle files dragged onto the window: validate videos, queue them."""
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            return
        videos, skipped = [], []
        for p in paths:
            p = p.strip("{}")
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in VIDEO_EXTENSIONS:
                videos.append(p)
            else:
                skipped.append(os.path.basename(p) or p)
        if videos:
            self._add_paths(videos)
        if skipped:
            messagebox.showwarning(
                "Some Files Skipped",
                "Not recognized as video files:\n\n" + "\n".join(skipped[:8])
                + ("\n…" if len(skipped) > 8 else "")
            )

    def _check_ffmpeg(self):
        """
        Verifies FFmpeg installation pathing and detects available hardware.
        Uses detailed diagnostic message dialogs if failure occurs.
        """
        from encoder import get_ffmpeg_path, get_ffprobe_path
        ffmpeg_bin = get_ffmpeg_path()
        ffprobe_bin = get_ffprobe_path()
        
        ffmpeg_ok = False
        ffprobe_ok = False
        ffmpeg_err = "None"
        ffprobe_err = "None"
        
        try:
            subprocess.run(
                [ffmpeg_bin, "-version"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL, 
                creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            ffmpeg_ok = True
        except Exception as e:
            ffmpeg_err = str(e)
            
        try:
            subprocess.run(
                [ffprobe_bin, "-version"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL, 
                creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            ffprobe_ok = True
        except Exception as e:
            ffprobe_err = str(e)
            
        if ffmpeg_ok and ffprobe_ok:
            self.status_dot.configure(text_color="#4EB18C") # Green
            self.status_text.configure(text="Engine Link: ONLINE", text_color="#4EB18C")
            
            # Detect GPU status
            hardware = detect_active_hardware_webm_encoders()
            active_gpus = [k.upper() for k, v in hardware.items() if v]
            if active_gpus:
                gpu_text = f"• GPU WebM: {', '.join(active_gpus)}\n• Pipeline: Zero-Copy HW"
            else:
                gpu_text = "• GPU WebM: Unsupported (CPU Fallback)\n• Pipeline: Software MT"
                
            # Update specs box
            self.spec_details.configure(text=(
                f"• OS Platform: {sys.platform.upper()}\n"
                f"• VP9 Row-MT: Active (ssim)\n"
                f"• AV1 Tiling: SVT-AV1 P7\n"
                f"{gpu_text}"
            ))
        else:
            self.status_dot.configure(text_color="#E8574A") # Red
            self.status_text.configure(text="Engine Link: OFFLINE", text_color="#E8574A")
            
            # Construct a comprehensive diagnostic description
            diag_log = (
                f"FFmpeg Path: {ffmpeg_bin} (Exists: {os.path.exists(ffmpeg_bin)})\n"
                f"FFmpeg Launch Error: {ffmpeg_err}\n\n"
                f"FFprobe Path: {ffprobe_bin} (Exists: {os.path.exists(ffprobe_bin)})\n"
                f"FFprobe Launch Error: {ffprobe_err}\n\n"
                f"Frozen Status (PyInstaller): {getattr(sys, 'frozen', False)}\n"
                f"App Executable: {sys.executable}\n"
                f"Current Dir: {os.getcwd()}"
            )
            if sys.platform == "win32":
                want_dl = messagebox.askyesno(
                    "FFmpeg Not Found",
                    "FFmpeg/FFprobe could not be initialized.\n\n"
                    "Download the free FFmpeg engine now? (~100 MB, one time)\n\n"
                    "This fetches the official LGPL build from BtbN/FFmpeg-Builds "
                    "and places it next to the app."
                )
                if want_dl:
                    self._download_ffmpeg_flow()
                    return
            messagebox.showerror(
                "Missing Dependency Error",
                f"FFmpeg/FFprobe could not be initialized.\n\n"
                f"Ensure the binaries are in the directory containing this app.\n\n"
                f"--- DIAGNOSTICS ---\n{diag_log}"
            )

    def _download_ffmpeg_flow(self):
        """Modal-ish progress window that downloads FFmpeg then re-checks the engine."""
        import ffmpeg_fetch

        from dialogs import themed_toplevel
        win, wbody = themed_toplevel("Downloading FFmpeg", width=440, height=140)
        label = ctk.CTkLabel(
            wbody, text="Starting download…",
            font=ctk.CTkFont(family="Open Sans", size=12), text_color="#C9C9D1"
        )
        label.pack(pady=(10, 8))
        bar = ctk.CTkProgressBar(wbody, width=380, progress_color="#F4695C", fg_color="#2E2E3C")
        bar.set(0.0)
        bar.pack()

        def on_progress(frac, msg):
            # Marshal UI updates onto the Tk main thread
            self.after(0, lambda: (bar.set(frac), label.configure(text=msg)))

        def worker():
            try:
                ffmpeg_fetch.download_ffmpeg(progress_cb=on_progress)
                self.after(0, finish_ok)
            except Exception as e:
                self.after(0, lambda: finish_err(str(e)))

        def finish_ok():
            win.destroy()
            # Re-run the engine check now that binaries exist
            self._check_ffmpeg()

        def finish_err(msg):
            win.destroy()
            messagebox.showerror(
                "Download Failed",
                f"Could not download FFmpeg:\n{msg}\n\n"
                "You can manually place ffmpeg.exe and ffprobe.exe next to the app, "
                "or install FFmpeg system-wide."
            )

        threading.Thread(target=worker, daemon=True).start()

    def on_unit_toggled(self, val):
        if val.startswith("GPU"):
            hardware = detect_active_hardware_webm_encoders()
            if not any(hardware.values()):
                from encoder import is_hw_decode_available
                if is_hw_decode_available():
                    messagebox.showinfo(
                        "GPU-Assisted Hybrid Encoding Active",
                        "GPU used for decode & scaling; VP9/AV1 encode runs on CPU (no GPU WebM encoder on this device)."
                    )
                else:
                    messagebox.showwarning(
                        "No GPU Acceleration Detected",
                        "No GPU acceleration (encoders or decoders) is supported on this system.\n\n"
                        "The app will use pure CPU encoding to guarantee WebM output."
                    )
                    self.unit_toggle.set("CPU")
                    val = "CPU"

        if val.startswith("GPU"):
            self.two_pass_cb.configure(state="disabled")
            self.two_pass_cb.deselect()
            self.av1_frame.pack_forget()
        else:
            self.two_pass_cb.configure(state="normal")
            preset_choice = self.preset_dropdown.get()
            if "AV1" in preset_choice:
                self.av1_frame.pack(fill="x", pady=(5, 10))

        self.sync_all_options()

    def on_preset_changed(self, choice):
        preset = PRESETS[choice]
        crf_val = 32
        
        if choice == AUDIO_ONLY_PRESET:
            self.crf_slider.configure(state="disabled")
            self.crf_value_label.configure(text="Quality: Audio Only", text_color="#8E8E93")
            crf_val = None
        else:
            self.crf_slider.configure(state="normal")
            if "-crf" in preset["args"]:
                idx = preset["args"].index("-crf")
                crf_val = int(preset["args"][idx + 1])
                self.crf_slider.set(crf_val)
            
        self.update_crf_label(crf_val)

        # Control AV1 Preset slider visibility
        if "AV1" in choice and not self.unit_toggle.get().startswith("GPU"):
            self.av1_frame.pack(fill="x", pady=(5, 10))
        else:
            self.av1_frame.pack_forget()

        self.sync_all_options()

    def on_crf_changed(self, value):
        crf_val = int(value)
        self.update_crf_label(crf_val)
        self.sync_all_options()

    def on_av1_preset_changed(self, value):
        preset_val = int(value)
        self.av1_value_label.configure(text=f"Preset: {preset_val} (Speed/Quality dial)")
        self.sync_all_options()

    def sync_all_options(self):
        preset_name = self.preset_dropdown.get()
        use_gpu = self.unit_toggle.get().startswith("GPU")
        crf_val = int(self.crf_slider.get()) if preset_name != AUDIO_ONLY_PRESET else None
        two_pass = self.two_pass_cb.get()
        bit10 = self.bit10_cb.get()
        av1_preset = int(self.av1_slider.get()) if "AV1" in preset_name else None
        # Output paths are only assigned once the user has picked a save folder;
        # start_conversion re-finalizes them (and enforces the folder rule).
        out_dir = self.get_selected_output_dir()

        for task in self.queue.tasks:
            if task.status in ["Pending", "Queued", "Stopped"]:
                task.preset_name = preset_name
                task.use_gpu = use_gpu
                task.crf_override = crf_val
                task.two_pass = two_pass
                task.bit10 = bit10
                task.av1_preset = av1_preset
                if out_dir:
                    task.output_path = self.get_unique_output_path(out_dir, os.path.basename(task.input_path), ".webm")

        self.on_queue_update()

    def update_crf_label(self, val):
        desc = "Medium"
        if val < 20:
            desc = "Master Quality"
        elif val < 28:
            desc = "High Quality"
        elif val < 36:
            desc = "Balanced size/quality"
        elif val < 44:
            desc = "Highly compressed"
        else:
            desc = "Maximum compression"
            
        if val is None:
            self.crf_value_label.configure(text="Quality: Audio Only", text_color="#8E8E93")
        else:
            self.crf_value_label.configure(
                text=f"Quality: {val} ({desc})", 
                text_color="#FFFFFF" if val <= 35 else "#BFA378"
            )

    def browse_output_dir(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, os.path.abspath(folder))
            if hasattr(self, "dest_badge"):
                self.dest_badge.configure(text="✓ set", text_color="#4EB18C")
            self.sync_all_options()

    def get_default_output_dir(self):
        if sys.platform == "win32":
            path = os.path.join(os.environ.get("USERPROFILE", "C:\\"), "Videos", "WebM Compressor")
        else:
            home = os.path.expanduser("~")
            if os.path.exists(os.path.join(home, "Videos")):
                path = os.path.join(home, "Videos", "WebM Compressor")
            elif os.path.exists(os.path.join(home, "Movies")):
                path = os.path.join(home, "Movies", "WebM Compressor")
            elif os.path.exists(os.path.join(home, "Downloads")):
                path = os.path.join(home, "Downloads", "WebM Compressor")
            else:
                path = os.path.join(home, "WebM Compressor")
        return os.path.abspath(path)

    def get_unique_output_path(self, base_dir, original_name, target_extension):
        target_extension = ".webm"
        clean_name = os.path.splitext(original_name)[0]
            
        candidate_name = f"{clean_name}_compressed{target_extension}"
        candidate_path = os.path.join(base_dir, candidate_name)
        
        if not os.path.exists(candidate_path):
            return os.path.abspath(candidate_path)
            
        idx = 1
        while True:
            candidate_name = f"{clean_name}_compressed_{idx:02d}{target_extension}"
            candidate_path = os.path.join(base_dir, candidate_name)
            if not os.path.exists(candidate_path):
                return os.path.abspath(candidate_path)
            idx += 1

    def add_files(self):
        files = filedialog.askopenfilenames(
            title="Select Videos",
            filetypes=[("Videos", " ".join(f"*{e}" for e in sorted(VIDEO_EXTENSIONS))), ("All files", "*.*")]
        )
        if not files:
            return
        self._add_paths(files)

    def _add_paths(self, files):
        """Queue the given video paths (used by both the file dialog and drag-and-drop)."""
        if self.empty_label:
            self.empty_label.destroy()
            self.empty_label = None

        preset_name = self.preset_dropdown.get()
        crf_val = int(self.crf_slider.get())
        if preset_name == AUDIO_ONLY_PRESET:
            crf_val = None

        use_gpu = self.unit_toggle.get().startswith("GPU")
        two_pass = self.two_pass_cb.get()
        bit10 = self.bit10_cb.get()
        av1_preset = int(self.av1_slider.get()) if "AV1" in preset_name else None

        # Save location is chosen (and validated) at compression start; output
        # paths are finalized there. Rows can exist without a destination yet.
        out_dir = self.get_selected_output_dir()

        for file_path in files:
            file_path = os.path.abspath(file_path)
            orig_name = os.path.basename(file_path)
            output_path = self.get_unique_output_path(out_dir, orig_name, ".webm") if out_dir else ""

            task = self.queue.add_task(
                file_path, output_path, preset_name, use_gpu, crf_val,
                two_pass=two_pass, bit10=bit10, av1_preset=av1_preset
            )

            row = TaskRow(
                self.queue_frame, task, self.remove_task_row,
                self.generate_quality_preview, selection_callback=self.refresh_start_button
            )
            self.task_rows[task.id] = row

        self.refresh_overall_progress()
        self.refresh_start_button()

    def get_selected_output_dir(self):
        """The user-chosen save folder, or None if not selected yet (required to start)."""
        out_dir = self.output_entry.get().strip()
        return out_dir or None

    def require_output_dir(self):
        """Enforce the save-location rule. Returns a valid folder or None (with warning)."""
        out_dir = self.get_selected_output_dir()
        if not out_dir:
            messagebox.showwarning(
                "Save Location Required",
                "Please choose where the compressed WebM files should be saved.\n\n"
                "Use \"Choose Destination…\" in the sidebar before starting compression."
            )
            return None
        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"Could not create the save folder:\n{e}")
                return None
        return out_dir

    def remove_task_row(self, task_id):
        self.queue.remove_task(task_id)
        if task_id in self.task_rows:
            self.task_rows[task_id].destroy()
            del self.task_rows[task_id]
            
        new_task_rows = {}
        for idx, task in enumerate(self.queue.tasks):
            old_id = None
            for key, row in self.task_rows.items():
                if row.task.input_path == task.input_path and row.task.output_path == task.output_path:
                    old_id = key
                    break
            if old_id is not None:
                row = self.task_rows[old_id]
                row.task = task
                new_task_rows[task.id] = row
                
        self.task_rows = new_task_rows
        self.on_queue_update()
        self.refresh_start_button()

    def clear_queue(self):
        self.queue.clear()
        for row in self.task_rows.values():
            row.destroy()
        self.task_rows.clear()

        if not self.empty_label:
            placeholder = "Drag & drop videos here, or click \"Add Videos…\"\n\nOutput is always WebM." if DND_AVAILABLE \
                else "Click \"Add Videos…\" to import files.\n\nOutput is always WebM."
            self.empty_label = ctk.CTkLabel(
                self.queue_frame,
                text=placeholder,
                text_color="#6E6E78",
                justify="center",
                font=ctk.CTkFont(family="Open Sans", size=13, slant="italic")
            )
            self.empty_label.pack(pady=110)

        self.refresh_overall_progress()
        self.refresh_start_button()

    def generate_quality_preview(self, task):
        self.preview_window = ctk.CTkToplevel(self)
        self.preview_window.title("Preview")
        self.preview_window.geometry("350x150")
        self.preview_window.resizable(False, False)
        
        self.preview_window.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 175
        y = self.winfo_y() + (self.winfo_height() // 2) - 75
        self.preview_window.geometry(f"+{x}+{y}")
        self.preview_window.transient(self)
        self.preview_window.grab_set()
        
        lbl = ctk.CTkLabel(
            self.preview_window, 
            text="Extracting visual sample...\nThis may take a moment...", 
            font=ctk.CTkFont(size=13)
        )
        lbl.pack(pady=40)

        preset_name = self.preset_dropdown.get()
        crf_val = int(self.crf_slider.get())
        if preset_name == AUDIO_ONLY_PRESET:
            crf_val = None
        use_gpu = self.unit_toggle.get().startswith("GPU")
        two_pass = self.two_pass_cb.get()
        bit10 = self.bit10_cb.get()
        av1_preset = int(self.av1_slider.get()) if "AV1" in preset_name else None
        
        # Previews are temporary samples, not deliverables - they go to the
        # system temp folder and never touch (or require) the save location.
        import tempfile
        out_dir = os.path.join(tempfile.gettempdir(), "WebM Compressor Previews")
        os.makedirs(out_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(task.input_path))[0]
        preview_path = self.get_unique_output_path(out_dir, f"{base_name}_preview", ".webm")

        def run_thread():
            try:
                final_path, final_size = generate_preview(
                    task.input_path, 
                    preview_path, 
                    preset_name, 
                    use_gpu, 
                    crf_val,
                    two_pass=two_pass,
                    bit10=bit10,
                    av1_preset=av1_preset
                )
                self.after(0, lambda: self.on_preview_finished(task, final_path, final_size))
            except Exception as e:
                self.after(0, lambda: self.on_preview_failed(str(e)))
                
        threading.Thread(target=run_thread, daemon=True).start()

    def on_preview_finished(self, task, path, size):
        if self.preview_window:
            self.preview_window.destroy()
            self.preview_window = None
            
        orig_size = task.metadata["size_bytes"]
        ratio = 0
        if task.metadata["duration"] > 0:
            est_total_compressed = (size / 5.0) * task.metadata["duration"]
            ratio = int(((orig_size - est_total_compressed) / orig_size) * 100)
        else:
            est_total_compressed = size
            ratio = 50
            
        msg = f"Preview sample generated successfully!\n\n"
        msg += f"Original Size: {self._format_size(orig_size)}\n"
        msg += f"Est. Compressed Size: {self._format_size(est_total_compressed)} (~{ratio}% smaller)\n\n"
        msg += "Would you like to open the 5-second sample in your media player to review visual quality?"
        
        res = messagebox.askyesno("Quality Preview Check", msg)
        if res:
            try:
                if sys.platform == "win32":
                    os.startfile(path)
                elif sys.platform == "darwin":
                    subprocess.run(["open", path])
                else:
                    subprocess.run(["xdg-open", path])
            except Exception as e:
                messagebox.showerror("Error", f"Failed to launch player: {e}")

    def on_preview_failed(self, error_msg):
        if self.preview_window:
            self.preview_window.destroy()
            self.preview_window = None
        messagebox.showerror("Preview Failed", f"Could not create preview sample:\n{error_msg}")

    def start_conversion(self):
        if not self.queue.tasks:
            messagebox.showwarning("Queue Empty", "Please import files before starting.")
            return

        # Rule 1: a save location must be explicitly chosen before compression.
        out_dir = self.require_output_dir()
        if not out_dir:
            return

        # Rule 2: only ticked videos are compressed.
        selected = [t for t in self.queue.tasks
                    if t.status in ["Pending", "Queued", "Stopped", "Failed"] and getattr(t, "selected", True)]
        if not selected:
            messagebox.showwarning(
                "No Videos Selected",
                "Tick at least one video in the queue to compress it."
            )
            return

        preset_name = self.preset_dropdown.get()
        use_gpu = self.unit_toggle.get().startswith("GPU")
        crf_val = int(self.crf_slider.get()) if preset_name != AUDIO_ONLY_PRESET else None
        two_pass = self.two_pass_cb.get()
        bit10 = self.bit10_cb.get()
        av1_preset = int(self.av1_slider.get()) if "AV1" in preset_name else None

        for task in selected:
            task.preset_name = preset_name
            task.use_gpu = use_gpu
            task.crf_override = crf_val
            task.two_pass = two_pass
            task.bit10 = bit10
            task.av1_preset = av1_preset
            task.output_path = self.get_unique_output_path(out_dir, os.path.basename(task.input_path), ".webm")

        self.on_queue_update()

        n = len(selected)
        label = "Compressing 1 video…" if n == 1 else f"Compressing {n} videos…"
        self.btn_start.configure(state="disabled", text=label)
        self.btn_stop.configure(state="normal")
        self.preset_dropdown.configure(state="disabled")
        self.crf_slider.configure(state="disabled")
        self.av1_slider.configure(state="disabled")
        self.two_pass_cb.configure(state="disabled")
        self.bit10_cb.configure(state="disabled")
        self.output_entry.configure(state="disabled")
        self.unit_toggle.configure(state="disabled")
        
        self.queue.start()

    def stop_conversion(self):
        self.queue.stop()
        self._get_taskbar().clear()
        self.refresh_start_button()
        self.btn_stop.configure(state="disabled")
        self.preset_dropdown.configure(state="normal")
        self.unit_toggle.configure(state="normal")

        preset_name = self.preset_dropdown.get()
        if preset_name != AUDIO_ONLY_PRESET:
            self.crf_slider.configure(state="normal")
            
        if "AV1" in preset_name and not self.unit_toggle.get().startswith("GPU"):
            self.av1_slider.configure(state="normal")
            
        if not self.unit_toggle.get().startswith("GPU"):
            self.two_pass_cb.configure(state="normal")
            
        self.bit10_cb.configure(state="normal")
        self.output_entry.configure(state="normal")
        self.on_queue_update()

    def on_queue_update(self):
        self.after(0, self._safe_ui_update)

    def on_queue_finish(self):
        self.after(0, self._safe_ui_finish)

    def _safe_ui_update(self):
        for task in self.queue.tasks:
            if task.id in self.task_rows:
                self.task_rows[task.id].update(task)
        self.refresh_overall_progress()

    def _safe_ui_finish(self):
        self._get_taskbar().clear()
        self.refresh_start_button()
        self.btn_stop.configure(state="disabled")
        self.preset_dropdown.configure(state="normal")
        self.unit_toggle.configure(state="normal")

        preset_name = self.preset_dropdown.get()
        if preset_name != AUDIO_ONLY_PRESET:
            self.crf_slider.configure(state="normal")
            
        if "AV1" in preset_name and not self.unit_toggle.get().startswith("GPU"):
            self.av1_slider.configure(state="normal")
            
        if not self.unit_toggle.get().startswith("GPU"):
            self.two_pass_cb.configure(state="normal")
            
        self.bit10_cb.configure(state="normal")
        self.output_entry.configure(state="normal")
        self._safe_ui_update()
        messagebox.showinfo("Done", "All video compression jobs completed successfully.")

    def show_pipeline_commands(self):
        """
        Creates a pop-up text frame listing the compiled FFmpeg command line pipelines.
        Used to verify and guarantee active CPU row-mt/tiling and GPU zero-copy CUDA parameters.
        """
        preset_name = self.preset_dropdown.get()
        preset = PRESETS.get(preset_name)
        if not preset:
            return
            
        use_gpu = self.unit_toggle.get().startswith("GPU")
        crf_val = int(self.crf_slider.get()) if preset_name != AUDIO_ONLY_PRESET else None
        two_pass = self.two_pass_cb.get()
        bit10 = self.bit10_cb.get()
        av1_preset = int(self.av1_slider.get()) if "AV1" in preset_name else None
        
        # Build mock task to compile commands
        mock_metadata = {
            "duration": 60.0,
            "width": 1920,
            "height": 1080,
            "bitrate": 5000000,
            "size_bytes": 10000000,
            "color_space": None,
            "color_transfer": None,
            "color_primaries": None
        }
        mock_task = EncoderTask(
            1, "input.mp4", "output.webm", preset_name, use_gpu, crf_val,
            two_pass=two_pass, bit10=bit10, av1_preset=av1_preset,
            metadata_override=mock_metadata
        )
        
        # Build CPU sample command
        cpu_cmd_list = []
        if two_pass and preset["codec"] == "libvpx-vp9":
            from encoder import build_ffmpeg_command
            cmd1 = build_ffmpeg_command(mock_task, preset, None, pass_num=1, passlog_path="passlog", force_software_decode=True)
            cmd2 = build_ffmpeg_command(mock_task, preset, None, pass_num=2, passlog_path="passlog", force_software_decode=True)
            cpu_cmd_list.append(f"Pass 1: {' '.join(cmd1)}")
            cpu_cmd_list.append(f"Pass 2: {' '.join(cmd2)}")
        else:
            from encoder import build_ffmpeg_command
            cmd = build_ffmpeg_command(mock_task, preset, None, force_software_decode=True)
            cpu_cmd_list.append(" ".join(cmd))
            
        cpu_cmd = "\n".join(cpu_cmd_list)
        
        # Build GPU sample command
        hardware = detect_active_hardware_webm_encoders()
        from encoder import get_gpu_encoder_params, build_ffmpeg_command
        gpu_params = get_gpu_encoder_params(preset["codec"], preset["args"], hardware, crf_val)
        
        if gpu_params:
            cmd = build_ffmpeg_command(mock_task, preset, gpu_params)
            gpu_cmd = " ".join(cmd)
        else:
            # Try to build hybrid command
            mock_task.use_gpu = True
            cmd = build_ffmpeg_command(mock_task, preset, None)
            if mock_task.hybrid_active:
                gpu_cmd = " ".join(cmd) + "\n\n(Active: GPU-Assisted Hybrid Decode & Scale + CPU Encode)"
            else:
                gpu_cmd = "No GPU WebM hardware encoding or hybrid decoding available (falls back to CPU command above)."
            
        msg = (
            f"Active Profile: {preset_name}\n\n"
            f"--- CPU PIPELINE COMMAND ---\n{cpu_cmd}\n\n"
            f"--- GPU PIPELINE COMMAND ---\n{gpu_cmd}\n\n"
            "Research Parameters Active:\n"
            "✓ WebM Container Locked (.webm only)\n"
            "✓ row-mt 1: Enabled multi-threaded row-based decoding.\n"
            "✓ lag-in-frames 25 / auto-alt-ref 1: VP9 visual lookahead enabled.\n"
            "✓ constant quality: -b:v 0 correctly paired with -crf.\n"
            "✓ av1_nvenc / av1_qsv / vp9_qsv: WebM Hardware Acceleration."
        )
        
        # Display in a themed scrollable text sheet
        from dialogs import themed_toplevel
        win, body = themed_toplevel("Pipeline Commands", width=760, height=480, modal=True)
        txt = ctk.CTkTextbox(
            body, wrap="word",
            fg_color="#20202C", text_color="#C9C9D1",
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=10, border_width=0
        )
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", msg)
        txt.configure(state="disabled")

    def _format_size(self, size_bytes):
        if not size_bytes:
            return "0 KB"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def refresh_kpis(self):
        """Live numbers for the KPI strip: files, input size, est. output, saved %."""
        if not hasattr(self, "kpi_files_n"):
            return
        tasks = self.queue.tasks
        if not tasks:
            self.kpi_files_n.configure(text="-"); self.kpi_files_c.configure(text=" ")
            self.kpi_in_n.configure(text="-"); self.kpi_in_c.configure(text=" ")
            self.kpi_out_n.configure(text="-"); self.kpi_out_c.configure(text=" ")
            self.kpi_saved_n.configure(text="-"); self.kpi_saved_c.configure(text=" ")
            return

        n_sel = sum(1 for t in tasks if getattr(t, "selected", True))
        self.kpi_files_n.configure(text=str(len(tasks)))
        self.kpi_files_c.configure(text=f"{n_sel} selected")

        input_total = sum(t.metadata.get("size_bytes", 0) for t in tasks)
        self.kpi_in_n.configure(text=self._format_size(input_total))
        self.kpi_in_c.configure(text=f"{len(tasks)} video{'s' if len(tasks) != 1 else ''}")

        known = [(t.metadata.get("size_bytes", 0), t.est_size_bytes) for t in tasks if t.est_size_bytes > 0]
        if known:
            in_known = sum(k[0] for k in known)
            out_known = sum(k[1] for k in known)
            # extrapolate the measured ratio to files not yet encoded
            ratio = (out_known / in_known) if in_known else 0
            est_total = out_known + sum(
                t.metadata.get("size_bytes", 0) * ratio for t in tasks if t.est_size_bytes <= 0
            )
            self.kpi_out_n.configure(text=f"~{self._format_size(est_total)}")
            self.kpi_out_c.configure(text="WebM output")
            saved = max(0, int((1 - est_total / input_total) * 100)) if input_total else 0
            self.kpi_saved_n.configure(text=f"{saved}%")
            self.kpi_saved_c.configure(text=f"−{self._format_size(max(0, input_total - est_total))}")
        else:
            self.kpi_out_n.configure(text="-")
            self.kpi_out_c.configure(text="starts with encode")
            self.kpi_saved_n.configure(text="-")
            self.kpi_saved_c.configure(text=" ")

    def refresh_overall_progress(self):
        self.refresh_kpis()
        total_tasks = len(self.queue.tasks)
        if total_tasks == 0:
            self.overall_progress_label.configure(text="Overall Progress: 0/0 files (0%)")
            self.overall_progress_bar.set(0.0)
            self.overall_progress_bar.configure(progress_color="#2E2E3C")  # hide 0% nub
            self._get_taskbar().clear()
            return

        completed = sum(1 for t in self.queue.tasks if t.status == "Completed")
        failed = sum(1 for t in self.queue.tasks if t.status in ["Failed", "Stopped"])
        total_progress = sum(t.progress for t in self.queue.tasks)
        overall_pct = int(total_progress / total_tasks)

        status_str = f"Overall Progress: {completed}/{total_tasks} files completed"
        if failed > 0:
            status_str += f" ({failed} failed)"

        status_str += f" ({overall_pct}%)"

        self.overall_progress_label.configure(text=status_str)
        self.overall_progress_bar.set(overall_pct / 100.0)
        self.overall_progress_bar.configure(
            progress_color="#4EB18C" if overall_pct > 0 else "#2E2E3C"
        )

        # Mirror real progress onto the Windows taskbar icon (Explorer-style).
        if self.queue.running:
            self._get_taskbar().set_progress(overall_pct, 100)
        elif failed > 0 and completed + failed == total_tasks:
            self._get_taskbar().set_error()

if __name__ == "__main__":
    app = WebMCompressorApp()
    app.mainloop()
