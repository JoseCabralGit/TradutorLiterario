# -*- coding: utf-8 -*-
"""Seleção de Excels locais + presets de agentes (cópia fiel de gui.py)."""
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from knowledge_base import GlossaryManager, CharactersManager
from models import AgentConfig


class DrivesMixin:
    def select_glossary_excel(self):
        file_path = filedialog.askopenfilename(
            title="Selecionar Planilha Excel de Glossário (Drive 1)",
            filetypes=[("Arquivos Excel", "*.xlsx *.xls")]
        )
        if file_path:
            self.glossary_excel_path = file_path
            self.glossary_label.config(text=os.path.basename(file_path), foreground="green")
            gm = GlossaryManager()
            log_result = gm.reset_and_sync_from_excel(file_path)
            self.log_text.insert(tk.END, log_result + "\n")
            messagebox.showinfo("Sucesso", "Drive 1 (Glossário) sincronizado e banco local resetado!")
            self.maybe_prompt_base_description("glossary", file_path)
        try:
            self._autosave_session()
        except Exception:
            pass

    def select_characters_excel(self):
        file_path = filedialog.askopenfilename(
            title="Selecionar Planilha Excel de Personagens (Drive 2)",
            filetypes=[("Arquivos Excel", "*.xlsx *.xls")]
        )
        if file_path:
            self.characters_excel_path = file_path
            self.characters_label.config(text=os.path.basename(file_path), foreground="green")
            cm = CharactersManager()
            log_result = cm.reset_and_sync_from_excel(file_path)
            self.log_text.insert(tk.END, log_result + "\n")
            self.update_narrator_dropdown()
            messagebox.showinfo("Sucesso", "Drive 2 (Personagens) sincronizado e banco local resetado!")
            self.maybe_prompt_base_description("characters", file_path)
        try:
            self._autosave_session()
        except Exception:
            pass


class PresetsMixin:
    def save_agents_preset(self):
        file_path = filedialog.asksaveasfilename(
            title="Salvar Pipeline de Agentes",
            defaultextension=".json",
            filetypes=[("Arquivos JSON", "*.json")]
        )
        if not file_path:
            return
        data = []
        for agent in self.agents_list:
            data.append({
                "name": agent.name,
                "system_prompt": agent.system_prompt,
                "model": agent.model,
                "temperature": agent.temperature,
                "max_tokens": int(getattr(agent, "max_tokens", 0) or 0),
                "timeout_s": int(getattr(agent, "timeout_s", 300) or 0),
                "reasoning_effort": getattr(agent, "reasoning_effort", "") or "",
                "truncation_retry": bool(getattr(agent, "truncation_retry", False)),
                "pause_after_s": int(getattr(agent, "pause_after_s", 0) or 0),
                "provider": agent.provider,
                "budget_mode": getattr(agent, "budget_mode", "unlimited"),
                "token_limit": getattr(agent, "token_limit", 0),
                "budget_scope": getattr(agent, "budget_scope", "per_execution"),
                "budget_action": getattr(agent, "budget_action", "stop"),
                "fallback_model": getattr(agent, "fallback_model", ""),
                "fallback_provider": getattr(agent, "fallback_provider", ""),
                "api_keys": list(getattr(agent, "api_keys", []) or []),
                "default_key_index": int(getattr(agent, "default_key_index", 0) or 0),
                "fallback_api_keys": list(getattr(agent, "fallback_api_keys", []) or []),
                "fallback_default_key_index": int(getattr(agent, "fallback_default_key_index", 0) or 0),
                "fallback_strategy": getattr(agent, "fallback_strategy", "model_first") or "model_first",
                "use_rag": bool(getattr(agent, "use_rag", True)),
                "send_original": bool(getattr(agent, "send_original", True)),
                "small_window": bool(getattr(agent, "small_window", False)),
                "window_tokens": int(getattr(agent, "window_tokens", 8192) or 8192),
            })
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Sucesso", "Pipeline de agentes salvo com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar arquivo:\n{e}")

    def load_agents_preset(self):
        file_path = filedialog.askopenfilename(
            title="Carregar Pipeline de Agentes",
            filetypes=[("Arquivos JSON", "*.json")]
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("O formato do arquivo JSON de agentes é inválido.")
            loaded_agents = []
            for item in data:
                loaded_agents.append(AgentConfig(
                    name=item.get("name", "Agente"),
                    system_prompt=item.get("system_prompt", "Você é um tradutor literário especialista."),
                    model=item.get("model", "gpt-4o"),
                    temperature=float(item.get("temperature", 0.3)),
                    max_tokens=int(item.get("max_tokens", 0) or 0),
                    timeout_s=int(item.get("timeout_s", 300) if item.get("timeout_s", 300) is not None else 300),
                    reasoning_effort=(item.get("reasoning_effort", "") or "") if (item.get("reasoning_effort", "") or "") in ("low", "medium", "high") else "",
                    truncation_retry=bool(item.get("truncation_retry", False)),
                    pause_after_s=int(item.get("pause_after_s", 0) or 0),
                    provider=item.get("provider", "openai"),
                    budget_mode=item.get("budget_mode", "unlimited"),
                    token_limit=int(item.get("token_limit", 0) or 0),
                    budget_scope=item.get("budget_scope", "per_execution"),
                    budget_action=item.get("budget_action", "stop"),
                    fallback_model=item.get("fallback_model", "") or "",
                    fallback_provider=item.get("fallback_provider", "") or "",
                    api_keys=[k for k in (item.get("api_keys", []) or []) if isinstance(k, str) and k.strip()],
                    default_key_index=int(item.get("default_key_index", 0) or 0),
                    fallback_api_keys=[k for k in (item.get("fallback_api_keys", []) or []) if isinstance(k, str) and k.strip()],
                    fallback_default_key_index=int(item.get("fallback_default_key_index", 0) or 0),
                    fallback_strategy=(item.get("fallback_strategy", "model_first") or "model_first"),
                    use_rag=bool(item.get("use_rag", True)),
                    send_original=bool(item.get("send_original", True)),
                    small_window=bool(item.get("small_window", False)),
                    window_tokens=int(item.get("window_tokens", 8192) or 8192),
                ))
            if loaded_agents:
                self.agents_list = loaded_agents
                self.update_agents_listbox()
                messagebox.showinfo("Sucesso", f"Pipeline carregado com {len(loaded_agents)} agentes!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao carregar arquivo:\n{e}")
