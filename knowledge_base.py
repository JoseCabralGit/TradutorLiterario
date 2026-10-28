# -*- coding: utf-8 -*-
"""Gerenciadores de base de conhecimento local (SQLite) alimentados por planilhas Excel.

Modulo extraído de gui.py (arquivo original monolítico) durante a modularização.
"""
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

import pandas as pd

from app_config import INTERNAL_RAG_DB, LOCAL_CHARACTERS_DB, LOCAL_GLOSSARY_DB
from base_schema import get_description_text
from lang_profiles import (
    extract_pronoun, get_dicendi, get_target_profile, is_first_person,
    pov_narration_rule,
)
from text_utils import (
    _CJK, _cell_candidates, _format_row, _norm, _norm_name, _partial_word_ok,
    _phrase_in, _row_matches, _tokens, bm25_rank, build_word_df,
    detect_pronoun_columns, find_speakers, nested_name_groups,
)

# Instruções enviadas junto com os blocos (sem elas, modelos fracos tratam a lista como "enfeite"
# ou usam o pronome da ficha no lugar do nome do personagem).
GLOSSARY_DIRECTIVE = (
    "Diretriz: use EXATAMENTE estas traduções para nomes e termos, sem sinônimos (flexione só se a língua exigir). "
    "O nome de um personagem deve aparecer pela forma deste dicionário em toda a tradução, "
    "inclusive na narração e em marcadores de fala (\"disse X\", \"X sorriu\")."
)
# Legado: regra fixa em japonês (mantida p/ compatibilidade; o caminho novo
# monta a diretiva do perfil do idioma-alvo — ver _build_characters_directive).
CHARACTERS_DIRECTIVE = (
    "Diretriz: use as fichas para a voz, a personalidade e o registro de fala de cada personagem. "
    "Se houver um campo de pronome, ele indica como o personagem fala de SI MESMO em primeira pessoa, "
    "e só vale DENTRO das falas (「」). NUNCA substitua o nome de um personagem por esse pronome: "
    "na narração e nos marcadores de fala use o nome do dicionário."
)


def _build_characters_directive(target_language: str, pov_mode: str = "",
                                narrator_name: str = "",
                                narrator_pronoun: str = "") -> str:
    """Diretiva de personagens como TEMPLATE do perfil do idioma-alvo.

    Japones/ingles = regra caprichada; outra lingua = perfil enxuto;
    lingua desconhecida = `default` generico (nunca herda 「」 por engano).
    Se POV for 1a pessoa, acrescenta a EXCECAO de narracao (pronome do
    narrador fora das aspas); 3a pessoa nao ganha nenhum token extra.
    A regra dos dialogos (pronome de quem fala de si dentro das aspas)
    continua valendo sempre, nos dois POVs.
    """
    prof = get_target_profile(target_language)
    intro = ("Diretriz: use as fichas para a voz, a personalidade e o registro de fala "
             "de cada personagem. ")
    if is_first_person(pov_mode):
        # 1a pessoa: a regra do NARRADOR vem PRIMEIRO e prevalece sobre a regra geral de
        # narração ("use o nome, nunca o pronome"), que passa a valer só para os demais.
        return (intro
                + "REGRA PRIORITARIA DO NARRADOR (prevalece sobre a regra de narracao abaixo, "
                  "somente para ele): "
                + pov_narration_rule(target_language, narrator_name, narrator_pronoun)
                + " REGRAS GERAIS (valem para os DEMAIS personagens): "
                + prof.get("pronoun_rule", ""))
    return intro + prof.get("pronoun_rule", "")


def _with_description(header: str, directive: str, description: str) -> str:
    """Monta o cabeçalho do bloco com a DESCRIÇÃO DA PLANILHA (texto do usuário,
    ver base_schema.py) como dado — SEMPRE antes e sem substituir a diretiva
    fixa do programa, que continua inviolável aqui."""
    parts = [header]
    desc = (description or "").strip()
    if desc:
        parts.append(
            "COMO A PLANILHA ESTÁ ORGANIZADA (orientação do autor da base; use-a para "
            "entender o que cada coluna das linhas abaixo significa):\n"
            + desc
        )
    parts.append(directive)
    return "\n".join(parts) + "\n"


def _name_core(raw) -> str:
    """Nome sem o detalhe entre parênteses: 'Sayaka Mizuno(Matadora de elfo)' -> 'Sayaka Mizuno'.
    O parêntese descreve a pessoa; suas palavras não são o nome e não devem casar sozinhas."""
    return " ".join(re.sub(r"\([^)]*\)?", " ", str(raw or "")).split())


def _clean_df(df: pd.DataFrame):
    """Limpa a planilha ao sincronizar: normaliza espaços/quebras de linha nas células e remove linhas
    duplicadas. Só mexe no banco local — a planilha original nunca é alterada. Devolve (df, n_duplicadas)."""
    df = df.apply(lambda col: col.map(lambda v: " ".join(v.split()) if isinstance(v, str) else v))
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    return df, before - len(df)


