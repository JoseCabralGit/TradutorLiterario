# -*- coding: utf-8 -*-
"""Narrador/POV (cópia fiel de gui.py)."""
import os
import sqlite3
from typing import List
import pandas as pd
from knowledge_base import CharactersManager


class NarratorMixin:
    def get_characters_list(self) -> List[str]:
        cm = CharactersManager()
        if not os.path.exists(cm.db_path):
            return ["(Nenhum personagem na base)"]
        try:
            conn = sqlite3.connect(cm.db_path)
            df = pd.read_sql("SELECT * FROM personagens", conn)
            conn.close()
            if df.empty or len(df.columns) == 0:
                return ["(Nenhum personagem cadastrado)"]
            name_col = df.columns[0]
            for col in df.columns:
                vals = df[col].dropna().astype(str).str.strip()
                vals = vals[vals != ""]
                if len(vals) and (~vals.str.replace(r"[.\-]", "", regex=True).str.isdigit()).mean() > 0.5:
                    name_col = col
                    break
            names = []
            for v in df[name_col].dropna().astype(str):
                v = v.strip()
                if v and v not in names:
                    names.append(v)
            return names if names else ["(Nenhum personagem cadastrado)"]
        except Exception as e:
            return [f"(Erro ao carregar personagens: {e})"]

    def update_narrator_dropdown(self):
        chars = self.get_characters_list()
        self.narrator_combo['values'] = chars
        if chars and not chars[0].startswith("("):
            self.narrator_combo.set(chars[0])
        else:
            self.narrator_combo.set("")

    def toggle_narrator_field(self, event=None):
        pov = self.pov_combo.get()
        if "Primeira" in pov:
            self.update_narrator_dropdown()
            self.narrator_combo.config(state="normal")
        else:
            self.narrator_combo.set("")
            self.narrator_combo.config(state="disabled")
