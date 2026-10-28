# -*- coding: utf-8 -*-
"""Perfis linguisticos por idioma (origem e destino).

Camada fina e universal para a logica de personagens. Ver
_build_characters_directive() em knowledge_base.py para o uso.
Zero dependencias, zero chamadas de rede.
"""
import re
import unicodedata


def _key_norm(value) -> str:
    """Normaliza nome de idioma: minusculas, sem acento."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.casefold().strip()


# ---------------------------------------------------------------------------
# ORIGEM: verbos de fala (para atribuicao de falante no texto original)
# ---------------------------------------------------------------------------

_SOURCE_DICENDI = {
    "portugues": [
        "disse", "diz", "dizem", "falou", "fala", "falam", "perguntou",
        "pergunta", "perguntam", "respondeu", "responde", "respondem",
        "gritou", "grita", "gritam", "sussurrou", "sussurra", "murmurou",
        "murmura", "exclamou", "exclama", "ordenou", "ordena", "pediu",
        "pede", "pedem", "implorou", "implora", "advertiu", "adverte",
        "declarou", "declara", "afirmou", "afirma", "comentou", "comenta",
        "replicou", "replica", "retrucou", "retruca", "concordou",
        "concorda", "negou", "nega", "riu", "ri", "riem", "chorou",
        "chora", "ironizou", "ironiza", "provocou", "provoca", "chamou",
        "chama", "narrou", "narra", "solucou", "soluca", "rosnou",
        "rosna", "gemeu", "geme",
    ],
    "ingles": [
        "said", "says", "say", "told", "tells", "tell", "asked", "asks",
        "ask", "replied", "replies", "reply", "answered", "answers",
        "answer", "shouted", "shouts", "shout", "whispered", "whispers",
        "whisper", "murmured", "murmurs", "murmur", "exclaimed",
        "exclaims", "ordered", "orders", "begged", "begs", "warned",
        "warns", "declared", "declares", "stated", "states", "commented",
        "comments", "retorted", "retorts", "agreed", "agrees", "denied",
        "denies", "laughed", "laughs", "cried", "cries", "sneered",
        "sneers", "teased", "teases", "called", "calls", "narrated",
        "narrates", "growled", "growls", "moaned", "moans", "sobbed",
        "sobs",
    ],
    "espanhol": [
        "dijo", "dice", "dicen", "pregunto", "pregunta", "respondio",
        "responde", "grito", "grita", "susurro", "susurra", "murmuro",
        "exclamo", "ordeno", "pidio", "suplico", "advirtio", "declaro",
        "afirmo", "comento", "replico", "rio", "lloro", "llamo",
        "narro",
    ],
    "japones": [
        "言った", "言う", "言い", "話した", "話す", "尋ねた", "尋ねる",
        "聞いた", "聞く", "答えた", "答える", "叫んだ", "叫ぶ",
        "囁いた", "囁く", "呟いた", "呟く", "怒鳴った", "怒鳴る",
        "笑った", "笑う", "泣いた", "泣く", "言い返した", "頷いた",
    ],
    "chines": [
        "说", "说道", "说着", "问", "问道", "问着", "答", "答道",
        "回答", "笑", "笑道", "笑着说", "喊", "喊道", "叫道",
        "低声说", "轻声说", "大声说", "冷笑", "叹道", "叹气说",
        "怒道", "惊呼", "喃喃道", "嘟囔", "shuo", "wen", "da",
    ],
    "coreano": [
        "말했다", "말한다", "말하였다", "말하였다고", "물었다", "묻는다",
        "대답했다", "답했다", "소리쳤다", "외쳤다", "속삭였다", "속삭인다",
        "웃었다", "웃으며", "울었다", "화냈다", "고개를 끄덕였다",
        "말했어", "물었어", "대답했어",
    ],
}

_SOURCE_ALIASES = {
    "portugues": "portugues", "portugues do brasil": "portugues",
    "portuguese": "portugues", "pt": "portugues", "pt-br": "portugues",
    "ingles": "ingles", "english": "ingles", "en": "ingles",
    "espanhol": "espanhol", "spanish": "espanhol", "es": "espanhol",
    "espanol": "espanhol",
    "japones": "japones", "japanese": "japones", "ja": "japones",
    "nihongo": "japones",
    "chines": "chines", "chinese": "chines", "zh": "chines",
    "mandarim": "chines", "mandarin": "chines",
    "coreano": "coreano", "korean": "coreano", "ko": "coreano",
}


def get_dicendi(source_language: str):
    """Lista de verbos de fala do idioma de ORIGEM ([] = generico)."""
    key = _SOURCE_ALIASES.get(_key_norm(source_language), "")
    return list(_SOURCE_DICENDI.get(key, []))



# ---------------------------------------------------------------------------
# DESTINO: perfil por idioma-alvo (aspas + regra de pessoa + pronomes)
# ---------------------------------------------------------------------------

_TARGET_PROFILES = {
    "japones": {
        "quotes": "「」",
        "quotes_inner": "『』",
        "pronoun_rule": (
            "o pronome indica como o personagem fala DE SI MESMO em primeira "
            "pessoa e so vale DENTRO das falas (「」); em 『』 (fala dentro de "
            "fala) vale igual. Na narracao e nos marcadores de fala use SEMPRE "
            "o nome do dicionario, NUNCA o pronome. Quando um personagem fala "
            "DE OUTRO, use o nome dele ou OMITA o sujeito (japones omite a 3a "
            "pessoa); proibido usar kare/kanojo como 'he/she' generico. "
            "ATENCAO: o pronome NAO identifica ninguem (personagens diferentes "
            "podem usar o mesmo pronome) — so o nome identifica."
        ),
        "pronouns": [
            "俺", "私", "僕", "あたし", "わたし", "わし", "ウチ", "うち",
            "自分", "儂", "お前", "貴様",
            "ore", "watashi", "boku", "atashi", "washi", "uchi",
            "jibun", "omae",
        ],
    },
    "ingles": {
        "quotes": '" "',
        "quotes_inner": "' '",
        "pronoun_rule": (
            "o pronome indica como o personagem fala DE SI MESMO em primeira "
            "pessoa: use I (sempre maiusculo, nunca omitido). A 3a pessoa e "
            "OBRIGATORIA e explicita: he/she/they com o nome na primeira "
            "mencao da cena — proibido omitir o sujeito. Nos marcadores de "
            "fala (\"...\" said X / X said) use SEMPRE o nome, nunca o pronome "
            "no lugar do nome. Mantenha o MESMO pronome para o mesmo referente "
            "no trecho (sem alternar he/they para a mesma pessoa). Registro "
            "de formalidade vem da ficha (tom), nao de particula."
        ),
        "pronouns": [
            "i", "me", "my", "mine", "he", "him", "his", "she", "her",
            "hers", "they", "them", "their", "it",
        ],
    },
    "espanhol": {
        "quotes": "«» / \" \"",
        "quotes_inner": "' '",
        "pronoun_rule": (
            "o pronome indica como o personagem fala DE SI MESMO: use o "
            "pronome da ficha quando ele falar de si dentro das aspas. O "
            "espanhol admite omitir o sujeito quando o verbo basta; use "
            "el/ella so para contraste ou enfase. Na narracao e nos "
            "marcadores (dijo X) use SEMPRE o nome do dicionario, nunca o "
            "pronome no lugar do nome."
        ),
        "pronouns": ["yo", "me", "mi", "el", "ella", "usted", "ellos", "ellas"],
    },
    "russo": {
        "quotes": "«»",
        "quotes_inner": ",, \"",
        "pronoun_rule": (
            "o pronome indica como o personagem fala DE SI MESMO dentro das "
            "aspas. A 3a pessoa e explicita — nao omita o sujeito. Na "
            "narracao e nos marcadores use SEMPRE o nome do dicionario, "
            "nunca o pronome no lugar do nome."
        ),
        "pronouns": ["я", "меня", "мой", "он", "она", "они", "его", "ее", "их"],
    },
    "chines": {
        "quotes": "“”",
        "quotes_inner": "‘’",
        "pronoun_rule": (
            "o pronome indica como o personagem fala DE SI MESMO em primeira "
            "pessoa: use 我 (informal) ou o pronome da ficha dentro das aspas. "
            "O chines NAO tem conjugacao nem distincao he/she NA FALA (ta e "
            "igual falado) — diferencie so pelo caractere (他/她/它). OMITA o "
            "sujeito quando estiver claro pelo contexto (pro-drop natural); "
            "NUNCA force pronome explicito estilo ingles. Na narracao e nos "
            "marcadores use SEMPRE o nome do dicionario, nunca o pronome no "
            "lugar do nome. Use caracteres SIMPLIFICADOS."
        ),
        "pronouns": [
            "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们",
            "它们", "自己", "大家", "wo", "ni", "ta", "women", "nimen",
        ],
    },
    "coreano": {
        "quotes": "“”",
        "quotes_inner": "‘’",
        "pronoun_rule": (
            "o pronome indica como o personagem fala DE SI MESMO: use 나 "
            "(informal) ou 저 (humilde/formal) conforme a ficha, dentro das "
            "aspas. O coreano OMITE o sujeito com frequencia (pro-drop "
            "forte) — nao force pronome explicito. Mantenha o NIVEL DE FALA "
            "do personagem (formal 합쇼체/해요체 vs informal 해체) consistente "
            "no trecho: proibido misturar ~합니다 com ~해 na mesma pessoa. "
            "Na narracao e nos marcadores use SEMPRE o nome do dicionario, "
            "nunca o pronome no lugar do nome."
        ),
        "pronouns": [
            "나", "저", "너", "당신", "그", "그녀", "우리", "저희",
            "그들", "자신", "na", "jeo", "neo", "geu", "uri",
        ],
    },
    "default": {
        "quotes": "as aspas do idioma-alvo",
        "quotes_inner": "as aspas internas do idioma-alvo",
        "pronoun_rule": (
            "o pronome indica como o personagem fala DE SI MESMO em primeira "
            "pessoa e so vale quando ele fala de si DENTRO das falas. Na "
            "narracao e nos marcadores de fala use SEMPRE o nome do "
            "dicionario, nunca o pronome no lugar do nome."
        ),
        "pronouns": [],
    },
}

_TARGET_ALIASES = {
    "japones": "japones", "japanese": "japones", "ja": "japones",
    "nihongo": "japones",
    "ingles": "ingles", "english": "ingles", "en": "ingles",
    "espanhol": "espanhol", "spanish": "espanhol", "es": "espanhol",
    "espanol": "espanhol",
    "russo": "russo", "russian": "russo", "ru": "russo",
    "chines": "chines", "chinese": "chines", "zh": "chines",
    "chines simplificado": "chines", "mandarim": "chines",
    "mandarin": "chines", "simplified chinese": "chines",
    "coreano": "coreano", "korean": "coreano", "ko": "coreano",
    "portugues": "espanhol", "portugues do brasil": "espanhol",
    "portuguese": "espanhol",
}




# ---------------------------------------------------------------------------
# Reconhecimento de coluna/celula de pronome (qualquer lingua)
# ---------------------------------------------------------------------------

_PRONOUN_HEADER_TOKENS = [
    "pronome", "pronoun", "pronombre", "pronom", "pronomen",
    "mestoimenie", "1a pessoa", "primeira pessoa", "first person",
    "como fala", "voz", "autoreferencia", "auto referencia",
]

_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]+")


def is_pronoun_header(header: str) -> bool:
    """True se o cabecalho parece indicar coluna de pronome (qualquer lingua)."""
    h = _key_norm(header)
    return any(tok in h for tok in _PRONOUN_HEADER_TOKENS)


def _all_pronoun_tokens():
    toks = set()
    for prof in _TARGET_PROFILES.values():
        for p in prof.get("pronouns", []):
            toks.add(_key_norm(p))
    return toks


_ALL_PRONOUN_TOKENS = None


def looks_like_pronoun_cell(cell) -> bool:
    """True se o conteudo da celula parece pronome.

    CJK = quase certeza (nome de personagem em planilha PT/EN nao tem kana).
    Sem CJK: vale se algum pedaco (separado por ; , / ( ) -) for pronome
    conhecido de algum perfil.
    """
    if cell is None:
        return False
    global _ALL_PRONOUN_TOKENS
    if _ALL_PRONOUN_TOKENS is None:
        _ALL_PRONOUN_TOKENS = _all_pronoun_tokens()
    s = str(cell).strip()
    if not s or len(s) > 60:
        return False
    if _CJK.search(s):
        return True
    parts = [p.strip().casefold() for p in re.split(r"[;,/|()\-–—]", s) if p.strip()]
    return any(p in _ALL_PRONOUN_TOKENS for p in parts)


def extract_pronoun(cell, target_language: str = "") -> str:
    """Extrai a FORMA FINAL de emissao do pronome de uma celula livre.

    - Com trecho CJK: devolve o 1o trecho ('Atashi (あたし)' -> 'あたし').
    - Sem CJK: devolve a cabeca compacta ('she/her'; 'Watakushi (formal)'
      -> 'Watakushi'). Celula vazia/longa demais -> ''.
    """
    if cell is None:
        return ""
    s = " ".join(str(cell).split())
    if not s:
        return ""
    m = _CJK.search(s)
    if m:
        return m.group(0)
    m2 = re.match(r"^([A-Za-zÀ-ÿ'/\-·]+)", s)
    if m2:
        head = m2.group(1).strip("/-·")
        tail = s[m2.end():].strip()
        if len(head) <= 24 and (not tail or tail.startswith("(")):
            return head
    return s if len(s) <= 24 else ""

def get_target_profile(target_language: str) -> dict:
    """Perfil do idioma de DESTINO (sempre existe: cai em `default`)."""
    key = _TARGET_ALIASES.get(_key_norm(target_language), "")
    return _TARGET_PROFILES.get(key, _TARGET_PROFILES["default"])


def target_key(target_language: str) -> str:
    """Chave canonica do destino ('japones', 'ingles', ... ou 'default')."""
    key = _TARGET_ALIASES.get(_key_norm(target_language), "")
    return key if key in _TARGET_PROFILES else "default"


def is_first_person(pov_mode: str) -> bool:
    """True se o modo POV indica narracao em 1a pessoa (qualquer acento)."""
    return bool(pov_mode and "primeira" in _key_norm(pov_mode))


def pov_narration_rule(target_language: str, narrator_name: str = "",
                       narrator_pronoun: str = "") -> str:
    """Excecao de NARRACAO em 1a pessoa (complementa a regra dos dialogos).

    A regra base dos dialogos (pronome de quem fala de si dentro das aspas)
    continua valendo sempre. Esta excecao so cobre a narracao FORA das aspas:
    quando o narrador fala de si, usa o PRONOME (nunca o proprio nome).
    Devolve '' se algum dado essencial faltar? Nao: com nome vazio usa texto
    generico ('quem narra'); com pronome vazio aponta para a ficha.
    """
    tkey = target_key(target_language)
    name_txt = "'%s'" % narrator_name.strip() if (narrator_name or "").strip() else "quem narra"
    has_name = bool((narrator_name or "").strip())
    pron_txt = ("'%s'" % narrator_pronoun.strip()) if (narrator_pronoun or "").strip() else "o pronome da ficha do narrador"
    if tkey == "japones":
        self_txt = ("quando %s fala DE SI na narracao (fora de 「」, ex. 'eu estava "
                    "na chuva'), use %s (ou omita o sujeito quando natural em "
                    "japones); NUNCA " % (name_txt, pron_txt))
        if has_name:
            self_txt += "o proprio nome %s para falar de si. " % name_txt
        else:
            self_txt += "o proprio nome do narrador para falar de si. "
        return ("EXCECAO — NARRACAO EM 1A PESSOA: o texto e narrado por %s. "
                "%sPara os outros personagens na narracao, continuam o nome ou "
                "a omissao. Os dialogos em 「」 seguem a regra normal."
                % (name_txt, self_txt))
    if tkey == "ingles":
        self_txt = ("quando %s fala DE SI na narracao (fora das aspas, ex. 'I was "
                    "in the rain'), use %s (sempre explicito, nunca omitido); NUNCA " % (name_txt, pron_txt))
        if has_name:
            self_txt += "o proprio nome %s para falar de si. " % name_txt
        else:
            self_txt += "o proprio nome do narrador para falar de si. "
        return ("EXCECAO — NARRACAO EM 1A PESSOA: o texto e narrado por %s. "
                "%sPara os outros personagens na narracao, continuam o nome + "
                "he/she/they explicitos. Os dialogos entre aspas seguem a regra normal."
                % (name_txt, self_txt))
    if tkey == "espanhol":
        return ("EXCECAO — NARRACAO EM 1A PESSOA: o texto e narrado por %s. "
                "Quando %s fala DE SI na narracao (fora das aspas), use %s "
                "(ou omita o sujeito quando o verbo bastar); NUNCA o proprio nome "
                "para falar de si. Os dialogos seguem a regra normal."
                % (name_txt, name_txt, pron_txt))
    if tkey == "russo":
        return ("EXCECAO — NARRACAO EM 1A PESSOA: o texto e narrado por %s. "
                "Quando %s fala DE SI na narracao (fora das aspas), use %s "
                "(sujeito explicito); NUNCA o proprio nome para falar de si. "
                "Os dialogos seguem a regra normal."
                % (name_txt, name_txt, pron_txt))
    if tkey == "chines":
        return ("EXCECAO — NARRACAO EM 1A PESSOA: o texto e narrado por %s. "
                "Quando %s fala DE SI na narracao (fora das aspas), use %s "
                "em caracteres SIMPLIFICADOS (ou omita o sujeito quando "
                "natural em chines); NUNCA o proprio nome para falar de si. "
                "Os dialogos entre aspas seguem a regra normal."
                % (name_txt, name_txt, pron_txt))
    if tkey == "coreano":
        return ("EXCECAO — NARRACAO EM 1A PESSOA: o texto e narrado por %s. "
                "Quando %s fala DE SI na narracao (fora das aspas), use %s "
                "(ou omita o sujeito, comum em coreano) mantendo o mesmo "
                "NIVEL DE FALA do personagem; NUNCA o proprio nome para "
                "falar de si. Os dialogos entre aspas seguem a regra normal."
                % (name_txt, name_txt, pron_txt))
    return ("EXCECAO — NARRACAO EM 1A PESSOA: o texto e narrado por %s. "
            "Quando %s fala DE SI na narracao (fora das falas), use %s; NUNCA "
            "o proprio nome para falar de si. Os dialogos seguem a regra normal."
            % (name_txt, name_txt, pron_txt))
