# -*- coding: utf-8 -*-
"""Utilitários de normalização de texto e correspondência de termos usados pela base de conhecimento.

Modulo extraído de gui.py (arquivo original monolítico) durante a modularização.
"""
import re
import unicodedata
from typing import List, Optional

import pandas as pd

# Caracteres de idiomas sem espaço entre palavras (japonês, chinês, coreano)
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")

def _norm(value) -> str:
    """Minúsculas e sem acentos, preservando qualquer alfabeto (cirílico, japonês etc.)."""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.casefold().strip()

def _phrase_in(phrase: str, text: str) -> bool:
    """Frase inteira presente no texto (ambos já normalizados)."""
    if not phrase:
        return False
    if _CJK.search(phrase):
        return phrase in text
    suffix = r"\w{0,3}" if len(phrase) >= 4 else ""  # tolera plural/sufixo curto
    return re.search(r"(?<!\w)" + re.escape(phrase) + suffix + r"(?!\w)", text) is not None

def _cell_candidates(cell) -> List[str]:
    """Células curtas viram 'chaves de busca'; textos longos (descrições) são ignorados.
    Separadores ; , / | permitem vários apelidos/variações na mesma célula."""
    if cell is None or (not isinstance(cell, str) and pd.isna(cell)):
        return []
    raw = str(cell).strip()
    if not raw or len(raw) > 80 or len(raw.split()) > 6:
        return []
    out = []
    for part in re.split(r"[;,/|]", raw):
        n = _norm(part)
        if len(n) >= 2 and not n.replace(".", "").replace("-", "").isdigit():
            out.append(n)
    return out

def _norm_name(value) -> str:
    """Normaliza NOME para busca: _norm + tira pontuacao final e titulos.

    'Shiranami Kaoru.' -> 'shiranami kaoru'; 'senhor Kaoru' -> 'kaoru'.
    Titulos PT/EN/ES comuns (nunca fazem parte do nome da ficha).
    """
    n = _norm(value).strip().strip(".!?,;:\"'()[]")
    for title in ("senhor ", "senhora ", "senhorita ", "sr ", "sr. ", "sra ",
                  "sra. ", "srta ", "srta. ", "dona ", "dom ", "seu ",
                  "mr ", "mr. ", "mrs ", "mrs. ", "ms ", "ms. ", "miss ",
                  "sir ", "lady ", "lord ", "don ", "dona ", "senor ",
                  "senorita ", "san ", "sama ", "kun ", "chan "):
        if n.startswith(title):
            n = n[len(title):].strip()
            break
    return n


_MIN_PARTIAL_WORD = 4


def _first_col_keys(cell) -> List[str]:
    """Chaves de busca da 1a coluna (termo/nome), já normalizadas com _norm_name."""
    out = []
    for cand in _cell_candidates(cell):
        c = _norm_name(cand)
        if c:
            out.append(c)
    return out


def build_word_df(first_col_cells) -> dict:
    """Em quantos TERMOS (linhas) cada palavra aparece na 1a coluna da base.

    Estatística da PRÓPRIA base (nenhuma lista fixa, qualquer idioma): uma palavra
    que aparece em vários termos ('elfo' em 'elfo' e 'matadora de elfo';
    'selamento' em 'Grande Selamento' e 'magia de selamento') é ambígua e NÃO
    identifica um termo sozinha. Só palavra que pertence a um único termo
    ('Saionji' em 'Saionji Haruto') pode casar isolada.
    """
    df: dict = {}
    for cell in first_col_cells:
        words = set()
        for key in _first_col_keys(cell):
            if _CJK.search(key):
                continue
            words.update(w for w in re.findall(r"\w+", key) if len(w) >= _MIN_PARTIAL_WORD)
        for w in words:
            df[w] = df.get(w, 0) + 1
    return df


def _partial_word_ok(word: str, word_df) -> bool:
    """Palavra isolada de termo composto pode casar? Sem estatística (word_df=None)
    mantém o comportamento antigo (qualquer palavra >= 4 letras)."""
    if len(word) < _MIN_PARTIAL_WORD:
        return False
    if word_df is None:
        return True
    return word_df.get(word, 0) <= 1


