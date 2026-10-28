# -*- coding: utf-8 -*-
"""Config da janela principal (cópia fiel de gui.py)."""
from app_config import load_persistent_config, t
from gui_windows import ConfigManagerWindow


class SettingsMixin:
    def open_config_window(self):
        ConfigManagerWindow(self.root, on_save_callback=self.reload_persistent_config)

    def reload_persistent_config(self):
        old_lang = getattr(self, "ui_lang", "Português")
        self.persistent_config = load_persistent_config()
        self.ui_lang = self.persistent_config.get("interface_language", "Português")
        self.root.title(t("app_title", self.ui_lang))
        # Preserva o que o usuario ja digitou/selecionou antes de reconstruir
        # a janela no novo idioma (sem isso o reload apagava tudo).
        snapshot = None
        try:
            from session_autosave import build_snapshot
            snapshot = build_snapshot(self)
        except Exception:
            snapshot = None
        saved_log = None
        try:
            import tkinter as tk
            if getattr(self, "log_text", None) is not None:
                saved_log = self.log_text.get("1.0", tk.END)
        except Exception:
            saved_log = None
        saved_output = None
        try:
            import tkinter as tk
            if getattr(self, "output_text", None) is not None:
                saved_output = self.output_text.get("1.0", tk.END)
        except Exception:
            saved_output = None
        for widget in self.root.winfo_children():
            widget.destroy()
        self.create_widgets()
        # Reaplica snapshot + religa o autosave nos widgets novos.
        try:
            if isinstance(snapshot, dict) and snapshot:
                self._restored_session = snapshot
                self._apply_restored_session()
        except Exception:
            pass
        try:
            if saved_output is not None and getattr(self, "output_text", None) is not None:
                import tkinter as tk
                self.output_text.delete("1.0", tk.END)
                if saved_output.strip():
                    self.output_text.insert(tk.END, saved_output.strip("\n"))
        except Exception:
            pass
        try:
            if getattr(self, "log_text", None) is not None:
                import tkinter as tk
                if saved_log is not None and saved_log.strip():
                    self.log_text.delete("1.0", tk.END)
                    self.log_text.insert(tk.END, saved_log.strip("\n") + "\n")
                if self.ui_lang != old_lang:
                    self.log_text.insert(tk.END, t("log_changed_to", self.ui_lang) + str(self.ui_lang) + "\n")
                    self.log_text.see(tk.END)
        except Exception:
            pass
        try:
            self._autosave_ready = True
            self._setup_autosave()
        except Exception:
            pass
