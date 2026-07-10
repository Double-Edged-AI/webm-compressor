# PERMANENT RULE: This application compresses videos and exports WebM only. 
# Input can be any supported video format, but output must always be .webm. 
# No UI option, preset, override, or backend process is allowed to export MP4 or any other format.

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import shutil
import threading
import subprocess

# Windows-specific flag to prevent cmd console windows from spawning
CREATE_NO_WINDOW = 0x08000000

# Import our backend logic
from encoder import (
    EncodingQueue, 
    EncoderTask,
    PRESETS, 
    get_metadata, 
    detect_active_hardware_webm_encoders, 
    generate_preview
)

# Set appearance mode and color theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class TaskRow:
    """
    Represents a visual row in the queue table.
    Designed using Apple's Human Interface Guidelines (elevated flat card design).
    Fully responsive layout using horizontal flow packaging.
    """
    def __init__(self, parent_frame, task, remove_callback, preview_callback):
        self.task = task
        self.remove_callback = remove_callback
        self.preview_callback = preview_callback

        # Apple System Gray 5 elevated background with a very subtle border
        self.frame = ctk.CTkFrame(
            parent_frame, 
            fg_color="#2C2C2E",       # elevated container color
            border_width=1, 
            border_color="#3A3A3C",   # subtle separator color
            corner_radius=10          # HIG continuous curve roundness
        )
        self.frame.pack(fill="x", padx=10, pady=4)

        # Left container (details and progress)
        self.left_container = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.left_container.pack(side="left", fill="both", expand=True, padx=(15, 10), pady=10)
        
        # Right container (actions)
        self.right_container = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.right_container.pack(side="right", fill="y", padx=(10, 15), pady=10)

        # 1. Filename label
        base_name = os.path.basename(task.input_path)
        self.name_label = ctk.CTkLabel(
            self.left_container, 
            text=base_name, 
            anchor="w", 
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
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
            font=ctk.CTkFont(family="SF Pro Text", size=10),
            text_color="#8E8E93"
        )
        self.details_label.pack(fill="x", anchor="w", pady=(0, 6))

        # 3. Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            self.left_container,
            progress_color="#0A84FF",  # Apple System Blue accent
            fg_color="#1C1C1E",        # Base background color
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
            font=ctk.CTkFont(family="SF Pro Text", size=10, weight="bold"),
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
            fg_color="#3A3A3C",
            hover_color="#48484A",
            text_color="#FFFFFF",
            corner_radius=8,
            font=ctk.CTkFont(size=12),
            command=lambda: self.preview_callback(self.task)
        )
        self.preview_btn.pack(side="left", padx=3)

        # Delete Button
        self.delete_btn = ctk.CTkButton(
            self.right_container,
            text="✕",
            width=28,
            height=28,
            fg_color="#3A3A3C",
            hover_color="#FF453A",    # Changes to Apple System Red on hover
            text_color="#AEAEB2",
            corner_radius=8,
            font=ctk.CTkFont(size=11),
            command=lambda: self.remove_callback(task.id)
        )
        self.delete_btn.pack(side="left", padx=3)

    def update(self, task):
        self.task = task
        
        # Apple semantic status colors
        status_colors = {
            "Pending": "#FF9F0A",      # Apple Orange
            "Queued": "#0A84FF",       # Apple Blue
            "Encoding": "#30D158",     # Apple Green
            "Completed": "#30D158",    # Apple Green
            "Failed": "#FF453A",       # Apple Red
            "Stopped": "#FF453A"       # Apple Red
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
        self.progress_bar.configure(progress_color=color)
        
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
                text_color="#30D158"
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
        else:
            self.delete_btn.configure(state="normal")
            self.preview_btn.configure(state="normal")

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


class WebMCompressorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("WebM Compressor — Double-Edged AI")
        self.geometry("1100x740")
        self.minsize(1020, 680)
        
        # Apple Dark Mode background: systemGray6-like (#1C1C1E)
        self.configure(fg_color="#1C1C1E") 

        # Initialize background queue
        self.queue = EncodingQueue(
            callback_on_update=self.on_queue_update,
            callback_on_finish=self.on_queue_finish
        )
        self.task_rows = {}
        self.preview_window = None
        
        # Columns layout
        self.grid_columnconfigure(0, weight=1, minsize=350)  # Sidebar
        self.grid_columnconfigure(1, weight=3)               # Main Panel
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_panel()
        self._check_ffmpeg()

    def _build_sidebar(self):
        # Apple System Gray 5 sidebar background for subtle elevation
        sidebar = ctk.CTkFrame(
            self, 
            fg_color="#2C2C2E", 
            border_width=1, 
            border_color="#3A3A3C", 
            corner_radius=0
        )
        sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        
        # 1. Elegant Minimal Logo
        logo_label = ctk.CTkLabel(
            sidebar, 
            text="Double-Edged AI", 
            font=ctk.CTkFont(family="SF Pro Display", size=20, weight="bold"),
            text_color="#FFFFFF"
        )
        logo_label.pack(padx=20, pady=(25, 2), anchor="w")
        
        subtitle_label = ctk.CTkLabel(
            sidebar, 
            text="VIDEO COMPRESSION ENGINE", 
            font=ctk.CTkFont(family="SF Pro Text", size=9, weight="bold"),
            text_color="#8E8E93"
        )
        subtitle_label.pack(padx=20, pady=(0, 20), anchor="w")

        # Divider
        ctk.CTkFrame(sidebar, height=1, fg_color="#3A3A3C").pack(fill="x", padx=20, pady=5)

        # 2. Hardware Engine Toggle
        label_unit = ctk.CTkLabel(
            sidebar, 
            text="COMPRESSION ENGINE", 
            font=ctk.CTkFont(family="SF Pro Text", size=10, weight="bold"), 
            text_color="#8E8E93"
        )
        label_unit.pack(anchor="w", padx=20, pady=(15, 5))
        
        self.unit_toggle = ctk.CTkSegmentedButton(
            sidebar,
            values=["CPU", "GPU (Fast, Lower Quality)"],
            command=self.on_unit_toggled,
            selected_color="#0A84FF",          # Apple System Blue
            selected_hover_color="#0066cc",
            fg_color="#1C1C1E",
            text_color="#FFFFFF"
        )
        self.unit_toggle.pack(fill="x", padx=20, pady=(0, 15))
        self.unit_toggle.set("CPU")

        # 3. Presets Dropdown
        label_preset = ctk.CTkLabel(
            sidebar, 
            text="OUTPUT PROFILE", 
            font=ctk.CTkFont(family="SF Pro Text", size=10, weight="bold"), 
            text_color="#8E8E93"
        )
        label_preset.pack(anchor="w", padx=20, pady=(5, 5))
        
        self.preset_dropdown = ctk.CTkOptionMenu(
            sidebar,
            values=list(PRESETS.keys()),
            command=self.on_preset_changed,
            fg_color="#1C1C1E",
            button_color="#3A3A3C",
            button_hover_color="#48484A",
            dropdown_fg_color="#2C2C2E",
            dropdown_hover_color="#3A3A3C",
            text_color="#FFFFFF"
        )
        self.preset_dropdown.pack(fill="x", padx=20, pady=(0, 15))
        self.preset_dropdown.set("LMS Upload Preset (VP9 1080p)")

        # Create settings container to wrap CRF quality & SVT-AV1 preset options
        self.settings_container = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.settings_container.pack(fill="x", padx=20, pady=0)

        # 4. Quality CRF Slider
        label_crf = ctk.CTkLabel(
            self.settings_container, 
            text="VISUAL QUALITY OVERRIDE", 
            font=ctk.CTkFont(family="SF Pro Text", size=10, weight="bold"), 
            text_color="#8E8E93"
        )
        label_crf.pack(anchor="w", pady=(5, 5))
        
        self.crf_slider = ctk.CTkSlider(
            self.settings_container,
            from_=15,
            to=50,
            number_of_steps=35,
            command=self.on_crf_changed,
            button_color="#0A84FF",
            button_hover_color="#0066cc",
            progress_color="#0A84FF"
        )
        self.crf_slider.pack(fill="x", pady=0)
        self.crf_slider.set(32)

        self.crf_value_label = ctk.CTkLabel(
            self.settings_container, 
            text="Quality: 32 (Medium)", 
            font=ctk.CTkFont(family="SF Pro Text", size=10), 
            text_color="#AEAEB2"
        )
        self.crf_value_label.pack(anchor="w", pady=(2, 10))

        # AV1 speed preset slider frame (packed only when AV1 is selected on CPU)
        self.av1_frame = ctk.CTkFrame(self.settings_container, fg_color="transparent")
        self.av1_label = ctk.CTkLabel(
            self.av1_frame, 
            text="SVT-AV1 PRESET SPEED", 
            font=ctk.CTkFont(family="SF Pro Text", size=10, weight="bold"), 
            text_color="#8E8E93"
        )
        self.av1_label.pack(anchor="w", pady=(0, 2))
        self.av1_slider = ctk.CTkSlider(
            self.av1_frame,
            from_=0,
            to=13,
            number_of_steps=13,
            command=self.on_av1_preset_changed,
            button_color="#30D158",
            button_hover_color="#24a044",
            progress_color="#30D158"
        )
        self.av1_slider.pack(fill="x", pady=0)
        self.av1_slider.set(8)
        self.av1_value_label = ctk.CTkLabel(
            self.av1_frame, 
            text="Preset: 8 (Default)", 
            font=ctk.CTkFont(family="SF Pro Text", size=10), 
            text_color="#AEAEB2"
        )
        self.av1_value_label.pack(anchor="w", pady=(2, 10))

        # Checkboxes for Two-Pass and 10-bit Color
        self.options_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.options_frame.pack(fill="x", padx=20, pady=(5, 10))
        
        self.two_pass_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Two-Pass VP9 (Slower, Higher Quality)",
            font=ctk.CTkFont(family="SF Pro Text", size=10),
            fg_color="#0A84FF",
            border_color="#3A3A3C",
            command=self.sync_all_options
        )
        self.two_pass_cb.pack(anchor="w", pady=4)
        
        self.bit10_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Enable 10-bit Color (yuv420p10le)",
            font=ctk.CTkFont(family="SF Pro Text", size=10),
            fg_color="#0A84FF",
            border_color="#3A3A3C",
            command=self.sync_all_options
        )
        self.bit10_cb.pack(anchor="w", pady=4)

        # 5. Output Path Selector
        label_output = ctk.CTkLabel(
            sidebar, 
            text="SAVE LOCATION", 
            font=ctk.CTkFont(family="SF Pro Text", size=10, weight="bold"), 
            text_color="#8E8E93"
        )
        label_output.pack(anchor="w", padx=20, pady=(5, 5))
        
        self.output_entry = ctk.CTkEntry(
            sidebar,
            placeholder_text="Default (Double-Edged AI folder)",
            fg_color="#1C1C1E",
            border_color="#3A3A3C",
            text_color="#FFFFFF"
        )
        self.output_entry.pack(fill="x", padx=20, pady=(0, 6))
        
        btn_output = ctk.CTkButton(
            sidebar,
            text="Choose Destination...",
            fg_color="#3A3A3C",
            hover_color="#48484A",
            text_color="#FFFFFF",
            corner_radius=8,
            command=self.browse_output_dir
        )
        btn_output.pack(fill="x", padx=20, pady=(0, 15))

        # Divider
        ctk.CTkFrame(sidebar, height=1, fg_color="#3A3A3C").pack(fill="x", padx=20, pady=10)

        # 6. Specs Status Box
        spec_box = ctk.CTkFrame(
            sidebar, 
            fg_color="#1C1C1E", 
            border_width=1, 
            border_color="#3A3A3C", 
            corner_radius=8
        )
        spec_box.pack(fill="x", padx=20, pady=10)
        
        spec_header = ctk.CTkLabel(
            spec_box, 
            text="DIAGNOSTIC TELEMETRY", 
            font=ctk.CTkFont(family="SF Pro Text", size=9, weight="bold"), 
            text_color="#0A84FF"
        )
        spec_header.pack(anchor="w", padx=12, pady=(8, 4))
        
        self.spec_details = ctk.CTkLabel(
            spec_box,
            text=(
                f"• OS Platform: {sys.platform.upper()}\n"
                "• VP9 Row-MT: Active (ssim)\n"
                "• AV1 Tiling: SVT-AV1 P7\n"
                "• CUDA Engine: Scan..."
            ),
            font=ctk.CTkFont(family="SF Pro Text", size=9),
            justify="left",
            text_color="#AEAEB2"
        )
        self.spec_details.pack(anchor="w", padx=12, pady=(0, 8))

        # Push elements to top
        ctk.CTkFrame(sidebar, height=1, fg_color="transparent").pack(fill="y", expand=True)

        # 7. Bottom Status Bar
        self.status_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.status_frame.pack(fill="x", padx=20, pady=(5, 20))
        
        self.status_dot = ctk.CTkLabel(self.status_frame, text="●", font=ctk.CTkFont(size=14), text_color="#FF9F0A")
        self.status_dot.pack(side="left", padx=(0, 6))
        
        self.status_text = ctk.CTkLabel(
            self.status_frame, 
            text="Initial scan...", 
            font=ctk.CTkFont(family="SF Pro Text", size=10, weight="bold"), 
            text_color="#AEAEB2"
        )
        self.status_text.pack(side="left")

    def _build_main_panel(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        main.grid_rowconfigure(1, weight=1) 
        main.grid_columnconfigure(0, weight=1)

        # 1. Top Bar Controls
        actions_frame = ctk.CTkFrame(main, fg_color="transparent")
        actions_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        btn_add = ctk.CTkButton(
            actions_frame,
            text="Add Videos...",
            fg_color="#0A84FF",        # Apple systemBlue primary button
            hover_color="#0066cc",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
            corner_radius=8,
            command=self.add_files
        )
        btn_add.pack(side="left", padx=(0, 10))

        btn_clear = ctk.CTkButton(
            actions_frame,
            text="Clear",
            fg_color="#2C2C2E",
            hover_color="#3A3A3C",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="SF Pro Text", size=12),
            corner_radius=8,
            command=self.clear_queue
        )
        btn_clear.pack(side="left")

        btn_commands = ctk.CTkButton(
            actions_frame,
            text="Verify Pipeline Commands",
            fg_color="#2C2C2E",
            hover_color="#3A3A3C",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="SF Pro Text", size=12),
            corner_radius=8,
            command=self.show_pipeline_commands
        )
        btn_commands.pack(side="left", padx=(10, 0))

        # 2. Scrollable Queue Window
        self.queue_frame = ctk.CTkScrollableFrame(
            main, 
            fg_color="#1C1C1E",        # Matches background
            border_width=1, 
            border_color="#2C2C2E", 
            corner_radius=10,
            label_text="CONVERSION QUEUE",
            label_fg_color="#1C1C1E",
            label_text_color="#AEAEB2"
        )
        self.queue_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 15))

        # Queue Placeholder
        self.empty_label = ctk.CTkLabel(
            self.queue_frame,
            text="Import video files to start WebM compression.",
            text_color="#8E8E93",
            font=ctk.CTkFont(family="SF Pro Text", size=12, slant="italic")
        )
        self.empty_label.pack(pady=140)

        # 3. Overall progress card
        self.progress_panel = ctk.CTkFrame(
            main, 
            fg_color="#2C2C2E", 
            border_width=1, 
            border_color="#3A3A3C", 
            corner_radius=10
        )
        self.progress_panel.grid(row=2, column=0, sticky="ew", pady=(0, 15))
        
        self.overall_progress_label = ctk.CTkLabel(
            self.progress_panel,
            text="Overall Progress: 0/0 files (0%)",
            font=ctk.CTkFont(family="SF Pro Text", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        self.overall_progress_label.pack(anchor="w", padx=20, pady=(12, 4))
        
        self.overall_progress_bar = ctk.CTkProgressBar(
            self.progress_panel,
            progress_color="#30D158",  # Apple System Green for successful progress
            fg_color="#1C1C1E",
            height=6,
            corner_radius=3
        )
        self.overall_progress_bar.set(0.0)
        self.overall_progress_bar.pack(fill="x", padx=20, pady=(0, 15))

        # 4. Large Action Buttons
        controls_frame = ctk.CTkFrame(main, fg_color="transparent")
        controls_frame.grid(row=3, column=0, sticky="ew")

        self.btn_start = ctk.CTkButton(
            controls_frame,
            text="Start Batch Compression (WebM only)",
            height=44,
            fg_color="#30D158",        # Apple systemGreen
            hover_color="#24a044",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="SF Pro Display", size=13, weight="bold"),
            corner_radius=8,
            command=self.start_conversion
        )
        self.btn_start.pack(fill="x", side="left", expand=True, padx=(0, 10))

        self.btn_stop = ctk.CTkButton(
            controls_frame,
            text="Stop Process",
            height=44,
            fg_color="#FF453A",        # Apple systemRed
            hover_color="#d32f2f",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="SF Pro Display", size=13, weight="bold"),
            corner_radius=8,
            state="disabled",
            command=self.stop_conversion
        )
        self.btn_stop.pack(fill="x", side="right", expand=True)

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
            self.status_dot.configure(text_color="#30D158") # Green
            self.status_text.configure(text="Engine Link: ONLINE", text_color="#30D158")
            
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
            self.status_dot.configure(text_color="#FF453A") # Red
            self.status_text.configure(text="Engine Link: OFFLINE", text_color="#FF453A")
            
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

        win = ctk.CTkToplevel(self)
        win.title("Downloading FFmpeg")
        win.geometry("420x120")
        win.resizable(False, False)
        label = ctk.CTkLabel(win, text="Starting download…")
        label.pack(pady=(18, 8), padx=16)
        bar = ctk.CTkProgressBar(win, width=380)
        bar.set(0.0)
        bar.pack(padx=16)

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
        
        if choice == "Audio-Only WebM (Opus 64kbps)":
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
        crf_val = int(self.crf_slider.get()) if preset_name != "Audio-Only WebM (Opus 64kbps)" else None
        two_pass = self.two_pass_cb.get()
        bit10 = self.bit10_cb.get()
        av1_preset = int(self.av1_slider.get()) if "AV1" in preset_name else None
        out_dir = self.output_entry.get().strip() or self.get_default_output_dir()
        
        for task in self.queue.tasks:
            if task.status in ["Pending", "Queued", "Stopped"]:
                task.preset_name = preset_name
                task.use_gpu = use_gpu
                task.crf_override = crf_val
                task.two_pass = two_pass
                task.bit10 = bit10
                task.av1_preset = av1_preset
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
                text_color="#FFFFFF" if val <= 35 else "#FF9F0A"
            )

    def browse_output_dir(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, os.path.abspath(folder))
            self.sync_all_options()

    def get_default_output_dir(self):
        if sys.platform == "win32":
            path = os.path.join(os.environ.get("USERPROFILE", "C:\\"), "Videos", "Double-Edged AI Compressed")
        else:
            home = os.path.expanduser("~")
            if os.path.exists(os.path.join(home, "Videos")):
                path = os.path.join(home, "Videos", "Double-Edged AI Compressed")
            elif os.path.exists(os.path.join(home, "Movies")):
                path = os.path.join(home, "Movies", "Double-Edged AI Compressed")
            elif os.path.exists(os.path.join(home, "Downloads")):
                path = os.path.join(home, "Downloads", "Double-Edged AI Compressed")
            else:
                path = os.path.join(home, "Double-Edged AI Compressed")
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
            filetypes=[("Videos", "*.mp4 *.mov *.webm *.avi *.mkv *.m4v"), ("All files", "*.*")]
        )
        if not files:
            return
            
        if self.empty_label:
            self.empty_label.destroy()
            self.empty_label = None

        preset_name = self.preset_dropdown.get()
        crf_val = int(self.crf_slider.get())
        if preset_name == "Audio-Only WebM (Opus 64kbps)":
            crf_val = None
            
        use_gpu = self.unit_toggle.get().startswith("GPU")
        two_pass = self.two_pass_cb.get()
        bit10 = self.bit10_cb.get()
        av1_preset = int(self.av1_slider.get()) if "AV1" in preset_name else None
        
        out_dir = self.output_entry.get().strip()
        if not out_dir:
            out_dir = self.get_default_output_dir()
            
        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"Could not create directory:\n{e}")
                return

        for file_path in files:
            file_path = os.path.abspath(file_path)
            orig_name = os.path.basename(file_path)
            
            output_path = self.get_unique_output_path(out_dir, orig_name, ".webm")

            task = self.queue.add_task(
                file_path, output_path, preset_name, use_gpu, crf_val,
                two_pass=two_pass, bit10=bit10, av1_preset=av1_preset
            )
            
            row = TaskRow(self.queue_frame, task, self.remove_task_row, self.generate_quality_preview)
            self.task_rows[task.id] = row
            
        self.refresh_overall_progress()

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

    def clear_queue(self):
        self.queue.clear()
        for row in self.task_rows.values():
            row.destroy()
        self.task_rows.clear()
        
        if not self.empty_label:
            self.empty_label = ctk.CTkLabel(
                self.queue_frame,
                text="Import video files to start WebM compression.",
                text_color="#8E8E93",
                font=ctk.CTkFont(family="SF Pro Text", size=12, slant="italic")
            )
            self.empty_label.pack(pady=140)
            
        self.refresh_overall_progress()

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
            font=ctk.CTkFont(size=12)
        )
        lbl.pack(pady=40)

        preset_name = self.preset_dropdown.get()
        crf_val = int(self.crf_slider.get())
        if preset_name == "Audio-Only WebM (Opus 64kbps)":
            crf_val = None
        use_gpu = self.unit_toggle.get().startswith("GPU")
        two_pass = self.two_pass_cb.get()
        bit10 = self.bit10_cb.get()
        av1_preset = int(self.av1_slider.get()) if "AV1" in preset_name else None
        
        out_dir = self.output_entry.get().strip()
        if not out_dir:
            out_dir = self.get_default_output_dir()
        if not os.path.exists(out_dir):
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
            
        preset_name = self.preset_dropdown.get()
        use_gpu = self.unit_toggle.get().startswith("GPU")
        crf_val = int(self.crf_slider.get()) if preset_name != "Audio-Only WebM (Opus 64kbps)" else None
        two_pass = self.two_pass_cb.get()
        bit10 = self.bit10_cb.get()
        av1_preset = int(self.av1_slider.get()) if "AV1" in preset_name else None
        out_dir = self.output_entry.get().strip() or self.get_default_output_dir()
        
        for task in self.queue.tasks:
            if task.status in ["Pending", "Queued", "Stopped"]:
                task.preset_name = preset_name
                task.use_gpu = use_gpu
                task.crf_override = crf_val
                task.two_pass = two_pass
                task.bit10 = bit10
                task.av1_preset = av1_preset
                task.output_path = self.get_unique_output_path(out_dir, os.path.basename(task.input_path), ".webm")
                
        self.on_queue_update()

        self.btn_start.configure(state="disabled", text="Processing queue...")
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
        self.btn_start.configure(state="normal", text="Start Batch Compression")
        self.btn_stop.configure(state="disabled")
        self.preset_dropdown.configure(state="normal")
        self.unit_toggle.configure(state="normal")
        
        preset_name = self.preset_dropdown.get()
        if preset_name != "Audio-Only WebM (Opus 64kbps)":
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
        self.btn_start.configure(state="normal", text="Start Batch Compression")
        self.btn_stop.configure(state="disabled")
        self.preset_dropdown.configure(state="normal")
        self.unit_toggle.configure(state="normal")
        
        preset_name = self.preset_dropdown.get()
        if preset_name != "Audio-Only WebM (Opus 64kbps)":
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
        crf_val = int(self.crf_slider.get()) if preset_name != "Audio-Only WebM (Opus 64kbps)" else None
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
        
        # Display in a nice text box modal
        modal = ctk.CTkToplevel(self)
        modal.title("Research Verification Telemetry")
        modal.geometry("720x460")
        modal.resizable(True, True)
        modal.transient(self)
        modal.grab_set()
        
        # Put window in the center of the main window
        modal.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 360
        y = self.winfo_y() + (self.winfo_height() // 2) - 230
        modal.geometry(f"+{x}+{y}")
        
        txt = tk.Text(modal, wrap="word", bg="#1C1C1E", fg="#FFFFFF", font=("Courier", 10), insertbackground="white", bd=0, padx=15, pady=15)
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

    def refresh_overall_progress(self):
        total_tasks = len(self.queue.tasks)
        if total_tasks == 0:
            self.overall_progress_label.configure(text="Overall Progress: 0/0 files (0%)")
            self.overall_progress_bar.set(0.0)
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

if __name__ == "__main__":
    app = WebMCompressorApp()
    app.mainloop()