def _row_matches(row, text_norm: str, word_df=None) -> bool:
    """Linha relevante se qualquer célula curta aparece no texto. Na primeira coluna
    (onde costuma ficar o termo/nome) também vale uma palavra isolada do termo composto,
    desde que ela seja ÚNICA daquele termo na base (ver build_word_df).
    Usa _norm_name nos candidatos (tira 'Shiranami Kaoru.' -> 'shiranami kaoru')."""
    for col_idx, cell in enumerate(row.tolist()):
        for cand in _cell_candidates(cell):
            cand = _norm_name(cand)
            if not cand:
                continue
            if _phrase_in(cand, text_norm):
                return True
            if col_idx == 0 and not _CJK.search(cand) and " " in cand:
                if any(_phrase_in(w, text_norm) for w in re.findall(r"\w+", cand) if _partial_word_ok(w, word_df)):
                    return True
    return False


def nested_name_groups(first_col_cells) -> List[tuple]:
    """Pares (forma_curta, forma_longa) em que TODAS as palavras da curta estão na longa
    ('haruto' ⊂ 'saionji haruto'): provável mesma entidade com 2 grafias na base.
    Retorna lista de (curta_original, longa_original) sem duplicar."""
    entries = []  # (original, set_de_palavras)
    seen = set()
    for cell in first_col_cells:
        if cell is None or (not isinstance(cell, str) and pd.isna(cell)):
            continue
        orig = " ".join(str(cell).split())
        # Só parece NOME PRÓPRIO se toda palavra começa com maiúscula
        # ('Saionji Haruto'); termos comuns ('matadora de elfo') ficam de fora.
        if not all(w[:1].isupper() for w in orig.split()):
            continue
        keys = _first_col_keys(cell)
        if not keys:
            continue
        key = keys[0]
        if _CJK.search(key) or key in seen:
            continue
        seen.add(key)
        words = frozenset(re.findall(r"\w+", key))
        if words:
            entries.append((orig, key, words))
    pairs = []
    for o1, k1, w1 in entries:
        for o2, k2, w2 in entries:
            if k1 != k2 and w1 < w2 and any(len(w) >= _MIN_PARTIAL_WORD for w in w1):
                pairs.append((o1, o2))
    return pairs


def detect_pronoun_columns(columns, sample_rows, max_check: int = 8) -> set:
    """Indices das colunas que parecem ser de PRONOME (qualquer lingua).

    Criterio: cabecalho suspeito (is_pronoun_header) OU maioria das celulas
    amostradas parece pronome (looks_like_pronoun_cell). Usado para EXCLUIR
    a coluna da busca por nome (evita 'ore'/'uchi' casarem com portugues).
    Import tardio de lang_profiles: evita import circular.
    """
    from lang_profiles import is_pronoun_header, looks_like_pronoun_cell
    out = set()
    cols = list(columns)
    for idx, col in enumerate(cols):
        if is_pronoun_header(col):
            out.add(idx)
            continue
        hits = total = 0
        for row in (sample_rows or [])[:max_check]:
            try:
                val = row[idx] if idx < len(row) else None
            except Exception:
                val = None
            if val is None or (not isinstance(val, str) and pd.isna(val)):
                continue
            if not str(val).strip():
                continue
            total += 1
            if looks_like_pronoun_cell(val):
                hits += 1
        if total >= 2 and hits * 2 >= total:
            out.add(idx)
    return out


