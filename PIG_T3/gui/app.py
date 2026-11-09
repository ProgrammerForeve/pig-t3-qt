import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import threading
import os
import json
import sys
import shutil
import tempfile
import uuid
import queue
import subprocess
import difflib
import time
import importlib.metadata

from ..config import ConfigManager
from ..core.analyzer import ProjectAnalyzer
from ..core.patcher import apply_llm_changes, clean_json_text
from ..utils.clipboard import copy_file_to_clipboard_windows
from ..core.ollama_client import OllamaClient, get_installed_models
from ..utils.BomjAPI import BomjAPI
from ..core.context_optimizer import ContextOptimizer
from ..core.plan_validator import validate_plan
from .tabs.quality_tab import QualityTab


class DarkApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()  # Скрываем главное окно при запуске
        self.show_splash()
        self.title("AI Context Generator & Patcher (JSON Edition)")
        self.geometry("1050x950")  # Modern wide layout, slightly taller for bottom status
        self.minsize(850, 680)
        self.configure(bg="#1e1e1e")
        self.config_manager = ConfigManager()
        self.settings = self.config_manager.load()
        self.analyzer = ProjectAnalyzer()
        self.setup_styles()
        self.setup_global_bindings()
        self._debounce_timer = None
        self._last_applied_content = None

        self.history_stack = []
        self.redo_stack = []
        self.current_project_path = None
        self.ui_queue = queue.Queue()
        self._process_ui_queue()
        self.is_generating = False
        self._cancel_generation = False
        self.create_widgets()
        self.bind("<FocusIn>", self._on_focus_in)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.git_available = False
        self.git_repo_path = None
        self.conversation_history = []

    def _process_ui_queue(self):
        try:
            while True:
                task = self.ui_queue.get_nowait()
                try:
                    task()
                except Exception as e:
                    print(f"UI Queue task error: {e}")
        except queue.Empty:
            pass
        self.after(50, self._process_ui_queue)

    def safe_after(self, func):
        self.ui_queue.put(func)

    def _on_focus_in(self, event):
        # Авто-обновление дерева файлов при возвращении фокуса в окно приложения
        if event.widget == self:
            self.on_param_change()
    def on_closing(self):
        try:
            if getattr(self, 'current_project_path', None):
                self.save_project_state(self.current_project_path)
            self.save_current_settings()
        except Exception as e:
            print(f"Error saving settings on exit: {e}")
        self.destroy()

    def show_splash(self):
        self.splash = tk.Toplevel(self)
        self.splash.overrideredirect(True)
        self.splash.attributes('-topmost', True)
        
        # Используем почти черный цвет как хромакей для прозрачности (работает на Windows)
        trans_color = "#000001"
        self.splash.configure(bg=trans_color)
        try:
            self.splash.attributes('-transparentcolor', trans_color)
        except Exception:
            pass
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        target_height = screen_height // 5
        
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            
        icon_path = os.path.join(base_path, "logo.png")
        
        try:
            from PIL import Image, ImageTk
            img = Image.open(icon_path).convert("RGBA")
            aspect = img.width / img.height
            target_width = int(target_height * aspect)
            resample = getattr(Image, "Resampling", Image).LANCZOS
            img = img.resize((target_width, target_height), resample)
            
            # Убираем полупрозрачность для идеального хромакея (избавляемся от черной окантовки)
            r, g, b, a = img.split()
            a = a.point(lambda p: 255 if p > 240 else 0)  # Более жесткий срез альфы (230) полностью удалит темную тень
            img = Image.merge("RGBA", (r, g, b, a))
            
            self.splash_img = ImageTk.PhotoImage(img)
            
            x = (screen_width - target_width) // 2
            y = (screen_height - target_height) // 2
            self.splash.geometry(f"{target_width}x{target_height}+{x}+{y}")
        except Exception:
            try:
                self.splash_img = tk.PhotoImage(file=icon_path)
                w, h = self.splash_img.width(), self.splash_img.height()
                x = (screen_width - w) // 2
                y = (screen_height - h) // 2
                self.splash.geometry(f"{w}x{h}+{x}+{y}")
            except Exception:
                self.splash_img = None
                self.splash.geometry(f"300x300+{(screen_width-300)//2}+{(screen_height-300)//2}")
                
        if self.splash_img:
            lbl = tk.Label(self.splash, image=self.splash_img, bg=trans_color, bd=0)
        else:
            lbl = tk.Label(self.splash, text="Загрузка...", bg=trans_color, fg="white", font=("Segoe UI", 16))
            
        lbl.pack(expand=True, fill=tk.BOTH)
        self.splash.update()
        
        # Скрываем сплеш-скрин через 1 секунду
        self.after(0, self.hide_splash)

    def hide_splash(self):
        if self.splash.winfo_exists():
            self.splash.destroy()
        self.deiconify()
        self.attributes('-topmost', True)
        self.update()
        self.attributes('-topmost', False)
        self.lift()
        self.focus_force()
        # Устанавливаем иконку основного окна
        try:
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            
            app_icon_path = os.path.join(base_path, "icon.png")
            try:
                from PIL import Image, ImageTk
                self.app_icon = ImageTk.PhotoImage(Image.open(app_icon_path))
                self.iconphoto(True, self.app_icon)
            except Exception:
                self.app_icon = tk.PhotoImage(file=app_icon_path)
                self.iconphoto(True, self.app_icon)
        except Exception:
            pass
    def get_theme_colors(self):
        theme = self.settings.get("theme", "dark")
        if theme not in ["light", "pink", "dark_pink", "eye_care", "dark"]:
            theme = "dark"
        
        if theme == "light":
            return {
                "bg": "#f0f0f0", "fg": "#000000", "entry_bg": "#ffffff", 
                "btn_bg": "#0078d7", "btn_active": "#005a9e", "text_bg": "#ffffff",
                "tree_heading_bg": "#e0e0e0", "tree_heading_active": "#d0d0d0",
                "tab_bg": "#e8e8e8", "tree_selected": "#cce8ff", "scroll_bg": "#c0c0c0",
                "fg_selected": "#000000"
            }
        elif theme == "pink":
            return {
                "bg": "#e4b5bb", "fg": "#432c39", "entry_bg": "#f4d6d9", 
                "btn_bg": "#8c6291", "btn_active": "#754f7a", "text_bg": "#f9e6e8",
                "tree_heading_bg": "#d4a3a9", "tree_heading_active": "#c49399",
                "tab_bg": "#d4a3a9", "tree_selected": "#a87b92", "scroll_bg": "#d4a3a9",
                "fg_selected": "#ffffff"
            }
        elif theme == "dark_pink":
            return {
                "bg": "#2b1b24", "fg": "#f8bbd0", "entry_bg": "#3e2736", 
                "btn_bg": "#d81b60", "btn_active": "#ad1457", "text_bg": "#1c1117",
                "tree_heading_bg": "#4a2c40", "tree_heading_active": "#5c364e",
                "tab_bg": "#361f2d", "tree_selected": "#880e4f", "scroll_bg": "#4a2c40",
                "fg_selected": "#ffffff"
            }
        elif theme == "eye_care":
            return {
                "bg": "#f4ecd8", "fg": "#4a4132", "entry_bg": "#e6dec6", 
                "btn_bg": "#8c7a5b", "btn_active": "#706249", "text_bg": "#faf6ed",
                "tree_heading_bg": "#e6dec6", "tree_heading_active": "#d4cbb3",
                "tab_bg": "#e6dec6", "tree_selected": "#d4cbb3", "scroll_bg": "#e6dec6",
                "fg_selected": "#2b251b"
            }
        else:
            return {
                "bg": "#1e1e1e", "fg": "#cccccc", "entry_bg": "#252526", 
                "btn_bg": "#0e639c", "btn_active": "#1177bb", "text_bg": "#181818",
                "tree_heading_bg": "#333333", "tree_heading_active": "#444444",
                "tab_bg": "#2d2d30", "tree_selected": "#04395e", "scroll_bg": "#333333",
                "fg_selected": "#ffffff"
            }

    def setup_styles(self):
        font_size = self.settings.get("font_size", 10)
        tree_row_height = self.settings.get("tree_row_height", 28)
        colors = self.get_theme_colors()

        style = ttk.Style(self)
        style.theme_use('clam')

        style.configure("TLabel", background=colors["bg"], foreground=colors["fg"], font=("Segoe UI", font_size))
        style.configure("TButton", background=colors["btn_bg"], foreground="#ffffff", borderwidth=0, font=("Segoe UI", font_size, "bold"), padding=5)
        style.map("TButton", background=[('active', colors["btn_active"])])
        
        indicator_size = self.settings.get("checkbox_size", 14)
        style.configure("TCheckbutton", background=colors["bg"], foreground=colors["fg"], font=("Segoe UI", font_size), indicatorsize=indicator_size, indicatormargin=4)
        style.map("TCheckbutton", background=[('active', colors["bg"])], indicatorcolor=[('selected', '#4CAF50'), ('pressed', colors["btn_bg"])])
        
        style.configure("TEntry", fieldbackground=colors["entry_bg"], foreground=colors["fg"], insertcolor=colors["fg"], borderwidth=0, font=("Segoe UI", font_size))
        style.configure("TCombobox", fieldbackground=colors["entry_bg"], background=colors["entry_bg"], foreground=colors["fg"], borderwidth=0, arrowcolor=colors["fg"], font=("Segoe UI", font_size))
        style.map("TCombobox", fieldbackground=[('readonly', colors["entry_bg"])], selectbackground=[('readonly', colors["entry_bg"])], selectforeground=[('readonly', colors["fg"])], foreground=[('readonly', colors["fg"])])
        style.configure("Horizontal.TProgressbar", background=colors["btn_bg"], troughcolor=colors["entry_bg"], bordercolor=colors["bg"], lightcolor=colors["btn_bg"], darkcolor=colors["btn_bg"])

        # Modern Tabs
        style.configure("TNotebook", background=colors["bg"], borderwidth=0, padding=0)
        style.configure("TNotebook.Tab", background=colors["tab_bg"], foreground=colors["fg"], padding=[15, 8], font=("Segoe UI", font_size), borderwidth=0)
        style.map("TNotebook.Tab", background=[('selected', colors["btn_bg"])], foreground=[('selected', "#ffffff")])

        # Modern Treeview
        style.configure("Treeview", background=colors["entry_bg"], foreground=colors["fg"], fieldbackground=colors["entry_bg"], borderwidth=0, font=("Segoe UI", font_size), rowheight=tree_row_height)
        style.map("Treeview", background=[('selected', colors["tree_selected"])], foreground=[('selected', colors["fg_selected"])])
        style.configure("Treeview.Heading", background=colors["tree_heading_bg"], foreground=colors["fg"], font=("Segoe UI", font_size, "bold"), borderwidth=0, padding=4)
        style.map("Treeview.Heading", background=[('active', colors["tree_heading_active"])])

        # Modern Scrollbars
        style.configure("Vertical.TScrollbar", background=colors["scroll_bg"], troughcolor=colors["bg"], bordercolor=colors["bg"], arrowcolor=colors["fg"], borderwidth=0)
        style.map("Vertical.TScrollbar", background=[('active', colors["tree_heading_active"])])
        style.configure("Horizontal.TScrollbar", background=colors["scroll_bg"], troughcolor=colors["bg"], bordercolor=colors["bg"], arrowcolor=colors["fg"], borderwidth=0)
        style.map("Horizontal.TScrollbar", background=[('active', colors["tree_heading_active"])])

        # Combobox dropdown list colors
        self.option_add('*TCombobox*Listbox.background', colors["entry_bg"])
        self.option_add('*TCombobox*Listbox.foreground', colors["fg"])
        self.option_add('*TCombobox*Listbox.selectBackground', colors["btn_bg"])
        self.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
    def setup_global_bindings(self):
        def select_all(event):
            widget = event.widget
            if isinstance(widget, tk.Entry):
                widget.select_range(0, 'end')
                widget.icursor('end')
            elif isinstance(widget, tk.Text) or isinstance(widget, scrolledtext.ScrolledText):
                widget.tag_add("sel", "1.0", "end")
            return "break"

        self.bind_class("Entry", "<Control-a>", select_all)
        self.bind_class("Text", "<Control-a>", select_all)
        self.bind_class("Entry", "<Control-f>", select_all)

        # Поддержка русских горячих клавиш (чтобы работали стандартные комбинации при русской раскладке)
        def copy(e): 
            try: e.widget.event_generate("<<Copy>>")
            except Exception: pass
            return "break"
            
        def paste(e): 
            try: e.widget.event_generate("<<Paste>>")
            except Exception: pass
            return "break"
            
        def cut(e): 
            try: e.widget.event_generate("<<Cut>>")
            except Exception: pass
            return "break"
            
        def undo(e):
            try: e.widget.event_generate("<<Undo>>")
            except Exception: pass
            return "break"

        ru_mapping = {
            'Cyrillic_ef': select_all, 'Cyrillic_EF': select_all, # Ctrl+A
            'Cyrillic_es': copy, 'Cyrillic_ES': copy,             # Ctrl+C
            'Cyrillic_em': paste, 'Cyrillic_EM': paste,           # Ctrl+V
            'Cyrillic_che': cut, 'Cyrillic_CHE': cut,             # Ctrl+X
            'Cyrillic_a': select_all, 'Cyrillic_A': select_all,   # Ctrl+F
            'Cyrillic_ya': undo, 'Cyrillic_YA': undo,             # Ctrl+Z
        }

        for keysym, func in ru_mapping.items():
            try:
                self.bind_class("Entry", f"<Control-{keysym}>", func)
                self.bind_class("Text", f"<Control-{keysym}>", func)
            except tk.TclError:
                pass

    def load_project_state(self, project_path):
        if not os.path.isdir(project_path): return
        state_file = os.path.join(project_path, ".pig", "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                for k in ["theme", "extensions", "ignore_list", "ui_tree_expanded", "ui_tree_unchecked"]:
                    if k in state:
                        self.settings[k] = state[k]
                self.history_stack = state.get("history_stack", [])
                self.redo_stack = state.get("redo_stack", [])
                # Очистка несуществующих путей из recent_projects
                recent = self.settings.get("recent_projects", [])
                self.settings["recent_projects"] = [p for p in recent if os.path.isdir(p)]
                if hasattr(self, 'combo_path'):
                    self.combo_path['values'] = self.settings["recent_projects"]
            except Exception as e:
                pass
        else:
            self.history_stack = []
            self.redo_stack = []

        self.update_undo_redo_buttons()
        self.setup_styles()
        self.apply_theme_recursive()
        
        if hasattr(self, 'ext_var'): self.ext_var.set(self.settings.get("extensions", self.ext_var.get()))
        if hasattr(self, 'ignore_var'): self.ignore_var.set(self.settings.get("ignore_list", self.ignore_var.get()))

    def save_project_state(self, project_path):
        if not os.path.isdir(project_path): return
        pig_dir = os.path.join(project_path, ".pig")
        os.makedirs(pig_dir, exist_ok=True)
        state_file = os.path.join(pig_dir, "state.json")
        
        expanded = []
        unchecked = []
        if hasattr(self, 'tree_path_map'):
            expanded, unchecked = self._get_tree_state()

        ign = getattr(self, 'ignore_var', tk.StringVar(value=self.settings.get("ignore_list", ""))).get()
        if ".pig" not in ign:
            ign = ign + ", .pig" if ign else ".pig"
            if hasattr(self, 'ignore_var'): self.ignore_var.set(ign)

        state = {
            "theme": self.settings.get("theme"),
            "extensions": getattr(self, 'ext_var', tk.StringVar(value=self.settings.get("extensions", ""))).get(),
            "ignore_list": ign,
            "ui_tree_expanded": list(expanded),
            "ui_tree_unchecked": list(unchecked),
            "history_stack": getattr(self, 'history_stack', []),
            "redo_stack": getattr(self, 'redo_stack', [])
        }
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving project state: {e}")

        recent = self.settings.get("recent_projects", [])
        if project_path in recent:
            recent.remove(project_path)
        recent.insert(0, project_path)
        recent = recent[:10]
        self.settings["recent_projects"] = recent
        self.config_manager.save(self.settings)
        if hasattr(self, 'combo_path'):
            self.combo_path['values'] = recent
    def create_widgets(self):
        self.path_var = tk.StringVar(value=self.settings["root_folder"])
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        font_size = self.settings.get("font_size", 10)
        self.btn_settings = tk.Button(self, text="⚙️", command=self.open_settings_dialog, bg="#1e1e1e", fg="#cccccc", activebackground="#1e1e1e", activeforeground="white", relief="flat", cursor="hand2", font=("Segoe UI", int(font_size * 1.4)), bd=0, highlightthickness=0, padx=6, pady=0)
        self.btn_settings.place(relx=1.0, x=-2, y=0, anchor="ne")

        self.tab_gen = tk.Frame(self.notebook, bg="#1e1e1e")
        self.tab_help = tk.Frame(self.notebook, bg="#1e1e1e")
        self.tab_editor = tk.Frame(self.notebook, bg="#1e1e1e")
        self.tab_plan = tk.Frame(self.notebook, bg="#1e1e1e")
        self.tab_quality = QualityTab(self.notebook, self.path_var)

        self.tabs_list = [
            ("generator", self.tab_gen, "🏠 Генератор"),
            ("info", self.tab_help, "🎓 Инфо / JSON Specs"),
            ("editor", self.tab_editor, "✏️Редактор (JSON Patcher)"),
            ("plan", self.tab_plan, "📝 План проекта"),
            ("quality", self.tab_quality, "📊 Анализ кода")
        ]
        self.update_tabs_visibility()

        self.create_generator_tab(self.tab_gen)
        self.create_help_tab(self.tab_help)
        self.create_editor_tab(self.tab_editor)
        self.create_plan_tab(self.tab_plan)
        self.apply_theme_recursive()
        try:
            version = importlib.metadata.version('pig-t3')
        except Exception:
            version = '?.?.?'
        self.version_label = tk.Label(self, text=f'v{version}', bg=self.get_theme_colors()['bg'], fg=self.get_theme_colors()['fg'], font=('Segoe UI', 7))
        self.version_label.place(relx=1.0, rely=1.0, anchor='se', x=-8, y=-4)

    def update_tabs_visibility(self):
        vis = self.settings.get("tabs_visibility", {})
        for key, widget, title in self.tabs_list:
            try:
                self.notebook.forget(widget)
            except Exception:
                pass
        for key, widget, title in self.tabs_list:
            if vis.get(key, True):
                self.notebook.add(widget, text=title)

    def apply_theme_recursive(self, widget=None):
        if widget is None:
            widget = self
        colors = self.get_theme_colors()
        font_size = self.settings.get("font_size", 10)
        base_font = ("Segoe UI", font_size)
        bold_font = ("Segoe UI", font_size, "bold")

        bg = colors["bg"]
        fg = colors["fg"]
        entry_bg = colors["entry_bg"]
        btn_bg = colors["btn_bg"]
        if hasattr(self, 'version_label') and widget is self.version_label:
            widget.configure(bg=bg, fg=fg)
            return
        text_bg = colors["text_bg"]

        try:
            if isinstance(widget, (tk.Toplevel, tk.Tk)):
                widget.configure(bg=bg)
                try:
                    import ctypes
                    widget.update_idletasks()
                    hwnd = ctypes.windll.user32.GetParent(widget.winfo_id())
                    theme_val = self.settings.get("theme", "dark")
                    is_dark = 1 if theme_val not in ("light", "eye_care") else 0
                    val = ctypes.c_int(is_dark)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))
                except Exception:
                    pass
            elif isinstance(widget, tk.LabelFrame):
                widget.configure(bg=bg, fg=fg)
            elif isinstance(widget, (tk.Frame, tk.PanedWindow)):
                widget.configure(bg=bg)
            elif isinstance(widget, tk.Label):
                current_font = widget.cget("font")
                new_font = bold_font if "bold" in str(current_font).lower() else base_font
                widget.configure(bg=bg, fg=fg, font=new_font)
            elif isinstance(widget, tk.Spinbox):
                widget.configure(bg=entry_bg, fg=fg, insertbackground=fg, font=base_font, buttonbackground=colors["scroll_bg"])
            elif isinstance(widget, tk.Entry):
                widget.configure(bg=entry_bg, fg=fg, insertbackground=fg, font=base_font)
            elif isinstance(widget, tk.Text):
                widget.configure(bg=text_bg, fg=fg, insertbackground=fg)
                theme = self.settings.get("theme", "dark")
                is_light = theme in ("light", "eye_care")
                try:
                    if is_light:
                        widget.tag_config("h1", foreground="#005a9e")
                        widget.tag_config("h2", foreground="#2b8a3e")
                        widget.tag_config("code", background="#e9ecef", foreground="#c92a2a")
                        widget.tag_config("warn", foreground="#b08d00")
                        widget.tag_config("crit", foreground="#c92a2a")
                        widget.tag_config("success", foreground="#2b8a3e")
                        widget.tag_config("dim", foreground="#868e96")
                        widget.tag_config("header_main", background="#005a9e", foreground="white")
                        widget.tag_config("label_def", foreground="#495057")
                        widget.tag_config("header_issues", foreground="#b08d00")
                        widget.tag_config("line_num", foreground="#005a9e")
                        widget.tag_config("tool_tag", foreground="#862e9c")
                        widget.tag_config("info", foreground="#005a9e")
                        widget.tag_config("err", foreground="#c92a2a")
                    else:
                        widget.tag_config("h1", foreground="#61afef")
                        widget.tag_config("h2", foreground="#98c379")
                        widget.tag_config("code", background="#3e4451", foreground="#56b6c2")
                        widget.tag_config("warn", foreground="#e5c07b")
                        widget.tag_config("crit", foreground="#e06c75")
                        widget.tag_config("success", foreground="#98c379")
                        widget.tag_config("dim", foreground="#5c6370")
                        widget.tag_config("header_main", background="#0e639c", foreground="white")
                        widget.tag_config("label_def", foreground="#cccccc")
                        widget.tag_config("header_issues", foreground="#e5c07b")
                        widget.tag_config("line_num", foreground="#61afef")
                        widget.tag_config("tool_tag", foreground="#c678dd")
                        widget.tag_config("info", foreground="#61afef")
                        widget.tag_config("err", foreground="#e06c75")
                except Exception:
                    pass
            elif isinstance(widget, tk.Button):
                current_font = widget.cget("font")
                new_font = bold_font if "bold" in str(current_font).lower() else base_font
                text_val = widget.cget("text")
                is_primary = widget in (getattr(self, 'btn_run', None), getattr(self, 'btn_apply', None), getattr(self.tab_quality, 'btn_scan', None))
                if text_val == "Сохранить" or text_val == "⏳ ОСТАНОВИТЬ / ПЕРЕЗАПУСТИТЬ" or is_primary:
                    widget.configure(bg=btn_bg, fg="white", font=new_font, activebackground=colors["btn_active"])
                elif text_val == "⚙️":
                    widget.configure(bg=bg, fg=fg, font=("Segoe UI", int(font_size * 1.4)), activebackground=bg, bd=0, highlightthickness=0)
                else:
                    widget.configure(bg=entry_bg, fg=fg, font=new_font, activebackground=colors["btn_active"], activeforeground="white")
        except Exception:
            pass

        for child in widget.winfo_children():
            self.apply_theme_recursive(child)
    def open_settings_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Настройки")
        
        main_w = self.winfo_width()
        main_h = self.winfo_height()
        dlg_w = 550
        dlg_h = 520
        
        main_x = self.winfo_rootx()
        main_y = self.winfo_rooty()
        dlg_x = main_x + (main_w - dlg_w) // 2
        dlg_y = main_y + (main_h - dlg_h) // 2
        
        dlg.geometry(f"{dlg_w}x{dlg_h}+{dlg_x}+{dlg_y}")
        colors = self.get_theme_colors()
        dlg.configure(bg=colors["bg"])
        dlg.transient(self)
        dlg.grab_set()

        container = tk.Frame(dlg, bg=colors["bg"], padx=20, pady=10)
        container.pack(fill=tk.BOTH, expand=True)
        
        notebook = ttk.Notebook(container)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        tab_appearance = tk.Frame(notebook, bg=colors["bg"], padx=15, pady=15)
        tab_functional = tk.Frame(notebook, bg=colors["bg"], padx=15, pady=15)

        notebook.add(tab_appearance, text="🎨 Внешний вид")
        notebook.add(tab_functional, text="⚙️ Функционал")

        # --- Внешний вид ---
        tk.Label(tab_appearance, text="Тема оформления:", bg=colors["bg"], fg=colors["fg"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        current_theme = self.settings.get("theme", "dark")
        if not current_theme or current_theme == "None":
            current_theme = "dark"
        theme_var = tk.StringVar(value=current_theme)
        valid_themes = ["dark", "light", "pink", "dark_pink", "eye_care"]
        
        theme_menu = tk.OptionMenu(tab_appearance, theme_var, *valid_themes)
        theme_menu.config(bg=colors["entry_bg"], fg=colors["fg"], activebackground=colors["btn_bg"], activeforeground="white", relief="flat", highlightthickness=0, width=18, font=("Segoe UI", 10))
        theme_menu["menu"].config(bg=colors["entry_bg"], fg=colors["fg"], font=("Segoe UI", 10))
        theme_menu.grid(row=0, column=1, sticky="e", pady=(0, 10), padx=(20, 0), ipady=2)

        tk.Label(tab_appearance, text="Размер шрифта (UI):", bg=colors["bg"], fg=colors["fg"], font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=10)
        font_var = tk.IntVar(value=self.settings.get("font_size", 10))
        tk.Spinbox(tab_appearance, from_=8, to_=24, textvariable=font_var, width=18, relief="flat", bg=colors["entry_bg"], fg=colors["fg"], buttonbackground=colors["scroll_bg"], font=("Segoe UI", 10)).grid(row=1, column=1, sticky="e", pady=10, padx=(20, 0), ipady=3)

        tk.Label(tab_appearance, text="Интервал строк (px):", bg=colors["bg"], fg=colors["fg"], font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w", pady=10)
        row_height_var = tk.IntVar(value=self.settings.get("tree_row_height", 28))
        tk.Spinbox(tab_appearance, from_=16, to_=60, textvariable=row_height_var, width=18, relief="flat", bg=colors["entry_bg"], fg=colors["fg"], buttonbackground=colors["scroll_bg"], font=("Segoe UI", 10)).grid(row=2, column=1, sticky="e", pady=10, padx=(20, 0), ipady=3)

        tk.Label(tab_appearance, text="Лимит чанка оптимизации:", bg=colors["bg"], fg=colors["fg"], font=("Segoe UI", 10)).grid(row=4, column=0, sticky="w", pady=10)
        opt_frame = tk.Frame(tab_appearance, bg=colors["bg"])
        opt_frame.grid(row=4, column=1, sticky="e", pady=10, padx=(20, 0))
        opt_chunk_var = tk.IntVar(value=self.settings.get("opt_chunk_size", 7000))
        tk.Entry(opt_frame, textvariable=opt_chunk_var, width=10, relief="flat", bg=colors["entry_bg"], fg=colors["fg"], font=("Segoe UI", 10)).pack(side=tk.LEFT, ipady=3)
        opt_unit_var = tk.StringVar(value=self.settings.get("opt_chunk_unit", "tokens"))
        ttk.Combobox(opt_frame, textvariable=opt_unit_var, values=["chars", "tokens", "lines"], state="readonly", width=7).pack(side=tk.LEFT, padx=(5, 0))
        tk.Label(tab_appearance, text="Размер галочек (px):", bg=colors["bg"], fg=colors["fg"], font=("Segoe UI", 10)).grid(row=3, column=0, sticky="w", pady=10)
        checkbox_size_var = tk.IntVar(value=self.settings.get("checkbox_size", 14))
        tk.Spinbox(tab_appearance, from_=10, to_=40, textvariable=checkbox_size_var, width=18, relief="flat", bg=colors["entry_bg"], fg=colors["fg"], buttonbackground=colors["scroll_bg"], font=("Segoe UI", 10)).grid(row=3, column=1, sticky="e", pady=10, padx=(20, 0), ipady=3)

        tab_appearance.columnconfigure(0, weight=1)

        # --- Функционал ---
        tk.Label(tab_functional, text="Параметры контекстного оптимизатора:", bg=colors["bg"], fg=colors["fg"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 10))

        bfs_depth_var = tk.IntVar(value=self.settings.get("opt_bfs_depth", 2))
        tk.Label(tab_functional, text="Глубина BFS:", bg=colors["bg"], fg=colors["fg"]).pack(anchor="w")
        tk.Spinbox(tab_functional, from_=1, to=10, textvariable=bfs_depth_var, width=5, relief="flat", bg=colors["entry_bg"], fg=colors["fg"]).pack(anchor="w", pady=(0,10))

        greedy_frame = tk.Frame(tab_functional, bg=colors["bg"])
        greedy_frame.pack(fill=tk.X, pady=5)
        tk.Label(greedy_frame, text="Веса отбора (LLM, PageRank, CC):", bg=colors["bg"], fg=colors["fg"]).pack(side=tk.LEFT)
        llm_weight_var = tk.DoubleVar(value=self.settings.get("opt_greedy_llm_weight", 0.6))
        pr_weight_var = tk.DoubleVar(value=self.settings.get("opt_greedy_pr_weight", 0.3))
        cc_weight_var = tk.DoubleVar(value=self.settings.get("opt_greedy_cc_weight", 0.1))
        tk.Entry(greedy_frame, textvariable=llm_weight_var, width=5, relief="flat", bg=colors["entry_bg"], fg=colors["fg"]).pack(side=tk.LEFT, padx=2)
        tk.Entry(greedy_frame, textvariable=pr_weight_var, width=5, relief="flat", bg=colors["entry_bg"], fg=colors["fg"]).pack(side=tk.LEFT, padx=2)
        tk.Entry(greedy_frame, textvariable=cc_weight_var, width=5, relief="flat", bg=colors["entry_bg"], fg=colors["fg"]).pack(side=tk.LEFT, padx=2)

        bytes_per_token_var = tk.IntVar(value=self.settings.get("opt_token_bytes_per_token", 4))
        tk.Label(tab_functional, text="Байт на токен (оценка):", bg=colors["bg"], fg=colors["fg"]).pack(anchor="w", pady=(10,0))
        tk.Spinbox(tab_functional, from_=1, to=10, textvariable=bytes_per_token_var, width=5, relief="flat", bg=colors["entry_bg"], fg=colors["fg"]).pack(anchor="w", pady=(0,10))

        tk.Label(tab_functional, text="Отображение вкладок:", bg=colors["bg"], fg=colors["fg"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 10))
        
        vis = self.settings.get("tabs_visibility", {})
        gen_var = tk.BooleanVar(value=vis.get("generator", True))
        info_var = tk.BooleanVar(value=vis.get("info", True))
        edit_var = tk.BooleanVar(value=vis.get("editor", True))
        plan_var = tk.BooleanVar(value=vis.get("plan", True))
        qual_var = tk.BooleanVar(value=vis.get("quality", True))

        ttk.Checkbutton(tab_functional, text="🏠 Генератор", variable=gen_var, style="TCheckbutton").pack(anchor="w", pady=5)
        ttk.Checkbutton(tab_functional, text="🎓 Инфо / JSON Specs", variable=info_var, style="TCheckbutton").pack(anchor="w", pady=5)
        ttk.Checkbutton(tab_functional, text="✏️ Редактор (JSON Patcher)", variable=edit_var, style="TCheckbutton").pack(anchor="w", pady=5)
        ttk.Checkbutton(tab_functional, text="📝 План проекта", variable=plan_var, style="TCheckbutton").pack(anchor="w", pady=5)
        ttk.Checkbutton(tab_functional, text="📊 Анализ кода", variable=qual_var, style="TCheckbutton").pack(anchor="w", pady=5)

        # --- Git Integration ---
        git_frame = tk.LabelFrame(tab_functional, text="🐙 Git интеграция", bg=colors["bg"], fg=colors["fg"])
        git_frame.pack(fill=tk.X, pady=(15, 5))

        self.git_enabled_var = tk.BooleanVar(value=self.settings.get("git_enabled", False))
        ttk.Checkbutton(git_frame, text="Включить авто-коммиты", variable=self.git_enabled_var, style="TCheckbutton").pack(anchor="w", padx=10, pady=5)

        branch_frame = tk.Frame(git_frame, bg=colors["bg"])
        branch_frame.pack(anchor="w", padx=10, pady=5)
        tk.Label(branch_frame, text="Режим веток:", bg=colors["bg"], fg=colors["fg"]).pack(side=tk.LEFT)
        self.git_branch_var = tk.StringVar(value=self.settings.get("git_branch_mode", "new"))
        ttk.Combobox(branch_frame, textvariable=self.git_branch_var, values=["new", "current"], state="readonly", width=8).pack(side=tk.LEFT, padx=5)

        self.git_auto_push_var = tk.BooleanVar(value=self.settings.get("git_auto_push", False))
        ttk.Checkbutton(git_frame, text="Делать push после каждого шага", variable=self.git_auto_push_var, style="TCheckbutton").pack(anchor="w", padx=10, pady=5)

        # --- LLM tuning ---
        llm_frame = tk.LabelFrame(tab_functional, text="⚙️ Параметры LLM", bg=colors["bg"], fg=colors["fg"])
        llm_frame.pack(fill=tk.X, pady=(15, 5))

        def add_int_row(parent, label, var, default):
            row = tk.Frame(parent, bg=colors["bg"])
            row.pack(fill=tk.X, padx=10, pady=2)
            tk.Label(row, text=label, bg=colors["bg"], fg=colors["fg"]).pack(side=tk.LEFT)
            var.set(default)
            tk.Entry(row, textvariable=var, width=10, bg=colors["entry_bg"], fg=colors["fg"], relief="flat").pack(side=tk.RIGHT)

        self.web_api_timeout_var = tk.IntVar()
        add_int_row(llm_frame, "Таймаут Web API (сек):", self.web_api_timeout_var, self.settings.get("web_api_timeout", 600))
        self.web_api_stable_var = tk.IntVar()
        add_int_row(llm_frame, "Стабильность ответа (сек):", self.web_api_stable_var, self.settings.get("web_api_stable_count", 7))
        self.plan_ctx_max_chars_var = tk.IntVar()
        add_int_row(llm_frame, "Макс. символов контекста плана:", self.plan_ctx_max_chars_var, self.settings.get("plan_context_max_chars", 1000000))
        self.plan_step_tokens_var = tk.IntVar()
        add_int_row(llm_frame, "Лимит токенов для шага плана:", self.plan_step_tokens_var, self.settings.get("plan_step_limit_tokens", 15000))
        self.plan_gen_tokens_var = tk.IntVar()
        add_int_row(llm_frame, "Лимит токенов для генерации плана:", self.plan_gen_tokens_var, self.settings.get("plan_generation_limit_tokens", 12000))
        self.quality_chunk_var = tk.IntVar()
        add_int_row(llm_frame, "Размер чанка для анализа:", self.quality_chunk_var, self.settings.get("quality_scan_chunk_size", 50))

        # --- Кнопки ---
        btn_frame = tk.Frame(container, bg=colors["bg"])
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        def save():
            self.settings["theme"] = theme_var.get()
            self.settings["font_size"] = int(font_var.get())
            self.settings["tree_row_height"] = int(row_height_var.get())
            self.settings["checkbox_size"] = int(checkbox_size_var.get())
            self.settings["opt_chunk_size"] = int(opt_chunk_var.get())
            self.settings["opt_chunk_unit"] = opt_unit_var.get()
            self.settings["git_enabled"] = self.git_enabled_var.get()
            self.settings["git_branch_mode"] = self.git_branch_var.get()
            self.settings["git_auto_push"] = self.git_auto_push_var.get()
            self.settings["web_api_timeout"] = int(self.web_api_timeout_var.get())
            self.settings["web_api_stable_count"] = int(self.web_api_stable_var.get())
            self.settings["plan_context_max_chars"] = int(self.plan_ctx_max_chars_var.get())
            self.settings["plan_step_limit_tokens"] = int(self.plan_step_tokens_var.get())
            self.settings["plan_generation_limit_tokens"] = int(self.plan_gen_tokens_var.get())
            self.settings["quality_scan_chunk_size"] = int(self.quality_chunk_var.get())
            self.settings["opt_bfs_depth"] = bfs_depth_var.get()
            self.settings["opt_greedy_llm_weight"] = llm_weight_var.get()
            self.settings["opt_greedy_pr_weight"] = pr_weight_var.get()
            self.settings["opt_greedy_cc_weight"] = cc_weight_var.get()
            self.settings["opt_token_bytes_per_token"] = bytes_per_token_var.get()
            self.settings["tabs_visibility"] = {
                "generator": gen_var.get(),
                "info": info_var.get(),
                "editor": edit_var.get(),
                "plan": plan_var.get(),
                "quality": qual_var.get()
            }
            self.config_manager.save(self.settings)
            self.setup_styles()
            self.update_tabs_visibility()
            self.apply_theme_recursive()
            dlg.destroy()

        save_btn = tk.Button(btn_frame, text="Сохранить", command=save, relief="flat", bg=colors["btn_bg"], fg="white", font=("Segoe UI", 10, "bold"), padx=25, pady=8, cursor="hand2")
        save_btn.pack(side=tk.RIGHT)

        cancel_btn = tk.Button(btn_frame, text="Отмена", command=dlg.destroy, relief="flat", bg=colors["entry_bg"], fg=colors["fg"], font=("Segoe UI", 10), padx=20, pady=8, cursor="hand2")
        cancel_btn.pack(side=tk.RIGHT, padx=15)

        self.apply_theme_recursive(dlg)
    def create_generator_tab(self, parent):
        main_frame = tk.Frame(parent, bg="#1e1e1e", padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Row 1: Path
        tk.Label(main_frame, text="Папка проекта:", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        path_frame = tk.Frame(main_frame, bg="#1e1e1e")
        path_frame.pack(fill=tk.X, pady=(5, 10))
        recent_projects = self.settings.get("recent_projects", [])
        self.combo_path = ttk.Combobox(path_frame, textvariable=self.path_var, values=recent_projects, style="TCombobox")
        self.combo_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        tk.Button(path_frame, text="Обзор...", command=self.browse_folder, bg="#333333", fg="white", relief="flat", cursor="hand2", padx=10).pack(side=tk.RIGHT)
        tk.Button(path_frame, text="Авто", command=self.auto_set_folder, bg="#333333", fg="white", relief="flat", cursor="hand2", padx=10).pack(side=tk.RIGHT, padx=(0, 5))

        # Row 2: Extensions & Output
        grid_frame = tk.Frame(main_frame, bg="#1e1e1e")
        grid_frame.pack(fill=tk.X, pady=5)

        tk.Label(grid_frame, text="Расширения:", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        self.ext_var = tk.StringVar(value=self.settings["extensions"])
        tk.Entry(grid_frame, textvariable=self.ext_var, bg="#252526", fg="white", relief="flat").grid(row=1, column=0, sticky="ew", padx=(0, 10), ipady=3)

        tk.Label(grid_frame, text="Имя отчета:", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w")
        self.out_var = tk.StringVar(value=self.settings["output_name"])
        tk.Entry(grid_frame, textvariable=self.out_var, bg="#252526", fg="white", relief="flat").grid(row=1, column=1, sticky="ew", ipady=3)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        # Row 3: Ignore
        tk.Label(main_frame, text="Исключить (Ignore):", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.ignore_var = tk.StringVar(value=self.settings["ignore_list"])
        tk.Entry(main_frame, textvariable=self.ignore_var, bg="#252526", fg="white", relief="flat").pack(fill=tk.X, pady=(5, 10), ipady=4)

        # Options
        options_frame = tk.LabelFrame(main_frame, text="Опции генерации", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 9), relief="flat", labelanchor="n")
        options_frame.pack(fill=tk.X, pady=(0, 15), ipady=5)

        self.include_empty_var = tk.BooleanVar(value=self.settings.get("include_empty_folders", False))
        ttk.Checkbutton(options_frame, text="Включить в отчёт пустые папки", variable=self.include_empty_var, style="TCheckbutton").pack(anchor="w", padx=10)

        self.add_edit_prompt_var = tk.BooleanVar(value=self.settings.get("add_edit_prompt", False))
        ttk.Checkbutton(options_frame, text="Добавить инструкцию для AI (JSON Format)", variable=self.add_edit_prompt_var, style="TCheckbutton").pack(anchor="w", padx=10)

        self.include_plan_var = tk.BooleanVar(value=self.settings.get("include_plan", False))
        ttk.Checkbutton(options_frame, text="Добавить текущий план к отчёту", variable=self.include_plan_var, style="TCheckbutton").pack(anchor="w", padx=10)
        self.line_numbers_var = tk.BooleanVar(value=self.settings.get("line_numbers", False))
        ttk.Checkbutton(options_frame, text="Нумеровать строки (для точного редактирования)", variable=self.line_numbers_var, style="TCheckbutton").pack(anchor="w", padx=10)

        self.auto_copy_var = tk.BooleanVar(value=self.settings.get("auto_copy_file", False))
        ttk.Checkbutton(options_frame, text="Авто-копировать ФАЙЛ в буфер (для вставки в чат)", variable=self.auto_copy_var, style="TCheckbutton").pack(anchor="w", padx=10)

        # Row 4: Project Tree Preview
        tree_label_frame = tk.Frame(main_frame, bg="#1e1e1e")
        tk.Label(tree_label_frame, text="Структура проекта (выберите файлы для отчёта) ", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Button(tree_label_frame, text="🔄 Обновить", command=self.on_param_change, bg="#252526", fg="#cccccc", activebackground="#1177bb", activeforeground="white", relief="flat", font=("Segoe UI", 8), cursor="hand2", padx=5, pady=0).pack(side=tk.LEFT)
        tk.Button(tree_label_frame, text="✨ Оптимизация контекста", command=self.open_optimization_dialog, bg="#8c6291", fg="white", activebackground="#754f7a", activeforeground="white", relief="flat", font=("Segoe UI", 8, "bold"), cursor="hand2", padx=5, pady=0).pack(side=tk.LEFT, padx=(5, 0))
        tk.Button(tree_label_frame, text="📝 План", command=self.open_plan_manager, bg="#8c6291", fg="white", activebackground="#754f7a", activeforeground="white", relief="flat", font=("Segoe UI", 8, "bold"), cursor="hand2", padx=5, pady=0).pack(side=tk.LEFT, padx=(5, 0))
        self.lbl_opt_quality = tk.Label(tree_label_frame, text="", bg="#1e1e1e", fg="#98c379", font=("Segoe UI", 9, "bold"))
        self.lbl_opt_quality.pack(side=tk.LEFT, padx=(10, 0))
        
        tree_container = tk.LabelFrame(main_frame, labelwidget=tree_label_frame, bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 9))
        tree_container.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # Treeview
        self.tree_scroll = ttk.Scrollbar(tree_container)
        self.tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree = ttk.Treeview(tree_container, selectmode="none", yscrollcommand=self.tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_scroll.config(command=self.tree.yview)
        
        # Configure Tree
        self.tree.heading("#0", text="Проект", anchor="w")
        self.tree.column("#0", width=500)
        self.tree.bind("<Button-1>", self.on_tree_click)
        
        # State storage for tree items: item_id -> True/False
        self.tree_checked_state = {}
        # Mapping: item_id -> full_path
        self.tree_path_map = {}

        # Run & Status Area (Bottom)
        self.bottom_action_frame = tk.Frame(main_frame, bg="#1e1e1e")
        self.bottom_action_frame.pack(fill=tk.X, pady=(5, 0))

        self.btn_run = tk.Button(self.bottom_action_frame, text="ГЕНЕРИРОВАТЬ КОНТЕКСТ", command=self.start_processing, bg="#0e639c", fg="white", font=("Segoe UI", 11, "bold"), relief="flat", pady=8, cursor="hand2")
        self.btn_run.pack(fill=tk.X)

        self.progress_container = tk.Frame(self.bottom_action_frame, bg="#1e1e1e", height=15)
        self.progress_container.pack_propagate(False)
        self.progress_container.pack(fill=tk.X, pady=(5, 0))

        self.progress = ttk.Progressbar(self.progress_container, orient="horizontal", length=100, mode="determinate", style="Horizontal.TProgressbar")
        
        self.status_var = tk.StringVar(value="Готов к работе")
        self.status_label = tk.Label(self.bottom_action_frame, textvariable=self.status_var, bg="#1e1e1e", fg="#808080", font=("Segoe UI", 9))
        self.status_label.pack(pady=(0, 5))

        # Bindings for auto-update
        self.path_var.trace_add("write", self.on_param_change)
        self.ext_var.trace_add("write", self.on_param_change)
        self.ignore_var.trace_add("write", self.on_param_change)
        # Force initial tree population
        self.refresh_preview_tree()

    def create_help_tab(self, parent):
        # Используем PanedWindow для разделения меню и контента
        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, sashwidth=4, bg="#1e1e1e")
        paned.pack(fill=tk.BOTH, expand=True)

        # --- Левая панель (Меню) ---
        nav_frame = tk.Frame(paned, bg="#1e1e1e", width=220)
        nav_frame.pack_propagate(False)  # Фиксируем ширину
        paned.add(nav_frame)

        tk.Label(nav_frame, text="СПРАВОЧНИК", bg="#1e1e1e", fg="#61afef", font=("Segoe UI", 12, "bold"), pady=10).pack(fill=tk.X)

        # Стиль кнопок меню
        def create_nav_btn(text, cmd):
            btn = tk.Button(nav_frame, text=text, command=cmd, bg="#252526", fg="#cccccc",
                            activebackground="#1177bb", activeforeground="white",
                            relief="flat", cursor="hand2", font=("Segoe UI", 10), anchor="w", padx=10)
            btn.pack(fill=tk.X, pady=2, padx=5)
            return btn

        create_nav_btn("🔰 БАЗОВАЯ ИНФО", lambda: self.show_help_content("basic"))

        tk.Label(nav_frame, text="ПРОДВИНУТОЕ", bg="#1e1e1e", fg="#5c6370", font=("Segoe UI", 9, "bold"), pady=5).pack(fill=tk.X, pady=(10, 0))
        
        create_nav_btn("🔧 Механика вкладок", lambda: self.show_help_content("mechanics"))
        create_nav_btn("🧬 JSON Структура", lambda: self.show_help_content("json"))
        create_nav_btn("📊 Расшифровка метрик", lambda: self.show_help_content("metrics"))
        create_nav_btn("🤖 Ollama и Авто-фикс", lambda: self.show_help_content("ollama"))

        # --- Правая панель (Контент) ---
        content_frame = tk.Frame(paned, bg="#1e1e1e")
        paned.add(content_frame)

        self.help_text = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, bg="#181818", fg="#abb2bf",
                                                   font=("Consolas", 11), relief="flat", padx=20, pady=20)
        self.help_text.pack(fill=tk.BOTH, expand=True)

        # Настройка тегов для красоты
        self.help_text.tag_config("h1", font=("Segoe UI", 18, "bold"), foreground="#61afef", spacing3=15)
        self.help_text.tag_config("h2", font=("Segoe UI", 14, "bold"), foreground="#98c379", spacing1=10, spacing3=5)
        self.help_text.tag_config("code", font=("Consolas", 10), background="#3e4451", foreground="#56b6c2")
        self.help_text.tag_config("warn", foreground="#e5c07b")
        self.help_text.tag_config("crit", foreground="#e06c75", font=("Segoe UI", 10, "bold"))
        self.help_text.tag_config("success", foreground="#98c379")
        self.help_text.tag_config("bold", font=("Segoe UI", 11, "bold"))

        # Загружаем базовый контент при старте
        self.show_help_content("basic")

    def show_help_content(self, section):
        self.help_text.config(state='normal')
        self.help_text.delete("1.0", tk.END)

        text_map = {
            "basic": self._get_text_basic,
            "mechanics": self._get_text_mechanics,
            "json": self._get_text_json,
            "metrics": self._get_text_metrics,
            "ollama": self._get_text_ollama
        }

        content_func = text_map.get(section, self._get_text_basic)
        content_func()

        self.help_text.config(state='disabled')

    # --- TEXT GENERATORS ---

    def _get_text_basic(self):
        self._insert_header("🔰 БАЗОВАЯ ИНСТРУКЦИЯ")
        
        self.help_text.insert(tk.END, "1. Вкладка 'Генератор'\n", "h2")
        self.help_text.insert(tk.END, "Эта вкладка создает 'контекст' — единый файл со всем кодом вашего проекта.\n\n")
        self.help_text.insert(tk.END, "• Выберите папку проекта.\n• Нажмите 'ГЕНЕРИРОВАТЬ'.\n• Полученный файл (.txt или .md) отправьте в чат с AI (ChatGPT, Claude, DeepSeek).\n")
        self.help_text.insert(tk.END, "💡 Совет: Включите 'Нумеровать строки' и 'Инструкцию для AI' для лучших результатов редактирования.\n")

        self.help_text.insert(tk.END, "\n2. Вкладка 'Редактор'\n", "h2")
        self.help_text.insert(tk.END, "Сюда вставляется ответ от нейросети в формате JSON для автоматического применения изменений.\n\n")
        self.help_text.insert(tk.END, "• Скопируйте JSON-код из ответа AI.\n• Вставьте в поле редактора.\n• Нажмите 'Проверить' -> 'Применить'.\n")

        self.help_text.insert(tk.END, "\n3. Вкладка 'Анализ кода'\n", "h2")
        self.help_text.insert(tk.END, "Локальный аудит качества без отправки кода в сеть.\n\n")
        self.help_text.insert(tk.END, "• Нажмите 'Запустить анализ'.\n• Смотрите таблицу метрик и детали найденных проблем.")

    def _get_text_mechanics(self):
        self._insert_header("🔧 КАК ЭТО РАБОТАЕТ (ПОД КАПОТОМ)")
        
        self.help_text.insert(tk.END, "Генератор контекста (Analyzer)\n", "h2")
        self.help_text.insert(tk.END, "Скрипт обходит дерево файлов, игнорируя папки из списка 'Ignore'.\n")
        self.help_text.insert(tk.END, "Он собирает весь код в один текстовый файл, добавляя XML-теги <file path='...'>.\n")
        self.help_text.insert(tk.END, "Это позволяет AI четко понимать, где начинается и заканчивается каждый файл.")

        self.help_text.insert(tk.END, "\n\nПатчер (Patcher)\n", "h2")
        self.help_text.insert(tk.END, "1. Разбирает входящий JSON.\n2. Для 'edit' операций сортирует изменения снизу вверх (чтобы не сбить номера строк).\n3. Безопасно перезаписывает файлы.\n")

        self.help_text.insert(tk.END, "\nАнализатор качества (Scanner)\n", "h2")
        self.help_text.insert(tk.END, "Запускает 4 утилиты как подпроцессы:\n")
        self.help_text.insert(tk.END, "• Radon CC (Сложность)\n• Radon MI (Поддерживаемость)\n• Pylint (Стиль/Ошибки)\n• Bandit (Безопасность)\n\n")
        self.help_text.insert(tk.END, "Результаты парсятся из JSON-вывода этих утилит и сводятся в единую таблицу.")

    def _get_text_json(self):
        self._insert_header("🧬 СТРУКТУРА JSON ДЛЯ РЕДАКТИРОВАНИЯ")
        self.help_text.insert(tk.END, "Чтобы изменить код, AI должен вернуть ответ строго в таком формате:\n\n")
        
        json_ex = """
[
  {
    "action": "create",
    "path": "utils/helper.py",
    "explanation": "Utility module created",
    "content": "def help():\n    pass"
  },
  {
    "action": "delete",
    "path": "old_file.py"
  },
  {
    "action": "move",
    "source": "old_folder/old_file.py",
    "destination": "new_folder/new_file.py"
  },
  {
    "action": "edit",
    "path": "main.py",
    "explanation": "Refactoring to use new helper",
    "operations": [
       {
         "type": "replace_lines",
         "start": 10, "end": 12,
         "content": "    new_code()\n    fixed_line()"
       },
       {
         "type": "insert_after_line",
         "line": 15,
         "content": "    print('Debug info')"
       },
       {
         "type": "replace_text",
         "find": "old_string",
         "replace": "new_string"
       }
    ]
  },
  {
    "action": "mark_step_completed",
    "step_id": "step_1",
    "completed": false,
    "explanation": "Reverting completion",
    "report": null,
    "append_description": "Additional tasks to be done later"
  }
]
"""
        self.help_text.insert(tk.END, json_ex, "code")
        self.help_text.insert(tk.END, "\n\n⚠️ ВАЖНО: При replace_lines не включайте контекст (соседние неизменные строки), иначе они продублируются. Для вставки нового блока лучше использовать insert_after_line.", "crit")

        self.help_text.insert(tk.END, "\n\n📌 Действие mark_step_completed теперь поддерживает:\n", "bold")
        self.help_text.insert(tk.END, "- \"completed\": false — снять галочку выполнения.\n")
        self.help_text.insert(tk.END, "- \"report\": null — очистить отчёт.\n")
        self.help_text.insert(tk.END, "- \"append_description\": \"текст\" — добавить текст в конец описания шага.\n")

    def _get_text_metrics(self):
        self._insert_header("📊 ПОДРОБНАЯ РАСШИФРОВКА МЕТРИК")
        
        self.help_text.insert(tk.END, "1. Cyclomatic Complexity (CC) — Цикломатическая сложность\n", "h2")
        self.help_text.insert(tk.END, "Мера запутанности логики (количество развилок if/for/while).\n")
        self.help_text.insert(tk.END, "• 1-10: ", "bold"); self.help_text.insert(tk.END, "Простой код (🟢)\n", "success")
        self.help_text.insert(tk.END, "• 11-20: ", "bold"); self.help_text.insert(tk.END, "Умеренная сложность (⚠️)\n", "warn")
        self.help_text.insert(tk.END, "• 21+: ", "bold"); self.help_text.insert(tk.END, "Сложный код, риск багов (🔴)\n", "crit")

        self.help_text.insert(tk.END, "\n2. Maintainability Index (MI) — Индекс поддерживаемости\n", "h2")
        self.help_text.insert(tk.END, "Оценка (0-100), насколько легко читать и менять код.\n")
        self.help_text.insert(tk.END, "• > 20: ", "bold"); self.help_text.insert(tk.END, "Высокая (🟢)\n", "success")
        self.help_text.insert(tk.END, "• 10-20: ", "bold"); self.help_text.insert(tk.END, "Средняя (⚠️)\n", "warn")
        self.help_text.insert(tk.END, "• < 10: ", "bold"); self.help_text.insert(tk.END, "Низкая, спагетти-код (🔴)\n", "crit")

        self.help_text.insert(tk.END, "\n3. Linter Score (Pylint) — Оценка качества\n", "h2")
        self.help_text.insert(tk.END, "Строгая оценка 'учителя' по 10-балльной шкале (PEP8, ошибки, стиль).\n")
        self.help_text.insert(tk.END, "• > 8.0: ", "bold"); self.help_text.insert(tk.END, "Отлично (🟢)\n", "success")
        self.help_text.insert(tk.END, "• 5.0-8.0: ", "bold"); self.help_text.insert(tk.END, "Есть замечания (⚠️)\n", "warn")
        self.help_text.insert(tk.END, "• < 5.0: ", "bold"); self.help_text.insert(tk.END, "Плохо (🔴)\n", "crit")

        self.help_text.insert(tk.END, "\n4. Security Issues (Bandit) — Безопасность\n", "h2")
        self.help_text.insert(tk.END, "Поиск уязвимостей: зашитые пароли, injection, unsafe functions.\n")
        self.help_text.insert(tk.END, "• 0 проблем: ", "bold"); self.help_text.insert(tk.END, "Чисто (🟢)\n", "success")
        self.help_text.insert(tk.END, "• > 0: ", "bold"); self.help_text.insert(tk.END, "Найдены уязвимости! (🔴)\n", "crit")

    def _get_text_ollama(self):
        self._insert_header("🤖 OLLAMA И AUTO-FIX")
        self.help_text.insert(tk.END, "Приложение умеет использовать локальные нейросети через Ollama.\n\n", "bold")
        self.help_text.insert(tk.END, "Зачем это нужно?\n", "h2")
        self.help_text.insert(tk.END, "Если вы вставили JSON с ошибкой (например, лишняя запятая), приложение может попросить локальную модель исправить синтаксис, не отправляя данные в интернет.\n\n")
        self.help_text.insert(tk.END, "Как настроить:\n", "h2")
        self.help_text.insert(tk.END, "1. Установите Ollama (ollama.com).\n")
        self.help_text.insert(tk.END, "2. Скачайте модель: `ollama pull qwen2.5-coder` (или любую другую).\n")
        self.help_text.insert(tk.END, "3. Перезапустите приложение — модель появится в списке во вкладке 'Редактор'.")

    def _insert_header(self, text):
        self.help_text.insert(tk.END, text + "\n", "h1")
        self.help_text.insert(tk.END, "=" * 60 + "\n\n", "dim")

    def create_editor_tab(self, parent):
        main_frame = tk.Frame(parent, bg="#1e1e1e", padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Папка
        top_frame = tk.Frame(main_frame, bg="#1e1e1e")
        top_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(top_frame, text="Целевая папка:", bg="#1e1e1e", fg="#cccccc").pack(side=tk.LEFT)
        tk.Entry(top_frame, textvariable=self.path_var, bg="#252526", fg="gray", relief="flat", width=40).pack(side=tk.LEFT, padx=10)

        self.btn_redo = tk.Button(top_frame, text="↪ Повторить", command=self.on_redo, state=tk.DISABLED, bg="#333333", fg="white", relief="flat", cursor="hand2", padx=10)
        self.btn_redo.pack(side=tk.RIGHT)

        self.btn_undo = tk.Button(top_frame, text="↩ Отменить", command=self.on_undo, state=tk.DISABLED, bg="#333333", fg="white", relief="flat", cursor="hand2", padx=10)
        self.btn_undo.pack(side=tk.RIGHT, padx=(5, 10))

        tk.Label(main_frame, text="Вставьте JSON ответ от AI (можно с ```json):", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.editor_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=20, bg="#252526", fg="#cccccc",
                                                     font=("Consolas", 10), insertbackground="white", relief="flat")
        self.editor_text.pack(fill=tk.BOTH, expand=True, pady=(5, 10))

        # --- Настройки Ollama (Collapsible or just frame) ---
        self.create_ollama_settings(main_frame)

        # Buttons
        btn_frame = tk.Frame(main_frame, bg="#1e1e1e")
        btn_frame.pack(fill=tk.X)

        tk.Button(btn_frame, text="📋 Вставить", command=self.paste_from_clipboard,
                  bg="#333333", fg="white", relief="flat", cursor="hand2", padx=15, pady=5).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(btn_frame, text="🔍 Проверить / Форматировать JSON", command=self.validate_json_ui,
                  bg="#333333", fg="white", relief="flat", cursor="hand2", padx=15, pady=5).pack(side=tk.LEFT, padx=(0, 10))

        self.btn_apply = tk.Button(btn_frame, text="ПРИМЕНИТЬ ИЗМЕНЕНИЯ", command=self.apply_changes,
                                   bg="#0e639c", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2", pady=5)
        self.btn_apply.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.editor_status_var = tk.StringVar(value="")
        tk.Label(main_frame, textvariable=self.editor_status_var, bg="#1e1e1e", fg="#e5c07b", font=("Consolas", 9)).pack(side=tk.BOTTOM, pady=5)

    def create_ollama_settings(self, parent):
        frame = tk.LabelFrame(parent, text="🛠️ Ollama Auto-Fix (Локальная LLM)", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 9), padx=10, pady=5)
        frame.pack(fill=tk.X, pady=(0, 10))

        # Model Selection
        row1 = tk.Frame(frame, bg="#1e1e1e")
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="Модель:", bg="#1e1e1e", fg="#cccccc", width=10, anchor="w").pack(side=tk.LEFT)
        
        current_model = self.settings.get("ollama_model", "None")
        web_models = ["Web: Gemini", "Web: DeepSeek", "Web: DeepSeek (DeepThink)", "Web: DeepSeek Expert", "Web: DeepSeek Expert (DeepThink)"]
        models = ["None", "BomjAPI"] + web_models + get_installed_models()
        
        self.ollama_model_var = tk.StringVar(value=current_model)
        self.combo_models = ttk.Combobox(row1, textvariable=self.ollama_model_var, values=models, state="readonly")
        self.combo_models.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Options
        row2 = tk.Frame(frame, bg="#1e1e1e")
        row2.pack(fill=tk.X, pady=5)
        
        def mk_entry(p, label, key, default):
            tk.Label(p, text=label, bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(5, 2))
            var = tk.StringVar(value=str(self.settings.get("ollama_options", {}).get(key, default)))
            e = tk.Entry(p, textvariable=var, bg="#252526", fg="white", width=8, relief="flat", font=("Consolas", 9))
            e.pack(side=tk.LEFT)
            return var

        self.opt_ctx = mk_entry(row2, "Ctx:", "num_ctx", 24000)
        self.opt_pred = mk_entry(row2, "Predict:", "num_predict", 12000)
        self.opt_temp = mk_entry(row2, "Temp:", "temperature", 0.5)
        self.opt_topp = mk_entry(row2, "TopP:", "top_p", 0.95)
        self.opt_topk = mk_entry(row2, "TopK:", "top_k", 100)
    def paste_from_clipboard(self):
        try:
            content = self.clipboard_get()
            self.editor_text.delete("1.0", tk.END)
            self.editor_text.insert("1.0", content)
            self.editor_status_var.set("📋 Вставлено из буфера обмена")
        except Exception:
            self.editor_status_var.set("⚠️ Ошибка: буфер обмена пуст или не содержит текста")
    def validate_json_ui(self):
        """Пытается распарсить JSON, форматирует его красиво или показывает ошибку."""
        raw_text = self.editor_text.get("1.0", tk.END).strip()
        if not raw_text:
            self.editor_status_var.set("Пустое поле.")
            return False

        # Пытаемся вытащить JSON из markdown
        cleaned = clean_json_text(raw_text)

        try:
            data = json.loads(cleaned)
            if not isinstance(data, list):
                raise ValueError("JSON должен быть списком (root array).")

            # Pretty print back to editor
            pretty_json = json.dumps(data, indent=2, ensure_ascii=False)
            self.editor_text.delete("1.0", tk.END)
            self.editor_text.insert("1.0", pretty_json)

            count = len(data)
            self.editor_status_var.set(f"✅ Валидный JSON. Найдено операций: {count}")
            return True
        except Exception as e:
            self.editor_status_var.set(f"❌ Ошибка JSON: {e}")
            
            # --- Auto Fix Logic ---
            model = self.ollama_model_var.get()
            if model and model != "None":
                self.run_ollama_fix(raw_text, model)
                return False
            # ----------------------

            messagebox.showerror("Ошибка валидации", f"Некорректный JSON:\n{e}")
            return False

    def apply_changes(self):
        if not self.validate_json_ui():
            return

        llm_text = self.editor_text.get("1.0", tk.END).strip()

        if self._last_applied_content and llm_text == self._last_applied_content:
            if not messagebox.askyesno("Подтверждение", "Эти изменения уже были применены.\nПовторить применение патча?"):
                return

        self._last_applied_content = llm_text
        root_folder = self.path_var.get()

        if not os.path.exists(root_folder):
            messagebox.showerror("Ошибка", "Папка проекта не существует.")
            return

        try:
            data = json.loads(clean_json_text(llm_text))
            raw_paths =[]
            for action in data:
                if 'path' in action: raw_paths.append(action['path'])
                if 'source' in action: raw_paths.append(action['source'])
                if 'destination' in action: raw_paths.append(action['destination'])
            filtered_paths = self._filter_paths(raw_paths)
        except Exception as e:
            self._on_apply_error(f"Ошибка чтения путей для бэкапа: {e}")
            return

        self.btn_apply.config(state=tk.DISABLED, text="Применение...", bg="#555555")

        def _apply():
            try:
                patch_id = str(uuid.uuid4())
                backup_root = os.path.join(root_folder, ".pig", "backups", patch_id)
                before_dir = os.path.join(backup_root, "before")
                after_dir = os.path.join(backup_root, "after")

                self._copy_paths(root_folder, before_dir, filtered_paths)
                log = apply_llm_changes(llm_text, root_folder)
                self._copy_paths(root_folder, after_dir, filtered_paths)

                record = {
                    "id": patch_id,
                    "paths": filtered_paths,
                    "llm_text": llm_text
                }
                self.safe_after(lambda: self._on_apply_success_history(log, record))
            except Exception as e:
                self.safe_after(lambda: self._on_apply_error(str(e)))

        threading.Thread(target=_apply).start()

    def _on_apply_complete(self, log):
        colors = self.get_theme_colors()
        self.btn_apply.config(state=tk.NORMAL, text="ПРИМЕНИТЬ ИЗМЕНЕНИЯ", bg=colors["btn_bg"])

        # Создаем окно с результатом
        top = tk.Toplevel(self)
        top.title("Результат патча")
        
        main_w = self.winfo_width()
        main_h = self.winfo_height()
        dlg_w = max(600, int(main_w * 0.5))
        dlg_h = max(400, int(main_h * 0.5))
        
        main_x = self.winfo_rootx()
        main_y = self.winfo_rooty()
        dlg_x = main_x + (main_w - dlg_w) // 2
        dlg_y = main_y + (main_h - dlg_h) // 2
        
        top.geometry(f"{dlg_w}x{dlg_h}+{dlg_x}+{dlg_y}")
        top.configure(bg=colors["bg"])

        st = scrolledtext.ScrolledText(top, bg=colors["text_bg"], fg=colors["fg"], font=("Consolas", 10), relief="flat")
        st.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        st.insert(tk.END, log)
        st.configure(state='disabled')
        
        self.apply_theme_recursive(top)

    def _on_apply_error(self, error_msg):
        colors = self.get_theme_colors()
        self.btn_apply.config(state=tk.NORMAL, text="ПРИМЕНИТЬ ИЗМЕНЕНИЯ", bg=colors["btn_bg"])
        messagebox.showerror("Критическая ошибка", error_msg)

    def _filter_paths(self, paths):
        normalized =[]
        for p in paths:
            norm_p = os.path.normpath(p).replace('\\', '/')
            if not os.path.isabs(norm_p) and not norm_p.startswith('..'):
                normalized.append(norm_p)

        normalized.sort()
        filtered =[]
        for p in normalized:
            if not any(p == parent or p.startswith(parent + '/') for parent in filtered):
                filtered.append(p)
        return filtered

    def _copy_paths(self, source_root, dest_root, paths):
        for p in paths:
            src = os.path.join(source_root, p)
            dst = os.path.join(dest_root, p)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

    def _restore_snapshot(self, root_folder, backup_dir, paths):
        for p in paths:
            target = os.path.join(root_folder, p)
            backup = os.path.join(backup_dir, p)

            if os.path.exists(target):
                if os.path.isdir(target):
                    shutil.rmtree(target)
                else:
                    os.remove(target)

            if os.path.exists(backup):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.isdir(backup):
                    shutil.copytree(backup, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(backup, target)

    def update_undo_redo_buttons(self):
        if hasattr(self, 'btn_undo'):
            self.btn_undo.config(state=tk.NORMAL if self.history_stack else tk.DISABLED)
            self.btn_redo.config(state=tk.NORMAL if self.redo_stack else tk.DISABLED)

    def _on_apply_success_history(self, log, record):
        self.history_stack.append(record)
        if len(self.history_stack) > 10:
            oldest = self.history_stack.pop(0)
            oldest_dir = os.path.join(self.path_var.get(), ".pig", "backups", oldest["id"])
            shutil.rmtree(oldest_dir, ignore_errors=True)

        self.redo_stack.clear()

        self.redo_stack.clear()
        self.update_undo_redo_buttons()
        self._on_apply_complete(log)

    def on_undo(self):
        if not self.history_stack: return
        record = self.history_stack.pop()
        self.redo_stack.append(record)
        self.update_undo_redo_buttons()

        root_folder = self.path_var.get()
        self.editor_status_var.set("⏳ Отмена изменений...")
        self.btn_apply.config(state=tk.DISABLED, bg="#555555")

        def _undo_task():
            try:
                before_dir = os.path.join(root_folder, ".pig", "backups", record["id"], "before")
                self._restore_snapshot(root_folder, before_dir, record["paths"])
                self.safe_after(lambda: self._on_undo_redo_complete("Изменения отменены", record["llm_text"]))
            except Exception as e:
                self.safe_after(lambda: self._on_apply_error(f"Ошибка отмены: {e}"))

        threading.Thread(target=_undo_task).start()

    def on_redo(self):
        if not self.redo_stack: return
        record = self.redo_stack.pop()
        self.history_stack.append(record)
        self.update_undo_redo_buttons()

        root_folder = self.path_var.get()
        self.editor_status_var.set("⏳ Повтор изменений...")
        self.btn_apply.config(state=tk.DISABLED, bg="#555555")

        def _redo_task():
            try:
                after_dir = os.path.join(root_folder, ".pig", "backups", record["id"], "after")
                self._restore_snapshot(root_folder, after_dir, record["paths"])
                self.safe_after(lambda: self._on_undo_redo_complete("Изменения повторно применены", record["llm_text"]))
            except Exception as e:
                self.safe_after(lambda: self._on_apply_error(f"Ошибка повтора: {e}"))

        threading.Thread(target=_redo_task).start()

    def _on_undo_redo_complete(self, msg, llm_text):
        colors = self.get_theme_colors()
        self.btn_apply.config(state=tk.NORMAL, bg=colors["btn_bg"])
        self.editor_status_var.set(f"✅ {msg}")

        self.editor_text.delete("1.0", tk.END)
        self.editor_text.insert("1.0", llm_text)
        self.validate_json_ui()


    def on_param_change(self, *args):
        """Debounced refresh of the tree."""
        if self._debounce_timer:
            self.after_cancel(self._debounce_timer)
        self._debounce_timer = self.after(600, self.refresh_preview_tree)
    def _get_tree_state(self):
        """Collects currently expanded paths and unchecked paths (relative)."""
        expanded = set()
        unchecked = set()
        root_path = self.path_var.get()
        
        if not self.tree.get_children():
            return expanded, unchecked

        for item_id, full_path in self.tree_path_map.items():
            # Check expansion
            if self.tree.item(item_id, "open"):
                try:
                    rel = os.path.relpath(full_path, root_path).replace("\\", "/")
                    expanded.add(rel)
                except ValueError:
                    pass
            
            # Check checked state
            if not self.tree_checked_state.get(item_id, True):
                try:
                    rel = os.path.relpath(full_path, root_path).replace("\\", "/")
                    unchecked.add(rel)
                except ValueError:
                    pass
        return expanded, unchecked

    def refresh_preview_tree(self):
        if hasattr(self, 'lbl_opt_quality'):
            self.lbl_opt_quality.config(text="")
            
        root_path = self.path_var.get()
        
        if os.path.isdir(root_path):
            if getattr(self, 'current_project_path', None) != root_path:
                if getattr(self, 'current_project_path', None):
                    self.save_project_state(self.current_project_path)
                self.load_project_state(root_path)
                self.current_project_path = root_path

        if not self.tree_path_map:
            current_expanded = set(self.settings.get("ui_tree_expanded", []))
            current_unchecked = set(self.settings.get("ui_tree_unchecked",[]))
        else:
            current_expanded, current_unchecked = self._get_tree_state()

        if not os.path.exists(root_path):
            root_path = self.path_var.get()
        if not os.path.exists(root_path):
            self.tree.delete(*self.tree.get_children())
            self.tree_checked_state.clear()
            self.tree_path_map.clear()
            return

        cfg = self.settings.copy()
        cfg.update({
            "root_folder": root_path,
            "extensions": self.ext_var.get(),
            "ignore_list": self.ignore_var.get(),
            "strict_mode": self.settings.get("strict_mode", False)
        })

        self.status_var.set("Обновление дерева файлов...")

        def _scan_thread():
            try:
                files, empty_dirs = self.analyzer.scan_directory(cfg)
                files.sort(key=lambda x: x[0])
                self.safe_after(lambda: self._update_tree_ui(root_path, files, current_expanded, current_unchecked))
            except Exception as e:
                print(f"Tree scan error: {e}")
                self.safe_after(lambda: self.status_var.set("Готов к работе"))

        threading.Thread(target=_scan_thread, daemon=True).start()

    def _update_tree_ui(self, root_path, files, current_expanded, current_unchecked):
        self.tree.delete(*self.tree.get_children())
        self.tree_checked_state.clear()
        self.tree_path_map.clear()

        root_id = self.tree.insert("", "end", text=f"✅ {root_path}", open=True)
        self.tree_path_map[root_id] = os.path.abspath(root_path)
        self.tree_checked_state[root_id] = True
        
        dir_nodes = {".": root_id}
        
        def set_state(node_id, rel_p, is_dir=False):
            should_be_checked = (rel_p not in current_unchecked)
            self.tree_checked_state[node_id] = should_be_checked
            
            if is_dir and rel_p in current_expanded:
                self.tree.item(node_id, open=True)
            
            txt = self.tree.item(node_id, "text")
            prefix = "✅ " if should_be_checked else "⬜ "
            if txt.startswith("✅ ") or txt.startswith("⬜ "):
                txt = txt[2:]
            self.tree.item(node_id, text=prefix + txt)

        for full_path, ext in files:
            rel_path = os.path.relpath(full_path, root_path)
            parts = rel_path.split(os.sep)
            
            parent_id = root_id
            current_rel = ""
            
            for part in parts[:-1]:
                current_rel = os.path.join(current_rel, part) if current_rel else part
                rel_slash = current_rel.replace("\\", "/")
                
                if current_rel not in dir_nodes:
                    node_id = self.tree.insert(parent_id, "end", text=f"{part}", open=False)
                    dir_nodes[current_rel] = node_id
                    self.tree_path_map[node_id] = os.path.join(root_path, current_rel)
                    set_state(node_id, rel_slash, is_dir=True)
                parent_id = dir_nodes[current_rel]
            
            fname = parts[-1]
            file_id = self.tree.insert(parent_id, "end", text=f"{fname} ({ext})")
            self.tree_path_map[file_id] = full_path
            set_state(file_id, rel_path.replace("\\", "/"), is_dir=False)

        self.status_var.set("Готов к работе")
    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        element = self.tree.identify_element(event.x, event.y)

        # Игнорируем клик по треугольнику раскрытия (пусть работает штатно)
        if "indicator" in element:
            return

        if region == "tree":
            item_id = self.tree.identify_row(event.y)
            if not item_id: return
            current = self.tree_checked_state.get(item_id, True)
            self._toggle_item(item_id, not current)
            # Блокируем стандартную обработку (чтобы клик по тексту не вызывал раскрытия/выделения)
            return "break"

    def _toggle_item(self, item_id, state):
        if hasattr(self, 'lbl_opt_quality') and self.lbl_opt_quality.cget("text") != "":
            self.lbl_opt_quality.config(text="")
        self.tree_checked_state[item_id] = state
        txt = self.tree.item(item_id, "text")
        clean_txt = txt[2:] if txt.startswith("✅ ") or txt.startswith("⬜ ") else txt
        prefix = "✅ " if state else "⬜ "
        self.tree.item(item_id, text=prefix + clean_txt)
        for child in self.tree.get_children(item_id):
            self._toggle_item(child, state)
    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.path_var.get())
        if folder: self.path_var.set(folder)

    def auto_set_folder(self):
        if getattr(sys, 'frozen', False):
            parent_dir = os.path.dirname(sys.executable)
        else:
            parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.path_var.set(parent_dir)

    def save_current_settings(self):
        # Get UI state to save
        expanded, unchecked = self._get_tree_state()
        self.settings.update({
            "root_folder": self.path_var.get(),
            "extensions": self.ext_var.get(),
            "ignore_list": self.ignore_var.get(),
            "output_name": self.out_var.get(),
            "include_empty_folders": getattr(self, 'include_empty_var', tk.BooleanVar(value=False)).get(),
            "add_edit_prompt": self.add_edit_prompt_var.get(),
            "include_plan": getattr(self, 'include_plan_var', tk.BooleanVar(value=False)).get(),
            "auto_copy_file": self.auto_copy_var.get(),
            "line_numbers": self.line_numbers_var.get(),
            "ollama_model": getattr(self, 'ollama_model_var', tk.StringVar(value="None")).get(),
            "ollama_options": {
                "num_ctx": int(getattr(self, 'opt_ctx', tk.StringVar(value="24000")).get()),
                "num_predict": int(getattr(self, 'opt_pred', tk.StringVar(value="12000")).get()),
                "temperature": float(getattr(self, 'opt_temp', tk.StringVar(value="0.5")).get()),
                "top_p": float(getattr(self, 'opt_topp', tk.StringVar(value="0.95")).get()),
                "top_k": int(getattr(self, 'opt_topk', tk.StringVar(value="100")).get())
            },
            "ui_tree_expanded": list(expanded),
            "ui_tree_unchecked": list(unchecked)
        })
        self.config_manager.save(self.settings)
        return self.settings

    def start_processing(self):
        if getattr(self, 'is_generating', False):
            self._cancel_generation = True
            self.btn_run.config(text="ОТМЕНА...", state=tk.DISABLED)
            return

        self.is_generating = True
        self._cancel_generation = False

        settings = self.save_current_settings()
        root_folder = settings.get("root_folder", "")
        if not root_folder or not os.path.exists(root_folder):
            messagebox.showerror("Ошибка", f"Указанная папка проекта не существует:\n{root_folder}")
            self.is_generating = False
            return
        
        if self.tree.get_children():
            excluded = set()
            for item_id, path in self.tree_path_map.items():
                # Собираем только явно отключенные файлы (Blacklist approach)
                if not self.tree_checked_state.get(item_id, True):
                    if os.path.isfile(path):
                        excluded.add(os.path.normcase(os.path.abspath(path)))
            settings["excluded_paths"] = list(excluded)

        # Добавляем скрытые настройки, которые не меняются в GUI, но нужны анализатору
        settings["strict_mode"] = self.settings.get("strict_mode", False)
        settings["ignore_self"] = True

        self.btn_run.config(text="❌ ОТМЕНИТЬ ГЕНЕРАЦИЮ", bg=self.get_theme_colors()["btn_active"])
        self.status_var.set("Поиск файлов...")
        self.progress.pack(fill=tk.BOTH, expand=True)
        self.progress['value'] = 0
        thread = threading.Thread(target=self.run_logic, args=(settings,))
        thread.start()

    def update_progress_safe(self, current, total):
        percent = int((current / total) * 100) if total > 0 else 0
        self.safe_after(lambda: self._update_ui_progress(current, total, percent))

    def _update_ui_progress(self, current, total, percent):
        self.progress['maximum'] = total
        self.progress['value'] = current
        self.status_var.set(f"Обработка: {current}/{total} ({percent}%)")

    def run_logic(self, settings):
        try:
            result = self.analyzer.process(settings, self.update_progress_safe, cancel_callback=lambda: self._cancel_generation)
            if result is None:
                self.safe_after(self.on_cancel)
            else:
                output_path, count, lines, chars = result
                self.safe_after(lambda: self.on_success(output_path, count, lines, chars, settings.get("auto_copy_file", False)))
        except Exception as e:
            self.safe_after(lambda: self.on_error(str(e)))

    def on_cancel(self):
        self.is_generating = False
        self.btn_run.config(state=tk.NORMAL, text="ГЕНЕРИРОВАТЬ КОНТЕКСТ", bg=self.get_theme_colors()["btn_bg"])
        self.status_var.set("Генерация отменена")
        self.progress.pack_forget()

    def on_success(self, path, count, lines, chars, auto_copy):
        self.is_generating = False
        self.btn_run.config(state=tk.NORMAL, text="ГЕНЕРИРОВАТЬ КОНТЕКСТ", bg=self.get_theme_colors()["btn_bg"])
        
        def fmt(n):
            if n >= 1_000_000:
                return f"{n / 1_000_000:.2f}".rstrip('0').rstrip('.') + "M"
            elif n >= 1_000:
                return f"{n / 1_000:.2f}".rstrip('0').rstrip('.') + "K"
            return str(n)

        fmt_lines = fmt(lines)
        fmt_chars = fmt(chars)

        self.status_var.set(f"Готово! Файлов: {count} | Строк: {fmt_lines} | Символов: {fmt_chars}")
        self.progress.pack_forget()

        msg = f"Отчет создан:\n{path}\n\nФайлов: {count}\nСтрок кода: {fmt_lines}\nСимволов: {fmt_chars}"
        if auto_copy:
            if copy_file_to_clipboard_windows(path):
                msg += "\n\n📋 ФАЙЛ СКОПИРОВАН В БУФЕР!"
            else:
                msg += "\n\n⚠️ Ошибка копирования в буфер."
        messagebox.showinfo("Успех", msg)

    def on_error(self, error_msg):
        self.is_generating = False
        self.btn_run.config(state=tk.NORMAL, text="ГЕНЕРИРОВАТЬ КОНТЕКСТ", bg=self.get_theme_colors()["btn_bg"])
        self.status_var.set("Ошибка выполнения")
        self.progress.pack_forget()
        messagebox.showerror("Ошибка", f"Что-то пошло не так:\n{error_msg}")

    def run_ollama_fix(self, text, model):
        if not messagebox.askyesno("Auto-Fix", f"JSON некорректен. Попробовать исправить через {model}?"):
            return
        self.editor_status_var.set(f"⏳ Исправление через {model}...")
        self.editor_text.config(state=tk.DISABLED)
        
        def _worker():
            if model == "BomjAPI":
                import re
                result_container = []
                ev = threading.Event()
                def _run_api():
                    try:
                        prompt_text = f"Fix the following JSON\nPay special attention to the SCREENING and BALANCING of brackets, quotation marks, etc.\nOutput ONLY fixed JSON\nDo NOT DELETE/CHANGE/ADD any INFORMATION or FIELDS!\n{text}"
                        api = BomjAPI(validators={"BomjAPI": lambda t: bool(re.search(r'\{.*\}|\[.*\]', t, re.DOTALL))})
                        res_text = api.send({"model": "BomjAPI", "prompt": prompt_text}, parent=self)
                        result_container.append(res_text)
                    except Exception as e:
                        print("BomjAPI error:", e)
                    finally:
                        ev.set()
                self.safe_after(_run_api)
                ev.wait()
                fixed = result_container[0] if result_container else ""
            elif model.startswith("Web: "):
                adapter = None
                try:
                    from ..utils.majorchic_api import MajorchicAPIAdapter
                    backend = "gemini" if "Gemini" in model else "deepseek"
                    expert = "Expert" in model
                    deep_think = "DeepThink" in model
                    
                    adapter = MajorchicAPIAdapter(
                        backend=backend, 
                        headless=False, 
                        profile_name="default", 
                        expert_mode=expert, 
                        deep_think=deep_think,
                        timeout=self.settings.get("web_api_timeout", 600),
                        stable_count=self.settings.get("web_api_stable_count", 7)
                    )
                    prompt_text = f"Fix the following JSON\nPay special attention to the SCREENING and BALANCING of brackets, quotation marks, etc.\nOutput ONLY fixed JSON\nDo NOT DELETE/CHANGE/ADD any INFORMATION or FIELDS!\n{text}"
                    fixed = adapter.send(prompt_text)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print("Web API error:", e)
                    fixed = ""
                    self.safe_after(lambda err=e: messagebox.showerror("Ошибка Web API", f"Не удалось выполнить запрос.\n{err}"))
                finally:
                    if adapter:
                        try:
                            adapter.close()
                        except Exception:
                            pass
            else:
                options = {
                    "num_ctx": int(self.opt_ctx.get()),
                    "num_predict": int(self.opt_pred.get()),
                    "temperature": float(self.opt_temp.get()),
                    "top_p": float(self.opt_topp.get()),
                    "top_k": int(self.opt_topk.get())
                }
                client = OllamaClient(model, options)
                fixed = client.fix_json(text)
            self.safe_after(lambda: self._on_fix_done(fixed))

        threading.Thread(target=_worker).start()

    def _on_fix_done(self, result):
        self.editor_text.config(state=tk.NORMAL)
        if result:
            # Дополнительная очистка на уровне GUI перед вставкой
            cleaned = clean_json_text(result)
            self.editor_text.delete("1.0", tk.END)
            self.editor_text.insert("1.0", cleaned)
            self.validate_json_ui() # Re-validate
        else:
            self.editor_status_var.set("❌ Не удалось исправить JSON.")
            messagebox.showerror("Ollama", "Модель вернула пустой ответ или произошла ошибка.")
    def open_optimization_dialog(self):
        total_tokens = 0
        for path in self.tree_path_map.values():
            if os.path.isfile(path) and path.endswith('.py'):
                try:
                    total_tokens += os.path.getsize(path) // 4
                except:
                    pass
        if total_tokens == 0:
            total_tokens = 1000

        dlg = tk.Toplevel(self)
        dlg.title("Оптимизация контекста")
        dlg.geometry("500x520")
        dlg.configure(bg="#1e1e1e")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="Описание задачи (на русском или английском):", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(15, 5))
        task_text = tk.Text(dlg, height=5, bg="#252526", fg="white", insertbackground="white", relief="flat", font=("Segoe UI", 10))
        task_text.pack(fill=tk.X, padx=20)

        tk.Label(dlg, text="Процент сжатия (оставить % объёма):", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(15, 5))
        pct_frame = tk.Frame(dlg, bg="#1e1e1e")
        pct_frame.pack(fill=tk.X, padx=20)
        pct_var = tk.IntVar(value=self.settings.get("opt_compression_pct", 50))
        
        lbl_est_tokens = tk.Label(dlg, text="", bg="#1e1e1e", fg="#98c379", font=("Segoe UI", 9, "bold"))
        
        def update_est_tokens(*args):
            tokens = max(1, int(total_tokens * (pct_var.get() / 100.0)))
            lbl_est_tokens.config(text=f"Ожидаемо токенов: ~{tokens} (из ~{total_tokens})")
            
        pct_var.trace_add("write", update_est_tokens)
        tk.Scale(pct_frame, from_=1, to_=100, orient=tk.HORIZONTAL, variable=pct_var, bg="#1e1e1e", fg="#cccccc", highlightthickness=0, bd=0, length=300).pack(side=tk.LEFT)
        tk.Label(pct_frame, text="%", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=5)
        lbl_est_tokens.pack(anchor="w", padx=20, pady=(5, 10))
        update_est_tokens()

        tk.Label(dlg, text="Глубина BFS обхода графа зависимостей:", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(5, 5))
        depth_var = tk.IntVar(value=2)
        tk.Spinbox(dlg, from_=1, to_=5, textvariable=depth_var, width=5, bg="#252526", fg="white", relief="flat").pack(anchor="w", padx=20)

        tk.Label(dlg, text="Модель LLM:", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(15, 5))
        web_models = ["Web: Gemini", "Web: DeepSeek", "Web: DeepSeek (DeepThink)", "Web: DeepSeek Expert", "Web: DeepSeek Expert (DeepThink)"]
        models = ["None", "BomjAPI"] + web_models + get_installed_models()
        model_var = tk.StringVar(value=self.settings.get("opt_default_model", "BomjAPI"))
        combo = ttk.Combobox(dlg, textvariable=model_var, values=models, state="readonly")
        combo.pack(fill=tk.X, padx=20)

        def start():
            task = task_text.get("1.0", tk.END).strip()
            pct = pct_var.get()
            limit = max(1, int(total_tokens * (pct / 100.0)))
            depth = depth_var.get()
            mod = model_var.get()
            if not task:
                messagebox.showwarning("Внимание", "Опишите задачу!")
                return
            self.settings["opt_default_model"] = mod
            self.settings["opt_compression_pct"] = pct
            dlg.destroy()
            self.start_optimization_process(task, limit, depth, mod)

        tk.Button(dlg, text="🚀 НАЧАТЬ ОПТИМИЗАЦИЮ", command=start, bg="#0e639c", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", pady=5).pack(fill=tk.X, padx=20, pady=20)
        self.apply_theme_recursive(dlg)
    def start_optimization_process(self, task, limit_tokens, depth, model):
        if getattr(self, 'is_generating', False):
            return
        self.is_generating = True
        self.btn_run.config(state=tk.DISABLED)
        self.status_var.set("Оптимизация: Подготовка файлов...")
        self.progress.pack(fill=tk.BOTH, expand=True)
        self.progress['value'] = 0

        root_path = self.path_var.get()
        cfg = self.settings.copy()
        cfg.update({"root_folder": root_path, "extensions": self.ext_var.get(), "ignore_list": self.ignore_var.get(), "strict_mode": self.settings.get("strict_mode", False)})

        threading.Thread(target=self._optimization_worker, args=(cfg, task, limit_tokens, depth, model, root_path), daemon=True).start()


    def _optimization_worker(self, cfg, task, limit_tokens, depth, model, root_path):
        try:
            # Инициализируем клиент LLM, если нужно
            llm_client = None
            if model != "None":
                if model == "BomjAPI":
                    from ..utils.BomjAPI import BomjAPI
                    # Для BomjAPI создадим обёртку, имитирующую интерфейс OllamaClient
                    class BomjWrapper:
                        def __init__(self, app_instance):
                            self.app = app_instance
                        def optimize_context(self, task, meta_list):
                            import json, re, threading
                            prompt = self._build_prompt(task, meta_list)
                            
                            result_container = [None]
                            ev = threading.Event()
                            
                            def _run_api():
                                try:
                                    api = BomjAPI(validators={"BomjAPI": lambda t: bool(re.search(r'\{.*\}', t, re.DOTALL))})
                                    res_text = api.send({"model": "BomjAPI", "prompt": prompt}, parent=self.app)
                                    result_container[0] = res_text
                                except Exception as e:
                                    print("BomjAPI error:", e)
                                finally:
                                    ev.set()
                            
                            self.app.safe_after(_run_api)
                            ev.wait()
                            
                            res_text = result_container[0]
                            if res_text:
                                match = re.search(r'\{.*\}', res_text, re.DOTALL)
                                if match:
                                    try:
                                        return json.loads(match.group(0))
                                    except:
                                        pass
                            return {}
                        def _build_prompt(self, task, meta_list):
                            context = ""
                            for m in meta_list:
                                context += f"File: {m['path']}\nLines: {m['lines']}\nClasses: {', '.join(m.get('classes', []))}\nFunctions: {', '.join(m.get('functions', []))}\n\n"
                            return f"""You are a Senior Software Architect. Evaluate importance of each file for task: {task}
Rules:
1. Assign an integer score from 0 to 100 for each file. Gradation is allowed (e.g., 57, 83, 98, 99).
2. SCORING CRITERIA:
   - 100: ONLY if the file is explicitly mentioned in the task by exact name and MUST be in context.
   - 99: If the file name is an inexact match but clearly intended.
   - 98: Files that are 100% necessary/crucial to modify for the given task.
   - 50-97: Gradation of importance (e.g., 57, 83). Highly important, necessary for understanding logic.
   - 30-49: Useful context.
   - 0-29: Unrelated or loosely related.
3. Output ONLY a valid JSON object where keys are file paths and values are integer scores.
Example: {{\"path/to/file1.py\": 100, \"path/to/file2.py\": 30, \"path/to/file3.py\": 57}}
Files:
{context}"""
                    llm_client = BomjWrapper(self)
                elif model.startswith("Web: "):
                    class WebAPIWrapper:
                        def __init__(self, app_instance, model_name):
                            self.app = app_instance
                            self.backend = "gemini" if "Gemini" in model_name else "deepseek"
                            self.expert = "Expert" in model_name
                            self.deep_think = "DeepThink" in model_name
                        
                        def optimize_context(self, task, meta_list):
                            import json, re
                            prompt = self._build_prompt(task, meta_list)

                            try:
                                from ..utils.majorchic_api import MajorchicAPIAdapter
                                adapter = MajorchicAPIAdapter(
                                    backend=self.backend, 
                                    headless=False, 
                                    profile_name="default", 
                                    expert_mode=self.expert, 
                                    deep_think=self.deep_think,
                                    timeout=self.app.settings.get("web_api_timeout", 600),
                                    stable_count=self.app.settings.get("web_api_stable_count", 7)
                                )
                                res_text = adapter.send(prompt)
                                if res_text:
                                    match = re.search(r'\{.*\}', res_text, re.DOTALL)
                                    if match:
                                        try:
                                            return json.loads(match.group(0))
                                        except:
                                            pass
                            except Exception as e:
                                import traceback
                                traceback.print_exc()
                                print("Optimization Web API Error:", e)
                                self.app.safe_after(lambda err=e: messagebox.showerror("Ошибка Web API", f"Не удалось выполнить запрос.\n{err}"))
                            finally:
                                if adapter:
                                    try:
                                        adapter.close()
                                    except Exception:
                                        pass
                            return {}
                        def _build_prompt(self, task, meta_list):
                            context = ""
                            for m in meta_list:
                                context += f"File: {m['path']}\nLines: {m['lines']}\nClasses: {', '.join(m.get('classes', []))}\nFunctions: {', '.join(m.get('functions', []))}\n\n"
                            return f"""You are a Senior Software Architect. Evaluate importance of each file for task: {task}
Rules:
1. Assign an integer score from 0 to 100 for each file. Gradation is allowed (e.g., 57, 83, 98, 99).
2. SCORING CRITERIA:
   - 100: ONLY if the file is explicitly mentioned in the task by exact name and MUST be in context.
   - 99: If the file name is an inexact match but clearly intended.
   - 98: Files that are 100% necessary/crucial to modify for the given task.
   - 50-97: Gradation of importance (e.g., 57, 83). Highly important, necessary for understanding logic.
   - 30-49: Useful context.
   - 0-29: Unrelated or loosely related.
3. Output ONLY a valid JSON object where keys are file paths and values are integer scores.
Example: {{"path/to/file1.py": 100, "path/to/file2.py": 30, "path/to/file3.py": 57}}
Files:
{context}"""
                    llm_client = WebAPIWrapper(self, model)
                else:
                    from ..core.ollama_client import OllamaClient
                    llm_client = OllamaClient(model, self.settings.get("ollama_options", {}))

            # Создаём оптимизатор
            optimizer = ContextOptimizer(
                root_folder=root_path,
                task=task,
                limit_tokens=limit_tokens,
                llm_client=llm_client,
                cache_dir=os.path.join(root_path, ".pig_cache"),
                bfs_depth=self.settings.get("opt_bfs_depth", 2),
                greedy_llm_weight=self.settings.get("opt_greedy_llm_weight", 0.6),
                greedy_pr_weight=self.settings.get("opt_greedy_pr_weight", 0.3),
                greedy_cc_weight=self.settings.get("opt_greedy_cc_weight", 0.1),
                token_bytes_per_token=self.settings.get("opt_token_bytes_per_token", 4)
            )
            # BFS глубина теперь управляется через self.bfs_depth; убираем хак

            # Запускаем оптимизацию с прогрессом
            def progress_callback(percent, msg):
                self.safe_after(lambda: self._update_opt_progress(percent, msg))

            def fallback_callback(msg):
                self.safe_after(lambda: messagebox.showinfo("Оптимизация (Оффлайн)", msg))

            selected_abs = optimizer.optimize(progress_callback=progress_callback, fallback_callback=fallback_callback)
            # Преобразуем в относительные пути
            selected_rel = [os.path.relpath(p, root_path).replace("\\", "/") for p in selected_abs]
            # Подсчёт качества (заглушка, можно вычислить позже)
            quality_pct = 100.0
            self.safe_after(lambda: self._apply_optimized_selection(selected_rel, quality_pct))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.safe_after(lambda e=e: self.on_error(f"Ошибка оптимизации: {e}"))

    def _update_opt_progress(self, percent, msg):
        self.progress['value'] = percent
        self.status_var.set(f"Оптимизация: {msg} ({percent}%)")

    def _apply_optimized_selection(self, selected_paths, quality_pct):
        self.is_generating = False
        self.btn_run.config(state=tk.NORMAL)
        self.progress.pack_forget()
        self.status_var.set(f"Оптимизация завершена. Выбрано файлов: {len(selected_paths)}")

        if hasattr(self, 'lbl_opt_quality'):
            self.lbl_opt_quality.config(text=f"Качество оптимизации: {quality_pct:.1f}%")

        # Uncheck all, then check only selected без вызова _toggle_item (чтобы не затереть надпись качества)
        for item_id, path in self.tree_path_map.items():
            if not os.path.isfile(path):
                continue
            rel = os.path.relpath(path, self.path_var.get()).replace("\\", "/")
            state = (rel in selected_paths)
            
            self.tree_checked_state[item_id] = state
            txt = self.tree.item(item_id, "text")
            clean_txt = txt[2:] if txt.startswith("✅ ") or txt.startswith("⬜ ") else txt
            prefix = "✅ " if state else "⬜ "
            self.tree.item(item_id, text=prefix + clean_txt)

    # ================== PLAN MANAGER ==================

    # ================== GIT INTEGRATION ==================
    def _check_git(self) -> bool:
        """Проверяет, доступен ли git и находится ли проект в репозитории."""
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True, timeout=5)
        except Exception:
            self.git_available = False
            self.git_repo_path = None
            return False

        root = self.path_var.get()
        try:
            result = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                self.git_available = True
                self.git_repo_path = result.stdout.strip()
                return True
        except Exception:
            pass
        self.git_available = False
        self.git_repo_path = None
        return False

    def _git_commit_before_plan(self):
        """Автоматический коммит перед выполнением плана. Учитывает настройки."""
        if not self.settings.get("git_enabled", False) or not self.git_available:
            return False
        root = self.git_repo_path
        try:
            subprocess.run(["git", "-C", root, "add", "-A"], check=True, timeout=10)
            timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            if self.settings.get("git_branch_mode", "new") == "new":
                branch_name = f"pig_plan_{timestamp}"
                subprocess.run(["git", "-C", root, "checkout", "-b", branch_name], check=True, timeout=10)
            subprocess.run(["git", "-C", root, "commit", "-m", f"PIG-T3: auto-save before plan execution ({timestamp})"],
                           check=True, timeout=10)
            if self.settings.get("git_auto_push", False):
                self._git_push()
            return True
        except Exception as e:
            print(f"Git auto-commit failed: {e}")
            return False

    def _git_push(self):
        """Выполняет git push, если настроено."""
        if not self.git_available:
            return
        try:
            subprocess.run(["git", "-C", self.git_repo_path, "push", "origin", "HEAD"], check=True, timeout=30)
        except Exception as e:
            print(f"Git push failed: {e}")

    # ================== PLAN VALIDATION & DIFF ==================
    def _validate_and_show_issues(self, plan_data):
        issues = validate_plan(plan_data)
        if issues:
            messagebox.showwarning("Проблемы плана", "Обнаружены следующие проблемы:\n\n" + "\n".join(issues))
        return len(issues) == 0

    def _log_plan_activity(self, step_title, status, message, raw_response=""):
        try:
            root_dir = self.path_var.get()
            if not root_dir or not os.path.exists(root_dir): return
            log_path = os.path.join(root_dir, "pig_plan_log.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                ts = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] STEP: {step_title} | STATUS: {status}\n")
                f.write(f"MESSAGE: {message}\n")
                if raw_response:
                    f.write("--- RAW LLM RESPONSE START ---\n")
                    f.write(str(raw_response))
                    f.write("\n--- RAW LLM RESPONSE END ---\n")
                f.write("="*80 + "\n\n")
        except Exception as e:
            print(f"Logger error: {e}")
    def open_plan_manager(self):
        self.notebook.select(self.tab_plan)
        self._load_plan()

    def _get_llm_wrapper(self, model_name, cancel_event=None):
        if model_name == "None": return None
        if model_name == "BomjAPI":
            from ..utils.BomjAPI import BomjAPI
            class BWrapper:
                def __init__(self, app): self.app = app
                def ask(self, prompt):
                    import threading, re
                    res = [None]
                    err = [None]
                    ev = threading.Event()
                    def run():
                        try:
                            api = BomjAPI(validators={"BomjAPI": lambda t: bool(re.search(r'\{.*\}|\[.*\]', t, re.DOTALL))})
                            res[0] = api.send({"model": "BomjAPI", "prompt": prompt}, parent=self.app)
                        except Exception as e:
                            err[0] = e
                            print("BomjAPI error:", e)
                        finally:
                            ev.set()
                    self.app.safe_after(run)
                    ev.wait()
                    if err[0]:
                        raise err[0]
                    return res[0]
            return BWrapper(self)
        elif model_name.startswith("Web: "):
            class WWrapper:
                def __init__(self, app, m, cancel_event=None):
                    self.app = app
                    self.m = m
                    self.cancel_event = cancel_event
                def ask(self, prompt):
                    from ..utils.majorchic_api import MajorchicAPIAdapter
                    adapter = None
                    try:
                        adapter = MajorchicAPIAdapter(
                            backend="gemini" if "Gemini" in self.m else "deepseek",
                            headless=False,
                            profile_name="default",
                            expert_mode="Expert" in self.m,
                            deep_think="DeepThink" in self.m
                        )
                        res = adapter.send(prompt, cancel_event=self.cancel_event)
                        return res
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        # Выбрасываем исключение дальше, чтобы сработал механизм повторных попыток
                        raise Exception(f"Web API Error: {str(e)}")
                    finally:
                        if adapter:
                            try:
                                adapter.close()
                            except Exception:
                                pass
            return WWrapper(self, model_name, cancel_event=cancel_event)
        else:
            from ..core.ollama_client import OllamaClient
            class OWrapper:
                def __init__(self, m, opts): self.client = OllamaClient(m, opts)
                def ask(self, prompt): return self.client.fix_json(prompt)
            return OWrapper(model_name, self.settings.get("ollama_options", {}))

    def _generate_context_in_memory(self, root_path):
        import tempfile, os
        cfg = self.settings.copy()
        cfg.update({"root_folder": root_path, "extensions": self.ext_var.get(), "ignore_list": self.ignore_var.get()})
        if self.tree.get_children():
            excluded = [os.path.normcase(os.path.abspath(p)) for i, p in self.tree_path_map.items() if not self.tree_checked_state.get(i, True)]
            cfg["excluded_paths"] = excluded
        tmp_path = os.path.join(tempfile.gettempdir(), f"temp_pig_context_{os.urandom(4).hex()}.txt")
        cfg["output_name"] = tmp_path
        res = self.analyzer.process(cfg)
        if res:
            try:
                with open(res[0], 'r', encoding='utf-8') as f:
                    content = f.read()
                return content
            finally:
                try:
                    os.remove(res[0])
                except Exception:
                    pass
        return ""

    def _get_optimized_context(self, task_desc, model_name=None, limit_tokens=15000):
        root_path = self.path_var.get()
        if not root_path or not os.path.exists(root_path): return ""
        from ..core.context_optimizer import ContextOptimizer
        # Создаём LLM-клиент, если указана модель
        llm_client = self._get_llm_wrapper(model_name) if model_name else None
        opt = ContextOptimizer(root_folder=root_path, task=task_desc, limit_tokens=limit_tokens, llm_client=llm_client,
                            bfs_depth=self.settings.get("opt_bfs_depth", 2),
                            greedy_llm_weight=self.settings.get("opt_greedy_llm_weight", 0.6),
                            greedy_pr_weight=self.settings.get("opt_greedy_pr_weight", 0.3),
                            greedy_cc_weight=self.settings.get("opt_greedy_cc_weight", 0.1),
                            token_bytes_per_token=self.settings.get("opt_token_bytes_per_token", 4))
        selected = opt.optimize()
        ctx = ""
        for p in selected:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    content = f.read()
                rel = os.path.relpath(p, root_path).replace("\\", "/")
                ctx += f'<file path="{rel}">\n{content}\n</file>\n\n'
            except: pass
        return ctx

    # ================== PLAN MANAGER UI ==================
    def create_plan_tab(self, parent):
        self.plan_data = []
        self.current_plan_sel = None
        self._is_plan_running = False
        self._cancel_plan_flag = False
        self._plan_cancel_event = None
        self._full_plan_running = False
        self._full_plan_cancel_flag = False
        self._full_plan_complete_event = None
        self.conversation_history = []

        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg="#1e1e1e", sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = tk.Frame(paned, bg="#1e1e1e")
        paned.add(left_frame, width=300)

        top_left = tk.Frame(left_frame, bg="#1e1e1e")
        top_left.pack(fill=tk.X, pady=(0, 5))
        tk.Button(top_left, text="🔄 Обновить", command=self._load_plan, bg="#333333", fg="white", relief="flat").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(top_left, text="✨ Новый План", command=self._open_plan_creation_dialog, bg="#8c6291", fg="white",
                  relief="flat").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

        self.plan_listbox = tk.Listbox(left_frame, bg="#252526", fg="white", font=("Segoe UI", 10),
                                       selectbackground="#0e639c", activestyle="none")
        self.plan_listbox.pack(fill=tk.BOTH, expand=True)
        self.plan_listbox.bind('<<ListboxSelect>>', self._on_plan_select)

        def on_drag_start(event):
            widget = event.widget
            widget._drag_start_idx = widget.nearest(event.y)

        def on_drag_motion(event):
            widget = event.widget
            idx = widget.nearest(event.y)
            if idx != widget._drag_start_idx and idx < len(self.plan_data):
                val = widget.get(widget._drag_start_idx)
                widget.delete(widget._drag_start_idx)
                widget.insert(idx, val)
                item = self.plan_data.pop(widget._drag_start_idx)
                self.plan_data.insert(idx, item)
                widget._drag_start_idx = idx
                widget.selection_clear(0, tk.END)
                widget.selection_set(idx)
                self._save_plan_silently()

        self.plan_listbox.bind('<Button-1>', on_drag_start)
        self.plan_listbox.bind('<B1-Motion>', on_drag_motion)
        self.plan_listbox.bind('<ButtonRelease-1>', lambda e: self._refresh_plan_listbox())

        right_frame = tk.Frame(paned, bg="#1e1e1e")
        paned.add(right_frame)

        status_frame = tk.Frame(right_frame, bg="#1e1e1e")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        self.plan_completed_var = tk.BooleanVar()
        cb = ttk.Checkbutton(status_frame, text="✅ Шаг выполнен", variable=self.plan_completed_var,
                             style="TCheckbutton", command=self._save_plan_step)
        cb.pack(side=tk.LEFT)
        tk.Button(status_frame, text="🗑️ Удалить шаг", command=self._delete_plan_step, bg="#e06c75", fg="white",
                  relief="flat").pack(side=tk.RIGHT)

        tk.Label(right_frame, text="Название:", bg="#1e1e1e", fg="#cccccc").pack(anchor="w")
        self.plan_entry_title = tk.Entry(right_frame, bg="#252526", fg="white", font=("Segoe UI", 10, "bold"),
                                         relief="flat")
        self.plan_entry_title.pack(fill=tk.X, pady=(0, 10), ipady=3)
        self.plan_entry_title.bind("<KeyRelease>", lambda e: self._save_plan_step_debounced())

        tk.Label(right_frame, text="Описание (задача для ИИ):", bg="#1e1e1e", fg="#cccccc").pack(anchor="w")
        self.plan_txt_desc = scrolledtext.ScrolledText(right_frame, bg="#252526", fg="white", font=("Segoe UI", 10),
                                                       height=8, relief="flat")
        self.plan_txt_desc.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.plan_txt_desc.bind("<KeyRelease>", lambda e: self._save_plan_step_debounced())

        tk.Label(right_frame, text="Отчёт ИИ о выполнении:", bg="#1e1e1e", fg="#98c379").pack(anchor="w")
        self.plan_txt_report = scrolledtext.ScrolledText(right_frame, bg="#181818", fg="#98c379", font=("Consolas", 10),
                                                         height=5, relief="flat")
        self.plan_txt_report.pack(fill=tk.X, pady=(0, 10))
        self.plan_txt_report.bind("<KeyRelease>", lambda e: self._save_plan_step_debounced())

        # СОЗДАЕМ bot_frame КАК АТРИБУТ КЛАССА
        self.bot_frame = tk.LabelFrame(parent, text="🤖 Выполнение", bg="#1e1e1e", fg="#cccccc", pady=10, padx=10)
        self.bot_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        tk.Label(self.bot_frame, text="Модель:", bg="#1e1e1e", fg="#cccccc").pack(side=tk.LEFT)
        models = ["BomjAPI"] + ["Web: Gemini", "Web: DeepSeek", "Web: DeepSeek Expert"] + get_installed_models()
        self.plan_model_var = tk.StringVar(value="BomjAPI")
        ttk.Combobox(self.bot_frame, textvariable=self.plan_model_var, values=models, state="readonly", width=20).pack(
            side=tk.LEFT, padx=(5, 15))

        self.plan_auto_apply_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.bot_frame, text="Авто-применение (Иначе - в Редактор)", variable=self.plan_auto_apply_var,
                        style="TCheckbutton").pack(side=tk.LEFT, padx=(0, 15))

        self.plan_progress = ttk.Progressbar(self.bot_frame, orient="horizontal", length=150, mode="indeterminate")
        # Не пакуем progress сразу, будем показывать только при выполнении

        self.btn_plan_exec = tk.Button(self.bot_frame, text="🚀 ВЫПОЛНИТЬ ВЫБРАННЫЙ ШАГ",
                                       command=self._execute_selected_step,
                                       bg="#0e639c", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", padx=10)
        self.btn_plan_exec.pack(side=tk.RIGHT)

        self.btn_full_plan = tk.Button(self.bot_frame, text="▶️ ВЫПОЛНИТЬ ВЕСЬ ПЛАН", command=self._execute_full_plan,
                                       bg="#0e639c", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", padx=10)
        self.btn_full_plan.pack(side=tk.RIGHT, padx=(0, 5))

        self.btn_retry_step = tk.Button(self.bot_frame, text="🔄 Повторить шаг с ошибкой",
                                        command=self._retry_failed_step,
                                        bg="#e06c75", fg="white", relief="flat", state=tk.DISABLED, padx=10)
        self.btn_retry_step.pack(side=tk.RIGHT, padx=5)

        # Добавляем глобальный прогресс-бар и статус
        self.plan_global_progress = ttk.Progressbar(self.bot_frame, orient="horizontal", length=250, mode="determinate")
        self.plan_global_progress.pack(side=tk.LEFT, padx=(10, 5))
        self.lbl_plan_status = tk.Label(self.bot_frame, text="Готов", bg="#1e1e1e", fg="#e5c07b")
        self.lbl_plan_status.pack(side=tk.LEFT, expand=True, padx=10)

        self._plan_save_timer = None


    def _execute_full_plan(self):
        if self._full_plan_running:
            self._full_plan_cancel_flag = True
            self.btn_full_plan.config(text="▶️ Отмена полного плана...", state=tk.DISABLED)
            return

        if not self.plan_data:
            messagebox.showwarning("Внимание", "План пуст. Сгенерируйте или создайте план.")
            return

        if all(step.get("completed", False) for step in self.plan_data):
            messagebox.showinfo("План выполнен", "Все шаги плана уже выполнены.")
            return

        self._full_plan_running = True
        self._full_plan_cancel_flag = False
        self.btn_full_plan.config(text="⏹ ОСТАНОВИТЬ ПОЛНЫЙ ПЛАН", bg=self.get_theme_colors()["btn_active"])
        self.plan_global_progress['maximum'] = len(self.plan_data)
        self.plan_global_progress['value'] = 0

        # Запуск событийно-ориентированного конвейера
        threading.Thread(target=self._run_next_full_plan_step, daemon=True).start()

    def _run_next_full_plan_step(self):
        if self._full_plan_cancel_flag:
            self.safe_after(lambda: self._finish_full_plan("отменён"))
            return

        # Ищем первый невыполненный шаг.
        # Поскольку каждый раз сканируется весь массив,
        # если шаг проверки снял галочку с шага исполнения,
        # цикл автоматически вернется к пункту исполнения.
        current_index = -1
        for i, step in enumerate(self.plan_data):
            if not step.get("completed", False):
                current_index = i
                break
        
        if current_index == -1:
            self.safe_after(lambda: self.plan_global_progress.config(value=len(self.plan_data)))
            self.safe_after(lambda: self._finish_full_plan("завершён"))
            return
        
        step = self.plan_data[current_index]

        self.safe_after(lambda idx=current_index: self._update_full_plan_progress(idx))
        self.safe_after(lambda s=step, idx=current_index: self.lbl_plan_status.config(text=f"Выполнение шага: {s.get('title', '')} ({idx+1}/{len(self.plan_data)})"))

        # Делегируем исполнение и передаем коллбэк
        self.safe_after(lambda s=step: self._execute_step_with_callback(s, self._on_step_done_callback))

    def _on_step_done_callback(self, step):
        if self._full_plan_cancel_flag:
            self.safe_after(lambda: self._finish_full_plan("отменён"))
            return

        if step.get("status") == "failed":
            self.safe_after(lambda: self._finish_full_plan("остановлен из-за ошибки"))
            return

        # Цепочка продолжается (запускаем в новом потоке, чтобы не копить стек вызовов)
        threading.Thread(target=self._run_next_full_plan_step, daemon=True).start()

    def _execute_step_with_callback(self, step, done_callback):
        # Устанавливаем текущий шаг в GUI
        try:
            idx = self.plan_data.index(step)
        except ValueError:
            idx = 0
        self.current_plan_sel = idx
        self.plan_listbox.selection_clear(0, tk.END)
        self.plan_listbox.selection_set(idx)
        self.plan_listbox.activate(idx)
        self._on_plan_select()

        model_name = self.plan_model_var.get()
        auto_apply = True  # При полном плане всегда применяем изменения
        self._is_plan_running = True
        self.btn_plan_exec.config(state=tk.DISABLED, text="⏳ Выполнение...")
        self.plan_progress.pack(side=tk.LEFT, padx=(10, 5))
        self.plan_progress.start(10)

        def on_step_complete():
            self._is_plan_running = False
            self.btn_plan_exec.config(state=tk.NORMAL, text="🚀 ВЫПОЛНИТЬ ВЫБРАННЫЙ ШАГ", bg=self.get_theme_colors()["btn_bg"])
            self.plan_progress.stop()
            self.plan_progress.pack_forget()
            if done_callback:
                done_callback(step)

        # Передаем on_step_complete в качестве done_callback в конечную задачу
        threading.Thread(target=lambda: self._run_plan_step_task(step, model_name, auto_apply, on_step_complete), daemon=True).start()
    def _update_full_plan_progress(self, current_index):
        self.plan_global_progress['value'] = current_index

    def _finish_full_plan(self, status_msg):
        self._full_plan_running = False
        self._full_plan_cancel_flag = False
        self._full_plan_complete_event = None
        self.btn_full_plan.config(text="▶️ ВЫПОЛНИТЬ ВЕСЬ ПЛАН", bg=self.get_theme_colors()["btn_bg"], state=tk.NORMAL)
        self.plan_global_progress['value'] = 0
        self.lbl_plan_status.config(text=f"Полный план {status_msg}.")
        self._refresh_plan_listbox()

    # ================== PLAN DATA MANAGEMENT ==================
    def _load_plan(self):
        root_path = self.path_var.get()
        if not root_path or not os.path.exists(root_path): return
        plan_path = os.path.join(root_path, ".pig", "plan.json")
        try:
            with open(plan_path, 'r', encoding='utf-8') as f:
                self.plan_data = json.load(f)
            self._validate_and_show_issues(self.plan_data)
        except Exception:
            self.plan_data = []
        self.conversation_history = []
        self._refresh_plan_listbox()

    def _save_plan_silently(self):
        root_path = self.path_var.get()
        if not root_path or not os.path.exists(root_path): return
        plan_path = os.path.join(root_path, ".pig", "plan.json")
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        with open(plan_path, 'w', encoding='utf-8') as f:
            json.dump(self.plan_data, f, indent=4, ensure_ascii=False)

    def _refresh_plan_listbox(self):
        sel = self.plan_listbox.curselection()
        self.plan_listbox.delete(0, tk.END)
        for s in self.plan_data:
            mark = "✅" if s.get("completed") else "⬜"
            status_icon = "🔵" if s.get("status") == "in_progress" else ("🔴" if s.get("status") == "failed" else mark)
            self.plan_listbox.insert(tk.END, f"{status_icon} {s.get('title', 'Без названия')}")
            if s.get("completed"):
                self.plan_listbox.itemconfig(tk.END, {'fg': '#98c379'})
            elif s.get("status") == "failed":
                self.plan_listbox.itemconfig(tk.END, {'fg': '#e06c75'})
            elif s.get("status") == "in_progress":
                self.plan_listbox.itemconfig(tk.END, {'fg': '#61afef'})
        if sel and sel[0] < len(self.plan_data):
            self.plan_listbox.selection_set(sel[0])
        elif self.plan_data:
            self.plan_listbox.selection_set(0)
        self._on_plan_select()

    def _on_plan_select(self, event=None):
        sel = self.plan_listbox.curselection()
        if not sel:
            self.current_plan_sel = None
            self.btn_retry_step.config(state=tk.DISABLED)
            return
        self.current_plan_sel = sel[0]
        step = self.plan_data[self.current_plan_sel]
        self.plan_completed_var.set(step.get("completed", False))
        self.plan_entry_title.delete(0, tk.END)
        self.plan_entry_title.insert(0, step.get('title', ''))
        self.plan_txt_desc.delete("1.0", tk.END)
        self.plan_txt_desc.insert("1.0", step.get('description', ''))
        self.plan_txt_report.delete("1.0", tk.END)
        self.plan_txt_report.insert("1.0", step.get('report', ''))
        if step.get('status') == 'failed':
            self.btn_retry_step.config(state=tk.NORMAL)
        else:
            self.btn_retry_step.config(state=tk.DISABLED)

    def _save_plan_step_debounced(self):
        if self._plan_save_timer:
            self.after_cancel(self._plan_save_timer)
        self._plan_save_timer = self.after(500, self._save_plan_step)

    def _save_plan_step(self):
        if self.current_plan_sel is None or self.current_plan_sel >= len(self.plan_data): return
        step = self.plan_data[self.current_plan_sel]
        step['completed'] = self.plan_completed_var.get()
        step['title'] = self.plan_entry_title.get()
        step['description'] = self.plan_txt_desc.get("1.0", tk.END).strip()
        step['report'] = self.plan_txt_report.get("1.0", tk.END).strip()
        if step['completed'] and step.get('status') in ["in_progress", "failed"]:
            step['status'] = "completed"
        self._save_plan_silently()
        self._refresh_plan_listbox()

    def _delete_plan_step(self):
        if self.current_plan_sel is None: return
        if messagebox.askyesno("Удалить", "Точно удалить этот шаг?"):
            self.plan_data.pop(self.current_plan_sel)
            self._save_plan_silently()
            self._refresh_plan_listbox()

    def _open_plan_creation_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Новый план")
        dlg.geometry("600x480")
        dlg.configure(bg="#1e1e1e")
        dlg.transient(self)

        tk.Label(dlg, text="Введите концепцию (задачу) проекта:", bg="#1e1e1e", fg="#cccccc").pack(pady=10)
        txt = scrolledtext.ScrolledText(dlg, height=10, bg="#252526", fg="white", font=("Segoe UI", 10))
        txt.pack(fill=tk.BOTH, expand=True, padx=20)

        tk.Label(dlg, text="Модель LLM:", bg="#1e1e1e", fg="#cccccc").pack(pady=(10, 0))
        models = ["BomjAPI"] + ["Web: Gemini", "Web: DeepSeek", "Web: DeepSeek Expert"] + get_installed_models()
        m_var = tk.StringVar(value="BomjAPI")
        ttk.Combobox(dlg, textvariable=m_var, values=models, state="readonly").pack(pady=5)

        def generate():
            concept = txt.get("1.0", tk.END).strip()
            if not concept:
                messagebox.showwarning("Внимание", "Введите задачу!")
                return
            dlg.destroy()
            self._generate_plan_from_concept(concept, m_var.get())

        tk.Button(dlg, text="Создать план", command=generate, bg="#8c6291", fg="white", relief="flat", padx=10, pady=5).pack(pady=10)

    def _generate_plan_from_concept(self, concept, model_name):
        self.lbl_plan_status.config(text="⏳ Генерация плана...")
        self.btn_full_plan.config(state=tk.DISABLED)
        self.btn_plan_exec.config(state=tk.DISABLED)
        
        def worker():
            try:
                root_path = self.path_var.get()
                ctx = self._get_optimized_context(concept, model_name=model_name, limit_tokens=self.settings.get("plan_generation_limit_tokens", 12000))
                if not ctx:
                    ctx = self._generate_context_in_memory(root_path)
                    #max_chars = self.settings.get("plan_context_max_chars", 1000000)
                    #if len(ctx) > max_chars:
                    #    ctx = ctx[:max_chars] + "\n... (truncated)\n"
                
                prompt = (
                    f"You are an expert AI architect. Break down the main task into a step-by-step implementation plan.\n"
                    f"Main Task: {concept}\n\n"
                    f"ARCHITECTURE REQUIREMENTS (CRITICAL):\n"
                    f"- The project must have a clear, well-organized architecture with folders and subfolders.\n"
                    f"- Avoid monolithic single-file design; split logic into modules and packages.\n"
                    f"- The plan should consist primarily of Implementation (Impl) steps. Each Impl step must contain a detailed technical specification: exact file paths, classes, functions, and logic to implement.\n"
                    f"- Include Verification (Verify) steps only where necessary to check correctness, but NOT as mandatory pairs for every stage.\n"
                    f"- Do NOT follow a rigid 'Spec-Impl-Verify' pattern.\n"
                    f"- The first step may be 'setup_workspace' (id: setup_workspace) to configure file extensions and ignore list, but it's optional.\n\n"
                    f"RULES:\n"
                    f"1. Return ONLY a valid JSON array of objects. NO MARKDOWN TEXT OUTSIDE THE ARRAY.\n"
                    f"2. Each object must have 'id', 'title' (string), and 'description' (string, detailed technical instructions).\n"
                    f"3. Order steps logically to achieve the task.\n"
                    f"[PROJECT CONTEXT]\n{ctx}"
                )

                llm = self._get_llm_wrapper(model_name)
                if not llm:
                    raise Exception("Не удалось инициализировать LLM.")

                res = llm.ask(prompt)
                if not res or "__ERROR" in str(res):
                    raise Exception("API вернуло пустой ответ или ошибку.")

                cleaned = clean_json_text(res)
                plan = json.loads(cleaned)
                self.safe_after(lambda: self._on_plan_generated(plan))
            except Exception as e:
                self.safe_after(lambda err=e: self._on_plan_gen_error(err))
                
        threading.Thread(target=worker, daemon=True).start()

    def _on_plan_generated(self, plan):
        self.plan_data = plan
        self._save_plan_silently()
        self._refresh_plan_listbox()
        self.lbl_plan_status.config(text="План успешно сгенерирован.")
        self.btn_full_plan.config(state=tk.NORMAL)
        self.btn_plan_exec.config(state=tk.NORMAL)
        self._validate_and_show_issues(self.plan_data)

    def _on_plan_gen_error(self, err):
        self.lbl_plan_status.config(text="Ошибка генерации плана.")
        self.btn_full_plan.config(state=tk.NORMAL)
        self.btn_plan_exec.config(state=tk.NORMAL)
        messagebox.showerror("Ошибка", f"Не удалось сгенерировать план:\n{err}")

    def _execute_selected_step(self):
        if self.current_plan_sel is None or self.current_plan_sel >= len(self.plan_data):
            messagebox.showwarning("Внимание", "Выберите шаг для выполнения.")
            return

        step = self.plan_data[self.current_plan_sel]
        if step.get("completed"):
            if not messagebox.askyesno("Подтверждение", "Этот шаг уже выполнен. Выполнить повторно?"):
                return

        model_name = self.plan_model_var.get()
        auto_apply = self.plan_auto_apply_var.get()

        self._is_plan_running = True
        self._cancel_plan_flag = False
        self.btn_plan_exec.config(state=tk.DISABLED, text="⏳ Выполнение...")
        self.plan_progress.pack(side=tk.LEFT, padx=(10, 5))
        self.plan_progress.start(10)
        self.lbl_plan_status.config(text=f"Запуск шага: {step.get('title', '')}")

        threading.Thread(target=lambda: self._run_plan_step_task(step, model_name, auto_apply), daemon=True).start()

    def _retry_failed_step(self):
        self._execute_selected_step()

    def _handle_plan_step_error(self, step, error_msg):
        self._log_plan_activity(step.get("title", "Unknown"), "FATAL_ERROR", error_msg)
        self._is_plan_running = False
        self._plan_cancel_event = None
        self.plan_progress.stop()
        self.plan_progress.pack_forget()
        self.btn_plan_exec.config(state=tk.NORMAL, text="🚀 ВЫПОЛНИТЬ ВЫБРАННЫЙ ШАГ", bg=self.get_theme_colors()["btn_bg"])
        
        step['status'] = "failed"
        step['report'] = f"Ошибка: {error_msg}"
        self._save_plan_silently()
        self._refresh_plan_listbox()
        self.lbl_plan_status.config(text="Ошибка выполнения шага.")

    def _finish_plan_task(self, status_msg, step):
        self._is_plan_running = False
        self._plan_cancel_event = None
        self.plan_progress.stop()
        self.plan_progress.pack_forget()
        self.btn_plan_exec.config(state=tk.NORMAL, text="🚀 ВЫПОЛНИТЬ ВЫБРАННЫЙ ШАГ", bg=self.get_theme_colors()["btn_bg"])
        self.lbl_plan_status.config(text=status_msg)
        self._refresh_plan_listbox()

    def _run_plan_step_task(self, step, model_name, auto_apply, done_callback=None):
        root_path = self.path_var.get()
        cancel_event = threading.Event()
        self._plan_cancel_event = cancel_event
        max_retries = 2
        last_error_log = ""

        for attempt in range(max_retries + 1):
            if self._cancel_plan_flag or (self._full_plan_cancel_flag if hasattr(self, '_full_plan_cancel_flag') else False):
                self.safe_after(lambda: self._finish_plan_task("Отменено", step))
                if done_callback: done_callback()
                return

            try:
                # Git auto-commit before step
                self._check_git()
                if self.git_available:
                    self.safe_after(lambda: self.lbl_plan_status.config(text="Создание Git-ветки..."))
                    self._git_commit_before_plan()

                if self._cancel_plan_flag or cancel_event.is_set():
                    self.safe_after(lambda: self._finish_plan_task("Отменено", step))
                    if done_callback: done_callback()
                    return

                self.safe_after(lambda: self.lbl_plan_status.config(text="Сбор оптимизированного контекста..."))
                ctx = None #self._get_optimized_context(step['description'], model_name=model_name, limit_tokens=self.settings.get("plan_step_limit_tokens", 15000))

                if not ctx:
                    ctx = self._generate_context_in_memory(root_path)
                    #max_chars = self.settings.get("plan_context_max_chars", 1000000)
                    #if len(ctx) > max_chars:
                    #    ctx = ctx[:max_chars] + "\n... (truncated)\n"

                if self._cancel_plan_flag or cancel_event.is_set():
                    self.safe_after(lambda: self._finish_plan_task("Отменено", step))
                    if done_callback: done_callback()
                    return

                '''history_text = ""
                if self.conversation_history:
                    history_text = "[CHAT HISTORY]\n" + "\n".join(
                        f"User: {h['user']}\nAssistant: {h['assistant']}" for h in self.conversation_history[-5:]
                    ) + "'''
                plan_json = json.dumps(self.plan_data, indent=2, ensure_ascii=False)
                prompt = (
                    f"You are a coding assistant executing a specific step of a project plan.\n"
                    f"FULL PROJECT PLAN:\n{plan_json}\n\n"
                    f"YOUR TASK: Execute ONLY the step described below.\n"
                    f"Step ID: {step.get('id', 'N/A')}\n"
                    f"Step Title: {step['title']}\n"
                    f"Step Description:\n{step['description']}\n\n"
                    f"CRITICAL INSTRUCTIONS:\n"
                    f"1. The project context INCLUDES LINE NUMBERS. You MUST use 'replace_lines' with 'start' and 'end' for all edits.\n"
                    f"2. NEVER use 'replace_text' unless line numbers are absent. It is error-prone and discouraged.\n"
                    f"3. When creating a new file, provide its FULL content in the 'create' action. Do NOT create empty files.\n"
                    f"4. Execute this step COMPLETELY and THOROUGHLY. All code described in the step must be written. Do not leave anything for later steps unless clearly intended for another step.\n"
                    f"5. You may add creative improvements that are not explicitly in the plan if they improve code quality, structure, or user experience, as long as they don't deviate from the core goal.\n"
                    f"6. Provide the exact JSON modifications required.\n"
                    f"7. FORMAT: Your entire response must be a SINGLE valid JSON array. No markdown, no extra text. Start with '[' and end with ']'.\n"
                    f"8. To update the plan status, include a 'mark_step_completed' action when done.\n"
                    f"9. ANTI-DESTRUCTION: Use 'edit' for existing files, never 'create' to overwrite.\n"
                    f"10. Do NOT execute other steps from the plan.\n\n"
                    #f"{history_text}"
                    f"[PROJECT CONTEXT]\n{ctx}"
                )

                self.safe_after(lambda: self.lbl_plan_status.config(text="Генерация кода (LLM)..."))
                llm = self._get_llm_wrapper(model_name, cancel_event=cancel_event)
                if not llm:
                    raise Exception("Не удалось инициализировать обертку модели.")

                if self._cancel_plan_flag or cancel_event.is_set():
                    self.safe_after(lambda: self._finish_plan_task("Отменено", step))
                    if done_callback: done_callback()
                    return
                res = llm.ask(prompt)

                if self._cancel_plan_flag or cancel_event.is_set():
                    self.safe_after(lambda: self._finish_plan_task("Отменено", step))
                    if done_callback: done_callback()
                    return

                self._log_plan_activity(step.get("title", "Unknown"), "LLM_RESPONSE_RECEIVED", "Got raw response from model", res)

                if not res or "__ERROR" in str(res):
                    raise Exception(f"API вернуло пустой ответ или ошибку: {res}")

                # УНИФИЦИРОВАННЫЙ АЛГОРИТМ: Очистка и валидация JSON как в Редакторе
                try:
                    cleaned_json = clean_json_text(res)
                    parsed_data = json.loads(cleaned_json)
                    if not isinstance(parsed_data, list):
                        raise ValueError("Корень JSON должен быть списком [ ... ].")
                    # Перезаписываем res идеальным отформатированным JSON-ом
                    res = json.dumps(parsed_data, indent=2, ensure_ascii=False)
                    self._log_plan_activity(step.get("title", "Unknown"), "JSON_PARSED_OK", "Successfully parsed JSON")
                except Exception as e:
                    # Если нейросеть выдала кривой JSON, логируем это как ошибку для повторной попытки
                    err_msg = f"Error: {e}\nCleaned text:\n{clean_json_text(str(res))}"
                    self._log_plan_activity(step.get("title", "Unknown"), "JSON_PARSE_ERROR", err_msg)
                    raise Exception(f"Ошибка валидации JSON ответа: {e}\nОтвет ИИ начинался так: {str(res)[:150]}...")

                self.safe_after(lambda: self._post_exec_success(step, res, auto_apply, root_path, done_callback))
                return  # успешно, выходим

            except Exception as e:
                last_error_log = f"Попытка {attempt+1}: {str(e)}"
                if cancel_event.is_set() or self._cancel_plan_flag:
                    self.safe_after(lambda: self._finish_plan_task("Отменено", step))
                    if done_callback: done_callback()
                    return
                if attempt < max_retries:
                    time.sleep(2)
                else:
                    self.safe_after(lambda err=last_error_log: self._handle_plan_step_error(step, err))
                    if done_callback: done_callback()
    def _post_exec_success(self, step, llm_response, auto_apply, root_path, done_callback=None):
        self._is_plan_running = False
        self._plan_cancel_event = None
        self.plan_progress.stop()
        self.plan_progress.pack_forget()
        self.btn_plan_exec.config(state=tk.NORMAL, text="🚀 ВЫПОЛНИТЬ ВЫБРАННЫЙ ШАГ", bg=self.get_theme_colors()["btn_bg"])

        # Сохраняем историю диалога
        self.conversation_history.append({
            "user": f"Execute step: {step['title']}",
            "assistant": llm_response
        })

        if auto_apply:
            self.lbl_plan_status.config(text="Применение изменений...")
            
            # Подготовка бэкапа для отмены (Undo)
            try:
                data = json.loads(clean_json_text(llm_response))
                raw_paths = []
                for action in data:
                    if 'path' in action: raw_paths.append(action['path'])
                    if 'source' in action: raw_paths.append(action['source'])
                    if 'destination' in action: raw_paths.append(action['destination'])
                filtered_paths = self._filter_paths(raw_paths)
            except Exception:
                filtered_paths = []

            patch_id = str(uuid.uuid4())
            backup_root = os.path.join(root_path, ".pig", "backups", patch_id)
            if filtered_paths:
                self._copy_paths(root_path, os.path.join(backup_root, "before"), filtered_paths)

            # Напрямую применяем патч
            log = apply_llm_changes(llm_response, root_path)
            
            # Сохраняем бэкап 'after' и добавляем в историю
            if filtered_paths:
                self._copy_paths(root_path, os.path.join(backup_root, "after"), filtered_paths)
                record = {
                    "id": patch_id,
                    "paths": filtered_paths,
                    "llm_text": llm_response
                }
                self.history_stack.append(record)
                if len(self.history_stack) > 10:
                    oldest = self.history_stack.pop(0)
                    shutil.rmtree(os.path.join(root_path, ".pig", "backups", oldest["id"]), ignore_errors=True)
                self.redo_stack.clear()
                self.update_undo_redo_buttons()

            if "❌" in log or "Ошибка" in log:
                step['status'] = "failed"
                step['report'] = log
                self._save_plan_silently()
                self._refresh_plan_listbox()
                self.lbl_plan_status.config(text="Ошибка применения патча.")
                self.btn_retry_step.config(state=tk.NORMAL)
                messagebox.showerror("Ошибка применения", log)
            else:
                self._apply_mark_step_completed(step, llm_response)
                step['status'] = "completed" if self._has_mark_step_completed(llm_response) else "pending"
                step['report'] = log
                self._save_plan_silently()
                self._refresh_plan_listbox()
                self.lbl_plan_status.config(text="Шаг успешно применён.")
                
                # Горячая перезагрузка UI если AI обновил настройки (update_settings)
                if "⚙️ SETTINGS UPDATED" in log:
                    self.safe_after(lambda: self.load_project_state(root_path))
                    self.safe_after(lambda: self.on_param_change())

                # Пушим изменения в Git только если файлы действительно обновились
                if self.settings.get("git_auto_push", False) and self.git_available:
                    self._git_push()
        else:
            # Не авто: просто переносим в редактор
            self.lbl_plan_status.config(text="Генерация завершена. Перейдите в Редактор.")
            self.notebook.select(self.tab_editor)
            self.editor_text.delete("1.0", tk.END)
            self.editor_text.insert("1.0", llm_response)
            self.validate_json_ui()

        if done_callback:
            done_callback()
    def _apply_mark_step_completed(self, step, llm_response):
        """Ищет mark_step_completed в ответе LLM и обновляет plan, если находит."""
        try:
            cleaned = clean_json_text(llm_response)
            actions = json.loads(cleaned)
            for action in actions:
                if action.get("action") == "mark_step_completed":
                    if 'completed' in action:
                        step['completed'] = bool(action['completed'])
                    else:
                        step['completed'] = True  # default
                    if 'explanation' in action and action['explanation']:
                        step['report'] = action['explanation']
                    elif 'report' in action:
                        report_val = action['report']
                        if report_val is None or report_val == "":
                            step['report'] = ""
                        else:
                            step['report'] = str(report_val)
                    if 'append_description' in action:
                        append_text = str(action['append_description'])
                        if append_text:
                            current_desc = step.get('description', '')
                            step['description'] = current_desc + '\n' + append_text if current_desc else append_text
                    self._save_plan_silently()
                    self._refresh_plan_listbox()
                    break
        except Exception:
            pass

    def _has_mark_step_completed(self, llm_response):
        try:
            cleaned = clean_json_text(llm_response)
            actions = json.loads(cleaned)
            return any(a.get("action") == "mark_step_completed" for a in actions)
        except:
            return False

    def _on_step_complete(self, step, done_callback):
        """Коллбэк, вызываемый при завершении выполнения шага в ручном режиме (для совместимости)."""
        if done_callback:
            done_callback()