def _unique(lines):
    seen, out = set(), []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            out.append(ln)
    return out


_KNOWN_PRONOUNS = None


def _known_pronouns() -> set:
    """Pronomes de 1a pessoa CONHECIDOS (perfis de idioma + grupos de grafias do japonês)."""
    global _KNOWN_PRONOUNS
    if _KNOWN_PRONOUNS is None:
        from lang_profiles import _TARGET_PROFILES, _key_norm
        known = {_key_norm(x) for prof in _TARGET_PROFILES.values() for x in prof.get("pronouns", [])}
        try:
            from consistency import _FIRST_PERSON_GROUPS
            known |= {_key_norm(f) for groups in _FIRST_PERSON_GROUPS.values() for g in groups for f in g}
        except Exception:
            pass
        _KNOWN_PRONOUNS = known
    return _KNOWN_PRONOUNS


def _pick_pronoun(vals, scan_cols, target_language: str = "", skip_first: bool = False) -> str:
    """Pronome de 1a pessoa de UMA linha da planilha de personagens.

    Entre as colunas candidatas, prefere a célula cujo pronome é CONHECIDO (あたし, 俺, 僕...).
    Assim, uma coluna de 'Voz'/'Estilo de fala' com kana (じゃん, だ, です) posta ANTES da coluna de
    pronome não é lida como pronome. Se nenhuma célula tiver pronome conhecido, mantém o
    comportamento antigo (primeira célula com cara de pronome)."""
    from lang_profiles import _key_norm, extract_pronoun, looks_like_pronoun_cell
    cands = []
    for c in scan_cols:
        if skip_first and c == 0:
            continue
        try:
            cell = vals[c] if c < len(vals) else None
        except Exception:
            cell = None
        if not looks_like_pronoun_cell(cell):
            continue
        p = extract_pronoun(cell, target_language)
        if p:
            cands.append(p)
    known = _known_pronouns()
    for p in cands:
        if _key_norm(p) in known:
            return p
    return cands[0] if cands else ""


class GlossaryManager:
    """Gerencia a Base de Dicionário de Termos (Drive 1) com suporte a correspondência exata e parcial."""
    def __init__(self, db_path: str = LOCAL_GLOSSARY_DB):
        self.db_path = db_path
        self.excel_path: str = ""

    def reset_and_sync_from_excel(self, excel_path: str) -> str:
        self.excel_path = excel_path or ""
        log_msg = f"[🔄 GlossaryManager] Sincronizando Dicionário de Termos com: {excel_path}\n"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            log_msg += f"   [🗑️] Banco de glossário antigo '{self.db_path}' resetado.\n"

        try:
            xls = pd.ExcelFile(excel_path)
        except Exception as e:
            log_msg += f"   [⚠️] Erro ao abrir Excel de Glossário: {e}\n"
            self._create_empty_db()
            return log_msg

        conn = sqlite3.connect(self.db_path)
        sheet_to_use = xls.sheet_names[0] if xls.sheet_names else "Glossario"
        if "Glossario" in xls.sheet_names:
            sheet_to_use = "Glossario"
        
        df, n_dup = _clean_df(pd.read_excel(xls, sheet_name=sheet_to_use))
        df.to_sql("glossario", conn, index=False, if_exists="replace")
        log_msg += f"   [📚] Tabela 'glossario' recarregada com {len(df)} registros.\n"
        try:
            pairs = nested_name_groups(df.iloc[:, 0].tolist()) if len(df.columns) else []
            if pairs:
                shown = "; ".join(f"'{a}' ~ '{b}'" for a, b in pairs[:8])
                log_msg += (f"   [⚠️] Possíveis nomes repetidos no glossário ({shown}"
                            f"{' ...' if len(pairs) > 8 else ''}). Se forem a mesma pessoa, "
                            "a tradução pode alternar entre as grafias; o programa orienta "
                            "o modelo a seguir a forma que o original usa em cada ponto.\n")
        except Exception:
            pass
        if n_dup:
            log_msg += f"   [🧹] {n_dup} linha(s) duplicada(s) ignorada(s) no banco local (a planilha não foi alterada).\n"
        conn.commit()
        conn.close()
        return log_msg

    def _create_empty_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS glossario (termo_original TEXT, traducao_sugerida TEXT, contexto TEXT)")
        conn.commit()
        conn.close()

    def get_relevant_glossary(self, text_chunk: str) -> str:
        if not os.path.exists(self.db_path):
            return "Nenhum dicionário de termos carregado."

        text_norm = _norm(text_chunk)
        matched = []
        matched_keys = []
        notes = []
        conn = sqlite3.connect(self.db_path)
        try:
            df = pd.read_sql("SELECT * FROM glossario", conn)
            first_col = df.iloc[:, 0].tolist() if len(df.columns) else []
            # Estatística da própria base: palavra solta só casa se for única de um termo.
            word_df = build_word_df(first_col)
            for _, row in df.iterrows():
                if _row_matches(row, text_norm, word_df):
                    matched.append("- " + _format_row(row))
                    matched_keys.append(" ".join(str(row.iloc[0]).split()))
            notes = self._alias_notes(df, matched_keys)
        except Exception:
            pass
        finally:
            conn.close()

        if not matched:
            return "Nenhum termo específico do dicionário foi detectado neste trecho."
        desc = get_description_text("glossary", self.excel_path)
        return (_with_description("--- DICIONÁRIO DE TERMOS (GLOSSÁRIO) ---", GLOSSARY_DIRECTIVE, desc)
                + "\n".join(_unique(matched))
                + ("\n" + "\n".join(notes) if notes else ""))

    @staticmethod
    def _alias_notes(df, matched_keys) -> List[str]:
        """Aviso quando um termo curto casado tem UMA forma longa na base
        ('Haruto' / 'Saionji Haruto'): são o mesmo nome; cada forma deve seguir
        a grafia que o ORIGINAL usa no ponto, em vez de o modelo escolher uma só."""
        if len(df.columns) < 2:
            return []
        col0 = df.iloc[:, 0].tolist()
        col1 = df.iloc[:, 1].tolist()
        tr = {}
        for k, v in zip(col0, col1):
            if isinstance(k, str) and v is not None and not (not isinstance(v, str) and pd.isna(v)):
                tr[" ".join(k.split())] = " ".join(str(v).split())
        longs_of = {}
        for short, long_ in nested_name_groups(col0):
            longs_of.setdefault(short, []).append(long_)
        out = []
        for key in matched_keys:
            longs = longs_of.get(key, [])
            if len(longs) == 1 and key in tr and longs[0] in tr:
                out.append(
                    f"Obs.: '{key}' e '{longs[0]}' são o MESMO nome. Siga a forma que o ORIGINAL usa em cada ponto: "
                    f"'{key}' -> {tr[key]}; '{longs[0]}' -> {tr[longs[0]]}. Não troque uma pela outra."
                )
        return _unique(out)