def find_speakers(text: str, known_names, dicendi_verbs, narrator_norm: str = "") -> dict:
    """Atribuicao de falante SEM LLM (regex sobre o texto ORIGINAL).

    Detecta: `X:` no inicio de linha; marcadores `— "..." — VERBO X`,
    `VERBO X`, `X VERBO` (VERBO = verbo dicendi do idioma de origem);
    `eu/me/mim/meu/minha` (PT) ou `i/me/my` (EN) = narrador (1a pessoa).
    Retorna {"speakers": [nomes], "narrator_in_first": bool}.
    `known_names`: lista de nomes da ficha (1a coluna); o match usa a forma
    normalizada e tambem palavra isolada do nome composto.
    """
    speakers: List[str] = []
    seen = set()
    norm_to_name = {}
    for n in (known_names or []):
        for cand in _cell_candidates(n):
            c = _norm_name(cand)
            if c:
                norm_to_name.setdefault(c, str(n).strip())

    def _hit(norm_name: str):
        if not norm_name:
            return
        if norm_name in norm_to_name and norm_name not in seen:
            seen.add(norm_name)
            speakers.append(norm_to_name[norm_name])
            return
        # Nome parcial ("sayaka" -> "sayaka mizuno"): primeiro token ou
        # sobrenome isolado tambem identifica o falante.
        cands = []
        for nn, orig in norm_to_name.items():
            if nn in seen:
                continue
            toks = nn.split()
            if norm_name == nn or (toks and (norm_name == toks[0] or norm_name == toks[-1])):
                cands.append((nn, orig))
        # Parte do nome comum a 2+ fichas (ex. sobrenome 'Elarion') é ambígua: não atribui a ninguém.
        if len(cands) == 1:
            seen.add(cands[0][0])
            speakers.append(cands[0][1])

    text_n = _norm(text or "")
    # 1) `Nome:` no inicio de linha (formato roteiro).
    for line in (text or "").splitlines():
        m = re.match(r"\s*([A-ZÀ-Þ][\wÀ-ÿ.'-]{1,40})\s*:", line)
        if m:
            cand = _norm_name(m.group(1))
            _hit(cand)
            if cand and " " not in cand:
                for nn, orig in norm_to_name.items():
                    if nn.split() and (nn == cand or nn.startswith(cand + " ") or nn.endswith(" " + cand)):
                        _hit(nn)
    # 2) Marcadores com verbo dicendi: `VERBO Nome` e `Nome VERBO`.
    verbs = [v.casefold() for v in (dicendi_verbs or [])]
    if verbs:
        vpat = "|".join(re.escape(v) for v in sorted(set(verbs), key=len, reverse=True)[:60])
        name_pat = r"([A-ZÀ-Þa-zà-ÿ][\wÀ-ÿ.'-]*(?:\s+[A-ZÀ-Þa-zà-ÿ][\wÀ-ÿ.'-]*){0,3})"
        for m in re.finditer(r"(?<!\w)(?:" + vpat + r")\s+" + name_pat, text or "", re.IGNORECASE):
            _hit(_norm_name(m.group(1)))
        for m in re.finditer(name_pat + r"\s+(?:" + vpat + r")(?!\w)", text or "", re.IGNORECASE):
            _hit(_norm_name(m.group(1)))
    # 3) Falas entre aspas/travessao seguidas de nome solto: `— "..." — Nome`.
    for m in re.finditer(r"[\"“”«»「『—–-]\s*[^\"“”«»「『—–\n]{2,400}\s*[\"“”«»」』—–-]\s*[,.!]?\s*([A-ZÀ-Þ][\wÀ-ÿ.'-]*(?:\s+[A-ZÀ-Þ][\wÀ-ÿ.'-]*){0,2})", text or ""):
        _hit(_norm_name(m.group(1)))
    # 4) 1a pessoa no original = narrador falando.
    narrator_hit = False
    if narrator_norm:
        low = text_n
        if re.search(r"(?<!\w)(eu|me|mim|comigo|meu|minha|meus|minhas)(?!\w)", low):
            narrator_hit = True
        elif re.search(r"(?<!\w)(i|me|my|mine)(?!\w)", low):
            narrator_hit = True
    return {"speakers": speakers, "narrator_in_first": narrator_hit}

def _format_row(row) -> str:
    return " | ".join(f"{c}: {' '.join(str(v).split())}" for c, v in row.items() if pd.notna(v) and str(v).strip())


# ---------------------------------------------------------------------------
# Busca por relevância (BM25 leve, sem dependências) para o banco de apoio
# linguístico. Substitui o antigo "qualquer palavra > 3 letras dá match".
# ---------------------------------------------------------------------------
import math

