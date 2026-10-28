# -*- coding: utf-8 -*-
"""Checagem de consistência de pronome por fala (SEM LLM, só avisa — nunca altera o texto).

Ideia: a planilha de personagens diz qual pronome de 1a pessoa cada um usa. Aqui o
programa descobre QUEM fala em cada fala do ORIGINAL (regex nas marcas de fala),
pega o pronome esperado dessa pessoa e confere se a fala traduzida usa outro
pronome de 1a pessoa. Nada é fixo para uma obra: o pronome vem da coluna que o
programa já detecta (detect_pronoun_columns) e os nomes vêm da 1a coluna.

Limites (de propósito): atribuição de falante por regex é conservadora — se não
tiver certeza, a fala simplesmente não é conferida. Hoje só o japonês como idioma
de destino tem lista de pronomes de 1a pessoa (ver _FIRST_PERSON_GROUPS).
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from lang_profiles import _key_norm, target_key
from text_utils import (
    _CJK, _norm, _norm_name, _partial_word_ok, _phrase_in, build_word_df,
)

# Grupos de grafias do MESMO pronome (japonês). Um pronome é "esperado" se a fala usa
# qualquer grafia do grupo dele. Fora do grupo esperado = divergência.
_FIRST_PERSON_GROUPS = {
    "japones": [
        ("私", "わたし", "ワタシ"),
        ("俺", "おれ", "オレ"),
        ("僕", "ぼく", "ボク"),
        ("あたし", "アタシ"),
        ("わたくし", "私め"),
        ("わし", "ワシ", "儂"),
        ("あたい", "アタイ"),
        ("ウチ", "うち"),
        ("自分", "じぶん"),
    ],
}
# Pronomes ambíguos no meio de palavras comuns (うち = "dentro", 自分 = "si mesmo"):
# só contam como ACHADOS quando são o pronome esperado, nunca como divergência.
_AMBIGUOUS = {"japones": {"うち", "ウチ", "自分", "じぶん"}}

# Marca "falou a 1a pessoa" nas tags de fala do ORIGINAL (narrador em 1a pessoa).
_FIRST_PERSON_TAG_WORDS = {
    "portugues": {
        "respondo", "digo", "pergunto", "falo", "murmuro", "sussurro", "grito",
        "suspiro", "retruco", "comento", "explico", "rebato", "continuo",
        "completo", "exclamo", "sorrio", "rio", "aponto", "peço", "pedi",
        "respondi", "perguntei", "falei", "murmurei", "sussurrei", "gritei",
        "suspirei", "retruquei", "comentei", "expliquei", "rebati", "continuei",
        "concordo", "nego", "protesto", "resmungo", "rosno", "mento", "blefo",
    },
    "espanhol": {
        "respondo", "digo", "pregunto", "hablo", "murmuro", "susurro", "grito",
        "suspiro", "comento", "explico", "continuo", "exclamo", "sonrio",
    },
}
_SOURCE_KEY = {
    "portugues": "portugues", "português": "portugues", "portuguese": "portugues",
    "pt": "portugues", "pt-br": "portugues", "portugues do brasil": "portugues",
    "espanhol": "espanhol", "spanish": "espanhol", "es": "espanhol", "espanol": "espanhol",
    "ingles": "ingles", "english": "ingles", "en": "ingles",
}

_DIALOGUE_START = re.compile(r"^\s*(?:[—–]\s*\S|-\s+\S|[\"“«]\S)")
_SEPARATOR = re.compile(r"^\s*[-—–_*=#~\s]{3,}\s*$")
_TAG_SPLIT = re.compile(r"\s*[—–]\s+|\s+-\s+")


def _paragraphs_idx(text: str) -> List[Tuple[int, str]]:
    """[(índice_da_linha_no_texto, parágrafo_sem_espaços)] — o índice permite gravar correções."""
    return [(i, ln.strip()) for i, ln in enumerate((text or "").split("\n"))
            if ln.strip() and not _SEPARATOR.match(ln)]


def _paragraphs(text: str) -> List[str]:
    return [p for _, p in _paragraphs_idx(text)]


def _is_dialogue_source(par: str) -> bool:
    return bool(_DIALOGUE_START.match(par))


def _src_key(lang: str) -> str:
    return _SOURCE_KEY.get(_key_norm(lang), "")


def _tag_of(par: str) -> str:
    """Parte da fala depois do travessão de fechamento ('— fala. — diz X, rindo' -> 'diz X, rindo')."""
    parts = [x for x in _TAG_SPLIT.split(par) if x.strip()]
    if len(parts) >= 2:
        return parts[-1]
    # aspas: "fala" disse X
    m = re.search(r"[\"”»]\s*[,.]?\s*(.+)$", par)
    return m.group(1) if m else ""


def _group_of(token: str, groups) -> Optional[tuple]:
    for g in groups:
        if token in g:
            return g
    return None


def _find_first_person(text_inside: str, groups, ambiguous) -> List[str]:
    """Pronomes de 1a pessoa (nome-base de cada grupo) presentes no texto das falas."""
    found = []
    for g in groups:
        for form in g:
            if form in text_inside:
                if g[0] in ambiguous or form in ambiguous:
                    break  # ambíguo: ignorado como achado
                found.append(g[0])
                break
    return found


def _inside_quotes(par: str, open_ch: str = "「", close_ch: str = "」") -> str:
    """Só o que está dentro de 「」/『』 (a narração fora das aspas não entra)."""
    chunks = re.findall(r"[「『]([^」』]*)[」』]?", par)
    return " ".join(chunks)


class _Cast:
    """Tabela de personagens (nome, núcleo do nome, pronome) + busca de nomes numa tag."""

    def __init__(self, table: List[Dict[str, str]]):
        self.table = table
        self.df = build_word_df([r["core"] for r in table])

    def who_in(self, text: str) -> List[int]:
        tn = _norm(text)
        hits = []
        for i, r in enumerate(self.table):
            core = _norm_name(r["core"])
            if not core:
                continue
            if _phrase_in(core, tn):
                hits.append(i)
                continue
            if " " in core:
                if any(_phrase_in(w, tn) for w in re.findall(r"\w+", core) if _partial_word_ok(w, self.df)):
                    hits.append(i)
        return hits


def _attribute(src_pars: List[str], cast: _Cast, narrator_idx: Optional[int],
               first_person_tags: set, first_person_pov: bool) -> List[Tuple[Optional[int], bool]]:
    """Para cada parágrafo de DIÁLOGO do original: (índice_do_personagem|None, inferido?)."""
    # índices dos diálogos + parágrafo anterior (para 'X continua:')
    items = []  # (par_index_in_all, text)
    for k, p in enumerate(src_pars):
        if _is_dialogue_source(p):
            items.append((k, p))

    direct: List[Optional[int]] = []
    for k, p in items:
        who = None
        tag = _tag_of(p)
        if tag:
            hits = cast.who_in(tag)
            first_word = re.findall(r"\w+", _norm(tag))[:1]
            fp_first = bool(first_word and first_word[0] in {_norm(w) for w in first_person_tags})
            if fp_first and first_person_pov and narrator_idx is not None:
                # Verbo de fala em 1a pessoa logo no início ("murmuro, tirando a mão da boca de
                # Calen"): quem fala é o NARRADOR, mesmo que outro nome apareça depois como objeto.
                who = narrator_idx
            elif len(hits) == 1:
                who = hits[0]
        if who is None and k > 0 and not _is_dialogue_source(src_pars[k - 1]):
            prev = src_pars[k - 1].rstrip()
            if prev.endswith(":"):
                hits = cast.who_in(prev)
                if len(hits) == 1:
                    who = hits[0]
                elif not hits and first_person_pov and narrator_idx is not None:
                    words = set(re.findall(r"\w+", _norm(prev)))
                    if words & {_norm(w) for w in first_person_tags}:
                        who = narrator_idx  # "Fico surpresa e digo:" -> narrador
        direct.append(who)

    result: List[Tuple[Optional[int], bool]] = [(w, False) for w in direct]

    # Alternância dentro de corridas de falas consecutivas (só com 2 participantes coerentes).
    n = len(items)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][0] == items[j][0] + 1:
            j += 1
        run = list(range(i, j + 1))
        if len(run) >= 2:
            labeled = [(pos, direct[pos]) for pos in run if direct[pos] is not None]
            speakers = {w for _, w in labeled}
            if labeled and len(speakers) <= 2:
                # coerência: mesma paridade <=> mesmo falante
                par_map: Dict[int, int] = {}
                ok = True
                for pos, w in labeled:
                    par = (pos - run[0]) % 2
                    if par in par_map and par_map[par] != w:
                        ok = False
                        break
                    par_map[par] = w
                if ok and len({v for v in par_map.values()}) == len(par_map):
                    if len(par_map) == 1 and first_person_pov and narrator_idx is not None:
                        only = next(iter(par_map.values()))
                        if only != narrator_idx:
                            par_map[1 - next(iter(par_map))] = narrator_idx
                    if len(par_map) == 2:
                        for pos in run:
                            if direct[pos] is None:
                                result[pos] = (par_map[(pos - run[0]) % 2], True)
        i = j + 1
    return result


# ---------------------------------------------------------------------------
# Narração (fora de 「」/『』) e correção automática (SEM LLM)
# ---------------------------------------------------------------------------
# Trechos entre 「」/『』 (o split com 1 grupo devolve: fora, dentro, fora, dentro, ...).
_QUOTED = re.compile(r"(「[^」]*」?|『[^』]*』?)")
# Um pronome só conta se vier seguido de partícula/pontuação/fim: evita pegar o pronome
# dentro de outras palavras (オレンジ, ボクシング, 折れた="おれた", 私立, 私服...).
_AFTER = r"(?=[はがをにのもへとでやかまっださじみこしよね、。！？!?…・「」『』（）()\s]|$)"
# Na narração, estas formas são comuns como palavra comum (ワシ = águia, うち = dentro...):
# nunca contam como divergência.
_NARR_AMBIGUOUS = {"うち", "ウチ", "自分", "じぶん", "わし", "ワシ"}


def _form_re(forms) -> "re.Pattern":
    """Pronome (grupo 'f') + plural opcional たち/達 (grupo 'pl'), só se seguido de partícula/pontuação."""
    alts = "|".join(re.escape(f) for f in sorted(set(forms), key=len, reverse=True))
    return re.compile("(?P<f>%s)(?P<pl>たち|達)?%s" % (alts, _AFTER))


def _outside_quotes(par: str) -> str:
    """Só a narração do parágrafo (tudo que NÃO está entre 「」/『』)."""
    return " ".join(seg for k, seg in enumerate(_QUOTED.split(par)) if k % 2 == 0)


def _check_narration(tgt_pars: List[Tuple[int, str]], src_pars: List[str], groups,
                     table: List[Dict[str, str]], narrator_idx: Optional[int],
                     cast: "_Cast") -> Optional[Tuple[int, List[Dict[str, Any]]]]:
    """Narrador em 1a pessoa: na narração (fora das aspas) só vale o pronome DELE.

    Devolve (parágrafos_conferidos, issues) ou None se não dá para checar (sem narrador na
    planilha / sem pronome / pronome fora dos grupos conhecidos). Se um personagem que usa o
    pronome 'errado' é citado no parágrafo (fala indireta dele), esse grupo é ignorado ali."""
    if narrator_idx is None:
        return None
    expected = (table[narrator_idx].get("pronoun") or "").strip()
    exp_group = _group_of(expected, groups) if expected else None
    if not exp_group:
        return None

    def _groups_of_others(text: str) -> set:
        skip = set()
        for i in cast.who_in(text):
            if i == narrator_idx:
                continue
            g = _group_of((table[i].get("pronoun") or "").strip(), groups)
            if g:
                skip.add(g)
        return skip

    aligned = len(src_pars) == len(tgt_pars)
    whole_skip = None if aligned else _groups_of_others("\n".join(src_pars))
    checked, issues = 0, []
    for n, (li, par) in enumerate(tgt_pars, start=1):
        narr = _outside_quotes(par)
        if not narr.strip():
            continue
        checked += 1
        skip = _groups_of_others(src_pars[n - 1]) if aligned else whole_skip
        found = []
        for g in groups:
            if g is exp_group or g in skip:
                continue
            if any(f in _NARR_AMBIGUOUS for f in g):
                continue
            if _form_re(g).search(narr):
                found.append(g)
        if found:
            issues.append({
                "kind": "narration", "n": n, "line": li,
                "who": table[narrator_idx]["name"], "expected": expected,
                "found": "/".join(g[0] for g in found), "found_groups": found,
                "inferred": False, "snippet": par[:60],
            })
    return checked, issues


def apply_pronoun_fixes(translated_text: str, issues: List[Dict[str, Any]],
                        allow_dialogue: bool = True) -> Tuple[str, int, List[str]]:
    """Troca o pronome errado pelo da ficha, SEM LLM, só onde é seguro.

    - narração (kind='narration'): troca só FORA de 「」/『』;
    - fala (kind='dialogue'): troca só DENTRO de 「」/『』 e só se o falante foi identificado
      direto (não inferido por alternância);
    - só troca a forma quando vem seguida de partícula/pontuação (nunca dentro de palavra).
    Devolve (texto_novo, nº_de_trocas, descrições). Nunca levanta exceção."""
    try:
        lines = (translated_text or "").split("\n")
        total, notes = 0, []
        for it in issues or []:
            li, groups, exp = it.get("line"), it.get("found_groups"), (it.get("expected") or "").strip()
            if li is None or not groups or not exp or not (0 <= li < len(lines)):
                continue
            kind = it.get("kind", "dialogue")
            if kind == "dialogue" and (it.get("inferred") or not allow_dialogue):
                continue
            rx = _form_re([f for g in groups for f in g])
            segs = _QUOTED.split(lines[li])
            changed = 0
            for k in range(len(segs)):
                if (k % 2 == 1) == (kind == "dialogue"):
                    segs[k], c = rx.subn(lambda m, e=exp: e + (m.group("pl") or ""), segs[k])
                    changed += c
            if changed:
                lines[li] = "".join(segs)
                total += changed
                notes.append("%s: %s→%s ×%d" % (it.get("who", "?"), it.get("found", "?"), exp, changed))
        return "\n".join(lines), total, notes
    except Exception:
        return translated_text, 0, []


def check_pronouns(source_text: str, translated_text: str, pronoun_table: List[Dict[str, str]],
                   source_language: str, target_language: str,
                   pov_mode: str = "", narrator_name: str = "") -> Dict[str, Any]:
    """Compara o pronome de 1a pessoa da tradução com o esperado pela ficha.

    Confere (1) as FALAS (dentro de 「」), atribuindo o falante pelo original, e (2) a NARRAÇÃO
    em 1a pessoa (fora das aspas, só o pronome do narrador vale).
    Retorna {"status": "ok"|"skipped", "reason": str, "checked": int (falas),
             "narr_checked": int (parágrafos de narração), "issues": [..],
             "src_dialogues": int, "tgt_dialogues": int}. Cada issue tem "kind"
    ('dialogue'|'narration'), "line" e "found_groups" (usados por apply_pronoun_fixes).
    "reason" = 'count_mismatch'/'no_dialogue' quando só a parte das falas foi pulada.
    Nunca levanta exceção para o chamador.
    """
    out = {"status": "skipped", "reason": "", "checked": 0, "narr_checked": 0, "issues": [],
           "src_dialogues": 0, "tgt_dialogues": 0}
    try:
        tkey = target_key(target_language)
        groups = _FIRST_PERSON_GROUPS.get(tkey)
        if not groups:
            out["reason"] = "target_unsupported"
            return out
        table = [r for r in (pronoun_table or []) if r.get("name")]
        if not any(r.get("pronoun") for r in table):
            out["reason"] = "no_pronoun_column"
            return out

        from lang_profiles import is_first_person
        first = is_first_person(pov_mode)
        cast = _Cast(table)
        narrator_idx = None
        if first and narrator_name:
            nn = _norm_name(narrator_name)
            for i, r in enumerate(table):
                rn = _norm_name(r["name"])
                if rn and (rn == nn or nn in rn or rn in nn):
                    narrator_idx = i
                    break

        src_pars = _paragraphs(source_text)
        tgt_idx = _paragraphs_idx(translated_text)
        src_dialog = [p for p in src_pars if _is_dialogue_source(p)]
        tgt_dialog = [(li, p) for li, p in tgt_idx if "「" in p]
        out["src_dialogues"], out["tgt_dialogues"] = len(src_dialog), len(tgt_dialog)

        ran = False
        # (1) FALAS
        if not src_dialog:
            out["reason"] = "no_dialogue"
        elif len(src_dialog) != len(tgt_dialog):
            out["reason"] = "count_mismatch"
        else:
            skey = _src_key(source_language)
            tags = _FIRST_PERSON_TAG_WORDS.get(skey, set())
            attrib = _attribute(src_pars, cast, narrator_idx, tags, first)
            ambiguous = _AMBIGUOUS.get(tkey, set())
            ran = True
            for n, ((who, inferred), (li, tgt)) in enumerate(zip(attrib, tgt_dialog), start=1):
                if who is None:
                    continue
                expected = (table[who].get("pronoun") or "").strip()
                if not expected:
                    continue
                exp_group = _group_of(expected, groups)
                exp_forms = set(exp_group) if exp_group else {expected}
                inside = _inside_quotes(tgt)
                if not inside:
                    continue
                out["checked"] += 1
                if any(f in inside for f in exp_forms):
                    # Usa o esperado. Se ainda aparece OUTRO pronome de 1a pessoa na mesma fala
                    # (falante identificado direto), é quase certo um escorregão: flagra.
                    # Falante inferido: não flagra (atribuição incerta). Grupos de OUTROS
                    # personagens citados na fala original são ignorados (podem ser citação).
                    if inferred:
                        continue
                    skip = set()
                    for oi in cast.who_in(src_dialog[n - 1]):
                        if oi != who:
                            og = _group_of((table[oi].get("pronoun") or "").strip(), groups)
                            if og:
                                skip.add(og)
                    mixed = [g for g in groups
                             if g is not exp_group and g not in skip
                             and not any(f in _NARR_AMBIGUOUS or f in ambiguous for f in g)
                             and _form_re(g).search(inside)]
                    if mixed:
                        out["issues"].append({
                            "kind": "dialogue", "n": n, "line": li, "mixed": True,
                            "who": table[who]["name"], "expected": expected,
                            "found": "/".join(g[0] for g in mixed), "inferred": False,
                            "found_groups": mixed, "snippet": tgt[:60],
                        })
                    continue
                found = _find_first_person(inside, groups, ambiguous)
                found = [f for f in found if f not in exp_forms]
                if found:
                    out["issues"].append({
                        "kind": "dialogue", "n": n, "line": li,
                        "who": table[who]["name"], "expected": expected,
                        "found": "/".join(found), "inferred": inferred,
                        "found_groups": [g for g in groups if g[0] in found],
                        "snippet": tgt[:60],
                    })

        # (2) NARRAÇÃO em 1a pessoa (independe de a contagem de falas bater)
        if first:
            res = _check_narration(tgt_idx, src_pars, groups, table, narrator_idx, cast)
            if res is not None:
                ran = True
                out["narr_checked"], narr_issues = res
                out["issues"].extend(narr_issues)

        if ran:
            out["status"] = "ok"
        return out
    except Exception as exc:  # checagem nunca derruba a tradução
        out["reason"] = f"error:{exc}"
        return out
