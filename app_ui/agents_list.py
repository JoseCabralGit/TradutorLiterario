# -*- coding: utf-8 -*-
"""Gestão visual da lista de agentes (cópia fiel de gui.py)."""
import tkinter as tk


class AgentsListMixin:
    def update_agents_listbox(self):
        self.agents_listbox.delete(0, tk.END)
        for i, agent in enumerate(self.agents_list):
            tag = ""
            if getattr(agent, "budget_mode", "unlimited") == "limited":
                scope_txt = "dia" if getattr(agent, "budget_scope", "") == "per_day" else "exec"
                tag = f" | ⏱️ {getattr(agent, 'token_limit', 0)}/{scope_txt}"
            if not getattr(agent, "use_rag", True):
                tag += " | sem RAG"
            info = f"[{i+1}] {agent.name} | Provedor: {agent.provider.upper()} | Modelo: {agent.model} | Temp: {agent.temperature}{tag}"
            self.agents_listbox.insert(tk.END, info)
        # A lista mudou (add/edit/del/preset/restauração) -> salva a sessão.
        try:
            autosave = getattr(self, "_autosave_session", None)
            if callable(autosave) and getattr(self, "root", None) is not None:
                autosave()
        except Exception:
            pass