_STOPWORDS = frozenset("""
that this with from have were been they them their there what when where which while would could should about into
than then also only just very more most some such over under after before because though through
para como mais mas isso isto essa esse essas esses esta este estas estes pelo pela pelos pelas
quando onde qual quais quem muito muita muitos muitas tudo todo toda todos todas ainda depois antes
sobre entre sem seu sua seus suas nosso nossa dele dela deles delas foram foi era eram tinha tinham
pero porque cuando donde como muy todo toda todos todas sobre entre sin desde hasta
""".split())

_WORD = re.compile(r"\w+", re.UNICODE)
_CJK_RUN = re.compile(r"[぀-ヿ㐀-鿿가-힯]+")
_ONLY_HIRAGANA = re.compile(r"^[ぁ-ゟ]+$")


def _stem(word: str) -> str:
    """Radical grosseiro (prefixo) para tolerar plural/conjugação: 'sussurrou' ~ 'sussurrar'."""
    return word[:6] if len(word) > 6 else word


def _tokens(text, min_len: int = 4, use_stopwords: bool = True) -> List[str]:
    """Tokens normalizados de busca. Latim/cirílico: palavras com >= `min_len` letras (sem stopwords se
    `use_stopwords`), com radical. CJK (sem espaços): bigramas de caracteres, exceto os formados só por hiragana."""
    if text is None or (not isinstance(text, str) and pd.isna(text)):
        return []
    norm = _norm(text)
    out: List[str] = []
    for run in _CJK_RUN.findall(norm):
        if len(run) >= 2:
            for i in range(len(run) - 1):
                bg = run[i:i + 2]
                # Bigrama só de hiragana (った, ない, こと, てい...) é GRAMÁTICA: aparece em quase toda
                # frase e fazia linhas sem relação "casarem". Só entram bigramas com kanji/katakana/hangul.
                if _ONLY_HIRAGANA.match(bg):
                    continue
                out.append(bg)
    non_cjk = _CJK_RUN.sub(" ", norm)
    for w in _WORD.findall(non_cjk):
        if len(w) >= min_len and not (use_stopwords and w in _STOPWORDS) and not w.isdigit():
            out.append(_stem(w))
    return out


def bm25_rank(query_text: str, docs: List[str], k1: float = 1.5, b: float = 0.75,
              min_len: int = 4, common_pct: int = 50, use_stopwords: bool = True,
              doc_tokens: Optional[List[List[str]]] = None):
    """Ranqueia `docs` pela relevância para `query_text`. Retorna lista (índice, score) com
    score > 0, do mais relevante ao menos.

    Filtros (todos configuráveis por base): `min_len` = tamanho mínimo da palavra;
    `use_stopwords` = ignora palavras muito comuns; `common_pct` = ignora termos que aparecem em
    mais de N% das linhas (só vale com >= 8 linhas; 0 = não ignora nada).

    `doc_tokens`: tokenização pré-calculada dos docs (cache por execução — evita
    retokenizar a base inteira a cada agente; importante em PC fraco). Deve ter
    sido gerada com os MESMOS min_len/use_stopwords."""
    q_tokens = set(_tokens(query_text, min_len, use_stopwords))
    if not q_tokens or not docs:
        return []
    if doc_tokens is None:
        doc_tokens = [_tokens(d, min_len, use_stopwords) for d in docs]
    n = len(docs)
    avg_len = (sum(len(t) for t in doc_tokens) / n) or 1.0
    df = {}
    for toks in doc_tokens:
        for tok in set(toks):
            df[tok] = df.get(tok, 0) + 1
    scored = []
    for idx, toks in enumerate(doc_tokens):
        if not toks:
            continue
        tf = {}
        for tok in toks:
            tf[tok] = tf.get(tok, 0) + 1
        score = 0.0
        for tok in q_tokens:
            f = tf.get(tok)
            if not f:
                continue
            d = df.get(tok, 0)
            if common_pct > 0 and n >= 8 and d / n > common_pct / 100.0:
                continue
            idf = math.log(1 + (n - d + 0.5) / (d + 0.5))
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * len(toks) / avg_len))
        if score > 0:
            scored.append((idx, score))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored
