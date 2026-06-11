"""AED desktop control panel built with tkinter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.app.factory import (
    build_current_manual_demo_session,
    format_session_summary,
)
from scripts.app.practical_stage import (
    practical_junction_focus_choices,
    practical_route_choices,
    practical_town_choices,
    practical_traffic_choices,
    practical_weather_choices,
    resolve_practical_route,
    resolve_practical_traffic,
)
from scripts.app.training_stages import (
    TRAINING_STAGE_OPTIONS,
    resolve_training_stage,
)
from scripts.app.runtime_support import (
    build_launcher_subprocess_command,
    configure_runtime_workspace,
)
from scripts.evaluation.result_models import EpisodeResult
from scripts.evaluation.scoring import compute_driving_score


APP_TITLE = "AutoDrive Environment Designer"
TRACK_STAGE_ID = "track"
PRACTICAL_STAGE_ID = "practical"
DRIVER_BACKEND_CHOICES = ("manual", "external_module", "external_command")


class AppShell(tk.Tk):
    """Application shell for current AED workflows."""

    def __init__(self, *, pythonapi_path: str | None = None) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x940")
        self.minsize(1220, 820)

        self.base_dir = configure_runtime_workspace(Path(__file__))
        self.results_dir = self.base_dir / "results" / "manual_sequence"
        self.current_process: subprocess.Popen[str] | None = None
        self.current_process_label = "Idle"
        self.output_queue: queue.Queue[str] = queue.Queue()
        self._recent_results: list[Path] = []
        self._track_only_buttons: list[ttk.Button] = []
        self._generation_stage_buttons: list[ttk.Button] = []
        self._practical_stage_buttons: list[ttk.Button] = []
        self._track_setup_widgets: list[tk.Widget] = []
        self._practical_setup_widgets: list[tk.Widget] = []
        self._generation_input_widgets: list[tk.Widget] = []
        self.sidebar_canvas: tk.Canvas | None = None
        self.practical_custom_window: tk.Toplevel | None = None
        self.integration_settings_window: tk.Toplevel | None = None
        self.drive_setup_frame: ttk.LabelFrame | None = None
        self.auto_generation_frame: ttk.LabelFrame | None = None
        self.actions_frame: ttk.LabelFrame | None = None

        self.host_var = tk.StringVar(value="localhost")
        self.port_var = tk.StringVar(value="2000")
        self.timeout_var = tk.StringVar(value="30.0")
        self.pythonapi_var = tk.StringVar(value=pythonapi_path or "")
        self.session_name_var = tk.StringVar(value="aed_manual_sequence_session")
        self.training_stage_var = tk.StringVar(value=TRACK_STAGE_ID)
        self.map_id_var = tk.StringVar(value="aed_sequence_demo")
        self.spectator_mode_var = tk.StringVar(value="fixed-overview")
        self.keep_vehicle_var = tk.BooleanVar(value=False)
        self.xodr_path_var = tk.StringVar(value="")
        self.auto_map_prefix_var = tk.StringVar(value="aed_auto_generated")
        self.practical_town_var = tk.StringVar(value="Town03")
        self.practical_weather_var = tk.StringVar(value="clear_noon")
        self.practical_traffic_var = tk.StringVar(value="moderate")
        self.practical_route_var = tk.StringVar(value="urban_loop")
        self.practical_scenario_path_var = tk.StringVar(value="")
        self.practical_custom_enabled_var = tk.BooleanVar(value=False)
        self.practical_custom_vehicle_count_var = tk.StringVar(value="")
        self.practical_custom_pedestrian_count_var = tk.StringVar(value="")
        self.practical_custom_route_length_var = tk.StringVar(value="")
        self.practical_custom_junction_focus_var = tk.StringVar(value="medium")
        self.practical_custom_note_entry_var = tk.StringVar(value="")
        self.integration_custom_enabled_var = tk.BooleanVar(value=False)
        self.preferred_blueprint_id_var = tk.StringVar(value="")
        self.vehicle_role_name_var = tk.StringVar(value="")
        self.driver_backend_var = tk.StringVar(value="manual")
        self.vehicle_config_path_var = tk.StringVar(value="")
        self.driver_module_path_var = tk.StringVar(value="")
        self.external_driver_command_var = tk.StringVar(value="")
        self.external_driver_working_dir_var = tk.StringVar(value="")
        self.external_driver_startup_wait_var = tk.StringVar(value="2.0")

        self.status_var = tk.StringVar(value="Ready")
        self.summary_text = tk.StringVar(value="")
        self.phase_badge_var = tk.StringVar(value="")
        self.phase_note_var = tk.StringVar(value="")
        self.workflow_note_var = tk.StringVar(value="")
        self.auto_generation_note_var = tk.StringVar(value="")
        self.result_score_var = tk.StringVar(value="Score: -")
        self.practical_note_var = tk.StringVar(value="")
        self.practical_custom_summary_var = tk.StringVar(value="")
        self.integration_summary_var = tk.StringVar(value="")
        self.practical_scenario_summary_var = tk.StringVar(value="Prepared Scenario: -")
        self.practical_scenario_detail_var = tk.StringVar(value="")
        self.practical_scenario_badge_var = tk.StringVar(value="")
        self._pending_practical_autorun = False

        self._configure_styles()
        self._build_ui()
        self._refresh_practical_custom_summary()
        self._refresh_integration_summary()
        self.training_stage_var.trace_add("write", self._on_training_stage_changed)
        self._on_training_stage_changed()
        self.refresh_session_summary()
        self.refresh_result_list()
        self.after(150, self._poll_process_output)

    def _configure_styles(self) -> None:
        self.option_add("*Font", "{Segoe UI} 10")

        self.palette = {
            "bg": "#eef2ef",
            "surface": "#fbfaf6",
            "surface_alt": "#f3efe6",
            "border": "#d9d3c5",
            "text": "#1f2933",
            "muted": "#607080",
            "accent": "#0f766e",
            "accent_dark": "#0b5f58",
            "accent_soft": "#d7efe9",
            "warning": "#b45309",
            "danger": "#b42318",
        }

        self.configure(background=self.palette["bg"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=self.palette["bg"])
        style.configure("Panel.TFrame", background=self.palette["surface"])
        style.configure(
            "Hero.TFrame",
            background=self.palette["surface"],
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe",
            background=self.palette["surface"],
            bordercolor=self.palette["border"],
            borderwidth=1,
            relief="solid",
            padding=14,
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=self.palette["surface"],
            foreground=self.palette["text"],
            font=("{Segoe UI Semibold}", 11),
        )
        style.configure(
            "Title.TLabel",
            background=self.palette["surface"],
            foreground=self.palette["text"],
            font=("{Segoe UI Semibold}", 18),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self.palette["surface"],
            foreground=self.palette["muted"],
            font=("{Segoe UI}", 10),
        )
        style.configure(
            "Body.TLabel",
            background=self.palette["surface"],
            foreground=self.palette["text"],
            font=("{Segoe UI}", 10),
        )
        style.configure(
            "Muted.TLabel",
            background=self.palette["surface"],
            foreground=self.palette["muted"],
            font=("{Segoe UI}", 9),
        )
        style.configure(
            "Badge.TLabel",
            background=self.palette["accent_soft"],
            foreground=self.palette["accent_dark"],
            font=("{Segoe UI Semibold}", 10),
            padding=(12, 6),
        )
        style.configure(
            "Status.TLabel",
            background=self.palette["surface"],
            foreground=self.palette["accent_dark"],
            font=("{Segoe UI Semibold}", 9),
        )
        style.configure(
            "Accent.TButton",
            background=self.palette["accent"],
            foreground="#ffffff",
            borderwidth=0,
            padding=(12, 8),
            font=("{Segoe UI Semibold}", 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", self.palette["accent_dark"]), ("disabled", "#b8c4bf")],
            foreground=[("disabled", "#f3f4f6")],
        )
        style.configure(
            "Ghost.TButton",
            background=self.palette["surface_alt"],
            foreground=self.palette["text"],
            bordercolor=self.palette["border"],
            padding=(12, 8),
            font=("{Segoe UI}", 10),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#ebe7de"), ("disabled", "#f4f4f2")],
            foreground=[("disabled", "#93a1ad")],
        )
        style.configure(
            "Danger.TButton",
            background="#fdecea",
            foreground=self.palette["danger"],
            bordercolor="#f5c2bd",
            padding=(12, 8),
            font=("{Segoe UI Semibold}", 10),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#f8d8d3"), ("disabled", "#f6eded")],
            foreground=[("disabled", "#bf8f8a")],
        )
        style.configure(
            "Stage.TRadiobutton",
            background=self.palette["surface"],
            foreground=self.palette["text"],
            font=("{Segoe UI Semibold}", 10),
            padding=(0, 4),
        )
        style.map(
            "Stage.TRadiobutton",
            background=[("active", self.palette["surface"])],
            foreground=[("disabled", "#9aa6b2")],
        )
        style.configure(
            "Footer.TLabel",
            background=self.palette["surface"],
            foreground=self.palette["muted"],
            font=("{Segoe UI}", 9),
        )

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_header()

        body = ttk.Frame(self, style="App.TFrame", padding=(18, 0, 18, 12))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        sidebar_container = ttk.Frame(body, style="App.TFrame")
        sidebar_container.grid(row=0, column=0, sticky="nsw")
        sidebar_container.columnconfigure(0, weight=1)
        sidebar_container.rowconfigure(0, weight=1)

        self.sidebar_canvas = tk.Canvas(
            sidebar_container,
            background=self.palette["bg"],
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
            width=470,
        )
        self.sidebar_canvas.grid(row=0, column=0, sticky="nsew")
        sidebar_scrollbar = ttk.Scrollbar(
            sidebar_container,
            orient="vertical",
            command=self.sidebar_canvas.yview,
        )
        sidebar_scrollbar.grid(row=0, column=1, sticky="ns")
        self.sidebar_canvas.configure(yscrollcommand=sidebar_scrollbar.set)

        sidebar = ttk.Frame(self.sidebar_canvas, style="App.TFrame")
        self._sidebar_window = self.sidebar_canvas.create_window((0, 0), window=sidebar, anchor="nw")
        sidebar.bind("<Configure>", self._on_sidebar_configure)
        self.sidebar_canvas.bind("<Configure>", self._on_sidebar_canvas_configure)
        self.sidebar_canvas.bind("<Enter>", self._bind_sidebar_mousewheel)
        self.sidebar_canvas.bind("<Leave>", self._unbind_sidebar_mousewheel)
        sidebar.columnconfigure(0, weight=1)

        content = ttk.Frame(body, style="App.TFrame")
        content.grid(row=0, column=1, sticky="nsew", padx=(18, 0))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=3)
        content.rowconfigure(2, weight=2)

        self._build_runtime_section(sidebar, row=0)
        self._build_stage_section(sidebar, row=1)
        self._build_map_section(sidebar, row=2)
        self._build_auto_generation_section(sidebar, row=3)
        self._build_actions_section(sidebar, row=4)

        self._build_results_section(content)
        self._build_log_section(content)
        self._build_footer()

    def _build_header(self) -> None:
        header = ttk.Frame(self, style="Hero.TFrame", padding=(20, 16))
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 14))
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text=APP_TITLE,
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=(
                "Result-driven OpenDRIVE generation, CARLA loading, manual validation, "
                "and next-map iteration in one control panel."
            ),
            style="Subtitle.TLabel",
            wraplength=880,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(
            header,
            textvariable=self.phase_badge_var,
            style="Badge.TLabel",
        ).grid(row=0, column=1, rowspan=2, sticky="ne")

    def _build_runtime_section(self, parent: ttk.Frame, *, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Runtime", style="Card.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Host", style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.host_var, width=24).grid(row=0, column=1, sticky="ew", pady=3)

        ttk.Label(frame, text="Port", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.port_var, width=24).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(frame, text="Timeout", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.timeout_var, width=24).grid(row=2, column=1, sticky="ew", pady=3)

        ttk.Label(frame, text="PythonAPI", style="Body.TLabel").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.pythonapi_var, width=24).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Button(
            frame,
            text="Browse",
            style="Ghost.TButton",
            command=self._browse_pythonapi_path,
        ).grid(row=3, column=2, padx=(8, 0), pady=3)

        ttk.Label(frame, text="Session", style="Body.TLabel").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.session_name_var, width=24).grid(
            row=4,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=3,
        )

        ttk.Button(
            frame,
            text="Refresh Session Summary",
            style="Ghost.TButton",
            command=self.refresh_session_summary,
        ).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        ttk.Button(
            frame,
            text="Open Vehicle / Driver Settings",
            style="Ghost.TButton",
            command=self.open_integration_settings,
        ).grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        ttk.Label(
            frame,
            textvariable=self.integration_summary_var,
            style="Muted.TLabel",
            wraplength=405,
            justify="left",
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _build_stage_section(self, parent: ttk.Frame, *, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Progression Stage", style="Card.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        frame.columnconfigure(0, weight=1)

        ttk.Label(
            frame,
            text=(
                "Pick the active validation stage once, then keep working in that mode "
                "until you intentionally switch."
            ),
            style="Muted.TLabel",
            wraplength=405,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        current_row = 1
        for option in TRAINING_STAGE_OPTIONS:
            ttk.Radiobutton(
                frame,
                text=option.display_name,
                value=option.stage_id,
                variable=self.training_stage_var,
                style="Stage.TRadiobutton",
            ).grid(row=current_row, column=0, sticky="w", pady=(10, 0))
            ttk.Label(
                frame,
                text=f"{option.short_label} - {option.description}",
                style="Muted.TLabel",
                wraplength=405,
                justify="left",
            ).grid(row=current_row + 1, column=0, sticky="w")
            current_row += 2

        ttk.Label(
            frame,
            textvariable=self.workflow_note_var,
            style="Status.TLabel",
            wraplength=405,
            justify="left",
        ).grid(row=current_row, column=0, sticky="w", pady=(10, 0))

    def _build_map_section(self, parent: ttk.Frame, *, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Drive Setup", style="Card.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        frame.columnconfigure(0, weight=1)
        self.drive_setup_frame = frame

        common_frame = ttk.Frame(frame, style="Panel.TFrame")
        common_frame.grid(row=0, column=0, sticky="ew")
        common_frame.columnconfigure(1, weight=1)

        ttk.Label(common_frame, text="Spectator", style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(
            common_frame,
            textvariable=self.spectator_mode_var,
            values=("fixed-overview", "follow"),
            state="readonly",
            width=21,
        ).grid(row=0, column=1, sticky="ew", pady=3)

        ttk.Checkbutton(
            common_frame,
            text="Keep vehicle after exit",
            variable=self.keep_vehicle_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 8))

        self.track_setup_frame = ttk.Frame(frame, style="Panel.TFrame")
        self.track_setup_frame.grid(row=1, column=0, sticky="ew")
        self.track_setup_frame.columnconfigure(1, weight=1)

        ttk.Label(self.track_setup_frame, text="Map ID", style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        self.map_id_entry = ttk.Entry(self.track_setup_frame, textvariable=self.map_id_var, width=24)
        self.map_id_entry.grid(row=0, column=1, sticky="ew", pady=3)

        ttk.Label(self.track_setup_frame, text="XODR File", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        self.xodr_entry = ttk.Entry(self.track_setup_frame, textvariable=self.xodr_path_var, width=24)
        self.xodr_entry.grid(row=1, column=1, sticky="ew", pady=3)
        self.xodr_browse_button = ttk.Button(
            self.track_setup_frame,
            text="Browse",
            style="Ghost.TButton",
            command=self._browse_xodr_path,
        )
        self.xodr_browse_button.grid(row=1, column=2, padx=(8, 0), pady=3)

        ttk.Label(
            self.track_setup_frame,
            text=(
                "Pick a local or generated .xodr here, then run it directly without "
                "scrolling down to the manual actions section."
            ),
            style="Muted.TLabel",
            wraplength=405,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 8))

        self.run_selected_xodr_button = ttk.Button(
            self.track_setup_frame,
            text="Run Selected XODR",
            style="Accent.TButton",
            command=self.run_manual_xodr,
        )
        self.run_selected_xodr_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=3)

        self.load_selected_xodr_button = ttk.Button(
            self.track_setup_frame,
            text="Load Selected XODR",
            style="Ghost.TButton",
            command=self.load_local_xodr,
        )
        self.load_selected_xodr_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=3)

        self.practical_setup_frame = ttk.Frame(frame, style="Panel.TFrame")
        self.practical_setup_frame.grid(row=2, column=0, sticky="ew")
        self.practical_setup_frame.columnconfigure(1, weight=1)

        ttk.Label(self.practical_setup_frame, text="Practical Town", style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        self.practical_town_combo = ttk.Combobox(
            self.practical_setup_frame,
            textvariable=self.practical_town_var,
            values=practical_town_choices(),
            state="readonly",
            width=21,
        )
        self.practical_town_combo.grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(self.practical_setup_frame, text="Weather", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        self.practical_weather_combo = ttk.Combobox(
            self.practical_setup_frame,
            textvariable=self.practical_weather_var,
            values=practical_weather_choices(),
            state="readonly",
            width=21,
        )
        self.practical_weather_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(self.practical_setup_frame, text="Traffic", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        self.practical_traffic_combo = ttk.Combobox(
            self.practical_setup_frame,
            textvariable=self.practical_traffic_var,
            values=practical_traffic_choices(),
            state="readonly",
            width=21,
        )
        self.practical_traffic_combo.grid(row=2, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(self.practical_setup_frame, text="Route", style="Body.TLabel").grid(row=3, column=0, sticky="w", pady=3)
        self.practical_route_combo = ttk.Combobox(
            self.practical_setup_frame,
            textvariable=self.practical_route_var,
            values=practical_route_choices(),
            state="readonly",
            width=21,
        )
        self.practical_route_combo.grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(
            self.practical_setup_frame,
            textvariable=self.practical_note_var,
            style="Muted.TLabel",
            wraplength=405,
            justify="left",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 8))

        self.custom_practical_settings_button = ttk.Button(
            self.practical_setup_frame,
            text="Open Custom Scenario Settings",
            style="Ghost.TButton",
            command=self.open_practical_custom_settings,
        )
        self.custom_practical_settings_button.grid(row=5, column=0, columnspan=3, sticky="ew", pady=3)
        self._practical_stage_buttons.append(self.custom_practical_settings_button)

        ttk.Label(
            self.practical_setup_frame,
            textvariable=self.practical_custom_summary_var,
            style="Muted.TLabel",
            wraplength=405,
            justify="left",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 8))

        ttk.Label(
            self.practical_setup_frame,
            textvariable=self.practical_scenario_summary_var,
            style="Status.TLabel",
            wraplength=405,
            justify="left",
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(
            self.practical_setup_frame,
            textvariable=self.practical_scenario_detail_var,
            style="Muted.TLabel",
            wraplength=405,
            justify="left",
        ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(self.practical_setup_frame, text="Scenario File", style="Body.TLabel").grid(row=9, column=0, sticky="w", pady=3)
        self.practical_scenario_entry = ttk.Entry(self.practical_setup_frame, textvariable=self.practical_scenario_path_var, width=24)
        self.practical_scenario_entry.grid(
            row=9,
            column=1,
            sticky="ew",
            pady=3,
        )
        self.practical_scenario_browse_button = ttk.Button(
            self.practical_setup_frame,
            text="Browse",
            style="Ghost.TButton",
            command=self._browse_practical_scenario_path,
        )
        self.practical_scenario_browse_button.grid(row=9, column=2, padx=(8, 0), pady=3)

        self.generate_practical_scenario_button = ttk.Button(
            self.practical_setup_frame,
            text="Generate Practical Scenario",
            style="Accent.TButton",
            command=self.generate_practical_scenario,
        )
        self.generate_practical_scenario_button.grid(row=10, column=0, columnspan=3, sticky="ew", pady=3)
        self._practical_stage_buttons.append(self.generate_practical_scenario_button)

        self.generate_and_run_practical_scenario_button = ttk.Button(
            self.practical_setup_frame,
            text="Generate + Run Practical Scenario",
            style="Accent.TButton",
            command=self.generate_and_run_practical_scenario,
        )
        self.generate_and_run_practical_scenario_button.grid(row=11, column=0, columnspan=3, sticky="ew", pady=3)
        self._practical_stage_buttons.append(self.generate_and_run_practical_scenario_button)

        self.run_practical_scenario_button = ttk.Button(
            self.practical_setup_frame,
            text="Run Practical Scenario",
            style="Accent.TButton",
            command=self.run_practical_scenario,
        )
        self.run_practical_scenario_button.grid(row=12, column=0, columnspan=3, sticky="ew", pady=3)
        self._practical_stage_buttons.append(self.run_practical_scenario_button)

        self.load_town_button = ttk.Button(
            self.practical_setup_frame,
            text="Load Selected Town",
            style="Ghost.TButton",
            command=self.load_practical_town,
        )
        self.load_town_button.grid(row=13, column=0, columnspan=3, sticky="ew", pady=3)
        self._practical_stage_buttons.append(self.load_town_button)

    def _build_auto_generation_section(self, parent: ttk.Frame, *, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Generation Loop", style="Card.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        frame.columnconfigure(1, weight=1)
        self.auto_generation_frame = frame

        ttk.Label(frame, text="Map Prefix", style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        self.auto_map_prefix_entry = ttk.Entry(frame, textvariable=self.auto_map_prefix_var, width=24)
        self.auto_map_prefix_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            pady=3,
        )
        self._generation_input_widgets.append(self.auto_map_prefix_entry)

        ttk.Label(
            frame,
            textvariable=self.auto_generation_note_var,
            style="Muted.TLabel",
            wraplength=405,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 10))

        self.generate_only_button = ttk.Button(
            frame,
            text="Generate Next Map",
            style="Ghost.TButton",
            command=lambda: self.generate_next_map(load_after_generate=False),
        )
        self.generate_only_button.grid(row=2, column=0, columnspan=2, sticky="ew", pady=3)
        self._generation_stage_buttons.append(self.generate_only_button)

        self.generate_load_button = ttk.Button(
            frame,
            text="Generate + Load Next Map",
            style="Ghost.TButton",
            command=lambda: self.generate_next_map(load_after_generate=True),
        )
        self.generate_load_button.grid(row=3, column=0, columnspan=2, sticky="ew", pady=3)
        self._generation_stage_buttons.append(self.generate_load_button)

        self.generate_drive_button = ttk.Button(
            frame,
            text="Generate + Drive Next Map",
            style="Accent.TButton",
            command=self.generate_and_drive_next_map,
        )
        self.generate_drive_button.grid(row=4, column=0, columnspan=2, sticky="ew", pady=3)
        self._generation_stage_buttons.append(self.generate_drive_button)

    def _build_actions_section(self, parent: ttk.Frame, *, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Manual Actions", style="Card.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        frame.columnconfigure(0, weight=1)
        self.actions_frame = frame

        self.track_actions_frame = ttk.Frame(frame, style="Panel.TFrame")
        self.track_actions_frame.grid(row=0, column=0, sticky="ew")
        self.track_actions_frame.columnconfigure(0, weight=1)

        self.manual_sequence_button = ttk.Button(
            self.track_actions_frame,
            text="Run Manual Sequence",
            style="Ghost.TButton",
            command=self.run_manual_sequence,
        )
        self.manual_sequence_button.grid(row=0, column=0, sticky="ew", pady=3)
        self._track_only_buttons.append(self.manual_sequence_button)

        self.manual_track_button = ttk.Button(
            self.track_actions_frame,
            text="Run Manual Track",
            style="Ghost.TButton",
            command=self.run_manual_track,
        )
        self.manual_track_button.grid(row=1, column=0, sticky="ew", pady=3)
        self._track_only_buttons.append(self.manual_track_button)

        ttk.Button(
            self.track_actions_frame,
            text="Run Manual XODR",
            style="Ghost.TButton",
            command=self.run_manual_xodr,
        ).grid(row=2, column=0, sticky="ew", pady=3)

        ttk.Button(
            self.track_actions_frame,
            text="Load Local XODR",
            style="Ghost.TButton",
            command=self.load_local_xodr,
        ).grid(row=3, column=0, sticky="ew", pady=3)

        self.shared_actions_frame = ttk.Frame(frame, style="Panel.TFrame")
        self.shared_actions_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.shared_actions_frame.columnconfigure(0, weight=1)

        ttk.Button(
            self.shared_actions_frame,
            text="Stop Current Process",
            style="Danger.TButton",
            command=self.stop_current_process,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 3))

    def _build_results_section(self, parent: ttk.Frame) -> None:
        summary_frame = ttk.LabelFrame(parent, text="Current Session Summary", style="Card.TLabelframe")
        summary_frame.grid(row=0, column=0, sticky="ew")
        summary_frame.columnconfigure(0, weight=1)

        ttk.Label(
            summary_frame,
            textvariable=self.summary_text,
            style="Body.TLabel",
            justify="left",
            wraplength=860,
        ).grid(row=0, column=0, sticky="ew")

        results_frame = ttk.LabelFrame(parent, text="Recent Evaluation Results", style="Card.TLabelframe")
        results_frame.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        results_frame.columnconfigure(0, weight=5, minsize=460)
        results_frame.columnconfigure(1, weight=2)
        results_frame.rowconfigure(1, weight=1)

        results_toolbar = ttk.Frame(results_frame, style="Panel.TFrame")
        results_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        results_toolbar.columnconfigure(0, weight=0)
        results_toolbar.columnconfigure(1, weight=1)

        ttk.Button(
            results_toolbar,
            text="Refresh Results",
            style="Ghost.TButton",
            command=self.refresh_result_list,
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            results_toolbar,
            textvariable=self.result_score_var,
            style="Badge.TLabel",
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))

        ttk.Label(
            results_toolbar,
            textvariable=self.practical_scenario_badge_var,
            style="Muted.TLabel",
        ).grid(row=0, column=2, sticky="w", padx=(12, 0))

        list_container = ttk.Frame(results_frame, style="Panel.TFrame")
        list_container.grid(row=1, column=0, sticky="nsew", padx=(0, 12), pady=(10, 0))
        list_container.columnconfigure(0, weight=1)
        list_container.rowconfigure(0, weight=1)

        self.results_listbox = tk.Listbox(
            list_container,
            exportselection=False,
            height=15,
            activestyle="none",
            borderwidth=0,
            highlightthickness=1,
            relief="flat",
            background=self.palette["surface"],
            foreground=self.palette["text"],
            selectbackground="#dbeafe",
            selectforeground=self.palette["text"],
            highlightbackground=self.palette["border"],
            highlightcolor=self.palette["accent"],
        )
        self.results_listbox.grid(row=0, column=0, sticky="nsew")
        self.results_listbox.bind("<<ListboxSelect>>", self._on_result_selected)

        result_scrollbar = ttk.Scrollbar(
            list_container,
            orient="vertical",
            command=self.results_listbox.yview,
        )
        result_scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_listbox.configure(yscrollcommand=result_scrollbar.set)

        result_x_scrollbar = ttk.Scrollbar(
            list_container,
            orient="horizontal",
            command=self.results_listbox.xview,
        )
        result_x_scrollbar.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.results_listbox.configure(xscrollcommand=result_x_scrollbar.set)

        self.result_preview = tk.Text(
            results_frame,
            wrap="word",
            height=15,
            state="disabled",
            borderwidth=0,
            highlightthickness=1,
            relief="flat",
            padx=10,
            pady=10,
            background=self.palette["surface"],
            foreground=self.palette["text"],
            highlightbackground=self.palette["border"],
            highlightcolor=self.palette["accent"],
        )
        self.result_preview.grid(row=1, column=1, sticky="nsew", pady=(10, 0))

    def _build_log_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Process Log", style="Card.TLabelframe")
        frame.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            frame,
            wrap="word",
            height=11,
            state="disabled",
            borderwidth=0,
            highlightthickness=1,
            relief="flat",
            padx=10,
            pady=10,
            background=self.palette["surface"],
            foreground=self.palette["text"],
            highlightbackground=self.palette["border"],
            highlightcolor=self.palette["accent"],
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, style="Hero.TFrame", padding=(18, 10))
        footer.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        footer.columnconfigure(0, weight=1)

        ttk.Label(
            footer,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=1100,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            footer,
            textvariable=self.phase_note_var,
            style="Footer.TLabel",
            wraplength=520,
            justify="right",
        ).grid(row=0, column=1, sticky="e")

    def _on_sidebar_configure(self, _event: object) -> None:
        if self.sidebar_canvas is None:
            return
        self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))

    def _on_sidebar_canvas_configure(self, event: tk.Event[tk.Misc]) -> None:
        if self.sidebar_canvas is None:
            return
        self.sidebar_canvas.itemconfigure(self._sidebar_window, width=event.width)

    def _bind_sidebar_mousewheel(self, _event: object) -> None:
        if self.sidebar_canvas is None:
            return
        self.sidebar_canvas.bind_all("<MouseWheel>", self._on_sidebar_mousewheel)
        self.sidebar_canvas.bind_all("<Button-4>", self._on_sidebar_mousewheel)
        self.sidebar_canvas.bind_all("<Button-5>", self._on_sidebar_mousewheel)

    def _unbind_sidebar_mousewheel(self, _event: object) -> None:
        if self.sidebar_canvas is None:
            return
        self.sidebar_canvas.unbind_all("<MouseWheel>")
        self.sidebar_canvas.unbind_all("<Button-4>")
        self.sidebar_canvas.unbind_all("<Button-5>")

    def _on_sidebar_mousewheel(self, event: tk.Event[tk.Misc]) -> None:
        if self.sidebar_canvas is None:
            return
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            raw_delta = int(getattr(event, "delta", 0) or 0)
            delta = -1 * int(raw_delta / 120) if raw_delta else 0
        if delta != 0:
            self.sidebar_canvas.yview_scroll(delta, "units")

    def _active_stage(self):
        return resolve_training_stage(self.training_stage_var.get())

    def _set_button_group_enabled(self, buttons: list[ttk.Button], enabled: bool) -> None:
        for button in buttons:
            if enabled:
                button.state(("!disabled",))
            else:
                button.state(("disabled",))

    def _set_panel_visible(self, panel: tk.Widget | None, visible: bool) -> None:
        if panel is None:
            return
        if visible:
            panel.grid()
        else:
            panel.grid_remove()

    def _on_training_stage_changed(self, *_args: object) -> None:
        stage_option = self._active_stage()
        self.phase_badge_var.set(f"Active Stage  {stage_option.short_label}")
        self.phase_note_var.set(stage_option.description)

        if stage_option.stage_id == TRACK_STAGE_ID:
            self.practical_scenario_badge_var.set("")
            if self.drive_setup_frame is not None:
                self.drive_setup_frame.configure(text="Track / XODR Setup")
            if self.auto_generation_frame is not None:
                self.auto_generation_frame.configure(text="Generation Loop")
            if self.actions_frame is not None:
                self.actions_frame.configure(text="Manual Actions")
            self.workflow_note_var.set(
                "Track quick flow: 1) pick or generate an XODR, 2) drive it manually, "
                "3) review the saved score, 4) generate the next map from that result."
            )
            self.auto_generation_note_var.set(
                "Use Generate + Drive for the fastest loop. The selected result is used first; "
                "if nothing is selected, the latest result is used automatically."
            )
            self.practical_note_var.set(
                "Track stage keeps the generated XODR loop visible. Switch to Practical only when you want "
                "Town-based scenario generation instead of XODR map generation."
            )
            self._set_panel_visible(getattr(self, "track_setup_frame", None), True)
            self._set_panel_visible(getattr(self, "practical_setup_frame", None), False)
            self._set_panel_visible(self.auto_generation_frame, True)
            self._set_panel_visible(getattr(self, "track_actions_frame", None), True)
            self._set_button_group_enabled(self._generation_stage_buttons, True)
            self._set_button_group_enabled(self._track_only_buttons, True)
            self._set_button_group_enabled(self._practical_stage_buttons, False)
        elif stage_option.stage_id == "intermediate":
            self.practical_scenario_badge_var.set("")
            if self.drive_setup_frame is not None:
                self.drive_setup_frame.configure(text="Intermediate Road Setup")
            if self.auto_generation_frame is not None:
                self.auto_generation_frame.configure(text="Generation Loop")
            if self.actions_frame is not None:
                self.actions_frame.configure(text="Manual Actions")
            self.workflow_note_var.set(
                "Intermediate quick flow: 1) generate a road-like map, 2) stay in the correct lane while driving, "
                "3) review lane discipline and offroad penalties, 4) regenerate from the saved result."
            )
            self.auto_generation_note_var.set(
                "Generation buttons now create the road-like baseline. Expect longer layouts, right-hand traffic, "
                "lane guidance, and tighter offroad penalties than Track stage."
            )
            self.practical_note_var.set(
                "Intermediate still uses generated XODR maps. Switch to Practical only when you want CARLA Town "
                "scenarios with route goals and background actors."
            )
            self._set_panel_visible(getattr(self, "track_setup_frame", None), True)
            self._set_panel_visible(getattr(self, "practical_setup_frame", None), False)
            self._set_panel_visible(self.auto_generation_frame, True)
            self._set_panel_visible(getattr(self, "track_actions_frame", None), True)
            self._set_button_group_enabled(self._generation_stage_buttons, True)
            self._set_button_group_enabled(self._track_only_buttons, False)
            self._set_button_group_enabled(self._practical_stage_buttons, False)
        else:
            if self.drive_setup_frame is not None:
                self.drive_setup_frame.configure(text="Practical Town Setup")
            if self.actions_frame is not None:
                self.actions_frame.configure(text="Shared Actions")
            self.workflow_note_var.set(
                "Practical quick flow: 1) choose Town, weather, traffic, and route, 2) Generate or Generate + Run, "
                "3) drive to the GOAL marker, 4) review the saved destination-based score."
            )
            self.auto_generation_note_var.set(
                "Track generation is hidden here. Practical uses Town-based scenarios, so Generate prepares the next "
                "scenario JSON and Run loads the Town, ego vehicle, traffic, and pedestrians."
            )
            self.practical_note_var.set(
                "Select a Town, weather, traffic, and route preset here. You can pin only the fields you want in "
                "Custom Scenario Settings; any blank field still follows automatic adaptation from previous results."
            )
            self._set_panel_visible(getattr(self, "track_setup_frame", None), False)
            self._set_panel_visible(getattr(self, "practical_setup_frame", None), True)
            self._set_panel_visible(self.auto_generation_frame, False)
            self._set_panel_visible(getattr(self, "track_actions_frame", None), False)
            self._set_button_group_enabled(self._generation_stage_buttons, False)
            self._set_button_group_enabled(self._track_only_buttons, False)
            self._set_button_group_enabled(self._practical_stage_buttons, True)
            self._refresh_practical_scenario_summary()

        if hasattr(self, "summary_text"):
            self.refresh_session_summary()
        if hasattr(self, "results_listbox"):
            self.refresh_result_list()

    def _browse_pythonapi_path(self) -> None:
        selected = filedialog.askdirectory(
            title="Select CARLA root or PythonAPI directory",
            initialdir=self.pythonapi_var.get() or str(self.base_dir),
        )
        if selected:
            self.pythonapi_var.set(selected)

    def _browse_external_driver_working_dir(self, target_var: tk.StringVar) -> None:
        selected = filedialog.askdirectory(
            title="Select external driver working directory",
            initialdir=target_var.get() or str(self.base_dir),
        )
        if selected:
            target_var.set(selected)

    def _browse_vehicle_config_path(self, target_var: tk.StringVar) -> None:
        selected = filedialog.askopenfilename(
            title="Select vehicle integration JSON",
            initialdir=str(self.base_dir),
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if selected:
            target_var.set(selected)

    def _browse_driver_module_path(
        self,
        target_var: tk.StringVar,
        backend_var: tk.StringVar | None = None,
    ) -> None:
        selected = filedialog.askopenfilename(
            title="Select driver Python module",
            initialdir=str(self.base_dir),
            filetypes=[("Python", "*.py"), ("All files", "*.*")],
        )
        if selected:
            target_var.set(selected)
            if backend_var is not None and backend_var.get().strip() in {"", "manual"}:
                backend_var.set("external_module")

    def _browse_xodr_path(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select OpenDRIVE file",
            initialdir=str(self.base_dir / "maps" / "generated"),
            filetypes=[("OpenDRIVE", "*.xodr"), ("All files", "*.*")],
        )
        if selected:
            self.xodr_path_var.set(selected)

    def _browse_practical_scenario_path(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select Practical scenario JSON",
            initialdir=str(self.base_dir / "scenarios" / "practical"),
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if selected:
            self.practical_scenario_path_var.set(selected)
            self._refresh_practical_scenario_summary()

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    @staticmethod
    def _parse_optional_int(raw_value: str) -> int | None:
        value = raw_value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _practical_custom_kwargs(self) -> dict[str, object]:
        if not self.practical_custom_enabled_var.get():
            return {
                "practical_custom_enabled": False,
                "practical_custom_vehicle_count": None,
                "practical_custom_pedestrian_count": None,
                "practical_custom_route_length": None,
                "practical_custom_junction_focus": None,
                "practical_custom_note": None,
            }
        return {
            "practical_custom_enabled": self.practical_custom_enabled_var.get(),
            "practical_custom_vehicle_count": self._parse_optional_int(
                self.practical_custom_vehicle_count_var.get()
            ),
            "practical_custom_pedestrian_count": self._parse_optional_int(
                self.practical_custom_pedestrian_count_var.get()
            ),
            "practical_custom_route_length": self._parse_optional_int(
                self.practical_custom_route_length_var.get()
            ),
            "practical_custom_junction_focus": (
                self.practical_custom_junction_focus_var.get().strip() or None
            ),
            "practical_custom_note": self.practical_custom_note_entry_var.get().strip() or None,
        }

    def _integration_kwargs(self) -> dict[str, object]:
        vehicle_config_path = self.vehicle_config_path_var.get().strip() or None
        preferred_blueprint_id = self.preferred_blueprint_id_var.get().strip() or None
        role_name = self.vehicle_role_name_var.get().strip() or None
        driver_backend = self.driver_backend_var.get().strip() or "manual"
        driver_module_path = self.driver_module_path_var.get().strip() or None
        external_driver_command = self.external_driver_command_var.get().strip() or None
        if driver_backend == "manual":
            if driver_module_path:
                driver_backend = "external_module"
            elif external_driver_command:
                driver_backend = "external_command"
        external_driver_working_dir = self.external_driver_working_dir_var.get().strip() or None
        startup_wait_text = self.external_driver_startup_wait_var.get().strip()
        startup_wait_value: float | None = None
        if startup_wait_text:
            try:
                startup_wait_value = float(startup_wait_text)
            except ValueError:
                startup_wait_value = None
        integration_active = bool(
            vehicle_config_path
            or preferred_blueprint_id
            or role_name
            or driver_module_path
            or external_driver_command
            or driver_backend != "manual"
        )
        return {
            "integration_custom_enabled": integration_active,
            "preferred_blueprint_id": preferred_blueprint_id,
            "role_name": role_name,
            "driver_backend": driver_backend,
            "vehicle_config_path": vehicle_config_path,
            "driver_module_path": driver_module_path,
            "external_driver_command": external_driver_command,
            "external_driver_working_dir": external_driver_working_dir,
            "external_driver_startup_wait": startup_wait_value,
        }

    def _refresh_practical_custom_summary(self) -> None:
        if not self.practical_custom_enabled_var.get():
            self.practical_custom_summary_var.set(
                "Scenario customization: automatic adaptation is active. Open the custom settings window only when you want to pin the next Practical scenario."
            )
            return

        override_lines: list[str] = []
        vehicle_count = self.practical_custom_vehicle_count_var.get().strip()
        pedestrian_count = self.practical_custom_pedestrian_count_var.get().strip()
        route_length = self.practical_custom_route_length_var.get().strip()
        junction_focus = self.practical_custom_junction_focus_var.get().strip()
        note = self.practical_custom_note_entry_var.get().strip()
        if vehicle_count:
            override_lines.append(f"{vehicle_count} vehicles")
        if pedestrian_count:
            override_lines.append(f"{pedestrian_count} pedestrians")
        if route_length:
            override_lines.append(f"~{route_length}m")
        if junction_focus:
            override_lines.append(f"junction {junction_focus}")
        if note:
            override_lines.append(f"note: {note}")
        if override_lines:
            summary = (
                "Custom scenario active: "
                + " / ".join(override_lines)
                + " / remaining fields use automatic adaptation"
            )
        else:
            summary = (
                "Custom scenario active: no field is pinned yet. "
                "Any blank field still uses automatic adaptation."
            )
        self.practical_custom_summary_var.set(summary)

    def _refresh_integration_summary(self) -> None:
        integration_kwargs = self._integration_kwargs()
        if not bool(integration_kwargs["integration_custom_enabled"]):
            self.integration_summary_var.set(
                "Integration: built-in CARLA ego vehicle + manual keyboard driving are active by default."
            )
            return

        vehicle_config_path = self.vehicle_config_path_var.get().strip()
        vehicle_config_data: dict[str, object] = {}
        if vehicle_config_path:
            try:
                vehicle_config_data = json.loads(Path(vehicle_config_path).read_text(encoding="utf-8"))
            except Exception:
                vehicle_config_data = {}

        role_name = (
            self.vehicle_role_name_var.get().strip()
            or str(vehicle_config_data.get("role_name", "")).strip()
            or "hero"
        )
        preferred_blueprint = (
            self.preferred_blueprint_id_var.get().strip()
            or str(vehicle_config_data.get("preferred_blueprint_id", "")).strip()
            or "auto-select"
        )
        driver_backend = str(integration_kwargs["driver_backend"])
        summary_parts = [
            f"role={role_name}",
            f"blueprint={preferred_blueprint}",
            f"driver={driver_backend}",
        ]
        driver_module_path = self.driver_module_path_var.get().strip()
        if vehicle_config_path:
            summary_parts.append(f"vehicle_file={Path(vehicle_config_path).name}")
        color_value = str(vehicle_config_data.get("color", "")).strip()
        if color_value:
            summary_parts.append(f"color={color_value}")
        if driver_backend == "external_module":
            summary_parts.append(
                f"driver_file={Path(driver_module_path).name if driver_module_path else 'missing module'}"
            )
        elif driver_backend == "external_command":
            launch_command = self.external_driver_command_var.get().strip() or "missing command"
            working_dir = self.external_driver_working_dir_var.get().strip()
            startup_wait = self.external_driver_startup_wait_var.get().strip() or "2.0"
            summary_parts.append(f"launch={launch_command}")
            if working_dir:
                summary_parts.append(f"cwd={working_dir}")
            summary_parts.append(f"wait={startup_wait}s")
        self.integration_summary_var.set("Integration override: " + " / ".join(summary_parts))

    def _refresh_practical_scenario_summary(self) -> None:
        scenario_path_text = self.practical_scenario_path_var.get().strip()
        if not scenario_path_text:
            self.practical_scenario_summary_var.set("Prepared Scenario: -")
            self.practical_scenario_detail_var.set(
                "Generate Practical Scenario prepares the next Town route baseline. "
                "Run Practical Scenario loads the Town, spawns the ego vehicle and background actors, "
                "then starts destination-based evaluation."
            )
            self.practical_scenario_badge_var.set("")
            return

        scenario_path = Path(scenario_path_text)
        if not scenario_path.exists():
            self.practical_scenario_summary_var.set("Prepared Scenario: selected file is missing.")
            self.practical_scenario_detail_var.set(
                "The selected Practical scenario file is missing. Generate a new scenario or browse to an existing one."
            )
            self.practical_scenario_badge_var.set("Scenario: missing")
            return

        try:
            payload = json.loads(scenario_path.read_text(encoding="utf-8"))
        except Exception:
            self.practical_scenario_summary_var.set("Prepared Scenario: selected file could not be read.")
            self.practical_scenario_detail_var.set(
                "The selected Practical scenario file could not be parsed. Generate it again or choose another scenario."
            )
            self.practical_scenario_badge_var.set("Scenario: unreadable")
            return

        scenario_id = str(payload.get("scenario_id", scenario_path.stem))
        town_id = str(payload.get("town_id", "-"))
        vehicle_count = int(payload.get("traffic_vehicle_count", 0))
        pedestrian_count = int(payload.get("pedestrian_count", 0))
        route_length_hint_m = int(payload.get("route_length_hint_m", 0))
        junction_focus = str(payload.get("junction_focus", "-"))
        adaptation_payload = payload.get("adaptation") or {}
        adaptation_mode = str(adaptation_payload.get("mode", payload.get("scenario_mode", "auto")))
        adaptation_summary = str(adaptation_payload.get("summary", "")).strip()
        if not adaptation_summary:
            adaptation_summary = (
                "This scenario uses the selected Town presets directly. "
                "Generate + Run will load the Town, spawn the ego vehicle and background actors, "
                "and score destination reach."
            )

        self.practical_scenario_summary_var.set(
            f"Prepared Scenario: {scenario_id} / {town_id} / "
            f"{vehicle_count} vehicles / {pedestrian_count} pedestrians / "
            f"~{route_length_hint_m}m / junction {junction_focus} / mode={adaptation_mode}"
        )
        self.practical_scenario_detail_var.set(f"Adaptation: {adaptation_summary}")
        self.practical_scenario_badge_var.set(
            f"Scenario: {scenario_id}   {town_id}   {vehicle_count} vehicles / {pedestrian_count} pedestrians"
        )

    def _active_results_dir(self) -> Path:
        stage_id = self.training_stage_var.get().strip() or TRACK_STAGE_ID
        if stage_id == PRACTICAL_STAGE_ID:
            return self.base_dir / "results" / "practical"
        return self.base_dir / "results" / "manual_sequence"

    def _fill_latest_practical_scenario(self) -> None:
        practical_dir = self.base_dir / "scenarios" / "practical"
        candidates = sorted(
            practical_dir.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            self.practical_scenario_path_var.set(str(candidates[0]))
            self._refresh_practical_scenario_summary()

    def _runtime_args(self) -> list[str]:
        args = [
            "--host",
            self.host_var.get().strip() or "localhost",
            "--port",
            self.port_var.get().strip() or "2000",
            "--timeout",
            self.timeout_var.get().strip() or "30.0",
            "--session-name",
            self.session_name_var.get().strip() or "aed_manual_sequence_session",
            "--training-stage",
            self.training_stage_var.get().strip() or TRACK_STAGE_ID,
            "--practical-town",
            self.practical_town_var.get().strip() or "Town03",
            "--practical-weather",
            self.practical_weather_var.get().strip() or "clear_noon",
            "--practical-traffic",
            self.practical_traffic_var.get().strip() or "moderate",
            "--practical-route",
            self.practical_route_var.get().strip() or "urban_loop",
        ]
        if self.practical_custom_enabled_var.get():
            args.append("--practical-custom-enabled")
            vehicle_count = self.practical_custom_vehicle_count_var.get().strip()
            pedestrian_count = self.practical_custom_pedestrian_count_var.get().strip()
            route_length = self.practical_custom_route_length_var.get().strip()
            junction_focus = self.practical_custom_junction_focus_var.get().strip()
            custom_note = self.practical_custom_note_entry_var.get().strip()
            if vehicle_count:
                args.extend(["--practical-custom-vehicle-count", vehicle_count])
            if pedestrian_count:
                args.extend(["--practical-custom-pedestrian-count", pedestrian_count])
            if route_length:
                args.extend(["--practical-custom-route-length", route_length])
            if junction_focus:
                args.extend(["--practical-custom-junction-focus", junction_focus])
            if custom_note:
                args.extend(["--practical-custom-note", custom_note])
        integration_kwargs = self._integration_kwargs()
        if integration_kwargs["integration_custom_enabled"]:
            args.append("--integration-custom-enabled")
            preferred_blueprint_id = self.preferred_blueprint_id_var.get().strip()
            role_name = self.vehicle_role_name_var.get().strip()
            driver_backend = self.driver_backend_var.get().strip() or "manual"
            vehicle_config_path = self.vehicle_config_path_var.get().strip()
            driver_module_path = self.driver_module_path_var.get().strip()
            external_command = self.external_driver_command_var.get().strip()
            external_working_dir = self.external_driver_working_dir_var.get().strip()
            startup_wait = self.external_driver_startup_wait_var.get().strip()
            if preferred_blueprint_id:
                args.extend(["--preferred-blueprint-id", preferred_blueprint_id])
            if role_name:
                args.extend(["--role-name", role_name])
            args.extend(["--driver-backend", driver_backend])
            if vehicle_config_path:
                args.extend(["--vehicle-config-path", vehicle_config_path])
            if driver_backend == "external_module" and driver_module_path:
                args.extend(["--driver-module-path", driver_module_path])
            if driver_backend == "external_command":
                if external_command:
                    args.extend(["--external-driver-command", external_command])
                if external_working_dir:
                    args.extend(["--external-driver-working-dir", external_working_dir])
                if startup_wait:
                    args.extend(["--external-driver-startup-wait", startup_wait])
        pythonapi_path = self.pythonapi_var.get().strip()
        if pythonapi_path:
            args.extend(["--pythonapi-path", pythonapi_path])
        return args

    def refresh_session_summary(self) -> None:
        session = build_current_manual_demo_session(
            session_name=self.session_name_var.get().strip() or "aed_manual_sequence_session",
            pythonapi_path=self.pythonapi_var.get().strip() or None,
            training_stage=self.training_stage_var.get().strip() or TRACK_STAGE_ID,
            practical_town=self.practical_town_var.get().strip() or "Town03",
            practical_weather=self.practical_weather_var.get().strip() or "clear_noon",
            practical_traffic=self.practical_traffic_var.get().strip() or "moderate",
            practical_route=self.practical_route_var.get().strip() or "urban_loop",
            **self._practical_custom_kwargs(),
            **self._integration_kwargs(),
        )
        self.summary_text.set(format_session_summary(session))
        self._set_status("Session summary refreshed.")

    def _preview_result_path(self, path: Path | None) -> None:
        if path is None:
            preview = "Select a result file to preview it here."
            self.result_score_var.set("Score: -")
        else:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as error:
                preview = f"Failed to load result file.\nReason: {error}"
                self.result_score_var.set("Score: unavailable")
            else:
                preview = json.dumps(payload, indent=2, ensure_ascii=False)
                self._update_result_score(payload)
        self.result_preview.configure(state="normal")
        self.result_preview.delete("1.0", "end")
        self.result_preview.insert("1.0", preview)
        self.result_preview.configure(state="disabled")

    def _update_result_score(self, payload: dict[str, object]) -> None:
        try:
            result = EpisodeResult.from_dict(payload)
            score = compute_driving_score(
                completion_ratio=result.completion_ratio,
                path_tracking_score=result.path_tracking_score,
                crossed_finish_line=result.crossed_finish_line,
                offroad_ratio=result.offroad_ratio,
                collision_count=result.collision_count,
                failure_reason=result.failure_reason,
                success=result.success,
                lane_discipline_score=result.lane_discipline_score,
                lane_departure_ratio=result.lane_departure_ratio,
                opposite_lane_ratio=result.opposite_lane_ratio,
            )
        except Exception:
            self.result_score_var.set("Score: unavailable")
            return

        outcome = "success" if result.success else str(result.failure_reason or "review")
        outcome = outcome.replace("_", " ")
        self.result_score_var.set(f"Score: {score * 100.0:5.1f} / 100   {outcome}")

    def refresh_result_list(self, *, select_latest: bool = False) -> None:
        self.results_dir = self._active_results_dir()
        self.results_dir.mkdir(parents=True, exist_ok=True)
        selected_result_name = None
        selection = self.results_listbox.curselection()
        if selection:
            index = selection[0]
            if 0 <= index < len(self._recent_results):
                selected_result_name = self._recent_results[index].name

        self.results_listbox.delete(0, "end")
        self._recent_results = sorted(
            self.results_dir.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        visible_results = self._recent_results[:20]
        for path in visible_results:
            self.results_listbox.insert("end", path.name)

        target_index = None
        if selected_result_name is not None:
            for index, path in enumerate(visible_results):
                if path.name == selected_result_name:
                    target_index = index
                    break
        if target_index is None and select_latest and visible_results:
            target_index = 0

        self.results_listbox.selection_clear(0, "end")
        if target_index is not None:
            self.results_listbox.selection_set(target_index)
            self.results_listbox.activate(target_index)
            self.results_listbox.see(target_index)
            self._preview_result_path(visible_results[target_index])
        else:
            self._preview_result_path(None)

        self._set_status("Result list refreshed.")

    def _on_result_selected(self, _event: object) -> None:
        selection = self.results_listbox.curselection()
        if not selection:
            self._preview_result_path(None)
            return
        index = selection[0]
        if index < 0 or index >= len(self._recent_results):
            self._preview_result_path(None)
            return
        self._preview_result_path(self._recent_results[index])

    def _start_process(self, command_label: str, extra_args: list[str]) -> None:
        if self.current_process is not None and self.current_process.poll() is None:
            messagebox.showwarning(
                APP_TITLE,
                "A process is already running. Stop it before starting another one.",
            )
            return

        launcher_path = Path(__file__).resolve().parent / "launcher.py"
        command = build_launcher_subprocess_command(launcher_path, extra_args)
        self._append_log(f"\n>>> Starting {command_label}\n{' '.join(command)}\n")
        self.current_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(self.base_dir),
        )
        self.current_process_label = command_label
        self._set_status(f"Running: {command_label}")
        threading.Thread(
            target=self._read_process_output,
            args=(self.current_process,),
            daemon=True,
        ).start()

    def _ensure_track_stage(self, action_label: str) -> bool:
        stage_option = self._active_stage()
        if stage_option.stage_id == TRACK_STAGE_ID:
            return True
        messagebox.showinfo(
            APP_TITLE,
            (
                f"{stage_option.display_name} is not connected yet.\n\n"
                f"'{action_label}' currently belongs to the Track Driving Stage workflow."
            ),
        )
        self._set_status(
            f"{action_label} is reserved for Track Driving Stage until the next workflow is connected."
        )
        return False

    def _ensure_generation_stage(self, action_label: str) -> bool:
        stage_option = self._active_stage()
        if stage_option.stage_id in {TRACK_STAGE_ID, "intermediate"}:
            return True
        messagebox.showinfo(
            APP_TITLE,
            (
                f"{stage_option.display_name} is not connected yet.\n\n"
                f"'{action_label}' is available in Track Driving Stage and Intermediate Road Stage."
            ),
        )
        self._set_status(
            f"{action_label} is reserved until the selected stage has a connected generation workflow."
        )
        return False

    def _ensure_practical_stage(self, action_label: str) -> bool:
        stage_option = self._active_stage()
        if stage_option.stage_id == PRACTICAL_STAGE_ID:
            return True
        messagebox.showinfo(
            APP_TITLE,
            (
                f"{action_label} belongs to the Practical Road Stage workflow.\n\n"
                "Switch the stage selector to Practical Road Stage first."
            ),
        )
        self._set_status(f"{action_label} is reserved for Practical Road Stage.")
        return False

    def open_integration_settings(self) -> None:
        if self.integration_settings_window is not None and self.integration_settings_window.winfo_exists():
            self.integration_settings_window.focus_force()
            return

        dialog = tk.Toplevel(self)
        dialog.title("Vehicle / Driver Integration Settings")
        dialog.geometry("640x700")
        dialog.minsize(600, 660)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(background=self.palette["surface"])
        self.integration_settings_window = dialog

        preferred_blueprint_var = tk.StringVar(value=self.preferred_blueprint_id_var.get().strip())
        role_name_var = tk.StringVar(value=self.vehicle_role_name_var.get().strip())
        driver_backend_var = tk.StringVar(value=self.driver_backend_var.get().strip() or "manual")
        vehicle_config_path_var = tk.StringVar(value=self.vehicle_config_path_var.get().strip())
        driver_module_path_var = tk.StringVar(value=self.driver_module_path_var.get().strip())
        external_command_var = tk.StringVar(value=self.external_driver_command_var.get().strip())
        external_working_dir_var = tk.StringVar(value=self.external_driver_working_dir_var.get().strip())
        startup_wait_var = tk.StringVar(value=self.external_driver_startup_wait_var.get().strip() or "2.0")

        body = ttk.Frame(dialog, style="Panel.TFrame", padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(
            body,
            text=(
                "Use this window when you want the AED app to keep spawning the ego vehicle, but let you "
                "override the vehicle setup and/or the driving backend. You can set only a vehicle file, "
                "only a driver module/command, or both together. Any field you leave blank falls back to "
                "the built-in default."
            ),
            style="Muted.TLabel",
            wraplength=540,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(body, text="Preferred Blueprint ID", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        preferred_blueprint_entry = ttk.Entry(body, textvariable=preferred_blueprint_var, width=26)
        preferred_blueprint_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(body, text="Vehicle Config File", style="Body.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        vehicle_config_entry = ttk.Entry(body, textvariable=vehicle_config_path_var, width=26)
        vehicle_config_entry.grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Button(
            body,
            text="Browse",
            style="Ghost.TButton",
            command=lambda: self._browse_vehicle_config_path(vehicle_config_path_var),
        ).grid(row=3, column=2, padx=(8, 0), pady=4)

        ttk.Label(body, text="Role Name", style="Body.TLabel").grid(row=4, column=0, sticky="w", pady=4)
        role_name_entry = ttk.Entry(body, textvariable=role_name_var, width=26)
        role_name_entry.grid(row=4, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(body, text="Driver Backend", style="Body.TLabel").grid(row=5, column=0, sticky="w", pady=4)
        driver_backend_combo = ttk.Combobox(
            body,
            textvariable=driver_backend_var,
            values=DRIVER_BACKEND_CHOICES,
            state="readonly",
            width=22,
        )
        driver_backend_combo.grid(row=5, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(body, text="Driver Module File", style="Body.TLabel").grid(row=6, column=0, sticky="w", pady=4)
        driver_module_entry = ttk.Entry(body, textvariable=driver_module_path_var, width=26)
        driver_module_entry.grid(row=6, column=1, sticky="ew", pady=4)
        ttk.Button(
            body,
            text="Browse",
            style="Ghost.TButton",
            command=lambda: self._browse_driver_module_path(driver_module_path_var, driver_backend_var),
        ).grid(row=6, column=2, padx=(8, 0), pady=4)

        ttk.Label(body, text="External Launch Command", style="Body.TLabel").grid(row=7, column=0, sticky="w", pady=4)
        external_command_entry = ttk.Entry(body, textvariable=external_command_var, width=26)
        external_command_entry.grid(row=7, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(body, text="Working Directory", style="Body.TLabel").grid(row=8, column=0, sticky="w", pady=4)
        external_working_dir_entry = ttk.Entry(body, textvariable=external_working_dir_var, width=26)
        external_working_dir_entry.grid(row=8, column=1, sticky="ew", pady=4)
        ttk.Button(
            body,
            text="Browse",
            style="Ghost.TButton",
            command=lambda: self._browse_external_driver_working_dir(external_working_dir_var),
        ).grid(row=8, column=2, padx=(8, 0), pady=4)

        ttk.Label(body, text="Startup Wait (s)", style="Body.TLabel").grid(row=9, column=0, sticky="w", pady=4)
        startup_wait_entry = ttk.Entry(body, textvariable=startup_wait_var, width=26)
        startup_wait_entry.grid(row=9, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(
            body,
            text=(
                "The app still owns Town/XODR loading, ego spawn, evaluation, and result saving. "
                "A vehicle JSON can override blueprint/color/role, while a Python driver module can "
                "override the built-in keyboard mapping for a quick integration check."
            ),
            style="Muted.TLabel",
            wraplength=540,
            justify="left",
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Label(
            body,
            text=(
                "Environment variables exported to the external command include AED_HOST, AED_PORT, "
                "AED_EGO_ROLE_NAME, AED_TRAINING_STAGE, and stage-specific paths such as AED_XODR_PATH "
                "or AED_SCENARIO_PATH. For file-based quick tests, choose Driver Backend = external_module."
            ),
            style="Muted.TLabel",
            wraplength=540,
            justify="left",
        ).grid(row=11, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(
            body,
            text=(
                "Current baseline applies to the main app-owned driving flows: Run Selected XODR, "
                "Generate + Drive, and Practical Scenario run. Legacy sequence/track demo buttons remain "
                "manual in this prototype."
            ),
            style="Muted.TLabel",
            wraplength=540,
            justify="left",
        ).grid(row=12, column=0, columnspan=3, sticky="w", pady=(8, 0))

        button_bar = ttk.Frame(body, style="Panel.TFrame")
        button_bar.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        button_bar.columnconfigure(0, weight=1)
        button_bar.columnconfigure(1, weight=1)
        button_bar.columnconfigure(2, weight=1)

        def refresh_dialog_state() -> None:
            preferred_blueprint_entry.configure(state="normal")
            vehicle_config_entry.configure(state="normal")
            role_name_entry.configure(state="normal")
            driver_backend_combo.configure(state="readonly")
            driver_module_entry.configure(state="normal")
            external_command_entry.configure(state="normal")
            external_working_dir_entry.configure(state="normal")
            startup_wait_entry.configure(state="normal")

        def close_dialog() -> None:
            if dialog.winfo_exists():
                dialog.grab_release()
                dialog.destroy()
            self.integration_settings_window = None

        def save_dialog() -> None:
            normalized_role_name = role_name_var.get().strip()
            normalized_driver_backend = driver_backend_var.get().strip() or "manual"
            vehicle_config_text = vehicle_config_path_var.get().strip()
            driver_module_text = driver_module_path_var.get().strip()
            external_command_text = external_command_var.get().strip()
            if normalized_driver_backend == "manual":
                if driver_module_text:
                    normalized_driver_backend = "external_module"
                elif external_command_text:
                    normalized_driver_backend = "external_command"
            if vehicle_config_text and not Path(vehicle_config_text).exists():
                messagebox.showerror(
                    APP_TITLE,
                    "Vehicle Config File does not exist.",
                    parent=dialog,
                )
                return
            if normalized_driver_backend == "external_module":
                if not driver_module_text:
                    messagebox.showerror(
                        APP_TITLE,
                        "Driver Module File must be provided when Driver Backend is external_module.",
                        parent=dialog,
                    )
                    return
                if not Path(driver_module_text).exists():
                    messagebox.showerror(
                        APP_TITLE,
                        "Driver Module File does not exist.",
                        parent=dialog,
                    )
                    return
            if normalized_driver_backend == "external_command":
                if not external_command_text:
                    messagebox.showerror(
                        APP_TITLE,
                        "External Launch Command must be provided when Driver Backend is external_command.",
                        parent=dialog,
                    )
                    return
                startup_wait_text = startup_wait_var.get().strip() or "0"
                try:
                    startup_wait_value = float(startup_wait_text)
                except ValueError:
                    messagebox.showerror(
                        APP_TITLE,
                        "Startup Wait must be a valid number.",
                        parent=dialog,
                    )
                    return
                if startup_wait_value < 0.0:
                    messagebox.showerror(
                        APP_TITLE,
                        "Startup Wait cannot be negative.",
                        parent=dialog,
                    )
                    return
            integration_active = bool(
                vehicle_config_text
                or preferred_blueprint_var.get().strip()
                or normalized_role_name
                or driver_module_text
                or normalized_driver_backend != "manual"
                or external_command_text
            )
            self.integration_custom_enabled_var.set(integration_active)
            self.preferred_blueprint_id_var.set(preferred_blueprint_var.get().strip())
            self.vehicle_role_name_var.set(normalized_role_name)
            self.driver_backend_var.set(normalized_driver_backend)
            self.vehicle_config_path_var.set(vehicle_config_path_var.get().strip())
            self.driver_module_path_var.set(driver_module_path_var.get().strip())
            self.external_driver_command_var.set(external_command_var.get().strip())
            self.external_driver_working_dir_var.set(external_working_dir_var.get().strip())
            self.external_driver_startup_wait_var.set(startup_wait_var.get().strip() or "2.0")
            self._refresh_integration_summary()
            self.refresh_session_summary()
            self._set_status("Vehicle / driver integration settings saved.")
            close_dialog()

        def reset_to_default() -> None:
            self.integration_custom_enabled_var.set(False)
            self.preferred_blueprint_id_var.set("")
            self.vehicle_role_name_var.set("")
            self.driver_backend_var.set("manual")
            self.vehicle_config_path_var.set("")
            self.driver_module_path_var.set("")
            self.external_driver_command_var.set("")
            self.external_driver_working_dir_var.set("")
            self.external_driver_startup_wait_var.set("2.0")
            self._refresh_integration_summary()
            self.refresh_session_summary()
            self._set_status("Vehicle / driver integration settings reset to the built-in default.")
            close_dialog()

        ttk.Button(
            button_bar,
            text="Use Built-in Default",
            style="Ghost.TButton",
            command=reset_to_default,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(
            button_bar,
            text="Cancel",
            style="Ghost.TButton",
            command=close_dialog,
        ).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(
            button_bar,
            text="Save Settings",
            style="Accent.TButton",
            command=save_dialog,
        ).grid(row=0, column=2, sticky="ew", padx=(8, 0))

        driver_backend_var.trace_add("write", lambda *_args: refresh_dialog_state())
        refresh_dialog_state()
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.focus_force()

    def open_practical_custom_settings(self) -> None:
        if not self._ensure_practical_stage("Open Custom Scenario Settings"):
            return
        if self.practical_custom_window is not None and self.practical_custom_window.winfo_exists():
            self.practical_custom_window.focus_force()
            return

        traffic_option = resolve_practical_traffic(self.practical_traffic_var.get())
        route_option = resolve_practical_route(self.practical_route_var.get())

        dialog = tk.Toplevel(self)
        dialog.title("Practical Custom Scenario Settings")
        dialog.geometry("520x420")
        dialog.minsize(500, 380)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(background=self.palette["surface"])
        self.practical_custom_window = dialog

        enabled_var = tk.BooleanVar(value=self.practical_custom_enabled_var.get())
        vehicle_var = tk.StringVar(
            value=self.practical_custom_vehicle_count_var.get().strip()
        )
        pedestrian_var = tk.StringVar(
            value=self.practical_custom_pedestrian_count_var.get().strip()
        )
        route_length_var = tk.StringVar(
            value=self.practical_custom_route_length_var.get().strip()
        )
        junction_focus_var = tk.StringVar(
            value=(self.practical_custom_junction_focus_var.get().strip() or "auto")
        )
        note_var = tk.StringVar(value=self.practical_custom_note_entry_var.get().strip())

        body = ttk.Frame(dialog, style="Panel.TFrame", padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(
            body,
            text=(
                "Use this window when you want to pin only specific Practical scenario values yourself. "
                "Any field left blank stays under automatic adaptation from the previous result."
            ),
            style="Muted.TLabel",
            wraplength=440,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Checkbutton(
            body,
            text="Use custom Practical scenario settings for the next run",
            variable=enabled_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 10))

        ttk.Label(body, text="Vehicle Count", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        vehicle_entry = ttk.Entry(body, textvariable=vehicle_var, width=20)
        vehicle_entry.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(body, text="Pedestrian Count", style="Body.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        pedestrian_entry = ttk.Entry(body, textvariable=pedestrian_var, width=20)
        pedestrian_entry.grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(body, text="Route Length (m)", style="Body.TLabel").grid(row=4, column=0, sticky="w", pady=4)
        route_length_entry = ttk.Entry(body, textvariable=route_length_var, width=20)
        route_length_entry.grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(body, text="Junction Focus", style="Body.TLabel").grid(row=5, column=0, sticky="w", pady=4)
        junction_combo = ttk.Combobox(
            body,
            textvariable=junction_focus_var,
            values=("auto", *practical_junction_focus_choices()),
            state="readonly",
            width=18,
        )
        junction_combo.grid(row=5, column=1, sticky="ew", pady=4)

        ttk.Label(body, text="Scenario Note", style="Body.TLabel").grid(row=6, column=0, sticky="w", pady=4)
        note_entry = ttk.Entry(body, textvariable=note_var, width=20)
        note_entry.grid(row=6, column=1, sticky="ew", pady=4)

        ttk.Label(
            body,
            text=(
                "Town, weather, traffic preset, and route preset are still selected in the main "
                "panel. Leave a field blank, or keep Junction Focus on 'auto', to let the app "
                "adapt that field automatically."
            ),
            style="Muted.TLabel",
            wraplength=440,
            justify="left",
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))

        button_bar = ttk.Frame(body, style="Panel.TFrame")
        button_bar.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        button_bar.columnconfigure(0, weight=1)
        button_bar.columnconfigure(1, weight=1)
        button_bar.columnconfigure(2, weight=1)

        def refresh_dialog_state() -> None:
            state = "normal" if enabled_var.get() else "disabled"
            readonly_state = "readonly" if enabled_var.get() else "disabled"
            vehicle_entry.configure(state=state)
            pedestrian_entry.configure(state=state)
            route_length_entry.configure(state=state)
            note_entry.configure(state=state)
            junction_combo.configure(state=readonly_state)

        def close_dialog() -> None:
            if dialog.winfo_exists():
                dialog.grab_release()
                dialog.destroy()
            self.practical_custom_window = None

        def save_dialog() -> None:
            if enabled_var.get():
                vehicle_text = vehicle_var.get().strip()
                pedestrian_text = pedestrian_var.get().strip()
                route_length_text = route_length_var.get().strip()
                if vehicle_text:
                    try:
                        vehicle_count = int(vehicle_text)
                    except ValueError:
                        messagebox.showerror(
                            APP_TITLE,
                            "Vehicle count must be a valid integer when provided.",
                            parent=dialog,
                        )
                        return
                    if vehicle_count < 0:
                        messagebox.showerror(
                            APP_TITLE,
                            "Vehicle count cannot be negative.",
                            parent=dialog,
                        )
                        return
                if pedestrian_text:
                    try:
                        pedestrian_count = int(pedestrian_text)
                    except ValueError:
                        messagebox.showerror(
                            APP_TITLE,
                            "Pedestrian count must be a valid integer when provided.",
                            parent=dialog,
                        )
                        return
                    if pedestrian_count < 0:
                        messagebox.showerror(
                            APP_TITLE,
                            "Pedestrian count cannot be negative.",
                            parent=dialog,
                        )
                        return
                if route_length_text:
                    try:
                        route_length = int(route_length_text)
                    except ValueError:
                        messagebox.showerror(
                            APP_TITLE,
                            "Route length must be a valid integer when provided.",
                            parent=dialog,
                        )
                        return
                    if route_length < 100:
                        messagebox.showerror(
                            APP_TITLE,
                            "Route length should be at least 100 meters for the Practical Stage shell.",
                            parent=dialog,
                        )
                        return
            self.practical_custom_enabled_var.set(enabled_var.get())
            self.practical_custom_vehicle_count_var.set(vehicle_var.get().strip())
            self.practical_custom_pedestrian_count_var.set(pedestrian_var.get().strip())
            self.practical_custom_route_length_var.set(route_length_var.get().strip())
            selected_junction_focus = junction_focus_var.get().strip().lower()
            self.practical_custom_junction_focus_var.set("" if selected_junction_focus == "auto" else selected_junction_focus)
            self.practical_custom_note_entry_var.set(note_var.get().strip())
            self._refresh_practical_custom_summary()
            self.refresh_session_summary()
            self._set_status("Practical custom scenario settings saved.")
            close_dialog()

        def reset_to_auto() -> None:
            self.practical_custom_enabled_var.set(False)
            self.practical_custom_vehicle_count_var.set("")
            self.practical_custom_pedestrian_count_var.set("")
            self.practical_custom_route_length_var.set("")
            self.practical_custom_junction_focus_var.set("")
            self.practical_custom_note_entry_var.set("")
            self._refresh_practical_custom_summary()
            self.refresh_session_summary()
            self._set_status("Practical custom scenario settings reset to automatic adaptation.")
            close_dialog()

        ttk.Button(
            button_bar,
            text="Use Automatic Adaptation",
            style="Ghost.TButton",
            command=reset_to_auto,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(
            button_bar,
            text="Cancel",
            style="Ghost.TButton",
            command=close_dialog,
        ).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(
            button_bar,
            text="Save Settings",
            style="Accent.TButton",
            command=save_dialog,
        ).grid(row=0, column=2, sticky="ew", padx=(8, 0))

        enabled_var.trace_add("write", lambda *_args: refresh_dialog_state())
        refresh_dialog_state()
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.focus_force()

    def run_manual_sequence(self) -> None:
        if not self._ensure_track_stage("Run Manual Sequence"):
            return
        extra_args = [
            "manual-sequence",
            "--map-id",
            self.map_id_var.get().strip() or "aed_sequence_demo",
            "--spectator-mode",
            self.spectator_mode_var.get(),
            *self._runtime_args(),
        ]
        if self.keep_vehicle_var.get():
            extra_args.append("--keep-vehicle")
        self._start_process("manual-sequence", extra_args)

    def run_manual_track(self) -> None:
        if not self._ensure_track_stage("Run Manual Track"):
            return
        extra_args = [
            "manual-track",
            "--map-id",
            self.map_id_var.get().strip() or "aed_manual_track_demo",
            "--spectator-mode",
            self.spectator_mode_var.get(),
            *self._runtime_args(),
        ]
        if self.keep_vehicle_var.get():
            extra_args.append("--keep-vehicle")
        self._start_process("manual-track", extra_args)

    def load_local_xodr(self) -> None:
        xodr_path = self.xodr_path_var.get().strip()
        if not xodr_path:
            messagebox.showinfo(APP_TITLE, "Select an .xodr file first.")
            return
        extra_args = [
            "load-xodr",
            "--xodr-path",
            xodr_path,
            *self._runtime_args(),
        ]
        self._start_process("load-xodr", extra_args)

    def run_manual_xodr(self) -> None:
        xodr_path = self.xodr_path_var.get().strip()
        if not xodr_path:
            messagebox.showinfo(
                APP_TITLE,
                "Select or generate an .xodr file first.",
            )
            return
        extra_args = [
            "manual-xodr",
            "--xodr-path",
            xodr_path,
            "--spectator-mode",
            self.spectator_mode_var.get(),
            *self._runtime_args(),
        ]
        if self.keep_vehicle_var.get():
            extra_args.append("--keep-vehicle")
        self._start_process("manual-xodr", extra_args)

    def load_practical_town(self) -> None:
        if not self._ensure_practical_stage("Load Selected Town"):
            return
        extra_args = [
            "load-town",
            *self._runtime_args(),
        ]
        self._start_process("load-town", extra_args)

    def generate_practical_scenario(self) -> None:
        if not self._ensure_practical_stage("Generate Practical Scenario"):
            return
        self._start_practical_scenario_generation(autorun=False)

    def generate_and_run_practical_scenario(self) -> None:
        if not self._ensure_practical_stage("Generate + Run Practical Scenario"):
            return
        self._start_practical_scenario_generation(autorun=True)

    def _start_practical_scenario_generation(self, *, autorun: bool) -> None:
        self._pending_practical_autorun = autorun
        extra_args = [
            "generate-practical-scenario",
            *self._runtime_args(),
        ]
        selected_result_path = self._selected_result_path()
        if selected_result_path is not None:
            extra_args.extend(["--result-path", str(selected_result_path)])
        self._start_process("generate-practical-scenario", extra_args)

    def _launch_practical_scenario_from_current_path(self) -> bool:
        scenario_path = self.practical_scenario_path_var.get().strip()
        if not scenario_path:
            self._fill_latest_practical_scenario()
            scenario_path = self.practical_scenario_path_var.get().strip()
        if not scenario_path:
            return False
        extra_args = [
            "run-practical-scenario",
            "--scenario-path",
            scenario_path,
            "--spectator-mode",
            self.spectator_mode_var.get(),
            *self._runtime_args(),
        ]
        if self.keep_vehicle_var.get():
            extra_args.append("--keep-vehicle")
        self._start_process("run-practical-scenario", extra_args)
        return True

    def run_practical_scenario(self) -> None:
        if not self._ensure_practical_stage("Run Practical Scenario"):
            return
        if not self._launch_practical_scenario_from_current_path():
            self._append_log(
                "\n>>> No prepared Practical scenario was found. Generating one automatically before launch.\n"
            )
            self._set_status("No Practical scenario was prepared yet. Generating one automatically.")
            self._start_practical_scenario_generation(autorun=True)
            return
        self._pending_practical_autorun = False

    def _selected_result_path(self) -> Path | None:
        selection = self.results_listbox.curselection()
        if not selection:
            return None
        index = selection[0]
        if index < 0 or index >= len(self._recent_results):
            return None
        return self._recent_results[index]

    def _fill_latest_generated_xodr(self) -> None:
        prefix = self.auto_map_prefix_var.get().strip() or "aed_auto_generated"
        generated_dir = self.base_dir / "maps" / "generated"
        candidates = sorted(
            generated_dir.glob(f"{prefix}_*.xodr"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            self.xodr_path_var.set(str(candidates[0]))

    def generate_next_map(self, *, load_after_generate: bool) -> None:
        if not self._ensure_generation_stage("Generate Next Map"):
            return
        extra_args = [
            "generate-next-map",
            "--map-prefix",
            self.auto_map_prefix_var.get().strip() or "aed_auto_generated",
            *self._runtime_args(),
        ]
        selected_result_path = self._selected_result_path()
        if selected_result_path is not None:
            extra_args.extend(["--result-path", str(selected_result_path)])
        if load_after_generate:
            extra_args.append("--load-after-generate")
        self._start_process(
            "generate-next-map-load" if load_after_generate else "generate-next-map",
            extra_args,
        )

    def generate_and_drive_next_map(self) -> None:
        if not self._ensure_generation_stage("Generate + Drive Next Map"):
            return
        extra_args = [
            "generate-next-map",
            "--map-prefix",
            self.auto_map_prefix_var.get().strip() or "aed_auto_generated",
            "--manual-drive-after-generate",
            "--spectator-mode",
            self.spectator_mode_var.get(),
            *self._runtime_args(),
        ]
        selected_result_path = self._selected_result_path()
        if selected_result_path is not None:
            extra_args.extend(["--result-path", str(selected_result_path)])
        if self.keep_vehicle_var.get():
            extra_args.append("--keep-vehicle")
        self._start_process("generate-next-map-drive", extra_args)

    def stop_current_process(self) -> None:
        if self.current_process is None or self.current_process.poll() is not None:
            self._set_status("No running process.")
            return
        self.current_process.terminate()
        self._append_log(f"\n>>> Stopped {self.current_process_label}\n")
        self._set_status(f"Stopped: {self.current_process_label}")

    def _read_process_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            self.output_queue.put(line)

    def _poll_process_output(self) -> None:
        while True:
            try:
                line = self.output_queue.get_nowait()
            except queue.Empty:
                break
            else:
                self._append_log(line)

        if self.current_process is not None:
            return_code = self.current_process.poll()
            if return_code is not None:
                finished_label = self.current_process_label
                self._append_log(
                    f"\n>>> Process finished ({finished_label}) with code {return_code}\n"
                )
                self._set_status(f"Finished: {finished_label} (code {return_code})")
                if return_code == 0 and finished_label.startswith("generate-next-map"):
                    self._fill_latest_generated_xodr()
                if return_code == 0 and finished_label == "generate-practical-scenario":
                    self._fill_latest_practical_scenario()
                    if self._pending_practical_autorun:
                        self._pending_practical_autorun = False
                        if self._launch_practical_scenario_from_current_path():
                            self.current_process = None
                            self.current_process_label = "Idle"
                            self.refresh_result_list(select_latest=False)
                            self.after(150, self._poll_process_output)
                            return
                elif finished_label == "generate-practical-scenario":
                    self._pending_practical_autorun = False
                select_latest_result = (
                    return_code == 0
                    and finished_label in {
                        "manual-sequence",
                        "manual-xodr",
                        "generate-next-map-drive",
                        "run-practical-scenario",
                    }
                )
                self.current_process = None
                self.current_process_label = "Idle"
                self.refresh_result_list(select_latest=select_latest_result)

        self.after(150, self._poll_process_output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the AED tkinter application shell.",
    )
    parser.add_argument(
        "--pythonapi-path",
        default=None,
        help="Optional CARLA PythonAPI path to pre-fill in the UI.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = AppShell(pythonapi_path=args.pythonapi_path)
    app.mainloop()


if __name__ == "__main__":
    main()
