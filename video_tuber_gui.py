import os
import shutil
import subprocess
import json
import threading
import time
from collections import deque
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import simpledialog
from tkinter import filedialog
from tkinter.scrolledtext import ScrolledText

import midi_config as midi_cfg
import midi_reader as midi_reader
import video_tuber as vt


class VideoTuberGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video Tuber GUI")
        self.geometry("820x830")
        self.resizable(False, False)

        self._engine_thread = None
        self._engine = vt.VideoTuberEngine()
        self._midi_wait_thread = None
        self._midi_waiting = False
        self._midi_led = midi_reader.MidiLedController()
        self._midi_reader_runner = None
        self._midi_reader_running = False
        self._mic_level = 0.0
        self._mic_level_decay = 0.9
        self._mic_test_enabled = False
        self._mic_avg = 0.0
        self._mic_avg_window = 0.5
        self._mic_samples = deque()

        self._build_ui()
        self._ui_tick()

    def _build_ui(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load", command=self.load_gui_settings)
        file_menu.add_command(label="Save", command=self.save_gui_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Load Backup", command=self.load_gui_settings_backup)
        file_menu.add_command(label="Save Backup", command=self.save_gui_settings_backup)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)

        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True)

        main_tab = ttk.Frame(notebook, padding=8)
        notebook.add(main_tab, text="Video")

        midi_tab = ttk.Frame(notebook, padding=8)
        notebook.add(midi_tab, text="MIDI")

        self._build_midi_tab(midi_tab)

        left = ttk.Frame(main_tab)
        left.pack(side=tk.LEFT, fill=tk.Y)

        right = ttk.Frame(main_tab)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="Stopped")
        self.state_var = tk.StringVar(value="-")

        status_row = ttk.Frame(left)
        status_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(status_row, text="Status:").pack(side=tk.LEFT)
        ttk.Label(status_row, textvariable=self.status_var).pack(side=tk.LEFT, padx=(6, 0))

        state_row = ttk.Frame(left)
        state_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(state_row, text="State:").pack(side=tk.LEFT)
        ttk.Label(state_row, textvariable=self.state_var).pack(side=tk.LEFT, padx=(6, 0))

        midi_state_row = ttk.Frame(left)
        midi_state_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(midi_state_row, text="MIDI state:").pack(side=tk.LEFT)
        self.midi_state_label = tk.Label(midi_state_row, text="Reader Off", fg="red")
        self.midi_state_label.pack(side=tk.LEFT, padx=(6, 0))
        self._sync_midi_status_labels(False)

        btn_row = ttk.Frame(left)
        btn_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Button(btn_row, text="Start", command=self.start_engine).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Stop", command=self.stop_engine).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btn_row, text="Reset", command=self.send_reset).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 8))
        ttk.Label(left, text="Configuration").pack(anchor=tk.W, pady=(0, 6))

        self.entries = {}

        window_box = ttk.LabelFrame(left, text="Window", padding=8)
        window_box.pack(fill=tk.X)
        self._add_entry(window_box, "Window Name", "window_name", vt.WINDOW_NAME)
        self._add_entry(window_box, "Width", "screen_width", str(vt.SCREEN_WIDTH))
        self._add_entry(window_box, "Height", "screen_height", str(vt.SCREEN_HEIGHT))

        mic_box = ttk.LabelFrame(left, text="Microphone", padding=8)
        mic_box.pack(fill=tk.X, pady=(8, 0))
        mic_row = ttk.Frame(mic_box)
        mic_row.pack(fill=tk.X, pady=2)
        ttk.Label(mic_row, text="Mic Device", width=14).pack(side=tk.LEFT)
        self.mic_device_var = tk.StringVar(value="")
        self.mic_device_combo = ttk.Combobox(
            mic_row, textvariable=self.mic_device_var, state="readonly"
        )
        self.mic_device_combo.configure(width=45)
        self.mic_device_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        mic_refresh_row = ttk.Frame(mic_box)
        mic_refresh_row.pack(fill=tk.X, pady=(4, 2))
        ttk.Button(mic_refresh_row, text="Refresh", command=self.refresh_mic_devices).pack(
            side=tk.LEFT
        )
        self._add_entry(mic_box, "Noise Thresh", "noise_thresh", str(vt.AUDIO_THRESHOLD_NOISE))
        self._add_entry(mic_box, "Noise Dur", "noise_dur", str(vt.NOISE_DURATION))
        self._add_entry(mic_box, "Silence Thresh", "silence_thresh", str(vt.AUDIO_THRESHOLD_SILENCE))
        self._add_entry(mic_box, "Silence Dur", "silence_dur", str(vt.SILENCE_DURATION))

        mic_test_row = ttk.Frame(mic_box)
        mic_test_row.pack(fill=tk.X, pady=(6, 0))
        self.mic_test_btn = ttk.Button(
            mic_test_row, text="Enable microphone test", command=self.toggle_mic_test
        )
        self.mic_test_btn.pack(side=tk.LEFT)

        mic_level_row = ttk.Frame(mic_box)
        mic_level_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(mic_level_row, text="Mic Level", width=14).pack(side=tk.LEFT)
        self.mic_level_bar = ttk.Progressbar(
            mic_level_row, orient=tk.HORIZONTAL, length=200, mode="determinate", maximum=1.0
        )
        self.mic_level_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        mic_avg_row = ttk.Frame(mic_box)
        mic_avg_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(mic_avg_row, text="Average volume", width=14).pack(side=tk.LEFT)
        self.mic_avg_var = tk.StringVar(value="0.00")
        self.mic_avg_entry = ttk.Entry(mic_avg_row, textvariable=self.mic_avg_var, state="disabled", width=8)
        self.mic_avg_entry.pack(side=tk.LEFT)

        flags_box = ttk.LabelFrame(left, text="Filters", padding=8)
        flags_box.pack(fill=tk.X, pady=(12, 0))

        self.glitch_var = tk.BooleanVar(value=vt.GLITCH_ENABLE)
        self.vhs_var = tk.BooleanVar(value=vt.ENABLE_VHS)
        self.scanline_var = tk.BooleanVar(value=vt.SCANLINE_ENABLE)
        self.ca_var = tk.BooleanVar(value=vt.ENABLE_CA)

        ttk.Checkbutton(flags_box, text="Glitch", variable=self.glitch_var).pack(anchor=tk.W)
        ttk.Checkbutton(flags_box, text="VHS", variable=self.vhs_var).pack(anchor=tk.W)
        ttk.Checkbutton(flags_box, text="Scanlines", variable=self.scanline_var).pack(anchor=tk.W)
        ttk.Checkbutton(flags_box, text="Chromatic Aberration", variable=self.ca_var).pack(anchor=tk.W)

        ttk.Button(left, text="Apply Config", command=self.apply_config).pack(fill=tk.X, pady=(12, 0))
        ttk.Button(left, text="Reload Videos", command=self.reload_videos).pack(fill=tk.X, pady=(6, 0))

        log_label = ttk.Label(right, text="Logs")
        log_label.pack(anchor=tk.W)

        self.log = ScrolledText(right, height=20, state=tk.DISABLED, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True)

    def _build_midi_tab(self, parent):
        header = ttk.Label(parent, text="MIDI")
        header.pack(anchor=tk.W)

        device_row = ttk.Frame(parent)
        device_row.pack(fill=tk.X, pady=(6, 4))
        ttk.Label(device_row, text="Device").pack(side=tk.LEFT)

        self.midi_device_var = tk.StringVar(value="")
        self.midi_device_combo = ttk.Combobox(
            device_row,
            textvariable=self.midi_device_var,
            state="readonly",
        )
        self.midi_device_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        ttk.Button(device_row, text="Refresh Devices", command=self.refresh_midi_devices).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        reader_label = ttk.Label(parent, text="MIDI Reader")
        reader_label.pack(anchor=tk.W)

        reader_row = ttk.Frame(parent)
        reader_row.pack(fill=tk.X, pady=(6, 4))
        self.reader_launch_btn = ttk.Button(
            reader_row, text="Launch MIDI Reader", command=self.launch_midi_reader
        )
        self.reader_launch_btn.pack(side=tk.LEFT)
        ttk.Button(reader_row, text="Reload Config", command=self.reload_midi_reader_config).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        self.reader_status_label = tk.Label(reader_row, text="Reader Off", fg="red")
        self.reader_status_label.pack(side=tk.LEFT, padx=(12, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.X, pady=(6, 8))

        self.midi_config_var = tk.StringVar(value="")
        self.midi_combo = ttk.Combobox(
            list_frame,
            textvariable=self.midi_config_var,
            state="readonly",
        )
        self.midi_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X)

        ttk.Button(btn_row, text="Refresh", command=self.refresh_midi_files).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Open Selected", command=self.open_selected_midi_file).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(btn_row, text="Rename", command=self.rename_midi_file).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btn_row, text="Duplicate", command=self.duplicate_midi_file).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btn_row, text="New", command=self.new_midi_file).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btn_row, text="Delete", command=self.delete_midi_file).pack(side=tk.LEFT, padx=(6, 0))

        launch_row = ttk.Frame(parent)
        launch_row.pack(fill=tk.X, pady=(6, 0))
        self.add_button_btn = ttk.Button(launch_row, text="Add Button", command=self.add_midi_button)
        self.add_button_btn.pack(side=tk.LEFT)
        self.save_config_btn = ttk.Button(launch_row, text="Save Config", command=self.save_midi_config)
        self.save_config_btn.pack(side=tk.LEFT, padx=(6, 0))

        status_row = ttk.Frame(parent)
        status_row.pack(anchor=tk.W, pady=(8, 0))
        self.loaded_file_label = tk.Label(status_row, text="No file loaded", fg="black")
        self.loaded_file_label.pack(side=tk.LEFT)
        self.save_status_label = tk.Label(status_row, text="", fg="green")
        self.save_status_label.pack(side=tk.LEFT, padx=(12, 0))

        mappings_label = ttk.Label(parent, text="Mappings")
        mappings_label.pack(anchor=tk.W, pady=(10, 2))

        mappings_container = ttk.Frame(parent)
        mappings_container.pack(fill=tk.BOTH, expand=True)

        self.midi_canvas = tk.Canvas(mappings_container, highlightthickness=0)
        self.midi_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        midi_scroll = ttk.Scrollbar(mappings_container, orient=tk.VERTICAL, command=self.midi_canvas.yview)
        midi_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.midi_canvas.configure(yscrollcommand=midi_scroll.set)

        self.midi_rows_frame = ttk.Frame(self.midi_canvas)
        self.midi_canvas.create_window((0, 0), window=self.midi_rows_frame, anchor="nw")

        self.midi_rows_frame.bind(
            "<Configure>",
            lambda event: self.midi_canvas.configure(scrollregion=self.midi_canvas.bbox("all")),
        )

        header = ttk.Frame(self.midi_rows_frame)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Note", width=8).pack(side=tk.LEFT)
        ttk.Label(header, text="Tag", width=24).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(header, text="Type", width=16).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(header, text="Color", width=8).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(header, text="").pack(side=tk.LEFT, padx=(6, 0))

        self.midi_rows = []
        self.current_midi_path = None
        self._set_midi_actions_enabled(False)
        self._set_save_status(saved=None)
        self._set_loaded_file_label("")

        self.refresh_midi_devices()
        self.refresh_midi_files()
        self.refresh_mic_devices()

    def _add_entry(self, parent, label, key, default_value):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=14).pack(side=tk.LEFT)
        entry = ttk.Entry(row)
        entry.insert(0, default_value)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entries[key] = entry

    def _log(self, message):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _ui_tick(self):
        self._drain_logs()
        self._update_state_label()
        self._update_mic_level()
        self.after(100, self._ui_tick)

    def _drain_logs(self):
        while not vt.log_queue.empty():
            args, kwargs = vt.log_queue.get()
            try:
                message = " ".join(str(a) for a in args)
            except Exception:
                message = str(args)
            self._log(message)

    def _update_state_label(self):
        if self._engine.sm is not None:
            self.state_var.set(self._engine.sm.current_state.name)
        else:
            self.state_var.set("-")

    def _update_mic_level(self):
        if not self._mic_test_enabled:
            self.mic_level_bar["value"] = 0.0
            self.mic_avg_var.set("0.00")
            self._mic_samples.clear()
            return
        # Drain audio queue and update a simple peak-hold meter with decay.
        try:
            while True:
                item = vt.audio_queue.get_nowait()
                if isinstance(item, tuple):
                    ts, vol = item
                else:
                    ts, vol = (time.time(), item)
                if vol > self._mic_level:
                    self._mic_level = vol
                self._mic_samples.append((ts, vol))
        except Exception:
            pass

        # Apply decay so the bar falls smoothly.
        self._mic_level *= self._mic_level_decay

        # Normalize roughly into 0..1 range
        level = min(max(self._mic_level, 0.0), 1.0)
        self.mic_level_bar["value"] = level
        now = time.time()
        cutoff = now - self._mic_avg_window
        while self._mic_samples and self._mic_samples[0][0] < cutoff:
            self._mic_samples.popleft()
        if self._mic_samples:
            self._mic_avg = sum(v for _, v in self._mic_samples) / len(self._mic_samples)
        else:
            self._mic_avg = 0.0
        self.mic_avg_var.set(f"{self._mic_avg:.2f}")

    def toggle_mic_test(self):
        self._mic_test_enabled = not self._mic_test_enabled
        if self._mic_test_enabled:
            self.mic_test_btn.configure(text="Disable microphone test")
        else:
            self.mic_test_btn.configure(text="Enable microphone test")
            self._mic_level = 0.0
            self._mic_avg = 0.0
            self._mic_samples.clear()

    def apply_config(self):
        try:
            vt.WINDOW_NAME = self.entries["window_name"].get().strip() or vt.WINDOW_NAME
            vt.SCREEN_WIDTH = int(self.entries["screen_width"].get())
            vt.SCREEN_HEIGHT = int(self.entries["screen_height"].get())
            vt.MIC_DEVICE_INDEX = self._get_selected_mic_index()
            vt.AUDIO_THRESHOLD_NOISE = float(self.entries["noise_thresh"].get())
            vt.NOISE_DURATION = float(self.entries["noise_dur"].get())
            vt.AUDIO_THRESHOLD_SILENCE = float(self.entries["silence_thresh"].get())
            vt.SILENCE_DURATION = float(self.entries["silence_dur"].get())
            vt.GLITCH_ENABLE = bool(self.glitch_var.get())
            vt.ENABLE_VHS = bool(self.vhs_var.get())
            vt.SCANLINE_ENABLE = bool(self.scanline_var.get())
            vt.ENABLE_CA = bool(self.ca_var.get())

            self._refresh_mic_transitions()
            self._log("Config applied")
        except Exception as exc:
            self._log(f"Config error: {exc}")

    def _refresh_mic_transitions(self):
        for state in vt.STATES.values():
            new_transitions = []
            for next_state, rule_name, config in state.transitions:
                if rule_name == "MIC" and next_state == "Talking":
                    new_transitions.append(
                        ("Talking", "MIC", (vt.AUDIO_THRESHOLD_NOISE, vt.NOISE_DURATION, "POSITIVE"))
                    )
                elif rule_name == "MIC" and next_state == "Idle":
                    new_transitions.append(
                        ("Idle", "MIC", (vt.AUDIO_THRESHOLD_SILENCE, vt.SILENCE_DURATION, "NEGATIVE"))
                    )
                else:
                    new_transitions.append((next_state, rule_name, config))
            state.transitions = new_transitions

    def reload_videos(self):
        vt.auto_load_videos_into_states(vt.STATES)
        self._log("Videos reloaded")

    def send_reset(self):
        try:
            vt.operation_requests.put("Reset")
            self._log("Reset requested")
        except Exception as exc:
            self._log(f"Reset error: {exc}")

    def refresh_midi_files(self):
        folder = os.path.join(os.getcwd(), "midi_configs")
        if not os.path.isdir(folder):
            self.midi_combo["values"] = []
            self.midi_config_var.set("")
            return
        files = [f for f in os.listdir(folder) if f.lower().endswith(".json")]
        files = sorted(files)
        self.midi_combo["values"] = files
        if files:
            current = self.midi_config_var.get()
            if current not in files:
                self.midi_config_var.set(files[0])
        else:
            self.midi_config_var.set("")

    def refresh_midi_devices(self):
        try:
            import mido
        except Exception as exc:
            self._log(f"MIDI device list error: {exc}")
            self.midi_device_combo["values"] = []
            self.midi_device_var.set("")
            return

        devices = list(mido.get_input_names())
        self.midi_device_combo["values"] = devices
        if devices:
            current = self.midi_device_var.get()
            if current not in devices:
                self.midi_device_var.set(devices[0])
        else:
            self.midi_device_var.set("")

    def refresh_mic_devices(self):
        if not hasattr(self, "mic_device_combo"):
            return
        try:
            import sounddevice as sd
        except Exception as exc:
            self._log(f"Mic device list error: {exc}")
            self.mic_device_combo["values"] = []
            self.mic_device_var.set("")
            return

        devices = []
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                devices.append(f"{idx}: {dev.get('name', '')}")

        self.mic_device_combo["values"] = devices
        if devices:
            selected = f"{vt.MIC_DEVICE_INDEX}:"
            match = None
            for item in devices:
                if item.startswith(selected):
                    match = item
                    break
            self.mic_device_var.set(match or devices[0])
        else:
            self.mic_device_var.set("")

    def _get_selected_mic_index(self):
        text = self.mic_device_var.get().strip()
        if not text:
            return vt.MIC_DEVICE_INDEX
        try:
            return int(text.split(":", 1)[0])
        except Exception:
            return vt.MIC_DEVICE_INDEX

    def open_selected_midi_file(self):
        folder = os.path.join(os.getcwd(), "midi_configs")
        if not os.path.isdir(folder):
            self._log("midi_configs folder not found")
            return
        filename = self.midi_config_var.get().strip()
        if not filename:
            self._log("No MIDI config selected")
            return
        path = os.path.join(folder, filename)
        try:
            device_name, buttons = self._load_midi_config_into_form(path)
            self.current_midi_path = path
            self._set_midi_actions_enabled(True)
            active_device = device_name or self.midi_device_var.get().strip()
            if active_device:
                ok = self._midi_led.apply_config(active_device, buttons)
                if not ok:
                    self._log("No MIDI output device found for selected or config device")
            else:
                self._log("No MIDI device selected; LEDs not updated")
            self._set_save_status(saved=True)
            self._set_loaded_file_label(filename)
            self._log(f"Loaded {filename}")
        except Exception as exc:
            self._log(f"Load failed: {exc}")

    def launch_midi_config(self):
        try:
            args = ["python", "midi_config.py"]
            selected_device = self.midi_device_var.get().strip()
            if selected_device:
                args.append(selected_device)
            subprocess.Popen(
                args,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._log("Launched MIDI config tool")
        except Exception as exc:
            self._log(f"Launch failed: {exc}")

    def launch_midi_reader(self):
        if self._midi_reader_running:
            if self._midi_reader_runner:
                self._midi_reader_runner.stop()
            self._midi_reader_running = False
            self._set_midi_reader_button_text()
            self._set_midi_reader_status(False)
            self._log("MIDI reader stopped")
            return

        selected = self.midi_config_var.get().strip()
        if not selected:
            self._log("Select a MIDI config from the dropdown first")
            return

        config_path = os.path.join(os.getcwd(), "midi_configs", selected)
        if not os.path.exists(config_path):
            self._log("Selected MIDI config file not found")
            return

        self._midi_reader_runner = midi_reader.MidiReaderRunner(
            config_path=config_path,
            message_queue=vt.video_requests,
            operation_queue=vt.operation_requests,
            operation_commands=vt.OPERATION_COMMANDS,
            log_fn=self._log,
        )
        started = self._midi_reader_runner.start()
        if started:
            self._midi_reader_running = True
            self._set_midi_reader_button_text()
            self._set_midi_reader_status(True)
            self._log("MIDI reader started")
        else:
            self._log("MIDI reader already running")

    def reload_midi_reader_config(self):
        if not self._midi_reader_running or not self._midi_reader_runner:
            self._log("MIDI reader is not running")
            return

        selected = self.midi_config_var.get().strip()
        if not selected:
            self._log("Select a MIDI config from the dropdown first")
            return

        config_path = os.path.join(os.getcwd(), "midi_configs", selected)
        if not os.path.exists(config_path):
            self._log("Selected MIDI config file not found")
            return

        self._midi_reader_runner.reload_config(config_path)
        self._log("MIDI reader config reloaded")

    def add_midi_button(self):
        if self._midi_waiting:
            self._log("Already waiting for MIDI input")
            return
        if not self.current_midi_path:
            self._log("Open a MIDI config first")
            return
        device_name = self.midi_device_var.get().strip()
        if not device_name:
            self._log("Select a MIDI device first")
            return

        self._midi_waiting = True
        self._log("Waiting for MIDI button press...")
        self._midi_wait_thread = threading.Thread(
            target=self._wait_for_midi_press, args=(device_name,), daemon=True
        )
        self._midi_wait_thread.start()

    def _wait_for_midi_press(self, device_name):
        try:
            import mido
        except Exception as exc:
            self.after(0, lambda: self._log(f"MIDI input error: {exc}"))
            self._midi_waiting = False
            return

        try:
            with mido.open_input(device_name) as inport:
                while True:
                    for msg in inport.iter_pending():
                        if msg.type == "note_on" and msg.velocity > 0:
                            note = msg.note
                            self.after(0, lambda n=note: self._add_midi_note_to_config(n))
                            self._midi_waiting = False
                            return
                    if not self._midi_waiting:
                        return
        except Exception as exc:
            self.after(0, lambda: self._log(f"MIDI input error: {exc}"))
            self._midi_waiting = False

    def _add_midi_note_to_config(self, note):
        path = self.current_midi_path
        if not path or not os.path.exists(path):
            self._log("Config file not found")
            return

        data = self._read_midi_json(path)
        buttons = data.get("buttons", {})

        note_key = str(note)
        if note_key in buttons:
            self._log(f"Note {note} already exists")
            return

        buttons[note_key] = {
            "tag": "",
            "type": midi_cfg.ALLOWED_TYPES[0] if midi_cfg.ALLOWED_TYPES else "",
            "color": midi_cfg.DEFAULT_COLOR,
        }
        data["buttons"] = buttons
        self._write_midi_json(path, data)
        self._add_midi_row(note, "", buttons[note_key]["type"], buttons[note_key]["color"])
        self._set_led(note, buttons[note_key]["color"])
        self._set_save_status(saved=False)
        self._log(f"Added note {note}")

    def _read_midi_json(self, path):
        return midi_cfg.MidiConfigManager.load(path)

    def _write_midi_json(self, path, data):
        midi_cfg.MidiConfigManager.save(path, data)

    def save_midi_config(self):
        if not self.current_midi_path:
            self._log("Open a MIDI config first")
            return
        if not os.path.exists(self.current_midi_path):
            self._log("Config file not found")
            return

        data = self._read_midi_json(self.current_midi_path)
        buttons = {}
        for row in self.midi_rows:
            try:
                note = int(row["note"])
            except Exception:
                continue
            tag = row["tag"].get().strip()
            btn_type = row["type"].get().strip()
            if btn_type not in midi_cfg.ALLOWED_TYPES:
                btn_type = midi_cfg.ALLOWED_TYPES[0] if midi_cfg.ALLOWED_TYPES else ""
            try:
                color_index = int(row["color"].get())
            except Exception:
                color_index = 0
            color_value = midi_cfg.MidiConfigManager.color_index_to_velocity(color_index)
            buttons[str(note)] = {"tag": tag, "type": btn_type, "color": color_value}

        data["buttons"] = buttons
        if "schema_version" not in data:
            data["schema_version"] = 1
        if not data.get("device_name"):
            data["device_name"] = self.midi_device_var.get().strip()

        try:
            self._write_midi_json(self.current_midi_path, data)
            self._set_save_status(saved=True)
            self._log("Config saved")
        except Exception as exc:
            self._log(f"Save failed: {exc}")

    def _clear_midi_rows(self):
        for row in self.midi_rows:
            try:
                row["frame"].destroy()
            except Exception:
                pass
        self.midi_rows = []

    def _load_midi_config_into_form(self, path):
        data = midi_cfg.MidiConfigManager.load(path)

        device_name = data.get("device_name", "")
        buttons_raw = data.get("buttons", {})
        entries = []
        buttons_for_leds = {}

        if isinstance(buttons_raw, list):
            for item in buttons_raw:
                try:
                    note = int(item.get("note"))
                    tag = item.get("tag", "")
                    btn_type = item.get("type", "")
                    color = item.get("color", midi_cfg.DEFAULT_COLOR)
                    entries.append((note, tag, btn_type, color))
                    buttons_for_leds[note] = {"tag": tag, "type": btn_type, "color": color}
                except Exception:
                    continue
        elif isinstance(buttons_raw, dict):
            for note_str, payload in buttons_raw.items():
                try:
                    note = int(note_str)
                    tag = payload.get("tag", "")
                    btn_type = payload.get("type", "")
                    color = payload.get("color", midi_cfg.DEFAULT_COLOR)
                    entries.append((note, tag, btn_type, color))
                    buttons_for_leds[note] = {"tag": tag, "type": btn_type, "color": color}
                except Exception:
                    continue

        entries.sort(key=lambda item: item[0])
        self._clear_midi_rows()

        for note, tag, btn_type, color in entries:
            self._add_midi_row(note, tag, btn_type, color)

        if device_name:
            self.midi_device_var.set(device_name)

        return device_name, buttons_for_leds

    def _set_led(self, note, velocity):
        device_name = self.midi_device_var.get().strip()
        try:
            ok = self._midi_led.set_led(device_name, note, velocity)
            if not ok:
                self._log(f"No MIDI output device found for '{device_name}'")
        except Exception as exc:
            self._log(f"MIDI LED error: {exc}")

    def _add_midi_row(self, note, tag, btn_type, color):
        row = ttk.Frame(self.midi_rows_frame)
        row.pack(fill=tk.X, pady=1)

        ttk.Label(row, text=str(note), width=8).pack(side=tk.LEFT)

        tag_entry = ttk.Entry(row, width=24)
        tag_entry.insert(0, tag)
        tag_entry.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)
        tag_entry.bind("<KeyRelease>", lambda event: self._set_save_status(saved=False))

        type_combo = ttk.Combobox(
            row,
            values=list(midi_cfg.ALLOWED_TYPES),
            state="readonly",
            width=14,
        )
        if btn_type in midi_cfg.ALLOWED_TYPES:
            type_combo.set(btn_type)
        elif midi_cfg.ALLOWED_TYPES:
            type_combo.set(midi_cfg.ALLOWED_TYPES[0])
        type_combo.pack(side=tk.LEFT, padx=(6, 0))
        type_combo.bind("<<ComboboxSelected>>", lambda event: self._set_save_status(saved=False))

        color_index = midi_cfg.MidiConfigManager.velocity_to_color_index(color)
        color_var = tk.IntVar(value=color_index)
        color_scale = tk.Scale(
            row,
            from_=0,
            to=len(midi_cfg.LAUNCHPAD_S_COLOR_VALUES) - 1,
            orient=tk.HORIZONTAL,
            length=120,
            variable=color_var,
            showvalue=True,
            command=lambda _v, n=note: self._on_color_change(n),
        )
        color_scale.pack(side=tk.LEFT, padx=(6, 0))

        delete_btn = ttk.Button(row, text="Delete")
        delete_btn.pack(side=tk.LEFT, padx=(6, 0))

        row_info = {
            "frame": row,
            "note": note,
            "tag": tag_entry,
            "type": type_combo,
            "color": color_var,
        }
        delete_btn.configure(command=lambda r=row_info: self._delete_midi_row(r))

        self.midi_rows.append(row_info)

    def _delete_midi_row(self, row_info):
        try:
            row_info["frame"].destroy()
        except Exception:
            pass
        self.midi_rows = [r for r in self.midi_rows if r is not row_info]
        try:
            self._set_led(row_info["note"], 0)
        except Exception:
            pass
        self._set_save_status(saved=False)

    def rename_midi_file(self):
        folder = os.path.join(os.getcwd(), "midi_configs")
        filename = self.midi_config_var.get().strip()
        if not filename:
            self._log("No MIDI config selected")
            return
        if not os.path.isdir(folder):
            self._log("midi_configs folder not found")
            return

        current_path = os.path.join(folder, filename)
        new_name = simpledialog.askstring(
            "Rename MIDI Config",
            "New file name (without extension):",
            parent=self,
        )
        if not new_name:
            return

        new_name = new_name.strip()
        if not new_name:
            self._log("Rename cancelled")
            return
        new_filename = f"{new_name}.json"
        new_path = os.path.join(folder, new_filename)
        if os.path.exists(new_path):
            messagebox.showerror("Rename", "File already exists.")
            return

        try:
            os.rename(current_path, new_path)
            self.refresh_midi_files()
            self.midi_config_var.set(new_filename)
            self.current_midi_path = new_path
            self._set_loaded_file_label(new_filename)
            self._log(f"Renamed to {new_filename}")
        except Exception as exc:
            self._log(f"Rename failed: {exc}")

    def duplicate_midi_file(self):
        folder = os.path.join(os.getcwd(), "midi_configs")
        filename = self.midi_config_var.get().strip()
        if not filename:
            self._log("No MIDI config selected")
            return
        if not os.path.isdir(folder):
            self._log("midi_configs folder not found")
            return

        src_path = os.path.join(folder, filename)
        new_name = simpledialog.askstring(
            "Duplicate MIDI Config",
            "New file name (without extension):",
            parent=self,
        )
        if not new_name:
            return

        new_name = new_name.strip()
        if not new_name:
            self._log("Duplicate cancelled")
            return
        new_filename = f"{new_name}.json"
        dst_path = os.path.join(folder, new_filename)
        if os.path.exists(dst_path):
            messagebox.showerror("Duplicate", "File already exists.")
            return

        try:
            shutil.copy2(src_path, dst_path)
            self.refresh_midi_files()
            self.midi_config_var.set(new_filename)
            self.current_midi_path = dst_path
            self._set_loaded_file_label(new_filename)
            self._log(f"Duplicated to {new_filename}")
        except Exception as exc:
            self._log(f"Duplicate failed: {exc}")

    def delete_midi_file(self):
        folder = os.path.join(os.getcwd(), "midi_configs")
        filename = self.midi_config_var.get().strip()
        if not filename:
            self._log("No MIDI config selected")
            return
        if not os.path.isdir(folder):
            self._log("midi_configs folder not found")
            return

        path = os.path.join(folder, filename)
        confirm = messagebox.askyesno(
            "Delete MIDI Config",
            f"Delete {filename}?",
            parent=self,
        )
        if not confirm:
            return

        try:
            os.remove(path)
            self.current_midi_path = None
            self._clear_midi_rows()
            self.refresh_midi_files()
            self._set_midi_actions_enabled(False)
            self._set_save_status(saved=None)
            self._set_loaded_file_label("")
            self._log(f"Deleted {filename}")
        except Exception as exc:
            self._log(f"Delete failed: {exc}")

    def new_midi_file(self):
        folder = os.path.join(os.getcwd(), "midi_configs")
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)

        new_name = simpledialog.askstring(
            "New MIDI Config",
            "New file name (without extension):",
            parent=self,
        )
        if not new_name:
            return

        new_name = new_name.strip()
        if not new_name:
            self._log("Create cancelled")
            return
        new_filename = f"{new_name}.json"
        new_path = os.path.join(folder, new_filename)
        if os.path.exists(new_path):
            messagebox.showerror("New MIDI Config", "File already exists.")
            return

        try:
            data = midi_cfg.MidiConfigManager.new_config(self.midi_device_var.get().strip())
            midi_cfg.MidiConfigManager.save(new_path, data)
            self.refresh_midi_files()
            self.midi_config_var.set(new_filename)
            self.current_midi_path = new_path
            self._clear_midi_rows()
            self._set_midi_actions_enabled(True)
            self._set_save_status(saved=True)
            self._set_loaded_file_label(new_filename)
            self._log(f"Created {new_filename}")
        except Exception as exc:
            self._log(f"Create failed: {exc}")

    def _set_midi_actions_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.add_button_btn.configure(state=state)
        self.save_config_btn.configure(state=state)

    def _set_midi_reader_button_text(self):
        if self._midi_reader_running:
            self.reader_launch_btn.configure(text="Stop MIDI Reader")
        else:
            self.reader_launch_btn.configure(text="Launch MIDI Reader")

    def _set_midi_reader_status(self, running):
        self._sync_midi_status_labels(running)

    def _sync_midi_status_labels(self, running):
        if running:
            if hasattr(self, "reader_status_label"):
                self.reader_status_label.configure(text="Reader Running", fg="green")
            if hasattr(self, "midi_state_label"):
                self.midi_state_label.configure(text="Reader Running", fg="green")
        else:
            if hasattr(self, "reader_status_label"):
                self.reader_status_label.configure(text="Reader Off", fg="red")
            if hasattr(self, "midi_state_label"):
                self.midi_state_label.configure(text="Reader Off", fg="red")

    def _set_save_status(self, saved):
        if saved is None:
            self.save_status_label.configure(text="", fg="green")
        elif saved:
            self.save_status_label.configure(text="Saved", fg="green")
        else:
            self.save_status_label.configure(text="Config not saved", fg="red")

    def _on_color_change(self, note):
        self._set_save_status(saved=False)
        try:
            for row in self.midi_rows:
                if row["note"] == note:
                    color_index = int(row["color"].get())
                    color_value = midi_cfg.MidiConfigManager.color_index_to_velocity(color_index)
                    self._set_led(note, color_value)
                    break
        except Exception:
            pass

    def _set_loaded_file_label(self, filename):
        if filename:
            self.loaded_file_label.configure(text=filename)
        else:
            self.loaded_file_label.configure(text="No file loaded")

    def save_gui_settings(self):
        settings = {
            "window_name": self.entries["window_name"].get().strip(),
            "screen_width": self.entries["screen_width"].get().strip(),
            "screen_height": self.entries["screen_height"].get().strip(),
            "mic_device_index": self._get_selected_mic_index(),
            "noise_thresh": self.entries["noise_thresh"].get().strip(),
            "noise_dur": self.entries["noise_dur"].get().strip(),
            "silence_thresh": self.entries["silence_thresh"].get().strip(),
            "silence_dur": self.entries["silence_dur"].get().strip(),
            "filters": {
                "glitch": bool(self.glitch_var.get()),
                "vhs": bool(self.vhs_var.get()),
                "scanlines": bool(self.scanline_var.get()),
                "chromatic": bool(self.ca_var.get()),
            },
            "midi_defaults": {
                "device": self.midi_device_var.get().strip(),
                "config": self.midi_config_var.get().strip(),
            },
        }
        try:
            with open("gui_settings.json", "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
            self._log("GUI settings saved")
        except Exception as exc:
            self._log(f"Save settings failed: {exc}")

    def load_gui_settings(self):
        try:
            with open("gui_settings.json", "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception as exc:
            self._log(f"Load settings failed: {exc}")
            return

        self.entries["window_name"].delete(0, tk.END)
        self.entries["window_name"].insert(0, settings.get("window_name", vt.WINDOW_NAME))

        self.entries["screen_width"].delete(0, tk.END)
        self.entries["screen_width"].insert(0, settings.get("screen_width", vt.SCREEN_WIDTH))

        self.entries["screen_height"].delete(0, tk.END)
        self.entries["screen_height"].insert(0, settings.get("screen_height", vt.SCREEN_HEIGHT))

        self.entries["noise_thresh"].delete(0, tk.END)
        self.entries["noise_thresh"].insert(0, settings.get("noise_thresh", vt.AUDIO_THRESHOLD_NOISE))

        self.entries["noise_dur"].delete(0, tk.END)
        self.entries["noise_dur"].insert(0, settings.get("noise_dur", vt.NOISE_DURATION))

        self.entries["silence_thresh"].delete(0, tk.END)
        self.entries["silence_thresh"].insert(0, settings.get("silence_thresh", vt.AUDIO_THRESHOLD_SILENCE))

        self.entries["silence_dur"].delete(0, tk.END)
        self.entries["silence_dur"].insert(0, settings.get("silence_dur", vt.SILENCE_DURATION))

        self.glitch_var.set(bool(settings.get("filters", {}).get("glitch", vt.GLITCH_ENABLE)))
        self.vhs_var.set(bool(settings.get("filters", {}).get("vhs", vt.ENABLE_VHS)))
        self.scanline_var.set(bool(settings.get("filters", {}).get("scanlines", vt.SCANLINE_ENABLE)))
        self.ca_var.set(bool(settings.get("filters", {}).get("chromatic", vt.ENABLE_CA)))

        self.refresh_mic_devices()
        mic_idx = settings.get("mic_device_index", vt.MIC_DEVICE_INDEX)
        if hasattr(self, "mic_device_combo") and self.mic_device_combo["values"]:
            match = None
            for item in self.mic_device_combo["values"]:
                if item.startswith(f"{mic_idx}:"):
                    match = item
                    break
            if match:
                self.mic_device_var.set(match)

        self.refresh_midi_devices()
        midi_defaults = settings.get("midi_defaults", {})
        midi_device = midi_defaults.get("device", "")
        if midi_device:
            self.midi_device_var.set(midi_device)

        self.refresh_midi_files()
        midi_config = midi_defaults.get("config", "")
        if midi_config and midi_config in self.midi_combo["values"]:
            self.midi_config_var.set(midi_config)

        self._log("GUI settings loaded")

    def save_gui_settings_backup(self):
        path = filedialog.asksaveasfilename(
            title="Save GUI Settings",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            settings = {
                "window_name": self.entries["window_name"].get().strip(),
                "screen_width": self.entries["screen_width"].get().strip(),
                "screen_height": self.entries["screen_height"].get().strip(),
                "mic_device_index": self._get_selected_mic_index(),
                "noise_thresh": self.entries["noise_thresh"].get().strip(),
                "noise_dur": self.entries["noise_dur"].get().strip(),
                "silence_thresh": self.entries["silence_thresh"].get().strip(),
                "silence_dur": self.entries["silence_dur"].get().strip(),
                "filters": {
                    "glitch": bool(self.glitch_var.get()),
                    "vhs": bool(self.vhs_var.get()),
                    "scanlines": bool(self.scanline_var.get()),
                    "chromatic": bool(self.ca_var.get()),
                },
                "midi_defaults": {
                    "device": self.midi_device_var.get().strip(),
                    "config": self.midi_config_var.get().strip(),
                },
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
            self._log("GUI settings backup saved")
        except Exception as exc:
            self._log(f"Save backup failed: {exc}")

    def load_gui_settings_backup(self):
        path = filedialog.askopenfilename(
            title="Load GUI Settings",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception as exc:
            self._log(f"Load backup failed: {exc}")
            return

        self.entries["window_name"].delete(0, tk.END)
        self.entries["window_name"].insert(0, settings.get("window_name", vt.WINDOW_NAME))

        self.entries["screen_width"].delete(0, tk.END)
        self.entries["screen_width"].insert(0, settings.get("screen_width", vt.SCREEN_WIDTH))

        self.entries["screen_height"].delete(0, tk.END)
        self.entries["screen_height"].insert(0, settings.get("screen_height", vt.SCREEN_HEIGHT))

        self.entries["noise_thresh"].delete(0, tk.END)
        self.entries["noise_thresh"].insert(0, settings.get("noise_thresh", vt.AUDIO_THRESHOLD_NOISE))

        self.entries["noise_dur"].delete(0, tk.END)
        self.entries["noise_dur"].insert(0, settings.get("noise_dur", vt.NOISE_DURATION))

        self.entries["silence_thresh"].delete(0, tk.END)
        self.entries["silence_thresh"].insert(0, settings.get("silence_thresh", vt.AUDIO_THRESHOLD_SILENCE))

        self.entries["silence_dur"].delete(0, tk.END)
        self.entries["silence_dur"].insert(0, settings.get("silence_dur", vt.SILENCE_DURATION))

        self.glitch_var.set(bool(settings.get("filters", {}).get("glitch", vt.GLITCH_ENABLE)))
        self.vhs_var.set(bool(settings.get("filters", {}).get("vhs", vt.ENABLE_VHS)))
        self.scanline_var.set(bool(settings.get("filters", {}).get("scanlines", vt.SCANLINE_ENABLE)))
        self.ca_var.set(bool(settings.get("filters", {}).get("chromatic", vt.ENABLE_CA)))

        self.refresh_mic_devices()
        mic_idx = settings.get("mic_device_index", vt.MIC_DEVICE_INDEX)
        if hasattr(self, "mic_device_combo") and self.mic_device_combo["values"]:
            match = None
            for item in self.mic_device_combo["values"]:
                if item.startswith(f"{mic_idx}:"):
                    match = item
                    break
            if match:
                self.mic_device_var.set(match)

        self.refresh_midi_devices()
        midi_defaults = settings.get("midi_defaults", {})
        midi_device = midi_defaults.get("device", "")
        if midi_device:
            self.midi_device_var.set(midi_device)

        self.refresh_midi_files()
        midi_config = midi_defaults.get("config", "")
        if midi_config and midi_config in self.midi_combo["values"]:
            self.midi_config_var.set(midi_config)

        self._log("GUI settings backup loaded")

    def start_engine(self):
        if self._engine_thread and self._engine_thread.is_alive():
            self._log("Engine already running")
            return

        self.apply_config()
        self.reload_videos()

        self._engine_thread = threading.Thread(target=self._engine.run, daemon=True)
        self._engine_thread.start()
        self.status_var.set("Running")
        self._log("Engine started")

    def stop_engine(self):
        if not self._engine_thread:
            return

        self._engine.request_stop()
        self._engine_thread.join(timeout=3.0)
        self.status_var.set("Stopped")
        self._log("Engine stopped")


if __name__ == "__main__":
    app = VideoTuberGUI()
    app.mainloop()


def main():
    app = VideoTuberGUI()
    app.mainloop()