class CharactersManager:
    """Gerencia a Base de Fichas de Personagens (Drive 2) com suporte a nomes parciais e apelidos."""
    def __init__(self, db_path: str = LOCAL_CHARACTERS_DB):
        self.db_path = db_path
        self.excel_path: str = ""

    def reset_and_sync_from_excel(self, excel_path: str) -> str:
        self.excel_path = excel_path or ""
        log_msg = f"[🔄 CharactersManager] Sincronizando Fichas de Personagens com: {excel_path}\n"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            log_msg += f"   [🗑️] Banco de personagens antigo '{self.db_path}' resetado.\n"

        try:
            xls = pd.ExcelFile(excel_path)
        except Exception as e:
            log_msg += f"   [⚠️] Erro ao abrir Excel de Personagens: {e}\n"
            self._create_empty_db()
            return log_msg

        conn = sqlite3.connect(self.db_path)
        sheet_to_use = xls.sheet_names[0] if xls.sheet_names else "Personagens"
        if "Personagens" in xls.sheet_names:
            sheet_to_use = "Personagens"
        
        df, n_dup = _clean_df(pd.read_excel(xls, sheet_name=sheet_to_use))
        df.to_sql("personagens", conn, index=False, if_exists="replace")
        log_msg += f"   [👥] Tabela 'personagens' recarregada com {len(df)} registros.\n"
        if n_dup:
            log_msg += f"   [🧹] {n_dup} linha(s) duplicada(s) ignorada(s) no banco local (a planilha não foi alterada).\n"
        conn.commit()
        conn.close()
        return log_msg

    def _create_empty_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS personagens (nome TEXT, descricao TEXT, notas TEXT)")
        conn.commit()
        conn.close()

    def get_pronoun_table(self, target_language: str = "") -> List[Dict[str, str]]:
        """Tabela [{name, core, pronoun}] de TODOS os personagens da base (sem LLM).

        `pronoun` vem da coluna que o programa detecta como pronome (qualquer
        organização de planilha); vazio se não houver. Usada pela checagem de
        consistência (consistency.check_pronouns)."""
        if not os.path.exists(self.db_path):
            return []
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                df = pd.read_sql("SELECT * FROM personagens", conn)
            finally:
                conn.close()
        except Exception:
            return []
        if df is None or len(df) == 0:
            return []
        from lang_profiles import looks_like_pronoun_cell
        cols = list(df.columns)
        rows = df.values.tolist()
        pron_cols = detect_pronoun_columns(cols, rows)
        scan_cols = sorted(pron_cols) if pron_cols else list(range(len(cols)))
        out = []
        for vals in rows:
            name = str(vals[0]).strip() if vals else ""
            pron = _pick_pronoun(vals, scan_cols, target_language, skip_first=True)
            out.append({"name": name, "core": _name_core(name), "pronoun": pron})
        return out

    def get_relevant_characters(self, text_chunk: str, source_language: str = "",
                                target_language: str = "", pov_mode: str = "",
                                narrator_name: str = "") -> str:
        """Bloco de personagens em 2 NIVEIS (universal, sem LLM, sem token extra).

        Nivel 1 (sempre, barato): elenco do trecho + 1 linha de pronome por
          nome (citado de passagem tambem entra — o pronome dele serve para
          NAO usar errado).
        Nivel 2 (so quem tem voz na cena): ficha COMPLETA com personalidade
          integral (falantes detectados + narrador em 1a pessoa + citados com
          nome explicito no trecho).

        Fallback: se NADA casar, manda o elenco compacto de TODOS (pronome
        continua disponivel; a ficha nunca "some" por causa do filtro).
        Parametros novos tem default: chamada antiga com so (texto) funciona.
        """
        if not os.path.exists(self.db_path):
            return "Nenhuma ficha de personagens carregada."

        desc = get_description_text("characters", self.excel_path)

        text_norm = _norm(text_chunk)
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                df = pd.read_sql("SELECT * FROM personagens", conn)
            finally:
                conn.close()
        except Exception:
            return "Nenhuma ficha de personagens carregada."
        if df is None or len(df) == 0:
            return "Nenhuma ficha de personagens carregada."

        cols = list(df.columns)
        rows = df.values.tolist()
        name_col = 0
        pron_cols = detect_pronoun_columns(cols, rows)

        def _row_name(idx_row):
            try:
                return str(rows[idx_row][name_col]).strip()
            except Exception:
                return ""

        def _row_matches_nonpronoun(idx_row):
            vals = rows[idx_row]
            for col_idx in range(len(cols)):
                if col_idx in pron_cols:
                    continue
                cell = vals[col_idx] if col_idx < len(vals) else None
                for cand in _cell_candidates(cell):
                    cand = _norm_name(cand)
                    if not cand:
                        continue
                    if _phrase_in(cand, text_norm):
                        return True
            return False

        name_df = build_word_df([_name_core(_row_name(i)) for i in range(len(rows))])
        matched_idx, mentioned_idx = [], []
        for i in range(len(rows)):
            if _row_matches_nonpronoun(i):
                if i not in matched_idx:
                    matched_idx.append(i)
            nm = _norm_name(_row_name(i))
            nm_core = _norm_name(_name_core(_row_name(i)))
            if nm and _phrase_in(nm, text_norm):
                if i not in mentioned_idx:
                    mentioned_idx.append(i)
            elif nm_core and " " in nm_core and not _CJK.search(nm_core):
                # Nome composto citado por uma palavra ("senhor Kaoru" com
                # ficha "Shiranami Kaoru."): palavra isolada >= 4 letras vale,
                # mas só se for ÚNICA daquele personagem (sobrenome comum a
                # 2 fichas, ex. 'Elarion', não identifica ninguém sozinho).
                if any(_phrase_in(w, text_norm)
                       for w in re.findall(r"\w+", nm_core) if _partial_word_ok(w, name_df)):
                    if i not in mentioned_idx:
                        mentioned_idx.append(i)

        # Falantes detectados (regex, sem LLM) + narrador em 1a pessoa.
        known_names = [_row_name(i) for i in range(len(rows))]
        spk = find_speakers(
            text_chunk, known_names, get_dicendi(source_language or "Português"),
            narrator_norm=_norm_name(narrator_name) if narrator_name else "",
        )
        speaker_idx = []
        for s in spk.get("speakers", []):
            sn = _norm_name(s)
            for i in range(len(rows)):
                if _norm_name(_row_name(i)) == sn and i not in speaker_idx:
                    speaker_idx.append(i)
        narrator_idx = []
        is_first = is_first_person(pov_mode)
        if is_first and narrator_name:
            nn = _norm_name(narrator_name)
            for i in range(len(rows)):
                rn = _norm_name(_row_name(i))
                if rn and (rn == nn or nn in rn or rn in nn):
                    narrator_idx.append(i)
                    break

        # Forma final de pronome por linha ('Atashi (あたし)' -> 'あたし').
        # So aceita celula com cara de pronome (evita usar o nome como pronome
        # quando a planilha nao tem coluna de pronome detectada).
        from lang_profiles import looks_like_pronoun_cell
        pronouns = {}
        scan_cols = sorted(pron_cols) if pron_cols else list(range(len(cols)))
        for i in range(len(rows)):
            p = _pick_pronoun(rows[i], scan_cols, target_language)
            if p:
                pronouns[i] = p

        def _alias_in_text(i):
            """Forma curta do nome que o TEXTO realmente usa ('Haruto' p/ ficha
            'Saionji Haruto'). '' se o nome completo aparece ou nada casa."""
            nm_raw = _name_core(_row_name(i))
            nm = _norm_name(nm_raw)
            if not nm or " " not in nm or _CJK.search(nm) or _phrase_in(nm, text_norm):
                return ""
            toks = nm_raw.split()
            used = [w for w in toks
                    if len(_norm_name(w)) >= 2 and _phrase_in(_norm_name(w), text_norm)
                    and (len(_norm_name(w)) < 4 or _partial_word_ok(_norm_name(w), name_df))]
            return " ".join(used) if used and len(used) < len(toks) else ""

        def _display(i):
            nm = _row_name(i)
            if not nm:
                return f"personagem-{i + 1}"
            al = _alias_in_text(i)
            return f"{nm} (no texto aparece como: {al})" if al else nm

        # Nivel 1: elenco (casados + citados + falantes + narrador).
        roster_idx = []
        for i in matched_idx + mentioned_idx + speaker_idx + narrator_idx:
            if i not in roster_idx:
                roster_idx.append(i)
        fallback_all = False
        if not roster_idx:
            roster_idx = list(range(len(rows)))
            fallback_all = True

        # Nivel 2: fichas completas de quem TEM VOZ (fala/narra/citado nominal).
        full_idx = []
        for i in speaker_idx + narrator_idx + mentioned_idx:
            if i not in full_idx:
                full_idx.append(i)
        if fallback_all:
            full_idx = []

        out = []
        out.append("--- ELENCO DO TRECHO (detectado pelo programa) ---")
        if fallback_all:
            out.append("(nenhum nome casou neste trecho; elenco completo abaixo)")
        if is_first and narrator_name:
            out.append(f"Narrador (1a pessoa): {narrator_name}")
        if speaker_idx:
            out.append("Falantes ativos: " + ", ".join(_display(i) for i in speaker_idx))
        out.append("Presentes/citados: " + ", ".join(_display(i) for i in roster_idx))
        out.append("")
        out.append("--- PRONOMES DE 1a PESSOA (citado tambem entra para NAO usar "
                   "o pronome dele ao falar DELE) ---")
        for i in roster_idx:
            p = pronouns.get(i, "")
            _tag = ("  [NARRADOR: use este pronome tambem na narracao, quando falar de si]"
                    if (p and i in narrator_idx) else "")
            out.append(f"- {_display(i)}" + (f" -> {p}" if p else "") + _tag)
        if full_idx:
            out.append("")
            out.append("--- FICHAS COMPLETAS (personalidade integral; so de quem "
                       "fala/narra/e citado nominalmente) ---")
            for i in full_idx:
                try:
                    out.append("- " + _format_row(df.iloc[i]))
                except Exception:
                    out.append(f"- {_display(i)}")
        out.append("")
        # Diretiva montada AQUI (no final): ja conhece o pronome do narrador,
        # entao a excecao de 1a pessoa sai com o valor concreto ('あたし').
        # Sem pronome na planilha -> aponta para a ficha; 3a pessoa -> sem
        # excecao, zero token extra.
        narr_pron = ""
        if is_first and narrator_idx:
            narr_pron = pronouns.get(narrator_idx[0], "")
        directive = _build_characters_directive(
            target_language or "Japonês", pov_mode=pov_mode,
            narrator_name=narrator_name or "", narrator_pronoun=narr_pron,
        )
        head = _with_description("--- FICHA DE PERSONAGENS ---", directive, desc)
        return head + "\n".join(out)

