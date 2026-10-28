# -*- coding: utf-8 -*-
"""Divisão de textos longos em trechos (sem LLM, sem lista fixa de idioma).

Para IAs gratuitas com janela/saída pequena: o capítulo é cortado em trechos de no
máximo `max_chars` caracteres, SEMPRE entre parágrafos. Prefere cortar onde menos
atrapalha o contexto: logo após uma linha separadora de cena (`---`, `***`...) e,
na falta dela, entre parágrafos de narração (nunca no meio de uma troca de falas).
Cada trecho seguinte recebe de volta os últimos parágrafos do anterior (ver
`tail_paragraphs`) como contexto SOMENTE DE LEITURA.

max_chars = 0 (padrão) => nenhum corte: o texto inteiro é um único trecho.
"""
import re
from typing import List

_SEPARATOR = re.compile(r"^\s*[-—–_*=~#\s]{3,}\s*$")
_DIALOGUE = re.compile(r"^\s*(?:[—–]\s*\S|-\s+\S|[\"“«「『]\S)")
# fim de frase em idiomas com e sem espaço (para parágrafo gigante sem quebras)
_SENTENCE_END = re.compile(r"(?<=[.!?…。！？」』”\"])\s*")


def _blocks(text: str) -> List[str]:
    """Parágrafos (linhas não vazias). Quebras simples também separam parágrafos."""
    return [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]


def _split_giant(par: str, max_chars: int) -> List[str]:
    """Parágrafo maior que o limite: corta em frases; em último caso, por tamanho."""
    parts = [p for p in _SENTENCE_END.split(par) if p]
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) + 1 > max_chars:
            out.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip() if cur else p
    if cur:
        out.append(cur)
    final = []
    for o in out:
        while len(o) > max_chars:
            final.append(o[:max_chars])
            o = o[max_chars:]
        if o:
            final.append(o)
    return final


def split_into_chunks(text: str, max_chars: int = 0) -> List[str]:
    """Lista de trechos (cada um com parágrafos separados por linha em branco)."""
    text = (text or "").strip()
    try:
        max_chars = int(max_chars or 0)
    except Exception:
        max_chars = 0
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]

    pars: List[str] = []
    for b in _blocks(text):
        if len(b) > max_chars:
            pars.extend(_split_giant(b, max_chars))
        else:
            pars.append(b)

    def _score(prev: str, nxt: str) -> int:
        """Qualidade de um ponto de corte entre `prev` e `nxt` (maior = melhor)."""
        if _SEPARATOR.match(prev):
            return 2
        if _DIALOGUE.match(prev) and _DIALOGUE.match(nxt):
            return 0
        return 1

    chunks: List[List[str]] = []
    cur: List[str] = []
    size = 0
    for idx, p in enumerate(pars):
        add = len(p) + (2 if cur else 0)
        if cur and size + add > max_chars:
            # escolhe o melhor corte na última parte (40%) do trecho já acumulado
            best, best_score = len(cur), -1
            acc = 0
            start_window = int(size * 0.6)
            for k in range(len(cur)):
                acc += len(cur[k]) + (2 if k else 0)
                if k + 1 < len(cur) and acc >= start_window:
                    sc = _score(cur[k], cur[k + 1])
                    if sc >= best_score and sc > 0:
                        best, best_score = k + 1, sc
                elif k + 1 == len(cur) and acc >= start_window:
                    sc = _score(cur[k], p)
                    if sc >= best_score and sc > 0:
                        best, best_score = k + 1, sc
            chunks.append(cur[:best])
            cur = cur[best:]
            size = sum(len(x) for x in cur) + 2 * max(0, len(cur) - 1)
            add = len(p) + (2 if cur else 0)
        cur.append(p)
        size += add
    if cur:
        chunks.append(cur)
    # separador solto no começo de um trecho vai para o fim do anterior
    for i in range(1, len(chunks)):
        while chunks[i] and _SEPARATOR.match(chunks[i][0]) and len(chunks[i]) > 1:
            chunks[i - 1].append(chunks[i].pop(0))
    return ["\n\n".join(c) for c in chunks if c]


def tail_paragraphs(text: str, n: int) -> str:
    """Últimos `n` parágrafos de `text` (ignora separadores de cena). '' se n <= 0."""
    try:
        n = int(n or 0)
    except Exception:
        n = 0
    if n <= 0:
        return ""
    pars = [p for p in _blocks(text) if not _SEPARATOR.match(p)]
    return "\n\n".join(pars[-n:])
