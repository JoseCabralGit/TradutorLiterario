# -*- coding: utf-8 -*-
"""Botão do preset "Janela pequena" (EXTRA opcional). Só preenche campos já existentes."""
import tkinter as tk

from app_config import t
from small_window import apply_to_agents, compute_preset, parse_window


class SmallWindowMixin:
    def apply_small_window_preset(self):
        _L = getattr(self, "ui_lang", "Português")
        win = parse_window(self.window_combo.get())
        if win <= 0:
            self._sw_rag_cap = 0
            self.window_status.config(text="", foreground="gray")
            return
        p = compute_preset(win, self.agents_list,
                           self.source_lang_combo.get(), self.target_lang_combo.get())
        if not p:
            return
        for widget, val in ((self.chunk_chars_entry, p["chunk_chars"]),
                            (self.chunk_ctx_entry, p["context_paragraphs"])):
            widget.delete(0, tk.END)
            widget.insert(0, str(val))
        if p["send_original"] is False:
            apply_to_agents(self.agents_list)
        self._sw_rag_cap = int(p["rag_max_chars"])
        try:
            self.update_agents_listbox()  # também dispara o autosave
        except Exception:
            pass
        msg = t("window_applied", _L).format(chars=p["chunk_chars"], ctx=p["context_paragraphs"],
                                             rag=p["rag_max_chars"])
        if not p["fits"]:
            msg += " " + t("window_small", _L).format(win=win)
        self.window_status.config(text=msg, foreground=("green" if p["fits"] else "red"))
