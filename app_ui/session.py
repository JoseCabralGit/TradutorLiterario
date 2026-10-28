# -*- coding: utf-8 -*-
"""Restauração/aplicação da sessão + salvamento automático silencioso."""
import os
import tkinter as tk

from session_autosave import build_snapshot, save_snapshot


class SessionMixin:
    # -- aplicação (chamado uma vez, após create_widgets) --
    def _apply_restored_session(self):
        snap = getattr(self, "_restored_session", None) or {}
        if not snap:
            return
        try:
            src = (snap.get("source_lang") or "").strip()
            if src and hasattr(self, "source_lang_combo"):
                try:
                    self.source_lang_combo.set(src)
                except Exception:
                    pass
            tgt = (snap.get("target_lang") or "").strip()
            if tgt and hasattr(self, "target_lang_combo"):
                try:
                    self.target_lang_combo.set(tgt)
                except Exception:
                    pass
            # Base RAG: só aplica se ainda existir no banco atual.
            rag = (snap.get("rag_base") or "").strip()
            if rag and hasattr(self, "rag_combo"):
                try:
                    vals = list(self.rag_combo["values"] or [])
                    if rag in vals:
                        self.rag_combo.set(rag)
                except Exception:
                    pass
            pov = (snap.get("pov") or "").strip()
            if pov and hasattr(self, "pov_combo"):
                try:
                    self.pov_combo.set(pov)
                except Exception:
                    pass
            # Narrador depende do POV + lista de personagens.
            try:
                if hasattr(self, "update_narrator_dropdown"):
                    # Reusa a lógica existente (habilita/desabilita o campo).
                    self.update_narrator_dropdown()
            except Exception:
                pass
            narr = (snap.get("narrator") or "").strip()
            if narr and hasattr(self, "narrator_combo"):
                try:
                    vals = list(self.narrator_combo["values"] or [])
                    if narr in vals:
                        self.narrator_combo.set(narr)
                    else:
                        # Personagem pode ter sido removido do banco; tenta mesmo assim.
                        self.narrator_combo.set(narr)
                except Exception:
                    pass
            # Caminhos D1/D2: restaura o caminho + rótulo se o arquivo ainda existir.
            gpath = snap.get("glossary_excel_path")
            if gpath and os.path.exists(gpath):
                self.glossary_excel_path = gpath
                try:
                    self.glossary_label.config(
                        text=os.path.basename(gpath), foreground="green"
                    )
                except Exception:
                    pass
            cpath = snap.get("characters_excel_path")
            if cpath and os.path.exists(cpath):
                self.characters_excel_path = cpath
                try:
                    self.characters_label.config(
                        text=os.path.basename(cpath), foreground="green"
                    )
                except Exception:
                    pass
            # Divisão em trechos (opcional): restaura os dois campos numéricos.
            for key, widget in (("chunk_chars", "chunk_chars_entry"), ("context_paragraphs", "chunk_ctx_entry")):
                val = str(snap.get(key, "")).strip()
                ent = getattr(self, widget, None)
                if val.isdigit() and ent is not None:
                    try:
                        ent.delete(0, tk.END)
                        ent.insert(0, val)
                    except Exception:
                        pass
            # Último texto de entrada (substitui o exemplo padrão).
            saved_input = snap.get("input_text")
            if isinstance(saved_input, str) and saved_input.strip():
                try:
                    self.input_text.delete("1.0", tk.END)
                    self.input_text.insert(tk.END, saved_input)
                except Exception:
                    pass
        except Exception:
            # Restauração nunca pode quebrar a abertura.
            pass

    # -- salvamento --
    def _autosave_session(self):
        # Só salva com a janela pronta (construção chama update_agents_listbox).
        if not getattr(self, "_autosave_ready", False):
            return
        try:
            save_snapshot(build_snapshot(self))
        except Exception:
            pass

    def _on_close_autosave(self):
        try:
            self._autosave_session()
        finally:
            try:
                self.root.destroy()
            except Exception:
                pass

    def _setup_autosave(self):
        # Aplica o snapshot carregado no init_state.
        try:
            self._apply_restored_session()
        except Exception:
            pass
        # Daqui em diante a janela está pronta: libera o salvamento.
        try:
            self._autosave_ready = True
        except Exception:
            pass
        # Salva sempre ao fechar a janela (X, Alt+F4, etc.).
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close_autosave)
        except Exception:
            pass
        # Salva quando trocar combos principais (idiomas, RAG, POV...).
        for combo_name in (
            "source_lang_combo",
            "target_lang_combo",
            "rag_combo",
            "pov_combo",
            "narrator_combo",
        ):
            try:
                combo = getattr(self, combo_name, None)
                if combo is not None:
                    combo.bind(
                        "<<ComboboxSelected>>",
                        lambda _e: self._autosave_session(),
                        add="+",
                    )
            except Exception:
                continue
        # Salva o rascunho do texto ao sair da caixa de entrada.
        try:
            if getattr(self, "input_text", None) is not None:
                self.input_text.bind(
                    "<FocusOut>",
                    lambda _e: self._autosave_session(),
                    add="+",
                )
        except Exception:
            pass
