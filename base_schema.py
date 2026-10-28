# -*- coding: utf-8 -*-
"""Descrição de como uma base (planilha) está organizada — "schema" da base.

O usuário (ou uma IA, só como RASCUNHO na primeira carga) descreve o que cada
coluna significa na planilha do Glossário (D1) ou de Personagens (D2). O texto
é persistido em config_models_keys.json (`base_descriptions`), POR BASE e POR
HASH DOS CABEÇALHOS: editar células não invalida a descrição; renomear/mudar
colunas invalida (status "stale") e reabre o popup de revisão.

O texto é injetado no prompt pelo knowledge_base como um bloco de DADO,
SEMPRE ANTES das diretivas fixas do programa (GLOSSARY_DIRECTIVE /
CHARACTERS_DIRECTIVE), que continuam invioláveis — descrever a planilha não
apaga a regra de "pronome só dentro de 「」".

A IA (build_draft) gera apenas um rascunho: ele só é persistido quando o
usuário clicar em Salvar no popup. Falha de IA nunca bloqueia nada.
"""
import hashlib
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from app_config import load_persistent_config, save_persistent_config

# Limite duro do texto (custa tokens no system prompt de TODOS os agentes).
DESC_MAX_CHARS = 600
KINDS = ("glossary", "characters")
KIND_LABELS = {"glossary": "Glossário (D1)", "characters": "Personagens (D2)"}
# Mesma preferência de aba usada pelos managers (knowledge_base).
_SHEET_PREFERENCE = {"glossary": "Glossario", "characters": "Personagens"}


def _sheet_for(kind: str, excel_path: str):
    """Aba escolhida exatamente como GlossaryManager/CharactersManager fazem."""
    xls = pd.ExcelFile(excel_path)
    names = list(xls.sheet_names or [])
    sheet = names[0] if names else None
    pref = _SHEET_PREFERENCE.get(kind)
    if pref and pref in names:
        sheet = pref
    df = pd.read_excel(xls, sheet_name=sheet) if sheet is not None else pd.DataFrame()
    return sheet, df


def source_hash(kind: str, excel_path: str) -> str:
    """Hash da ESTRUTURA (aba + cabeçalhos), não do conteúdo: a descrição
    fala de colunas, então editar valores de células não a invalida."""
    sheet, df = _sheet_for(kind, excel_path)
    payload = f"{sheet}|" + "|".join(str(c) for c in df.columns)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _entries(kind: str) -> Dict[str, Any]:
    try:
        cfg = load_persistent_config()
        bd = cfg.get("base_descriptions") or {}
        entries = bd.get(kind)
        return dict(entries) if isinstance(entries, dict) else {}
    except Exception:
        return {}


def get_description(kind: str, excel_path: Optional[str]) -> Optional[Dict[str, Any]]:
    """Entrada salva para a ATUAL estrutura da planilha, ou None."""
    if not kind or not excel_path or not os.path.exists(excel_path):
        return None
    try:
        h = source_hash(kind, excel_path)
    except Exception:
        return None
    entry = _entries(kind).get(h)
    if isinstance(entry, dict) and str(entry.get("text") or "").strip():
        return entry
    return None


def get_description_text(kind: str, excel_path: Optional[str]) -> str:
    entry = get_description(kind, excel_path)
    return str(entry.get("text") or "").strip() if entry else ""


def save_description(kind: str, excel_path: str, text: str, origin: str = "manual") -> str:
    """Persiste a descrição da estrutura ATUAL da planilha. Devolve log (PT)."""
    text = (text or "").strip()[:DESC_MAX_CHARS]
    h = source_hash(kind, excel_path)
    cfg = load_persistent_config()
    bd = cfg.setdefault("base_descriptions", {})
    if not isinstance(bd.get(kind), dict):
        bd[kind] = {}
    bd[kind][h] = {
        "text": text,
        "origin": origin if origin in ("manual", "ai") else "manual",
        "updated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "label": os.path.basename(excel_path),
    }
    save_persistent_config(cfg)
    origem = "escrita por você" if origin != "ai" else "gerada por IA e confirmada por você"
    return (f"[📝] Descrição {KIND_LABELS.get(kind, kind)} salva ({len(text)}/{DESC_MAX_CHARS} "
            f"chars, {origem}; planilha '{os.path.basename(excel_path)}').\n")


