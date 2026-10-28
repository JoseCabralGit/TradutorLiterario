# -*- coding: utf-8 -*-
"""Preset "Janela pequena" (EXTRA opcional — não muda o modo atual).

Só calcula valores para opções que JÁ existem (tamanho do trecho, parágrafos de
contexto, reenvio do original, limite do RAG). Glossário e fichas de personagens
NUNCA são cortados: o espaço deles é reservado antes e o trecho é que encolhe.
Sem rede, sem LLM, independente de idioma (usa só uma razão caracteres/token).
"""
from typing import Any, Dict, List, Optional

from token_usage import estimate_tokens

# Janelas de contexto oferecidas (em tokens). 0 = preset desligado.
WINDOW_CHOICES = (4096, 8192, 16384, 32768, 65536, 131072)

# Caracteres por token (aproximação conservadora; o menor valor vale p/ entrada e saída).
_CJK = ("japon", "chin", "corean", "japanese", "chinese", "korean", "日本", "中文", "한국")
_CYR = ("russo", "russian", "рус")
RESERVE_KB_FRACTION = 0.30   # espaço reservado p/ glossário + fichas (+ RAG), em fração da janela
SAFETY = 0.85                # margem de segurança (a estimativa de tokens é aproximada)
MIN_CHUNK_CHARS = 300
FIXED_DIRECTIVES_TOKENS = 700  # diretivas fixas do pipeline (glossário/personagens/idioma/POV)


def chars_per_token(*languages: str) -> float:
    """Menor razão caracteres/token entre os idiomas citados (pior caso)."""
    best = 3.5
    for lang in languages:
        low = (lang or "").lower()
        if any(k in low for k in _CJK):
            best = min(best, 1.2)
        elif any(k in low for k in _CYR):
            best = min(best, 2.5)
    return best


def parse_window(value) -> int:
    """'8k', '8192', '8 192' -> 8192. Inválido/0 -> 0."""
    s = str(value or "").strip().lower().replace(" ", "").replace(".", "").replace(",", "")
    if not s:
        return 0
    try:
        if s.endswith("k"):
            return max(0, int(float(s[:-1]) * 1024))
        return max(0, int(s))
    except ValueError:
        return 0


def compute_preset(window_tokens: int, agents: List[Any], source_lang: str = "",
                   target_lang: str = "") -> Optional[Dict[str, Any]]:
    """Valores sugeridos para a janela informada, ou None se window_tokens <= 0."""
    w = int(window_tokens or 0)
    if w <= 0:
        return None
    cpt = chars_per_token(source_lang, target_lang)
    longest_prompt = max((estimate_tokens(getattr(a, "system_prompt", "") or "") for a in (agents or [])), default=0)
    reserve_kb = int(w * RESERVE_KB_FRACTION)
    ctx_paragraphs = 1 if w <= 8192 else 2
    # contexto anterior (original + tradução), por parágrafo ~120 tokens cada
    ctx_tokens = ctx_paragraphs * 2 * 120
    free = w - longest_prompt - FIXED_DIRECTIVES_TOKENS - reserve_kb - ctx_tokens
    # cada chamada carrega o trecho na entrada E na saída => 2x
    chunk_tokens = int(max(0, free) / 2 * SAFETY)
    chunk_chars = max(MIN_CHUNK_CHARS, int(chunk_tokens * cpt) // 100 * 100)
    fits = free > 0 and chunk_tokens * cpt >= MIN_CHUNK_CHARS
    return {
        "window_tokens": w,
        "chunk_chars": chunk_chars,
        "context_paragraphs": ctx_paragraphs,
        "send_original": False,
        "rag_max_chars": int(w * 0.08 * cpt) // 100 * 100,
        "fits": bool(fits),
        "reserve_kb_tokens": reserve_kb,
    }


def apply_to_agents(agents: List[Any]) -> None:
    """Desliga o reenvio do original (o usuário pode religar em cada agente)."""
    for a in agents or []:
        try:
            a.send_original = False
        except Exception:
            pass
