# -*- coding: utf-8 -*-
"""Orquestra o layout chamando as partes."""
import tkinter as tk
from tkinter import ttk
from .layout_top import LayoutTopMixin
from .layout_mid import LayoutMidMixin
from .layout_bottom import LayoutBottomMixin
from gui_windows import RAGBuilderWindow, BaseDescriptionWindow
from base_schema import status as base_desc_status


class LayoutMixin(LayoutTopMixin, LayoutMidMixin, LayoutBottomMixin):
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        self.build_top(main_frame)
        self.build_pov(main_frame)
        self.build_agents(main_frame)
        self.build_split(main_frame)

    def update_rag_bases_dropdown(self):
        bases = self.rag_mgr.get_all_bases()
        self.rag_combo['values'] = bases
        if bases:
            self.rag_combo.set(bases[0])

    def open_rag_builder(self):
        RAGBuilderWindow(self.root, on_update_callback=self.update_rag_bases_dropdown)

    def open_base_description(self, initial_kind="characters", reason=""):
        """Popup de descrição da base (D1/D2). O texto vira bloco de DADO no
        prompt; as diretivas fixas do programa continuam invioláveis."""
        BaseDescriptionWindow(
            self.root,
            glossary_path=self.glossary_excel_path,
            characters_path=self.characters_excel_path,
            on_saved=self._log_base_desc_saved,
            initial_kind=initial_kind,
            reason=reason,
        )

    def _log_base_desc_saved(self, log_msg: str):
        try:
            self.log_text.insert(tk.END, log_msg)
            self.log_text.see(tk.END)
        except Exception:
            pass

    def maybe_prompt_base_description(self, kind: str, excel_path: str, force: bool = False):
        """Após carregar/sincronizar uma base: abre o popup se a descrição
        estiver ausente ou desatualizada (hash dos cabeçalhos mudou).
        `force=True` sempre abre (botão manual)."""
        if not force:
            try:
                st = base_desc_status(kind, excel_path)
            except Exception:
                return
            if st not in ("missing", "stale"):
                return
        self.open_base_description(initial_kind=kind)