# Modos de uso de uma base do RAG interno:
#  "classic" = comportamento original (referência de frases, todas as colunas no prompt).
#  "support" = APOIO LINGUÍSTICO: só inspiração de vocabulário/tom; a IA é instruída a
#              NÃO copiar nem reaproveitar as frases. Combine com `prompt_columns` para
#              mostrar apenas a coluna do idioma-alvo.
RAG_MODES = ("classic", "support")
# NENHUM limite é imposto: 0 = sem limite. Quem define é o usuário (⚙️ Configurar uso do banco).
DEFAULT_BASE_SETTINGS = {
    "mode": "support",
    "prompt_columns": [],   # [] = todas as colunas (exceto id) vão para o prompt
    "search_columns": [],   # [] = todas as colunas participam da busca
    "top_k": 15,            # máx. de linhas enviadas à IA (0 = todas as que forem relevantes)
    "max_chars": 0,         # máx. de caracteres do bloco inteiro (0 = sem limite)
    "cell_clip": 0,         # corta cada célula em N caracteres (0 = não corta)
    "min_word_len": 4,      # tamanho mínimo da palavra usada na busca
    "use_stopwords": True,  # ignora palavras muito comuns (de, que, with, that...)
    "common_pct": 50,       # ignora termos presentes em mais de N% das linhas (0 = não ignora)
}


