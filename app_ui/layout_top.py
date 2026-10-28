# -*- coding: utf-8 -*-
"""Topo da janela principal (parte 1 do create_widgets original)."""
import tkinter as tk
from tkinter import ttk
from app_config import t


class LayoutTopMixin:
    def build_top(self, main_frame):
        top_frame = ttk.LabelFrame(main_frame, text=f" {t('settings_title', self.ui_lang)} ", padding=10)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(top_frame, text=t("lang_source", self.ui_lang)).grid(row=0, column=0, sticky=tk.W, padx=3, pady=3)
        self.source_lang_combo = ttk.Combobox(top_frame, values=["Português", "Inglês", "Espanhol", "Francês", "Alemão", "Italiano", "Russo", "Japonês", "Chinês", "Coreano", "Latim", "Outro"], width=12)
        self.source_lang_combo.set("Inglês")
        self.source_lang_combo.grid(row=0, column=1, sticky=tk.W, padx=3, pady=3)
        ttk.Label(top_frame, text=t("lang_target", self.ui_lang)).grid(row=0, column=2, sticky=tk.W, padx=3, pady=3)
        self.target_lang_combo = ttk.Combobox(top_frame, values=["Português do Brasil", "Português de Portugal", "Inglês", "Espanhol", "Francês", "Alemão", "Italiano", "Japonês", "Chinês", "Coreano", "Russo"], width=15)
        self.target_lang_combo.set("Português do Brasil")
        self.target_lang_combo.grid(row=0, column=3, sticky=tk.W, padx=3, pady=3)
        ttk.Label(top_frame, text=t("rag_base", self.ui_lang)).grid(row=0, column=4, sticky=tk.W, padx=3, pady=3)
        self.rag_combo = ttk.Combobox(top_frame, state="readonly", width=12)
        self.update_rag_bases_dropdown()
        self.rag_combo.grid(row=0, column=5, sticky=tk.W, padx=3, pady=3)
        ttk.Button(top_frame, text=t("rag_builder", self.ui_lang), command=self.open_rag_builder).grid(row=0, column=6, padx=5, pady=3)
        ttk.Button(top_frame, text=t("keys_gdrive", self.ui_lang), command=self.open_config_window).grid(row=0, column=7, padx=5, pady=3)
        self.glossary_btn = ttk.Button(top_frame, text=t("d1_glossary", self.ui_lang), command=self.select_glossary_excel)
        self.glossary_btn.grid(row=1, column=0, columnspan=2, sticky=tk.W+tk.E, padx=3, pady=4)
        ttk.Button(top_frame, text=t("d1_gdrive", self.ui_lang), command=self.sync_glossary_gdrive).grid(row=1, column=2, sticky=tk.W+tk.E, padx=3, pady=4)
        self.glossary_label = ttk.Label(top_frame, text=t("no_glossary", self.ui_lang), foreground="gray")
        self.glossary_label.grid(row=1, column=3, columnspan=2, sticky=tk.W, padx=3, pady=4)
        self.characters_btn = ttk.Button(top_frame, text=t("d2_characters", self.ui_lang), command=self.select_characters_excel)
        self.characters_btn.grid(row=1, column=5, columnspan=2, sticky=tk.W+tk.E, padx=3, pady=4)
        ttk.Button(top_frame, text=t("d2_gdrive", self.ui_lang), command=self.sync_characters_gdrive).grid(row=1, column=7, sticky=tk.W+tk.E, padx=3, pady=4)
        self.characters_label = ttk.Label(top_frame, text=t("no_characters", self.ui_lang), foreground="gray")
        self.characters_label.grid(row=1, column=8, columnspan=3, sticky=tk.W, padx=3, pady=4)
        ttk.Label(top_frame, text=t("chunk_chars_label", self.ui_lang)).grid(row=2, column=0, columnspan=3, sticky=tk.W, padx=3, pady=3)
        self.chunk_chars_entry = ttk.Entry(top_frame, width=8)
        self.chunk_chars_entry.insert(0, "0")
        self.chunk_chars_entry.grid(row=2, column=3, sticky=tk.W, padx=3, pady=3)
        ttk.Label(top_frame, text=t("chunk_ctx_label", self.ui_lang)).grid(row=2, column=4, columnspan=2, sticky=tk.W, padx=3, pady=3)
        self.chunk_ctx_entry = ttk.Entry(top_frame, width=4)
        self.chunk_ctx_entry.insert(0, "2")
        self.chunk_ctx_entry.grid(row=2, column=6, sticky=tk.W, padx=3, pady=3)
        ttk.Button(top_frame, text=t("base_desc_btn", self.ui_lang),
                   command=lambda: self.maybe_prompt_base_description("characters", self.characters_excel_path, force=True)
                   ).grid(row=1, column=11, sticky=tk.W, padx=3, pady=4)
