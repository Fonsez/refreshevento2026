from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from PIL import Image

from automation import AutomationEngine, discover_window_titles
from config_loader import resolve_resource_path

# Configure base theme
ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class AutomationApp:
    def __init__(self, config: dict) -> None:
        self.config = config
        
        self.root = ctk.CTk()
        self.root.title(config["app"].get("title", "Evento 2026 Automator"))
        window_cfg = config["ui"].get("window", {})
        self.root.geometry(window_cfg.get("geometry", "560x900"))
        self.root.minsize(*window_cfg.get("min_size", [500, 860]))

        icon_path = resolve_resource_path(config, config["ui"].get("icon"))
        if icon_path and icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        self.title_name = ""
        self.loaded_images = []
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
        self.container = ctk.CTkScrollableFrame(self.root, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        # Header
        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        
        title_label = ctk.CTkLabel(header, text=self.config["app"].get("title", "Evento 2026 Automator"), font=ctk.CTkFont(size=28, weight="bold"))
        title_label.pack(anchor="w")
        
        subtitle_label = ctk.CTkLabel(header, text="Loop automático para Abismo Modo Desafio - Andar 2", font=ctk.CTkFont(size=13), text_color="gray")
        subtitle_label.pack(anchor="w", pady=(0, 5))
        
        pill = ctk.CTkLabel(header, text="ESC para parar", fg_color="#F2A900", text_color="#1a1a1a", font=ctk.CTkFont(size=12, weight="bold"), corner_radius=6, padx=10, pady=4)
        pill.pack(anchor="w")

        # Layout grids
        content_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)

        left_column = ctk.CTkFrame(content_frame, fg_color="transparent")
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right_column = ctk.CTkFrame(content_frame, fg_color="transparent")
        right_column.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # Target Card
        target_card = self._make_card(left_column, "Janela Alvo")
        ctk.CTkLabel(target_card, text="Escolha a janela do jogo aberta no PC.", text_color="gray").pack(anchor="w", pady=(0, 10))
        
        titles = discover_window_titles(self.config)
        self.title_combo = ctk.CTkOptionMenu(target_card, values=titles if titles else ["Nenhuma janela encontrada"], command=self._on_title_change_menu)
        self.title_combo.pack(fill="x", pady=(0, 10))
        if titles:
            self.title_name = titles[0]
            self.title_combo.set(titles[0])

        # Settings Card
        settings_card = self._make_card(left_column, "Configurações")
        
        chk = ctk.CTkCheckBox(settings_card, text="Mover janela p/ canto superior", variable=self.move_window_var)
        chk.pack(anchor="w", pady=5)
        
        self._pack_select("Modo de input", self.input_mode_var, ["sendinput_cursor", "pyautogui", "win32_cursor", "window_message"], settings_card)
        self._pack_entry("Velocidade do mouse (s)", self.mouse_speed_var, settings_card)
        self._pack_entry("Velocidade da captura (s)", self.screenshot_speed_var, settings_card)
        self._pack_entry("Limite de loops (vazio=inf)", self.loop_limit_var, settings_card)

        # Status Card
        status_card = self._make_card(left_column, "Status")
        self.status_label = ctk.CTkLabel(status_card, text="Parado", font=ctk.CTkFont(size=18, weight="bold"), text_color="#F2A900")
        self.status_label.pack(anchor="w", pady=(0, 5))
        self.last_match_label = ctk.CTkLabel(status_card, text="Último template: -")
        self.last_match_label.pack(anchor="w")
        self.last_action_label = ctk.CTkLabel(status_card, text="Última ação: -")
        self.last_action_label.pack(anchor="w")

        # Assets Card
        assets_card = self._make_card(right_column, "Templates")
        ctk.CTkLabel(assets_card, text="Recortes usados para detecção", text_color="gray").pack(anchor="w", pady=(0, 10))

        assets_dir = resolve_resource_path(self.config, self.config["app"].get("assets_dir", "assets"))
        for item in self.config.get("templates", []):
            self._pack_template(item, assets_dir, assets_card)

        # Footer
        footer = ctk.CTkFrame(self.container, fg_color="transparent")
        footer.pack(fill="x", pady=(20, 0))
        ctk.CTkLabel(footer, text="Quando o loop estiver rodando, não mexa no jogo.", text_color="gray").pack(side="left")
        
        self.start_button = ctk.CTkButton(footer, text="Iniciar Automação", font=ctk.CTkFont(size=15, weight="bold"), height=45, fg_color="#2b6ef2", hover_color="#1f56bf", command=self.start_automation)
        self.start_button.pack(side="right")
        self._sync_start_button_state()

        # Keyboard bind for ESC
        self.root.bind("<Escape>", self._on_escape)

    def _on_escape(self, event=None):
        if self.is_running and hasattr(self, 'engine'):
            self.engine.stop()

    def _make_card(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill="x", pady=(0, 20))
        # padding inside
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=15, pady=15)
        ctk.CTkLabel(inner, text=title, font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 10))
        return inner

    def _pack_entry(self, label_text: str, variable: tk.StringVar, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(frame, text=label_text).pack(side="left")
        entry = ctk.CTkEntry(frame, textvariable=variable, width=80, corner_radius=6)
        entry.pack(side="right")
        frame.pack(fill="x", pady=5)

    def _pack_select(self, label_text: str, variable: tk.StringVar, options: list[str], parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(frame, text=label_text).pack(side="left")
        
        def menu_callback(choice):
            variable.set(choice)
            
        opt = ctk.CTkOptionMenu(frame, values=options, command=menu_callback, width=130, corner_radius=6)
        opt.set(variable.get())
        opt.pack(side="right")
        frame.pack(fill="x", pady=5)

    def _pack_template(self, item: dict, assets_dir, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        image_path = assets_dir / item["path"] if assets_dir is not None else None
        
        if image_path is not None and image_path.exists():
            my_image = ctk.CTkImage(light_image=Image.open(image_path), dark_image=Image.open(image_path), size=(42, 42))
            img_label = ctk.CTkLabel(frame, image=my_image, text="")
            img_label.image_ref = my_image # keep strong ref
            img_label.pack(side="right")
            color = "white"
            name = item["name"]
        else:
            color = "#ff8a80"
            name = item["name"] + " [missing]"

        text_frame = ctk.CTkFrame(frame, fg_color="transparent")
        ctk.CTkLabel(text_frame, text=name, font=ctk.CTkFont(weight="bold", size=12), text_color=color).pack(anchor="w")
        ctk.CTkLabel(text_frame, text=item["path"], font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        text_frame.pack(side="left", fill="x", expand=True)

        frame.pack(fill="x", pady=(0, 10))

    def _on_title_change_menu(self, choice: str) -> None:
        if choice and choice != "Nenhuma janela encontrada":
            self.title_name = choice.strip()
        else:
            self.title_name = ""
        self._sync_start_button_state()

    def _sync_start_button_state(self) -> None:
        is_enabled = bool(self.title_name) and not self.is_running
        self.start_button.configure(state="normal" if is_enabled else "disabled")
        if self.is_running:
            self.start_button.configure(text="Rodando... (ESC p/ parar)", fg_color="#3b3b3b", hover_color="#3b3b3b")
        else:
            self.start_button.configure(text="Iniciar Automação", fg_color="#2b6ef2", hover_color="#1f56bf")

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
        raw_limit = self.loop_limit_var.get().strip()
        loop_limit = int(raw_limit) if raw_limit and raw_limit.isdigit() else None

        self.is_running = True
        self._sync_start_button_state()
        self.status_label.configure(text="Rodando...")

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
        self.root.after(0, lambda: self.status_label.configure(text=f"Etapa: {step_name}"))

    def _on_match(self, template_name: str) -> None:
        self.root.after(0, lambda: self.last_match_label.configure(text=f"Último template: {template_name}"))

    def _on_loop(self, loop_count: int) -> None:
        pass

    def _on_action(self, action: str) -> None:
        self.root.after(0, lambda: self.last_action_label.configure(text=f"Ação: {action}"))

    def _on_stop(self, error, stats) -> None:
        def finish():
            self.is_running = False
            self._sync_start_button_state()
            self.status_label.configure(text=f"Parado | Loops: {stats.loop_count}")
            if error:
                messagebox.showerror("Automation stopped", str(error))

        self.root.after(0, finish)