class InternalRAGManager:
    """
    Gerencia o Banco de Frases de Referência (Memory Translation / RAG Interno).
    Fornece exemplos de frases e traduções para enriquecer a naturalidade 
    sem alterar a voz narrativa original do texto.
    """
    def __init__(self, db_path: str = INTERNAL_RAG_DB):
        self.db_path = db_path
        self._ensure_default_db()

    def _ensure_default_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS metadata_bases (base_name TEXT PRIMARY KEY, columns TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS base_settings (base_name TEXT PRIMARY KEY, settings TEXT)")
        cursor.execute("SELECT count(*) FROM metadata_bases")
        if cursor.fetchone()[0] == 0:
            default_cols = ["Frase_Original", "Frase_Alvo", "Contexto_Referencia"]
            cols_str = json.dumps(default_cols)
            cursor.execute("INSERT INTO metadata_bases (base_name, columns) VALUES (?, ?)", ("Banco_Frases_Padrao", cols_str))
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Banco_Frases_Padrao (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Frase_Original TEXT,
                    Frase_Alvo TEXT,
                    Contexto_Referencia TEXT
                )
            """)
            cursor.execute("INSERT INTO Banco_Frases_Padrao (Frase_Original, Frase_Alvo, Contexto_Referencia) VALUES (?, ?, ?)",
                           ("The autumn wind whispered", "O vento de outono sussurrou", "Exemplo de naturalidade frasal"))
        conn.commit()
        conn.close()

    def get_all_bases(self) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT base_name FROM metadata_bases")
        bases = [row[0] for row in cursor.fetchall()]
        conn.close()
        return bases

    def get_base_columns(self, base_name: str) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT columns FROM metadata_bases WHERE base_name = ?", (base_name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return []

    def create_new_base(self, base_name: str, columns: List[str]):
        clean_name = base_name.strip().replace(" ", "_")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cols_str = json.dumps(columns)
        cursor.execute("INSERT OR REPLACE INTO metadata_bases (base_name, columns) VALUES (?, ?)", (clean_name, cols_str))
        
        cols_sql = ", ".join([f'"{col.strip()}" TEXT' for col in columns])
        cursor.execute(f'CREATE TABLE IF NOT EXISTS "{clean_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})')
        
        conn.commit()
        conn.close()

    def delete_base(self, base_name: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM metadata_bases WHERE base_name = ?", (base_name,))
        cursor.execute("DELETE FROM base_settings WHERE base_name = ?", (base_name,))
        cursor.execute(f'DROP TABLE IF EXISTS "{base_name}"')
        conn.commit()
        conn.close()

    def get_base_data(self, base_name: str) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        try:
            df = pd.read_sql(f'SELECT * FROM "{base_name}"', conn)
        except Exception:
            df = pd.DataFrame()
        conn.close()
        return df

    def add_row_to_base(self, base_name: str, values: Dict[str, Any]):
        conn = sqlite3.connect(self.db_path)
        cols = self.get_base_columns(base_name)
        valid_cols = [c for c in cols if c in values]
        placeholders = ", ".join(["?" for _ in valid_cols])
        cols_sql = ", ".join([f'"{c}"' for c in valid_cols])
        vals = [values[c] for c in valid_cols]
        
        sql = f'INSERT INTO "{base_name}" ({cols_sql}) VALUES ({placeholders})'
        cursor = conn.cursor()
        cursor.execute(sql, vals)
        conn.commit()
        conn.close()

    def delete_row_from_base(self, base_name: str, row_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f'DELETE FROM "{base_name}" WHERE id = ?', (row_id,))
        conn.commit()
        conn.close()

    def update_row_in_base(self, base_name: str, row_id: int, values: Dict[str, Any]) -> None:
        """ADICAO: atualiza uma linha existente (edicao). Nao altera add/delete."""
        conn = sqlite3.connect(self.db_path)
        cols = self.get_base_columns(base_name)
        valid_cols = [c for c in cols if c in values]
        if not valid_cols:
            conn.close()
            return
        sets_sql = ", ".join([f'"{c}" = ?' for c in valid_cols])
        vals = [values[c] for c in valid_cols] + [row_id]
        cur = conn.cursor()
        cur.execute(f'UPDATE "{base_name}" SET {sets_sql} WHERE id = ?', vals)
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Exportacao / importacao Excel (ADICAO: nao altera nada existente)
    # Formato: aba "frases" (1 coluna por campo, sem id) + aba "_settings"
    # (chave/valor da configuracao de uso da base).
    # ------------------------------------------------------------------
    SETTINGS_SHEET = "_settings"

    def export_base_to_excel(self, base_name: str, path: str) -> Dict[str, int]:
        """Exporta base RAG para Excel. Retorna {"rows": N}. Nao mexe no banco."""
        df = self.get_base_data(base_name)
        cols = self.get_base_columns(base_name)
        data_cols = [c for c in cols if c in df.columns] or [c for c in df.columns if c != "id"]
        out = df[data_cols] if data_cols else pd.DataFrame()
        settings = self.get_base_settings(base_name)
        s_df = pd.DataFrame(
            [{"chave": k, "valor": (",".join(str(x) for x in v) if isinstance(v, list) else v)}
             for k, v in settings.items()]
        )
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            out.to_excel(w, sheet_name="frases", index=False)
            s_df.to_excel(w, sheet_name=self.SETTINGS_SHEET, index=False)
        return {"rows": int(len(out))}

    def import_base_from_excel(self, path: str, base_name: Optional[str] = None,
                               mode: str = "append") -> Dict[str, Any]:
        """Importa Excel para base RAG. Nao remove nada salvo com mode="append".

        - base_name None: usa o nome do arquivo (sem extensao).
        - mode "append" (padrao): acrescenta, pulando linhas duplicadas.
        - mode "replace": apaga as linhas atuais antes (settings preservados).
        Retorna {"base": nome, "new": N, "skipped": M}.
        """
        xls = pd.ExcelFile(path)
        sheet = "frases" if "frases" in xls.sheet_names else xls.sheet_names[0]
        df = pd.read_excel(xls, sheet_name=sheet)
        if base_name is None:
            base_name = os.path.splitext(os.path.basename(path))[0].strip().replace(" ", "_") or "Base_Importada"
        cols = [str(c).strip() for c in list(df.columns) if str(c).strip()]
        if not cols:
            raise ValueError("O Excel nao tem colunas (cabecalho vazio).")
        df = df.where(pd.notna(df), "")

        existing = self.get_all_bases()
        if base_name not in existing:
            self.create_new_base(base_name, cols)
        base_cols = self.get_base_columns(base_name)
        use_cols = [c for c in cols if c in base_cols] or base_cols

        if mode == "replace":
            conn = sqlite3.connect(self.db_path)
            conn.execute(f'DELETE FROM "{base_name}"')
            conn.commit()
            conn.close()
            seen = set()
        else:
            cur = self.get_base_data(base_name)
            seen = set()
            if not cur.empty:
                for _, r in cur.iterrows():
                    seen.add(tuple(" ".join(str(r.get(c, "")).split()).lower() for c in use_cols))

        new_n, skip_n = 0, 0
        for _, row in df.iterrows():
            vals = {c: str(row[c]).strip() if c in df.columns else "" for c in use_cols}
            if not any(vals.values()):
                skip_n += 1
                continue
            key = tuple(" ".join(vals[c].split()).lower() for c in use_cols)
            if key in seen:
                skip_n += 1
                continue
            self.add_row_to_base(base_name, vals)
            seen.add(key)
            new_n += 1

        # Aba de settings (opcional): restaura configuracao se existir.
        try:
            if self.SETTINGS_SHEET in xls.sheet_names:
                s_df = pd.read_excel(xls, sheet_name=self.SETTINGS_SHEET)
                s_map = {str(r.iloc[0]).strip(): r.iloc[1]
                         for _, r in s_df.iterrows() if str(r.iloc[0]).strip()}
                if s_map:
                    cur_s = self.get_base_settings(base_name)
                    for k in list(cur_s.keys()):
                        if k in s_map:
                            v = s_map[k]
                            if k in ("prompt_columns", "search_columns"):
                                cur_s[k] = [x.strip() for x in str(v).split(",") if x.strip()]
                            elif k == "mode":
                                cur_s[k] = str(v).strip() or cur_s[k]
                            elif k == "use_stopwords":
                                cur_s[k] = str(v).strip().lower() not in ("0", "false", "nao", "não", "")
                            else:
                                try:
                                    cur_s[k] = int(float(str(v).strip() or cur_s[k]))
                                except (TypeError, ValueError):
                                    pass
                    self.save_base_settings(base_name, cur_s)
        except Exception:
            pass
        return {"base": base_name, "new": new_n, "skipped": skip_n}


    # ------------------------------------------------------------------
    # Configuração de uso por base (opcional; sem configurar = padrão)
    # ------------------------------------------------------------------
    def get_base_settings(self, base_name: str) -> Dict[str, Any]:
        settings = dict(DEFAULT_BASE_SETTINGS)
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute("SELECT settings FROM base_settings WHERE base_name = ?", (base_name,)).fetchone()
            conn.close()
            if row and row[0]:
                saved = json.loads(row[0])
                if isinstance(saved, dict):
                    settings.update({k: saved[k] for k in DEFAULT_BASE_SETTINGS if k in saved})
        except Exception:
            pass
        return self._sanitize_settings(settings)

    def save_base_settings(self, base_name: str, settings: Dict[str, Any]) -> None:
        clean = self._sanitize_settings(settings)
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS base_settings (base_name TEXT PRIMARY KEY, settings TEXT)")
        conn.execute("INSERT OR REPLACE INTO base_settings (base_name, settings) VALUES (?, ?)",
                     (base_name, json.dumps(clean, ensure_ascii=False)))
        conn.commit()
        conn.close()

    @staticmethod
    def _sanitize_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
        mode = settings.get("mode", DEFAULT_BASE_SETTINGS["mode"])
        if mode not in RAG_MODES:
            mode = DEFAULT_BASE_SETTINGS["mode"]

        def _int(key, default, lo, hi):
            try:
                v = int(settings.get(key, default))
            except (TypeError, ValueError):
                v = default
            return max(lo, min(v, hi))

        return {
            "mode": mode,
            "prompt_columns": [str(c) for c in (settings.get("prompt_columns") or [])],
            "search_columns": [str(c) for c in (settings.get("search_columns") or [])],
            "top_k": _int("top_k", DEFAULT_BASE_SETTINGS["top_k"], 0, 100000),
            "max_chars": _int("max_chars", 0, 0, 10000000),
            "cell_clip": _int("cell_clip", 0, 0, 100000),
            "min_word_len": _int("min_word_len", 4, 1, 20),
            "use_stopwords": bool(settings.get("use_stopwords", True)),
            "common_pct": _int("common_pct", 50, 0, 100),
        }

    # ------------------------------------------------------------------
    # Recuperação
    # ------------------------------------------------------------------
    @staticmethod
    def _clip(value, limit: int = 0) -> str:
        text = " ".join(str(value).split())
        return text if limit <= 0 or len(text) <= limit else text[:limit].rstrip() + "…"

    def get_reference_context(self, text_chunk: str, active_base: str, extra_text: str = "",
                              cache: Optional[Dict[str, Any]] = None, max_chars_cap: int = 0):
        """Busca as linhas mais relevantes da base (BM25) e monta o bloco para o prompt.

        `text_chunk` = texto original; `extra_text` = texto já traduzido por um agente anterior
        (útil porque ele está no idioma-alvo e casa com as colunas do idioma-alvo da base).
        `cache` = dict opcional de por-execução (o pipeline passa um por run): guarda docs +
        tokenização BM25 para NÃO refazer iterrows/tokenização a cada agente (CPU em PC fraco).
        Retorna (texto_do_prompt, quantidade_de_linhas). Em modo apoio, sem resultado = ("", 0).
        """
        settings = self.get_base_settings(active_base)
        support = settings["mode"] == "support"
        df = self.get_base_data(active_base)
        if df.empty:
            return ("" if support else "Banco de frases de referência vazio."), 0

        data_cols = [c for c in df.columns if c != "id"]
        search_cols = [c for c in settings["search_columns"] if c in data_cols] or data_cols
        prompt_cols = [c for c in settings["prompt_columns"] if c in data_cols] or data_cols

        # Fingerprint: muda base/colunas/params de tokenização => invalida o cache.
        fp = (active_base, tuple(search_cols), settings["min_word_len"], settings["use_stopwords"])
        entry = cache.get("rag_docs") if isinstance(cache, dict) else None
        if entry is not None and entry[0] == fp:
            docs, doc_tokens = entry[1], entry[2]
        else:
            docs = [" ".join(str(row[c]) for c in search_cols if pd.notna(row[c]))
                    for _, row in df.iterrows()]
            doc_tokens = [_tokens(d, settings["min_word_len"], settings["use_stopwords"])
                          for d in docs]
            if isinstance(cache, dict):
                cache["rag_docs"] = (fp, docs, doc_tokens)
        ranked = bm25_rank(
            f"{text_chunk}\n{extra_text or ''}", docs,
            min_len=settings["min_word_len"], common_pct=settings["common_pct"],
            use_stopwords=settings["use_stopwords"], doc_tokens=doc_tokens)
        if settings["top_k"] > 0:
            ranked = ranked[: settings["top_k"]]
        # Teto extra opcional (modo janela pequena do agente): vale o MENOR entre o da base e este.
        _cap = settings["max_chars"]
        if max_chars_cap and max_chars_cap > 0:
            _cap = min(_cap, max_chars_cap) if _cap > 0 else max_chars_cap

        lines: List[str] = []
        total = 0
        for idx, _score in ranked:
            row = df.iloc[idx]
            parts = [(c, self._clip(row[c], settings["cell_clip"])) for c in prompt_cols if pd.notna(row[c]) and str(row[c]).strip()]
            if not parts:
                continue
            if support:
                body = parts[0][1] if len(parts) == 1 else " | ".join(f"{c}: {v}" for c, v in parts)
                line = f"- {body}"
            else:
                line = f"- [{active_base.upper()}] " + " | ".join(f"{c}: {v}" for c, v in parts)
            if _cap > 0 and lines and total + len(line) > _cap:
                break
            lines.append(line)
            total += len(line)

        if not lines:
            return ("" if support else "Nenhuma frase de referência relevante foi encontrada para este trecho."), 0

        if support:
            header = (
                f"=== APOIO LINGUÍSTICO — VOCABULÁRIO E TOM ({active_base.upper()}) ===\n"
                "Diretriz: os itens abaixo são APENAS inspiração de vocabulário, registro e naturalidade. "
                "NÃO copie, NÃO reutilize estas frases nem a estrutura delas e NÃO as insira no texto traduzido. "
                "Use uma ideia ou expressão daqui somente se ela se encaixar naturalmente no que o texto original já diz. "
                "A tradução deve seguir fielmente o texto original, seu sentido e sua voz narrativa.\n"
            )
        else:
            header = (
                f"=== BANCO DE FRASES DE REFERÊNCIA PARA ENRIQUECER A NATURALIDADE ({active_base.upper()}) ===\n"
                "Diretriz: Utilize estes exemplos apenas como referência de naturalidade frasal, "
                "preservando rigorosamente a voz narrativa original do texto.\n"
            )
        return header + "\n".join(lines), len(lines)

    def get_relevant_reference_phrases(self, text_chunk: str, active_base: str, target_language: str = "", extra_text: str = "") -> str:
        """Compatível com a assinatura antiga; `target_language` não é mais usado na busca."""
        return self.get_reference_context(text_chunk, active_base, extra_text)[0]
