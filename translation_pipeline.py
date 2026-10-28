# -*- coding: utf-8 -*-
"""Pipeline multi-agente de tradução literária com RAG híbrido (banco de frases, glossário e personagens).

Modulo extraído de gui.py (arquivo original monolítico) durante a modularização.
"""
from typing import Any, Dict, List, Optional

from app_config import t
from chunking import split_into_chunks, tail_paragraphs
from consistency import apply_pronoun_fixes, check_pronouns
from knowledge_base import CharactersManager, GlossaryManager, InternalRAGManager
from llm_client import LLMProviderFactory
from models import AgentConfig, PipelineConfig, PipelineResult
from token_usage import AgentBudget, TokenLimitExceeded, TokenUsageManager, estimate_tokens, parse_usage

# True = mostra na aba Logs o texto que CADA agente devolveu (útil para achar em qual etapa um erro entrou).
LOG_AGENT_OUTPUTS = True


def _count_paragraphs(text) -> int:
    """Número de linhas não vazias (parágrafos) de um texto."""
    return sum(1 for ln in (text or "").splitlines() if ln.strip())

class LiteraryTranslationPipeline:
    def __init__(self, agents: List[AgentConfig], pipeline_config: Optional[PipelineConfig] = None, active_rag_base: str = "Banco_Frases_Padrao", usage_manager: Optional[TokenUsageManager] = None, ui_lang: str = "Português"):
        self.agents = agents
        self.config = pipeline_config or PipelineConfig()
        self.rag_manager = InternalRAGManager()
        self.glossary_manager = GlossaryManager(db_path=self.config.glossary_db_path)
        self.characters_manager = CharactersManager(db_path=self.config.characters_db_path)
        self.active_rag_base = active_rag_base
        self.usage_manager = usage_manager or TokenUsageManager()
        self.ui_lang = ui_lang or "Português"

    def _sw_preset(self, agent_cfg):
        """Preset do modo janela pequena deste agente, ou None (desmarcado = nada muda)."""
        if not getattr(agent_cfg, "small_window", False):
            return None
        from small_window import compute_preset
        return compute_preset(int(getattr(agent_cfg, "window_tokens", 0) or 0), [agent_cfg],
                              self.config.source_language, self.config.target_language)

    @staticmethod
    def _budget_of(agent_cfg: AgentConfig) -> AgentBudget:
        return AgentBudget(
            mode=getattr(agent_cfg, "budget_mode", "unlimited") or "unlimited",
            limit=int(getattr(agent_cfg, "token_limit", 0) or 0),
            scope=getattr(agent_cfg, "budget_scope", "per_execution") or "per_execution",
            action=getattr(agent_cfg, "budget_action", "stop") or "stop",
        )

    @staticmethod
    def _clean_keys(raw) -> List[str]:
        """Normaliza lista de chaves (remove vazias/duplicadas, preserva ordem)."""
        out: List[str] = []
        if isinstance(raw, str):
            raw = [raw]
        for k in (raw or []):
            ks = (k or "").strip() if isinstance(k, str) else ""
            if ks and ks not in out:
                out.append(ks)
        return out

    def _global_keys(self, provider: str) -> List[str]:
        """Chaves globais do provedor (config). Aceita str ou lista."""
        try:
            from app_config import load_persistent_config
            cfg = load_persistent_config()
            val = (cfg.get("api_keys", {}) or {}).get((provider or "").lower(), "")
        except Exception:
            val = ""
        if isinstance(val, list):
            return self._clean_keys(val)
        return self._clean_keys([val] if val else [])

    def _agent_keys(self, agent_cfg: AgentConfig, provider: str, is_fb: bool) -> List[str]:
        """Chaves efetivas: lista do agente ou global. Padrao primeiro.

        Reserva: se o agente definiu modelo reserva mas NAO definiu chaves
        reserva, usa as chaves do PRINCIPAL (mesmo provedor em geral) —
        nunca puxa a global do provedor reserva por engano.
        So usa a global do provedor reserva quando o agente nao tem
        nenhuma chave propria (nem principal nem reserva).
        """
        local_main = self._clean_keys(getattr(agent_cfg, "api_keys", []) or [])
        local_fb = self._clean_keys(getattr(agent_cfg, "fallback_api_keys", []) or [])
        if is_fb:
            local = local_fb if local_fb else local_main
            idx = int(getattr(agent_cfg, "fallback_default_key_index", 0) or 0)
            pool = local if local else self._global_keys(provider)
        else:
            idx = int(getattr(agent_cfg, "default_key_index", 0) or 0)
            pool = local_main if local_main else self._global_keys(provider)
        if not pool:
            return []
        idx = max(0, min(idx, len(pool) - 1))
        return [pool[idx]] + [k for j, k in enumerate(pool) if j != idx]

    def _stages_for(self, agent_cfg, main_keys, fb_keys, has_reserve):
        """Ordem das tentativas conforme fallback_strategy do agente."""
        strategy = (getattr(agent_cfg, "fallback_strategy", "model_first") or "model_first").strip()
        if strategy not in ("model_first", "key_first", "keys_only", "model_only"):
            strategy = "model_first"
        main_p = (agent_cfg.provider or "").strip()
        main_m = (agent_cfg.model or "").strip()
        fb_m = (getattr(agent_cfg, "fallback_model", "") or "").strip()
        fb_p = (getattr(agent_cfg, "fallback_provider", "") or "").strip() or main_p
        if strategy == "keys_only" or not has_reserve:
            yield ("main", main_p, main_m, main_keys)
            return
        if strategy == "model_only":
            yield ("main", main_p, main_m, main_keys[:1])
            yield ("reserve", fb_p, fb_m, fb_keys[:1])
            return
        if strategy == "key_first":
            yield ("main", main_p, main_m, main_keys)
            yield ("reserve", fb_p, fb_m, fb_keys)
            return
        yield ("main", main_p, main_m, main_keys[:1])
        yield ("reserve", fb_p, fb_m, fb_keys[:1])
        if len(main_keys) > 1:
            yield ("main-keys", main_p, main_m, main_keys[1:])
        if len(fb_keys) > 1:
            yield ("reserve-keys", fb_p, fb_m, fb_keys[1:])

    @staticmethod
    def _call_opts(agent_cfg) -> dict:
        """Opções de chamada escolhidas pelo usuário no agente (nada é imposto pelo programa)."""
        _to = getattr(agent_cfg, "timeout_s", 300)
        return dict(
            reasoning_effort=getattr(agent_cfg, "reasoning_effort", "") or "",
            retry_on_truncation=bool(getattr(agent_cfg, "truncation_retry", False)),
            timeout=300 if _to is None else int(_to),
        )

    def _call_with_fallback(self, agent_cfg, log, ctx_prompt: str, user_payload: str):
        """Tenta a cascata; 429/cota roda as chaves; outro erro de API pula p/ reserva (se houver)."""
        main_p = (agent_cfg.provider or "").strip()
        fb_m = (getattr(agent_cfg, "fallback_model", "") or "").strip()
        fb_p = (getattr(agent_cfg, "fallback_provider", "") or "").strip() or main_p
        has_reserve = bool(fb_m)
        main_keys = self._agent_keys(agent_cfg, main_p, False)
        fb_keys = self._agent_keys(agent_cfg, fb_p, True) if has_reserve else []
        if not main_keys and main_p.lower() != "ollama":
            main_keys = [""]
        if has_reserve and not fb_keys and fb_p.lower() != "ollama":
            fb_keys = [""]
        last_err = None
        for stage, prov, model, keys in self._stages_for(agent_cfg, main_keys, fb_keys, has_reserve):
            for key in keys:
                try:
                    res = LLMProviderFactory.call_llm(
                        provider=prov, model=model,
                        system_prompt=ctx_prompt, user_prompt=user_payload,
                        temperature=agent_cfg.temperature, max_tokens=agent_cfg.max_tokens,
                        api_key=key, **self._call_opts(agent_cfg))
                    pool = main_keys if (prov == main_p and model == (agent_cfg.model or "").strip()) else fb_keys
                    try:
                        gidx = pool.index(key)
                    except ValueError:
                        gidx = 0
                    return res[0], res[1], res[2], prov, model, gidx, (stage != "main")
                except Exception as e:
                    if not LLMProviderFactory.is_rate_limit_error(e):
                        # Qualquer outro erro (401/404/500/timeout/conexão/sem chave):
                        # com reserva e ainda no principal, pula para a reserva.
                        if has_reserve and stage in ("main", "main-keys"):
                            last_err = e
                            try:
                                log(t("log_api_error", self.ui_lang).format(
                                    prov=prov, model=model, err=str(e)[:160]))
                            except Exception:
                                pass
                            break
                        raise
                    last_err = e
                    try:
                        log(t("log_rate_limit", self.ui_lang).format(
                            prov=prov, model=model,
                            key=LLMProviderFactory.mask_key(key), err=str(e)[:160]))
                    except Exception:
                        pass
                    continue
        raise last_err if last_err is not None else RuntimeError("Todas as chaves/modelos retornaram 429/cota.")

    def sync_glossary_from_excel(self, excel_path: str) -> str:
        return self.glossary_manager.reset_and_sync_from_excel(excel_path)

    def sync_characters_from_excel(self, excel_path: str) -> str:
        return self.characters_manager.reset_and_sync_from_excel(excel_path)

    @staticmethod
    def _log_pron(_r, log, _L):
        """Registra no log o resultado de check_pronouns (falas + narração)."""
        if _r.get("reason") == "count_mismatch":
            log(t("log_pron_count_mismatch", _L).format(src=_r["src_dialogues"], tgt=_r["tgt_dialogues"]))
        if _r.get("status") != "ok":
            return
        for _it in _r["issues"]:
            if _it.get("kind") == "narration":
                log(t("log_pron_narr_mismatch", _L).format(
                    n=_it["n"], who=_it["who"], exp=_it["expected"], found=_it["found"],
                    snip=_it["snippet"].replace("&#x20;", "").strip()[:50]))
            else:
                log(t("log_pron_mismatch", _L).format(
                    n=_it["n"], who=_it["who"],
                    inf=t("log_pron_inferred", _L) if _it["inferred"] else "",
                    exp=_it["expected"], found=_it["found"],
                    snip=_it["snippet"].replace("&#x20;", "").strip()[:50]))
        if _r["issues"]:
            log(t("log_pron_summary", _L).format(bad=len(_r["issues"]), n=_r["checked"] + _r.get("narr_checked", 0)))
        else:
            if _r["checked"]:
                log(t("log_pron_ok", _L).format(n=_r["checked"]))
            if _r.get("narr_checked"):
                log(t("log_pron_ok_narr", _L).format(m=_r["narr_checked"]))

    def _run_one(self, source_text: str, log, ctx=None, chunk_no: int = 0, rag_cache=None):
        """Roda a cadeia de agentes em UM trecho (ou no texto inteiro, se não houver divisão).

        `ctx` = {"orig", "trans"}: últimos parágrafos do trecho anterior (somente leitura).
        `chunk_no` = 0 sem divisão; 1..N com divisão. Devolve (texto_final, historico)."""
        _L = self.ui_lang or "Português"
        ctx = ctx or {}
        # Glossário/personagens procuram nomes também no contexto anterior (quem já falava na cena).
        match_text = (ctx.get("orig", "") + "\n\n" + source_text) if ctx.get("orig") else source_text
        if rag_cache is None:
            rag_cache = {}
        # 2. Dicionário de Termos (Glossário)
        glossary_context = self.glossary_manager.get_relevant_glossary(match_text)
        log(t("log_glossary", _L))

        # 3. Fichas de Personagens (bloco universal em 2 níveis: elenco +
        # pronomes para todos; ficha integral só de quem tem voz na cena)
        characters_context = self.characters_manager.get_relevant_characters(
            match_text,
            source_language=self.config.source_language,
            target_language=self.config.target_language,
            pov_mode=self.config.pov_mode,
            narrator_name=self.config.narrator_name,
        )
        log(t("log_chars", _L))
        
        current_text = source_text
        history = []
        ctx_block = ""
        if ctx and (ctx.get("orig") or ctx.get("trans")):
            ctx_block = (
                "=== CONTEXTO ANTERIOR (SOMENTE LEITURA — NÃO traduza, NÃO repita e NÃO devolva) ===\n"
                + (f"Original:\n{ctx['orig']}\n\n" if ctx.get("orig") else "")
                + (f"Tradução já feita:\n{ctx['trans']}\n\n" if ctx.get("trans") else "")
            )
        _pron_tbl = None  # tabela de pronomes (lida 1x, usada na checagem após cada agente)
        for i, agent_cfg in enumerate(self.agents):
            log(t("log_agent", _L).format(i=i+1, name=agent_cfg.name))
            _mt = int(getattr(agent_cfg, "max_tokens", 0) or 0)
            _rs = getattr(agent_cfg, "reasoning_effort", "") or ""
            log(f"   Model: {agent_cfg.model} | Provider: {agent_cfg.provider} | "
                f"Max output: {_mt if _mt > 0 else 'no limit'}" + (f" | Reasoning: {_rs}" if _rs else ""))
            
            _sw = self._sw_preset(agent_cfg)
            rag_context = ""
            if getattr(agent_cfg, "use_rag", True):
                try:
                    _extra = current_text if current_text != source_text else ""
                    rag_context, _n_rag = self.rag_manager.get_reference_context(
                        source_text, self.active_rag_base, extra_text=_extra, cache=rag_cache,
                        max_chars_cap=(_sw["rag_max_chars"] if _sw else 0)
                    )
                except Exception as _exc:  # RAG nunca deve derrubar a tradução
                    rag_context, _n_rag = "", 0
                    log(f"   [RAG] {_exc}")
                log(t("log_rag_agent", _L).format(n=_n_rag, base=self.active_rag_base))
            else:
                log(t("log_rag_agent_off", _L))

            contextualized_prompt = (
                f"{agent_cfg.system_prompt}\n\n"
                + (f"{rag_context}\n\n" if rag_context else "")
                + f"{glossary_context}\n\n"
                f"{characters_context}\n\n"
                f"====================================================\n"
                f"IMPORTANTE: O idioma de destino obrigatório para esta tradução é: {self.config.target_language}."
            )
            if chunk_no > 1:
                contextualized_prompt += (
                    "\nEste texto é a CONTINUAÇÃO de um capítulo traduzido em trechos: não começa pelo título. "
                    "Não invente título, subtítulo nem abertura. "
                    + ("O bloco CONTEXTO ANTERIOR serve só para consulta (nomes, quem fala, tom): "
                       "devolva SOMENTE o trecho marcado, sem o contexto e sem os títulos dos blocos."
                       if ctx_block else "")
                )
            if self.config.pov_mode and "Primeira" in self.config.pov_mode and self.config.narrator_name:
                contextualized_prompt += (
                    f"\nEste texto é narrado em PRIMEIRA PESSOA pelo personagem: '{self.config.narrator_name}'."
                )

            step_input = current_text
            # --- Orçamento de tokens (por agente) ---
            budget = self._budget_of(agent_cfg)
            scope = budget.scope
            agent_key = (agent_cfg.name or "").strip() or f"agente-{i+1}"
            if budget.is_limited():
                used = self.usage_manager.get_used(agent_key, scope)
                scope_txt = "por execucao" if scope == "per_execution" else "por dia"
                log(f"   [Orcamento] {used}/{budget.limit} tokens usados ({scope_txt}).")
            _first_step = (i == 0 or current_text == source_text)
            _with_orig = bool(getattr(agent_cfg, "send_original", True)) and not _sw
            if _first_step:
                user_payload = (ctx_block + "=== TRECHO A TRADUZIR ===\n" + step_input) if ctx_block else step_input
            elif _with_orig:
                user_payload = (
                    ctx_block
                    + "=== TEXTO ORIGINAL DE REFERÊNCIA (ÂNCORA OBRIGATÓRIA — não altere o sentido, "
                    "a voz nem os fatos do original) ===\n"
                    f"{source_text}\n\n"
                    "=== VERSÃO ANTERIOR A SER PROCESSADA NESTA ETAPA ===\n"
                    f"{step_input}"
                )
            else:
                # Opção do agente: NÃO reenviar o original (economiza tokens em IA gratuita).
                user_payload = (ctx_block + "=== VERSÃO A SER PROCESSADA NESTA ETAPA ===\n" + step_input) if ctx_block else step_input
            # reserva estimada = entrada + saida maxima permitida
            needed_est = (
                estimate_tokens(contextualized_prompt)
                + estimate_tokens(user_payload)
                + int(agent_cfg.max_tokens or 0)
            )
            if _sw:
                _kb = estimate_tokens(glossary_context) + estimate_tokens(characters_context)
                _call = (estimate_tokens(contextualized_prompt) + estimate_tokens(user_payload)
                         + estimate_tokens(step_input))  # + saída estimada ~ tamanho do trecho
                _win = _sw["window_tokens"]
                if _kb > _win * 0.6:
                    log(t("log_window_kb_big", _L).format(i=i + 1, name=agent_cfg.name, kb=_kb, win=_win))
                elif _call > _win:
                    log(t("log_window_over", _L).format(i=i + 1, name=agent_cfg.name, need=_call, win=_win))
            _fallback_used = False
            try:
                self.usage_manager.check(agent_key, agent_cfg.name, budget, needed_est)
            except TokenLimitExceeded as exc:
                _action = budget.action or "stop"
                if _action == "skip":
                    log(t("log_budget_skip", _L).format(err=exc))
                    history.append({
                        "step": i + 1,
                        "agent_name": agent_cfg.name,
                        "model": agent_cfg.model,
                        "provider": agent_cfg.provider,
                        "target_language": self.config.target_language,
                        "input": step_input,
                        "output": step_input,
                        "skipped": True,
                        "skip_reason": str(exc),
                        "chunk": chunk_no,
                    })
                    continue
                fb_model = (getattr(agent_cfg, "fallback_model", "") or "").strip()
                if _action == "fallback" and fb_model:
                    _fallback_used = True
                    log(t("log_budget_fallback", _L).format(err=exc))
                else:
                    log(t("log_budget_stop", _L).format(err=exc))
                    raise
            _eff_model = agent_cfg.model
            _eff_provider = agent_cfg.provider
            _is_fallback = False
            _key_idx = 0
            if _fallback_used:
                # Orcamento estourou: vai direto p/ reserva com a chave padrao dela.
                _eff_model = agent_cfg.fallback_model.strip()
                _eff_provider = (getattr(agent_cfg, "fallback_provider", "") or "").strip() or agent_cfg.provider
                _is_fallback = True
                log(t("log_budget_reserve", _L).format(prov=_eff_provider, model=_eff_model))
                _fb_keys = self._agent_keys(agent_cfg, _eff_provider, True)
                _def = int(getattr(agent_cfg, "fallback_default_key_index", 0) or 0)
                _key0 = _fb_keys[_def] if _fb_keys and 0 <= _def < len(_fb_keys) else (_fb_keys[0] if _fb_keys else "")
                call_result = LLMProviderFactory.call_llm(
                    provider=_eff_provider,
                    model=_eff_model,
                    system_prompt=contextualized_prompt,
                    user_prompt=user_payload,
                    temperature=agent_cfg.temperature,
                    max_tokens=agent_cfg.max_tokens,
                    api_key=_key0, **self._call_opts(agent_cfg))
                if isinstance(call_result, tuple) and len(call_result) == 3:
                    output_text, provider_log, report = call_result
                else:
                    output_text, provider_log = call_result[0], call_result[1]
                    report = parse_usage(None, _eff_provider, contextualized_prompt, user_payload, output_text)
            else:
                # Caminho normal: cascata 429/cota (chaves + modelo reserva).
                output_text, provider_log, report, _eff_provider, _eff_model, _key_idx, _is_fallback = \
                    self._call_with_fallback(agent_cfg, log, contextualized_prompt, user_payload)
                if _is_fallback:
                    log(t("log_fallback_using", _L).format(prov=_eff_provider, model=_eff_model, n=_key_idx + 1))
            log(provider_log)
            self.usage_manager.consume_detailed(agent_key, scope, (_eff_provider or "").lower(), report)
            log(t("log_tokens_line", _L).format(inp=report.input_tokens, out=report.output_tokens,
                tot=report.total_tokens, src=report.label()))
            if budget.is_limited():
                used_now = self.usage_manager.get_used(agent_key, scope)
                log(t("log_budget_total", _L).format(used=used_now, limit=budget.limit))
            history.append({
                "step": i + 1,
                "agent_name": agent_cfg.name,
                "model": _eff_model,
                "provider": _eff_provider,
                "target_language": self.config.target_language,
                "input": step_input,
                "output": output_text,
                "tokens_input": int(report.input_tokens or 0),
                "tokens_output": int(report.output_tokens or 0),
                "tokens_used": int(report.total_tokens or 0),
                "tokens_used_est": int(report.total_tokens or 0),
                "tokens_source": report.source,
                "fallback": _is_fallback,
                "key_index": _key_idx,
                "chunk": chunk_no,
            })
            
            # Avisos de integridade: o agente perdeu parágrafos (ex.: o título) ou deixou fala sem fechar?
            _n_in, _n_out = _count_paragraphs(step_input), _count_paragraphs(output_text)
            if _n_out < _n_in:
                log(t("log_paragraph_loss", _L).format(i=i + 1, name=agent_cfg.name, new=_n_out, old=_n_in))
            _b_open, _b_close = (output_text or "").count("「"), (output_text or "").count("」")
            if _b_open != _b_close:
                log(t("log_bracket_unbalanced", _L).format(i=i + 1, name=agent_cfg.name, open=_b_open, close=_b_close))
            if LOG_AGENT_OUTPUTS:
                log(t("log_agent_output", _L).format(i=i + 1, name=agent_cfg.name) + "\n" + (output_text or "") + "\n")

            # Pausa opcional APÓS este agente (0 = sem pausa). Entre o último e o fim, não pausa.
            _pause = int(getattr(agent_cfg, "pause_after_s", 0) or 0)
            if _pause > 0 and i < len(self.agents) - 1:
                log(t("log_pause_after", _L).format(s=_pause, name=agent_cfg.name))
                try:
                    import time as _time
                    _time.sleep(_pause)
                except Exception:
                    pass

            # Checagem de pronome após ESTE agente (sem LLM, só registra): mostra em que etapa o desvio
            # entrou ou foi corrigido. A correção automática continua só no final.
            try:
                if _pron_tbl is None:
                    _pron_tbl = self.characters_manager.get_pronoun_table(self.config.target_language)
                _rs = check_pronouns(source_text, output_text, _pron_tbl, self.config.source_language,
                                     self.config.target_language, self.config.pov_mode,
                                     self.config.narrator_name)
                if _rs["status"] == "ok":
                    _bad = _rs["issues"]
                    if _bad:
                        _det = "; ".join(
                            ("narr." if _it.get("kind") == "narration" else "fala") +
                            f" {str(_it['who'])[:14]}: {_it['expected']}→{_it['found']}" for _it in _bad[:4])
                        _w = {"Português": "divergência(s)", "Inglês": "mismatch(es)", "Espanhol": "divergencia(s)",
                              "Japonês": "件の不一致", "Russo": "расхождений"}.get(_L, "divergência(s)")
                        _res = f"{len(_bad)} {_w} — {_det}" + (" …" if len(_bad) > 4 else "")
                    else:
                        _res = {"Português": "sem divergência de pronome.", "Inglês": "no pronoun mismatch.",
                                "Espanhol": "sin divergencias de pronombre.", "Japonês": "一人称の不一致なし。",
                                "Russo": "расхождений нет."}.get(_L, "sem divergência de pronome.")
                    log(t("log_pron_step", _L).format(i=i + 1, name=agent_cfg.name, res=_res))
            except Exception:
                pass

            current_text = output_text

        # Checagem de pronome (sem LLM): falas + narração em 1a pessoa. Se `pronoun_autofix`, o programa
        # troca sozinho o pronome errado pelo da ficha (só onde é seguro) e confere de novo.
        try:
            _tbl = self.characters_manager.get_pronoun_table(self.config.target_language)
            _chk = lambda txt: check_pronouns(
                source_text, txt, _tbl, self.config.source_language, self.config.target_language,
                self.config.pov_mode, self.config.narrator_name)
            _r = _chk(current_text)
            self._log_pron(_r, log, _L)
            if _r["status"] == "ok" and _r["issues"] and getattr(self.config, "pronoun_autofix", True):
                _new, _nfix, _notes = apply_pronoun_fixes(current_text, _r["issues"])
                if _nfix:
                    current_text = _new
                    log(t("log_pron_autofix", _L).format(n=_nfix, detail="; ".join(_notes)[:300]))
                    _r2 = _chk(current_text)
                    log(t("log_pron_after", _L).format(
                        left=len(_r2["issues"]) if _r2["status"] == "ok" else "?"))
        except Exception as _exc:
            try:
                log(t("log_pron_error", _L).format(err=str(_exc)[:160]))
            except Exception:
                pass
        return current_text, history

    def run(self, source_text: str, log_callback=None) -> PipelineResult:
        _L = self.ui_lang or "Português"

        def log(msg):
            if log_callback:
                log_callback(msg + "\n")
            else:
                print(msg)

        # Divisão opcional em trechos (0 = sem divisão = comportamento original).
        _max = int(getattr(self.config, "chunk_chars", 0) or 0)
        _ctx_n = int(getattr(self.config, "context_paragraphs", 2) or 0)
        # Modo janela pequena (só agentes marcados): o trecho tem de caber no MENOR deles.
        _presets = [(a, p) for a in self.agents for p in [self._sw_preset(a)] if p]
        if _presets:
            _a_min, _p_min = min(_presets, key=lambda ap: ap[1]["chunk_chars"])
            _auto = _p_min["chunk_chars"]
            if _max <= 0 or _auto < _max:
                _max = _auto
                _sw_note = (_a_min.name, _auto)
            else:
                _sw_note = None
            _ctx_n = min(_ctx_n, min(p["context_paragraphs"] for _, p in _presets))
        else:
            _sw_note = None
        chunks = split_into_chunks(source_text, _max)
        n_chunks = len(chunks)

        log(t("log_starting", _L))
        log(f"{t('log_target', _L)}{self.config.target_language}")
        log(f"{t('log_total_agents', _L)}{len(self.agents)}")
        for _a, _p in _presets:
            log(t("log_small_window_agent", _L).format(name=_a.name, win=_p["window_tokens"], rag=_p["rag_max_chars"]))
        if _sw_note:
            log(t("log_chunks_auto", _L).format(name=_sw_note[0], max=_sw_note[1]))
        if n_chunks > 1:
            log(t("log_chunks", _L).format(n=n_chunks, max=_max, ctx=_ctx_n))
        log("-" * 50)

        self.usage_manager.reset_execution()
        # Cache BM25/docs POR EXECUÇÃO: compartilhado por agentes E trechos.
        rag_cache: Dict[str, Any] = {}

        finals: List[str] = []
        history: List[Dict[str, Any]] = []
        ctx = None
        for ci, chunk in enumerate(chunks, start=1):
            if n_chunks > 1:
                log("\n" + t("log_chunk_start", _L).format(i=ci, n=n_chunks, chars=len(chunk)))
            final, hist = self._run_one(chunk, log, ctx=ctx, chunk_no=(ci if n_chunks > 1 else 0),
                                        rag_cache=rag_cache)
            finals.append(final)
            history.extend(hist)
            ctx = None
            if _ctx_n > 0 and ci < n_chunks:
                ctx = {"orig": tail_paragraphs(chunk, _ctx_n), "trans": tail_paragraphs(final, _ctx_n)}
        current_text = "\n\n".join(f for f in finals if f is not None) if n_chunks > 1 else finals[0]


        try:
            log("\n" + t("log_tokens_usage", _L))
            _any_est = False
            for _k in sorted(self.usage_manager.exec_detail().keys()):
                _d = self.usage_manager.exec_detail()[_k]
                _tag = "estimado" if _d.get("estimated") else "via API"
                if _d.get("estimated"):
                    _any_est = True
                log(f"   - {_k} [{_d.get('provider', '')}]: "
                    f"entrada={_d.get('input', 0)} saida={_d.get('output', 0)} "
                    f"total={int(_d.get('input', 0)) + int(_d.get('output', 0))} ({_tag})")
            log("\n" + t("log_provider_summary", _L))
            for _prov, _vals in sorted(self.usage_manager.summary_by_provider().items()):
                log(f"   - {_prov}: entrada={_vals['input']} saida={_vals['output']} total={_vals['total']}")
            _tot = self.usage_manager.totals_execution()
            log(f"\n{t('log_total_general', _L)}entrada={_tot['input']} saida={_tot['output']} total={_tot['total']}"
                + (" (inclui valores estimados)" if _any_est else ""))
        except Exception:
            pass
        log("\n" + "="*50)
        log(t("log_done", _L))
        return PipelineResult(
            original_text=source_text,
            target_language=self.config.target_language,
            final_text=current_text,
            steps_history=history
        )
