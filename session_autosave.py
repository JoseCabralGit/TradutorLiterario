# -*- coding: utf-8 -*-
"""Salvamento automático da última sessão (agentes + ajustes da tela).

Arquivo: `session_autosave.json` ao lado do programa.
- Salva silenciosamente (sem popup) após mudanças relevantes e ao fechar.
- Restaura na abertura: agentes, idiomas, banco RAG, POV/narrador,
  caminhos D1/D2 e o último texto de entrada.
- Nunca quebra a abertura: arquivo ausente/corrompido = usa o padrão.
"""
import json
import os
from typing import Any, Dict, List

AUTOSAVE_FILE = "session_autosave.json"


def agent_to_dict(agent) -> Dict[str, Any]:
    return {
        "name": getattr(agent, "name", "Agente"),
        "system_prompt": getattr(agent, "system_prompt", ""),
        "model": getattr(agent, "model", ""),
        "temperature": getattr(agent, "temperature", 0.3),
        "max_tokens": int(getattr(agent, "max_tokens", 0) or 0),
        "timeout_s": int(getattr(agent, "timeout_s", 300) or 0),
        "reasoning_effort": getattr(agent, "reasoning_effort", "") or "",
        "truncation_retry": bool(getattr(agent, "truncation_retry", False)),
        "pause_after_s": int(getattr(agent, "pause_after_s", 0) or 0),
        "provider": getattr(agent, "provider", "openai"),
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
    }


def agent_from_dict(item: Dict[str, Any], agent_cls):
    def _keys(v):
        if isinstance(v, str):
            v = [v] if v.strip() else []
        return [k.strip() for k in (v or []) if isinstance(k, str) and k.strip()]
    strat = (item.get("fallback_strategy", "model_first") or "model_first").strip()
    if strat not in ("model_first", "key_first", "keys_only", "model_only"):
        strat = "model_first"
    return agent_cls(
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
        api_keys=_keys(item.get("api_keys", [])),
        default_key_index=int(item.get("default_key_index", 0) or 0),
        fallback_api_keys=_keys(item.get("fallback_api_keys", [])),
        fallback_default_key_index=int(item.get("fallback_default_key_index", 0) or 0),
        fallback_strategy=strat,
        use_rag=bool(item.get("use_rag", True)),
        send_original=bool(item.get("send_original", True)),
        small_window=bool(item.get("small_window", False)),
        window_tokens=int(item.get("window_tokens", 8192) or 8192),
    )


def build_snapshot(app) -> Dict[str, Any]:
    """Monta o dicionário da sessão atual a partir dos widgets."""
    import tkinter as tk

    def _get(combo, default=""):
        try:
            return combo.get().strip() or default
        except Exception:
            return default

    def _text(widget):
        try:
            txt = widget.get("1.0", tk.END)
            # Text do tkinter sempre termina com "\n"; remove só a borda.
            return txt.strip("\n")
        except Exception:
            return ""

    agents: List[Dict[str, Any]] = []
    try:
        for agent in getattr(app, "agents_list", []) or []:
            agents.append(agent_to_dict(agent))
    except Exception:
        pass

    return {
        "version": 1,
        "agents": agents,
        "source_lang": _get(getattr(app, "source_lang_combo", None), "Inglês"),
        "target_lang": _get(getattr(app, "target_lang_combo", None), "Português do Brasil"),
        "rag_base": _get(getattr(app, "rag_combo", None), ""),
        "pov": _get(getattr(app, "pov_combo", None), "Terceira Pessoa (ou Neutro)"),
        "narrator": _get(getattr(app, "narrator_combo", None), ""),
        "glossary_excel_path": getattr(app, "glossary_excel_path", None),
        "characters_excel_path": getattr(app, "characters_excel_path", None),
        "input_text": _text(getattr(app, "input_text", None)),
        "chunk_chars": _get(getattr(app, "chunk_chars_entry", None), "0"),
        "context_paragraphs": _get(getattr(app, "chunk_ctx_entry", None), "2"),
    }


def save_snapshot(snapshot: Dict[str, Any], path: str = AUTOSAVE_FILE) -> bool:
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def load_snapshot(path: str = AUTOSAVE_FILE) -> Dict[str, Any]:
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
