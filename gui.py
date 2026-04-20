from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from automation import AutomationEngine, discover_window_titles
from config_loader import resolve_resource_path


class AutomationApp:
    def __init__(self, config: dict) -> None:
        self.config = config
        theme = config.get("theme", {})
        self.bg = theme.get("background", "#171717")
        self.fg = theme.get("foreground", "#dddddd")
        self.accent = theme.get("accent", "#FFBF00")
        self.input_bg = theme.get("input_background", "#333333")
        self.card_bg = "#202020"
        self.muted_fg = "#a7a7a7"
        self.button_bg = "#2b6ef2"
        self.button_fg = "#ffffff"
        self.button_disabled_bg = "#3b3b3b"
        self.button_disabled_fg = "#9b9b9b"

        self.root = tk.Tk()
        self.root.title(config["app"].get("title", "Evento 2026 Automator"))
        window = config["ui"].get("window", {})
        self.root.geometry(window.get("geometry", "500x860"))
        self.root.minsize(*window.get("min_size", [500, 860]))
        self.root.config(bg=self.bg)
        self.root.option_add("*Font", "Helvetica 10")

        icon_path = resolve_resource_path(config, config["ui"].get("icon"))
        if icon_path and icon_path.exists():
            self.root.iconbitmap(str(icon_path))

        self.title_name = ""
        self.hint_window = None
        self.loaded_images = []
        self.template_status_labels: dict[str, tk.Label] = {}
        self.is_running = False

        self.mouse_speed_var = tk.StringVar(value=str(config["flow"]["timing"].get("mouse_sleep", 0.3)))
        self.screenshot_speed_var = tk.StringVar(value=str(config["flow"]["timing"].get("screenshot_sleep", 0.3)))
        self.loop_limit_var = tk.StringVar()
        self.move_window_var = tk.BooleanVar(value=True)
        self.input_mode_var = tk.StringVar(value=config["window"].get("input_mode", "pyautogui"))

        self._build_ui()

    def run(self) -> None:
        self.root.mainloop()

    def _build_ui(self) -> None:
        container = tk.Frame(self.root, bg=self.bg, padx=18, pady=16)
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure(0, weight=3)
        container.grid_columnconfigure(1, weight=2)
        container.grid_rowconfigure(1, weight=1)

        header = tk.Frame(container, bg=self.bg)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text=self.config["app"].get("title", "Evento 2026 Automator"),
            font=("Helvetica", 24, "bold"),
            bg=self.bg,
            fg=self.fg,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Loop automatico para Abismo Modo Desafio - Andar 2",
            font=("Helvetica", 11),
            bg=self.bg,
            fg=self.muted_fg,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        pill = tk.Label(
            header,
            text="ESC para parar",
            font=("Helvetica", 10, "bold"),
            bg="#2a2514",
            fg=self.accent,
            padx=12,
            pady=6,
        )
        pill.grid(row=0, column=1, rowspan=2, sticky="e")

        left_column = tk.Frame(container, bg=self.bg)
        left_column.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left_column.grid_columnconfigure(0, weight=1)

        right_column = tk.Frame(container, bg=self.bg)
        right_column.grid(row=1, column=1, sticky="nsew")
        right_column.grid_columnconfigure(0, weight=1)

        target_card = self._make_card(left_column)
        target_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._section_title(target_card, "Janela")
        tk.Label(
            target_card,
            text="Escolha a janela do jogo aberta no PC.",
            font=("Helvetica", 10),
            bg=self.card_bg,
            fg=self.muted_fg,
        ).pack(anchor="w")

        titles = discover_window_titles(self.config)
        self.title_combo = ttk.Combobox(target_card, values=titles, state="normal")
        self.title_combo.pack(fill="x", pady=(10, 0))
        self.title_combo.bind("<<ComboboxSelected>>", self._on_title_change)
        self.title_combo.bind("<KeyRelease>", self._on_title_change)
        if titles:
            self.title_name = titles[0]
            self.title_combo.set(titles[0])

        settings_card = self._make_card(left_column)
        settings_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self._section_title(settings_card, "Configuracoes")
        self._pack_checkbox("Mover janela para o canto superior esquerdo", self.move_window_var, settings_card)
        self._pack_select(
            "Modo de input",
            self.input_mode_var,
            ["sendinput_cursor", "pyautogui", "win32_cursor", "window_message"],
            settings_card,
        )
        self._pack_entry("Velocidade do mouse", self.mouse_speed_var, settings_card, suffix="s")
        self._pack_entry("Velocidade da captura", self.screenshot_speed_var, settings_card, suffix="s")
        self._pack_entry("Limite de loops", self.loop_limit_var, settings_card)

        status_card = self._make_card(left_column)
        status_card.grid(row=2, column=0, sticky="ew")
        self._section_title(status_card, "Status")
        self.status_label = tk.Label(
            status_card,
            text="Parado",
            font=("Helvetica", 12, "bold"),
            bg=self.card_bg,
            fg=self.accent,
        )
        self.status_label.pack(anchor="w")
        self.last_match_label = tk.Label(
            status_card,
            text="Ultimo template: -",
            font=("Helvetica", 10),
            bg=self.card_bg,
            fg=self.fg,
            wraplength=360,
            justify="left",
        )
        self.last_match_label.pack(anchor="w", pady=(10, 4))
        self.last_action_label = tk.Label(
            status_card,
            text="Ultima acao: -",
            font=("Helvetica", 10),
            bg=self.card_bg,
            fg=self.fg,
            wraplength=360,
            justify="left",
        )
        self.last_action_label.pack(anchor="w")

        assets_card = self._make_card(right_column)
        assets_card.grid(row=0, column=0, sticky="nsew")
        self._section_title(assets_card, "Templates")
        tk.Label(
            assets_card,
            text="Recortes usados para detectar cada tela do loop.",
            font=("Helvetica", 10),
            bg=self.card_bg,
            fg=self.muted_fg,
        ).pack(anchor="w", pady=(0, 10))

        assets_list = tk.Frame(assets_card, bg=self.card_bg)
        assets_list.pack(fill="both", expand=True)
        assets_dir = resolve_resource_path(self.config, self.config["app"].get("assets_dir", "assets"))
        for item in self.config.get("templates", []):
            self._pack_template(item, assets_dir, assets_list)

        footer = tk.Frame(container, bg=self.bg)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=1)

        tk.Label(
            footer,
            text="Quando o loop estiver rodando, nao mexa no jogo nem no mouse.",
            font=("Helvetica", 10),
            bg=self.bg,
            fg=self.muted_fg,
        ).grid(row=0, column=0, sticky="w", padx=(2, 16))

        self.start_button = tk.Button(
            footer,
            text="Iniciar Automacao",
            font=("Helvetica", 13, "bold"),
            command=self.start_automation,
            state=tk.NORMAL if self.title_name else tk.DISABLED,
            bg=self.button_bg,
            fg=self.button_fg,
            activebackground="#1f56bf",
            activeforeground=self.button_fg,
            relief="flat",
            bd=0,
            padx=18,
            pady=12,
            cursor="hand2",
        )
        self.start_button.grid(row=0, column=1, sticky="e")
        self._sync_start_button_state()

    def _make_card(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=self.card_bg, padx=14, pady=14, highlightthickness=1, highlightbackground="#2f2f2f")

    def _section_title(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            font=("Helvetica", 15, "bold"),
            bg=self.card_bg,
            fg=self.fg,
        ).pack(anchor="w", pady=(0, 10))

    def _pack_checkbox(self, text: str, variable: tk.Variable, parent: tk.Widget) -> None:
        frame = tk.Frame(parent, bg=self.card_bg)
        tk.Label(frame, text=text, font=("Helvetica", 11), bg=self.card_bg, fg=self.fg).pack(side=tk.LEFT)
        tk.Checkbutton(
            frame,
            variable=variable,
            bg=self.card_bg,
            activebackground=self.card_bg,
            selectcolor=self.card_bg,
        ).pack(side=tk.RIGHT)
        frame.pack(pady=4)

    def _pack_entry(self, label_text: str, variable: tk.StringVar, parent: tk.Widget, suffix: str = "") -> None:
        frame = tk.Frame(parent, bg=self.card_bg)
        tk.Label(frame, text=label_text, font=("Helvetica", 11), bg=self.card_bg, fg=self.fg).pack(side=tk.LEFT)
        right = tk.Frame(frame, bg=self.card_bg)
        entry = tk.Entry(
            right,
            textvariable=variable,
            bg=self.input_bg,
            fg=self.fg,
            relief="flat",
            insertbackground=self.fg,
            width=12,
        )
        entry.pack(side=tk.LEFT)
        if suffix:
            tk.Label(right, text=suffix, font=("Helvetica", 10), bg=self.card_bg, fg=self.muted_fg).pack(side=tk.LEFT, padx=(6, 0))
        right.pack(side=tk.RIGHT)
        frame.pack(fill="x", pady=4)

    def _pack_select(self, label_text: str, variable: tk.StringVar, options: list[str], parent: tk.Widget) -> None:
        frame = tk.Frame(parent, bg=self.card_bg)
        tk.Label(frame, text=label_text, font=("Helvetica", 11), bg=self.card_bg, fg=self.fg).pack(side=tk.LEFT)
        ttk.Combobox(frame, textvariable=variable, values=options, state="readonly", width=18).pack(side=tk.RIGHT)
        frame.pack(pady=4)

    def _pack_template(self, item: dict, assets_dir, parent: tk.Widget) -> None:
        frame = tk.Frame(parent, bg=self.card_bg, pady=5)
        image_path = assets_dir / item["path"] if assets_dir is not None else None
        preview = None
        if image_path is not None and image_path.exists():
            image = Image.open(image_path).resize((42, 42))
            preview = ImageTk.PhotoImage(image)
            self.loaded_images.append(preview)

        text = f"{item['name']}"
        label_text = text if preview is not None else f"{text} [missing]"
        label_color = self.fg if preview is not None else "#ff8a80"
        text_frame = tk.Frame(frame, bg=self.card_bg)
        tk.Label(text_frame, text=label_text, font=("Helvetica", 10, "bold"), bg=self.card_bg, fg=label_color).pack(anchor="w")
        tk.Label(text_frame, text=item["path"], font=("Helvetica", 9), bg=self.card_bg, fg=self.muted_fg).pack(anchor="w")
        text_frame.pack(side=tk.LEFT, fill="x", expand=True)
        if preview is not None:
            tk.Label(frame, image=preview, bg=self.accent).pack(side=tk.RIGHT)
        frame.pack(fill="x")

    def _on_title_change(self, _event=None) -> None:
        self.title_name = self.title_combo.get().strip()
        self._sync_start_button_state()

    def _sync_start_button_state(self) -> None:
        is_enabled = bool(self.title_name) and not self.is_running
        self.start_button.config(state=tk.NORMAL if is_enabled else tk.DISABLED)
        self.start_button.config(
            bg=self.button_bg if is_enabled else self.button_disabled_bg,
            fg=self.button_fg if is_enabled else self.button_disabled_fg,
            activebackground=self.button_bg if is_enabled else self.button_disabled_bg,
            activeforeground=self.button_fg if is_enabled else self.button_disabled_fg,
            cursor="hand2" if is_enabled else "arrow",
        )

    def start_automation(self) -> None:
        if not self.title_name:
            messagebox.showerror("Window", "Selecione a janela alvo.")
            return

        runtime_config = {
            **self.config,
            "window": {
                **self.config["window"],
                "input_mode": self.input_mode_var.get(),
            },
            "flow": {
                **self.config["flow"],
                "timing": {
                    **self.config["flow"]["timing"],
                    "mouse_sleep": float(self.mouse_speed_var.get() or 0.3),
                    "screenshot_sleep": float(self.screenshot_speed_var.get() or 0.3),
                },
            },
        }
        loop_limit = int(self.loop_limit_var.get()) if self.loop_limit_var.get().strip() else None

        self.is_running = True
        self._sync_start_button_state()
        self.status_label.config(text="Rodando")
        self.root.title("Press ESC to stop")

        self.engine = AutomationEngine(
            config=runtime_config,
            selected_title=self.title_name,
            budget=loop_limit,
            allow_move=not self.move_window_var.get(),
            ui_hooks={
                "on_step": self._on_step,
                "on_match": self._on_match,
                "on_action": self._on_action,
                "on_loop": self._on_loop,
                "on_stop": self._on_stop,
            },
        )
        self.engine.start()

    def _on_step(self, step_name: str) -> None:
        self.root.after(0, lambda: self.status_label.config(text=f"Etapa: {step_name}"))

    def _on_match(self, template_name: str) -> None:
        self.root.after(0, lambda: self.last_match_label.config(text=f"Ultimo template: {template_name}"))

    def _on_loop(self, loop_count: int) -> None:
        self.root.after(0, lambda: self.root.title(f"Press ESC to stop | Loop {loop_count}"))

    def _on_action(self, action: str) -> None:
        self.root.after(0, lambda: self.last_action_label.config(text=f"Ultima acao: {action}"))

    def _on_stop(self, error, stats) -> None:
        def finish():
            self.is_running = False
            self.root.title(self.config["app"].get("title", "Evento 2026 Automator"))
            self._sync_start_button_state()
            self.status_label.config(text=f"Parado | Loops: {stats.loop_count}")
            if error:
                messagebox.showerror("Automation stopped", str(error))

        self.root.after(0, finish)
