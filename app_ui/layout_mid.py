# -*- coding: utf-8 -*-
"""Meio da janela principal (POV + lista de agentes)."""
import tkinter as tk
from tkinter import ttk
from app_config import t


class LayoutMidMixin:
    def build_pov(self, main_frame):
        pov_frame = ttk.Frame(main_frame, padding=2)
        pov_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(pov_frame, text=t("pov_label", self.ui_lang)).pack(side=tk.LEFT, padx=2)
        self.pov_combo = ttk.Combobox(pov_frame, values=["Terceira Pessoa (ou Neutro)", "Primeira Pessoa (1ª Pessoa)"], width=25, state="readonly")
        self.pov_combo.set("Terceira Pessoa (ou Neutro)")
        self.pov_combo.pack(side=tk.LEFT, padx=5)
        self.pov_combo.bind("<<ComboboxSelected>>", self.toggle_narrator_field)
        ttk.Label(pov_frame, text=t("narrator_label", self.ui_lang)).pack(side=tk.LEFT, padx=5)
        self.narrator_combo = ttk.Combobox(pov_frame, values=self.get_characters_list(), width=25, state="disabled")
        self.narrator_combo.pack(side=tk.LEFT, padx=5)

    def build_agents(self, main_frame):
        agents_frame = ttk.LabelFrame(main_frame, text=t("agents_frame", self.ui_lang), padding=10)
        agents_frame.pack(fill=tk.X, padx=5, pady=5)
        self.agents_listbox = tk.Listbox(agents_frame, height=4, width=110)
        self.agents_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.update_agents_listbox()
        agents_btn_frame = ttk.Frame(agents_frame)
        agents_btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        ttk.Button(agents_btn_frame, text=t("add_agent", self.ui_lang), command=self.add_new_agent).pack(fill=tk.X, pady=2)
        ttk.Button(agents_btn_frame, text=t("edit_agent", self.ui_lang), command=self.edit_selected_agent).pack(fill=tk.X, pady=2)
        ttk.Button(agents_btn_frame, text=t("delete_agent", self.ui_lang), command=self.delete_selected_agent).pack(fill=tk.X, pady=2)
        ttk.Separator(agents_btn_frame, orient="horizontal").pack(fill=tk.X, pady=5)
        ttk.Button(agents_btn_frame, text=t("save_pipeline", self.ui_lang), command=self.save_agents_preset).pack(fill=tk.X, pady=2)
        ttk.Button(agents_btn_frame, text=t("load_pipeline", self.ui_lang), command=self.load_agents_preset).pack(fill=tk.X, pady=2)
