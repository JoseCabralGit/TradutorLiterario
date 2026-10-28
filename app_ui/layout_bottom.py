# -*- coding: utf-8 -*-
"""Parte de baixo da janela (textos + logs)."""
import tkinter as tk
from tkinter import ttk, scrolledtext
from app_config import t


class LayoutBottomMixin:
    def build_split(self, main_frame):
        _L = self.ui_lang
        split_frame = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        split_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        left_pane = ttk.Frame(split_frame, padding=5)
        split_frame.add(left_pane, weight=1)
        ttk.Label(left_pane, text=t("input_label", _L)).pack(anchor=tk.W, padx=5)
        self.run_btn = ttk.Button(left_pane, text=t("run_btn_bottom", _L), command=self.run_pipeline)
        self.run_btn.pack(fill=tk.X, padx=5, pady=5)
        self.input_text = scrolledtext.ScrolledText(left_pane, height=14, width=45, wrap=tk.WORD)
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.input_text.insert(tk.END, "The autumn wind whispered through the desolate valley, while Reginald watched in silence.")
        right_pane = ttk.Frame(split_frame, padding=5)
        split_frame.add(right_pane, weight=1)
        notebook = ttk.Notebook(right_pane)
        notebook.pack(fill=tk.BOTH, expand=True)
        result_tab = ttk.Frame(notebook, padding=5)
        notebook.add(result_tab, text=t("result_tab", _L))
        ttk.Label(result_tab, text=t("result_label", _L)).pack(anchor=tk.W, padx=5)
        self.output_text = scrolledtext.ScrolledText(result_tab, height=12, width=45, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        log_tab = ttk.Frame(notebook, padding=5)
        notebook.add(log_tab, text=t("log_tab", _L))
        self.log_text = scrolledtext.ScrolledText(log_tab, height=12, width=45, wrap=tk.WORD, background="#1e1e1e", foreground="#00ff00")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
