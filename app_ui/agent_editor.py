# -*- coding: utf-8 -*-
"""Editor de agente (cópia fiel de gui.py)."""
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Optional
from app_config import t
from models import AgentConfig


class AgentEditorMixin:
    def edit_selected_agent(self):
        selection = self.agents_listbox.curselection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecione um agente na lista para editar.")
            return
        idx = selection[0]
        self.open_agent_editor(self.agents_list[idx], index=idx)

    def add_new_agent(self):
        self.open_agent_editor(AgentConfig(name=f"Agente {len(self.agents_list)+1}: Novo Agente"), index=None)

    def delete_selected_agent(self):
        selection = self.agents_listbox.curselection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecione um agente para excluir.")
            return
        idx = selection[0]
        if len(self.agents_list) <= 1:
            messagebox.showwarning("Aviso", "O pipeline precisa ter pelo menos um agente.")
            return
        if messagebox.askyesno("Confirmar", f"Excluir agente '{self.agents_list[idx].name}'?"):
            self.agents_list.pop(idx)
            self.update_agents_listbox()

    def open_agent_editor(self, agent: AgentConfig, index: Optional[int] = None):
        editor = tk.Toplevel(self.root)
        editor.title("Configuração do Agente")
        editor.geometry("580x700")
        editor.transient(self.root)
        editor.grab_set()
        # Rolagem da página (rodinha) + botão Salvar FIXO embaixo.
        from .scroll_helper import add_text_scrollbar, make_scrollable_frame
        _outer, _canvas, _sb, body = make_scrollable_frame(editor)
        footer = ttk.Frame(editor)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=8)
        ttk.Separator(footer, orient="horizontal").pack(fill=tk.X, pady=(0, 8))
        ttk.Label(body, text="Nome do Agente:").pack(anchor=tk.W, padx=10, pady=5)
        name_entry = ttk.Entry(body, width=50)
        name_entry.insert(0, agent.name)
        name_entry.pack(padx=10, pady=5)
        ttk.Label(body, text="Provedor:").pack(anchor=tk.W, padx=10, pady=5)
        providers = list(self.persistent_config.get("custom_models", {}).keys())
        prov_combo = ttk.Combobox(body, values=providers, state="readonly", width=47)
        if agent.provider in providers:
            prov_combo.set(agent.provider)
        elif providers:
            prov_combo.current(0)
        prov_combo.pack(padx=10, pady=5)
        ttk.Label(body, text="Modelo:").pack(anchor=tk.W, padx=10, pady=5)
        model_combo = ttk.Combobox(body, width=47)
        model_combo.pack(padx=10, pady=5)

        def update_models(event=None):
            p = prov_combo.get()
            m_list = self.persistent_config.get("custom_models", {}).get(p, [])
            model_combo['values'] = m_list
            if agent.model in m_list:
                model_combo.set(agent.model)
            elif m_list:
                model_combo.current(0)

        # Bind do provedor principal feito após definir update_fb_models (ver abaixo).
        update_models()
        ttk.Label(body, text="Temperatura:").pack(anchor=tk.W, padx=10, pady=5)
        temp_entry = ttk.Entry(body, width=50)
        temp_entry.insert(0, str(agent.temperature))
        temp_entry.pack(padx=10, pady=5)
        ttk.Label(body, text="System Prompt:").pack(anchor=tk.W, padx=10, pady=5)
        prompt_text = scrolledtext.Text(body, height=8, width=55, wrap=tk.WORD)
        prompt_text.insert(tk.END, agent.system_prompt)
        prompt_text.pack(padx=10, pady=5)
        use_rag_var = tk.BooleanVar(value=bool(getattr(agent, "use_rag", True)))
        ttk.Checkbutton(
            body,
            text="Receber o banco de apoio linguístico (RAG de frases/vocabulário) neste agente",
            variable=use_rag_var,
        ).pack(anchor=tk.W, padx=10, pady=2)
        ttk.Label(body, text="(Glossário e personagens continuam indo para todos os agentes.)", foreground="gray").pack(anchor=tk.W, padx=10)
        send_orig_var = tk.BooleanVar(value=bool(getattr(agent, "send_original", True)))
        ttk.Checkbutton(
            body,
            text=t("agent_send_original", getattr(self, "ui_lang", "Português")),
            variable=send_orig_var,
        ).pack(anchor=tk.W, padx=10, pady=2)
        # EXTRA opcional: modo janela pequena (desmarcado = tudo como sempre foi).
        _L = getattr(self, "ui_lang", "Português")
        small_var = tk.BooleanVar(value=bool(getattr(agent, "small_window", False)))
        sw_frame = ttk.Frame(body)
        sw_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Checkbutton(sw_frame, text=t("agent_small_window", _L), variable=small_var).pack(side=tk.LEFT)
        ttk.Label(sw_frame, text=t("agent_window_label", _L)).pack(side=tk.LEFT, padx=(8, 2))
        window_combo = ttk.Combobox(sw_frame, values=["4k", "8k", "16k", "32k", "64k", "128k"], width=7)
        window_combo.set(str(int(getattr(agent, "window_tokens", 8192) or 8192)))
        window_combo.pack(side=tk.LEFT)
        ttk.Label(body, text=t("agent_small_window_hint", _L), foreground="gray", wraplength=480,
                  justify=tk.LEFT).pack(anchor=tk.W, padx=10)

        # --- Limites da chamada (todos opcionais; 0 = sem limite) ---
        ttk.Separator(body, orient="horizontal").pack(fill=tk.X, padx=10, pady=8)
        ttk.Label(body, text="Resposta e desempenho (nada é limitado se você não definir):").pack(anchor=tk.W, padx=10, pady=2)
        lim_frame = ttk.Frame(body)
        lim_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(lim_frame, text="Máx. tokens da resposta:").pack(side=tk.LEFT)
        maxtok_entry = ttk.Entry(lim_frame, width=8)
        maxtok_entry.insert(0, str(int(getattr(agent, "max_tokens", 0) or 0)))
        maxtok_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(lim_frame, text="(0 = sem limite)", foreground="gray").pack(side=tk.LEFT)
        to_frame = ttk.Frame(body)
        to_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(to_frame, text="Tempo máx. de espera (s):").pack(side=tk.LEFT)
        timeout_entry = ttk.Entry(to_frame, width=8)
        _to = getattr(agent, "timeout_s", 300)
        timeout_entry.insert(0, str(300 if _to is None else int(_to)))
        timeout_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(to_frame, text="(0 = sem limite)", foreground="gray").pack(side=tk.LEFT)
        rs_frame = ttk.Frame(body)
        rs_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(rs_frame, text="Raciocínio do modelo:").pack(side=tk.LEFT)
        reasoning_combo = ttk.Combobox(rs_frame, values=["Padrão do modelo", "Baixo", "Médio", "Alto"], state="readonly", width=16)
        _re = getattr(agent, "reasoning_effort", "") or ""
        reasoning_combo.set({"low": "Baixo", "medium": "Médio", "high": "Alto"}.get(_re, "Padrão do modelo"))
        reasoning_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(rs_frame, text="(Groq / OpenAI / OpenRouter)", foreground="gray").pack(side=tk.LEFT)
        trunc_var = tk.BooleanVar(value=bool(getattr(agent, "truncation_retry", False)))
        ttk.Checkbutton(
            body,
            text="Se a resposta for cortada pelo limite acima, tentar de novo com o dobro",
            variable=trunc_var,
        ).pack(anchor=tk.W, padx=10, pady=2)
        pause_frame = ttk.Frame(body)
        pause_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(pause_frame, text="Pausa após este agente (s):").pack(side=tk.LEFT)
        pause_entry = ttk.Entry(pause_frame, width=8)
        pause_entry.insert(0, str(int(getattr(agent, "pause_after_s", 0) or 0)))
        pause_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(pause_frame, text="(0 = sem pausa)", foreground="gray").pack(side=tk.LEFT)

        ttk.Separator(body, orient="horizontal").pack(fill=tk.X, padx=10, pady=8)
        ttk.Label(body, text="Limite de tokens deste agente:").pack(anchor=tk.W, padx=10, pady=2)
        budget_frame = ttk.Frame(body)
        budget_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(budget_frame, text="Modo:").pack(side=tk.LEFT)
        mode_combo = ttk.Combobox(
            budget_frame,
            values=["Ilimitado", "Limitado"],
            state="readonly",
            width=12,
        )
        cur_mode = getattr(agent, "budget_mode", "unlimited") or "unlimited"
        mode_combo.set("Limitado" if cur_mode == "limited" else "Ilimitado")
        mode_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(budget_frame, text="Limite:").pack(side=tk.LEFT)
        limit_entry = ttk.Entry(budget_frame, width=10)
        limit_entry.insert(0, str(getattr(agent, "token_limit", 0) or 0))
        limit_entry.pack(side=tk.LEFT, padx=5)

        scope_frame = ttk.Frame(body)
        scope_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(scope_frame, text="Contagem:").pack(side=tk.LEFT)
        scope_combo = ttk.Combobox(
            scope_frame,
            values=["Por execução", "Por dia"],
            state="readonly",
            width=14,
        )
        cur_scope = getattr(agent, "budget_scope", "per_execution") or "per_execution"
        scope_combo.set("Por dia" if cur_scope == "per_day" else "Por execução")
        scope_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(scope_frame, text="Se estourar:").pack(side=tk.LEFT)
        action_combo = ttk.Combobox(
            scope_frame,
            values=["Parar programa", "Pular agente", "Usar modelo reserva"],
            state="readonly",
            width=18,
        )
        cur_action = getattr(agent, "budget_action", "stop") or "stop"
        action_combo.set(
            "Pular agente" if cur_action == "skip"
            else "Usar modelo reserva" if cur_action == "fallback"
            else "Parar programa"
        )
        action_combo.pack(side=tk.LEFT, padx=5)

        fb_frame = ttk.Frame(body)
        fb_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(fb_frame, text="Reserva (modelo):").pack(side=tk.LEFT)
        fb_model_combo = ttk.Combobox(fb_frame, width=22)
        fb_model_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(fb_frame, text="Provedor:").pack(side=tk.LEFT)
        fb_prov_combo = ttk.Combobox(fb_frame, values=["(mesmo do principal)"] + providers,
                                     state="readonly", width=20)
        _fbp0 = getattr(agent, "fallback_provider", "") or ""
        fb_prov_combo.set(_fbp0 if _fbp0 in providers else "(mesmo do principal)")
        fb_prov_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(body, text="(Reserva vazia = sem reserva. Lista vem de Config > Modelos.)",
                  foreground="gray").pack(anchor=tk.W, padx=10)

        def update_fb_models(event=None):
            fp = fb_prov_combo.get().strip()
            if fp in ("", "(mesmo do principal)"):
                fp_eff = prov_combo.get().strip()
            else:
                fp_eff = fp
            m_list = self.persistent_config.get("custom_models", {}).get(fp_eff, [])
            cur = fb_model_combo.get().strip()
            saved = getattr(agent, "fallback_model", "") or ""
            fb_model_combo['values'] = ["(sem reserva)"] + list(m_list)
            if saved in m_list:
                fb_model_combo.set(saved)
            elif cur in m_list or cur in ("", "(sem reserva)"):
                fb_model_combo.set(cur if cur else "(sem reserva)")
            elif saved and saved not in m_list:
                # Reserva digitada fora da lista: preserva o texto.
                fb_model_combo.set(saved)

        def _refresh_all_models(event=None):
            update_models(event)
            update_fb_models(event)

        prov_combo.bind("<<ComboboxSelected>>", _refresh_all_models)
        fb_prov_combo.bind("<<ComboboxSelected>>", update_fb_models)
        update_fb_models()

        ttk.Separator(body, orient="horizontal").pack(fill=tk.X, padx=10, pady=8)
        ttk.Label(body, text="Chaves deste agente (vazio = usa as globais):").pack(anchor=tk.W, padx=10, pady=2)
        ttk.Label(body, text="Principal (1 por linha):", foreground="gray").pack(anchor=tk.W, padx=10)
        keys_text = scrolledtext.Text(body, height=3, width=60, wrap=tk.NONE)
        keys_text.insert(tk.END, "\n".join(getattr(agent, "api_keys", []) or []))
        keys_text.pack(padx=10, pady=2)
        add_text_scrollbar(keys_text)
        keys_def_frame = ttk.Frame(body)
        keys_def_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(keys_def_frame, text="Padrão nº:").pack(side=tk.LEFT)
        keys_def_entry = ttk.Entry(keys_def_frame, width=6)
        keys_def_entry.insert(0, str(int(getattr(agent, "default_key_index", 0) or 0) + 1))
        keys_def_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(keys_def_frame, text="(1 = 1ª da lista)", foreground="gray").pack(side=tk.LEFT)
        ttk.Label(body, text="Reserva (1 por linha, p/ modelo reserva de outro provedor):", foreground="gray").pack(anchor=tk.W, padx=10)
        fb_keys_text = scrolledtext.Text(body, height=2, width=60, wrap=tk.NONE)
        fb_keys_text.insert(tk.END, "\n".join(getattr(agent, "fallback_api_keys", []) or []))
        fb_keys_text.pack(padx=10, pady=2)
        add_text_scrollbar(fb_keys_text)
        strat_frame = ttk.Frame(body)
        strat_frame.pack(fill=tk.X, padx=10, pady=4)
        ttk.Label(strat_frame, text="Se der 429/cota:").pack(side=tk.LEFT)
        strat_combo = ttk.Combobox(
            strat_frame,
            values=["Modelo reserva primeiro", "Outra chave primeiro", "Só outras chaves", "Só modelo reserva"],
            state="readonly",
            width=24,
        )
        _strat = getattr(agent, "fallback_strategy", "model_first") or "model_first"
        strat_combo.set(
            "Outra chave primeiro" if _strat == "key_first"
            else "Só outras chaves" if _strat == "keys_only"
            else "Só modelo reserva" if _strat == "model_only"
            else "Modelo reserva primeiro")
        strat_combo.pack(side=tk.LEFT, padx=5)

        def save():
            try:
                agent.name = name_entry.get().strip()
                agent.provider = prov_combo.get().strip()
                agent.model = model_combo.get().strip()
                agent.temperature = float(temp_entry.get().strip())
                agent.system_prompt = prompt_text.get("1.0", tk.END).strip()
                agent.use_rag = bool(use_rag_var.get())
                agent.send_original = bool(send_orig_var.get())
                from small_window import parse_window
                _win = parse_window(window_combo.get())
                if small_var.get() and _win <= 0:
                    raise ValueError(t("agent_window_invalid", getattr(self, "ui_lang", "Português")))
                agent.small_window = bool(small_var.get())
                agent.window_tokens = _win if _win > 0 else int(getattr(agent, "window_tokens", 8192) or 8192)
                try:
                    agent.max_tokens = int((maxtok_entry.get() or "0").strip())
                    agent.timeout_s = int((timeout_entry.get() or "0").strip())
                except ValueError:
                    raise ValueError("Limite de resposta/tempo inválido: use números inteiros (0 = sem limite).")
                if agent.max_tokens < 0 or agent.timeout_s < 0:
                    raise ValueError("Limite de resposta/tempo inválido: não pode ser negativo.")
                agent.reasoning_effort = {"Baixo": "low", "Médio": "medium", "Alto": "high"}.get(reasoning_combo.get(), "")
                agent.truncation_retry = bool(trunc_var.get())
                try:
                    agent.pause_after_s = int((pause_entry.get() or "0").strip())
                except ValueError:
                    raise ValueError("Pausa após o agente inválida: use segundos inteiros (0 = sem pausa).")
                if agent.pause_after_s < 0:
                    raise ValueError("Pausa após o agente inválida: não pode ser negativa.")
                agent.budget_mode = "limited" if mode_combo.get() == "Limitado" else "unlimited"
                try:
                    agent.token_limit = int(limit_entry.get().strip() or 0)
                except ValueError:
                    raise ValueError("Limite de tokens inválido.")
                if agent.token_limit < 0:
                    raise ValueError("Limite de tokens inválido.")
                agent.budget_scope = "per_day" if scope_combo.get() == "Por dia" else "per_execution"
                act_txt = action_combo.get()
                agent.budget_action = (
                    "skip" if act_txt == "Pular agente"
                    else "fallback" if act_txt == "Usar modelo reserva"
                    else "stop"
                )
                _fb_m = fb_model_combo.get().strip()
                agent.fallback_model = "" if _fb_m in ("", "(sem reserva)") else _fb_m
                _fp = fb_prov_combo.get().strip()
                agent.fallback_provider = "" if _fp in ("", "(mesmo do principal)") else _fp
                # Multi-chaves do agente (1 por linha). Vazio = usa globais.
                _k = [l.strip() for l in keys_text.get("1.0", tk.END).splitlines() if l.strip()]
                agent.api_keys = _k
                try:
                    _di = int((keys_def_entry.get() or "1").strip()) - 1
                except ValueError:
                    _di = 0
                agent.default_key_index = max(0, min(_di, max(0, len(_k) - 1)))
                agent.fallback_api_keys = [l.strip() for l in fb_keys_text.get("1.0", tk.END).splitlines() if l.strip()]
                agent.fallback_default_key_index = 0
                _st = strat_combo.get()
                agent.fallback_strategy = (
                    "key_first" if _st == "Outra chave primeiro"
                    else "keys_only" if _st == "Só outras chaves"
                    else "model_only" if _st == "Só modelo reserva"
                    else "model_first")
                if agent.budget_mode == "limited":
                    if agent.token_limit <= 0:
                        raise ValueError("Defina um limite maior que zero ou use Ilimitado.")
                    if agent.budget_action == "fallback" and not agent.fallback_model:
                        raise ValueError("Informe o modelo reserva.")
                # Valida estrategia: se escolheu usar modelo reserva, precisa ter um.
                if agent.fallback_strategy in ("model_first", "model_only") and agent.fallback_model == "" and len(agent.api_keys) <= 1:
                    pass  # 1 chave so: sem reserva e sem extra = 1 tentativa (vale).
                if agent.fallback_strategy in ("model_first", "model_only") and agent.fallback_model == "" and len(agent.api_keys) > 1:
                    pass  # so chaves extras, ok mesmo com label "modelo primeiro".
                if agent.fallback_strategy in ("model_first", "model_only") and agent.fallback_model:
                    pass
                if agent.fallback_strategy in ("model_first", "model_only") and not agent.fallback_model:
                    # Sem modelo reserva: forca modo so-chaves p/ nao prometer o que nao ha.
                    agent.fallback_strategy = "keys_only"
                if index is not None:
                    self.agents_list[index] = agent
                else:
                    self.agents_list.append(agent)
                self.update_agents_listbox()
                editor.destroy()
            except ValueError as ve:
                msg = str(ve)
                if "invalid literal" in msg or "Limite" in msg or "reserva" in msg or "zero" in msg or "Pausa" in msg or "pausa" in msg:
                    messagebox.showerror("Erro", msg, parent=editor)
                else:
                    messagebox.showerror("Erro", "Temperatura inválida.", parent=editor)

        ttk.Button(footer, text="💾 Salvar Agente", command=save).pack()