def clear_description(kind: str, excel_path: Optional[str]) -> str:
    """Remove a entrada da estrutura ATUAL (se houver). Devolve log (PT)."""
    if not excel_path or not os.path.exists(excel_path):
        return "[📝] Nenhuma planilha carregada; nada a limpar.\n"
    try:
        h = source_hash(kind, excel_path)
    except Exception as e:
        return f"[📝] Falha ao ler a planilha para limpar: {e}\n"
    cfg = load_persistent_config()
    bd = cfg.setdefault("base_descriptions", {})
    removed = False
    if isinstance(bd.get(kind), dict) and h in bd[kind]:
        bd[kind].pop(h, None)
        removed = True
        save_persistent_config(cfg)
    if removed:
        return f"[📝] Descrição {KIND_LABELS.get(kind, kind)} removida.\n"
    return f"[📝] Não havia descrição salva para a estrutura atual de {KIND_LABELS.get(kind, kind)}.\n"


def status(kind: str, excel_path: Optional[str]) -> str:
    """'ok' | 'missing' | 'stale' | 'no_sheet' — para o popup/avisos."""
    if not excel_path or not os.path.exists(excel_path):
        return "no_sheet"
    try:
        h = source_hash(kind, excel_path)
    except Exception:
        return "missing"
    if h in _entries(kind):
        return "ok"
    return "stale" if _entries(kind) else "missing"


def other_labels(kind: str, excel_path: Optional[str]) -> List[str]:
    """Rótulos (arquivos) das descrições salvas de OUTRAS estruturas.
    Compara por hash-chave (o config é reparseado a cada leitura, então
    identidade de objeto não serve)."""
    try:
        h = source_hash(kind, excel_path) if excel_path and os.path.exists(excel_path) else None
    except Exception:
        h = None
    out: List[str] = []
    for key, entry in _entries(kind).items():
        if not isinstance(entry, dict) or (h is not None and key == h):
            continue
        label = str(entry.get("label") or "")
        if label and label not in out:
            out.append(label)
    return out


def _sample_text(kind: str, excel_path: str) -> str:
    """Amostra para a IA: cabeçalhos + linhas espalhadas (não só as3 primeiras,
    senão colunas esparsas como 'pronome' passam despercebidas)."""
    sheet, df = _sheet_for(kind, excel_path)
    n = len(df)
    idx = [0, 1, 2]
    if n > 6:
        idx += [n // 2, n - 1]
    else:
        idx += list(range(3, n))
    idx = sorted({i for i in idx if 0 <= i < n})

    def cell(v) -> str:
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return ""
        return " ".join(str(v).split())[:120]

    lines = [
        f"Base: {KIND_LABELS.get(kind, kind)} | arquivo: {os.path.basename(excel_path)} | "
        f"aba: {sheet} | linhas: {n}",
        "Colunas: " + " | ".join(str(c) for c in df.columns),
    ]
    for i in idx:
        row = df.iloc[i]
        vals = [f"{c} = {cell(row[c])}" for c in df.columns]
        lines.append(f"Linha {i + 1}: " + " | ".join(vals))
    return "\n".join(lines)


def build_draft(kind: str, excel_path: str, provider: str, model: str,
                timeout: int = 180) -> str:
    """UMA chamada de LLM para rascunho da descrição. NÃO persiste nada:
    o texto só grava quando o usuário confirmar com Salvar no popup."""
    from llm_client import LLMProviderFactory  # import local (evita peso no boot)

    system = (
        "Você recebe cabeçalhos e amostras de uma planilha usada como base de conhecimento "
        f"de um tradutor literário (base: {KIND_LABELS.get(kind, kind)}).\n"
        "Escreva em PORTUGUÊS DO BRASIL uma descrição curta de como a planilha está organizada "
        "e o que cada coluna significa.\n"
        f"REGRAS: no máximo 4 frases e no máximo {DESC_MAX_CHARS} caracteres; sem Markdown; "
        "sem título; sem opiniões sobre a história; NÃO invente colunas que não existam; "
        "se uma coluna parecer de pronome/primeira pessoa, diga que ela indica como o personagem "
        "fala de SI MESMO e que só vale dentro das falas.\n"
        "Responda somente com o texto da descrição."
    )
    user = _sample_text(kind, excel_path)
    text, _log, _report = LLMProviderFactory.call_llm(
        provider=(provider or "").strip(),
        model=(model or "").strip(),
        system_prompt=system,
        user_prompt=user,
        temperature=0.2,
        max_tokens=400,
        api_key="",
        timeout=timeout,
    )
    return " ".join((text or "").split())[:DESC_MAX_CHARS]


def has_api_key(provider: str) -> bool:
    """True se o provedor tem chave global configurada (ollama não precisa)."""
    prov = (provider or "").strip().lower()
    if prov == "ollama":
        return True
    try:
        val = (load_persistent_config().get("api_keys") or {}).get(prov, "")
    except Exception:
        return False
    if isinstance(val, list):
        return any(str(k).strip() for k in val)
    return bool(str(val).strip())
