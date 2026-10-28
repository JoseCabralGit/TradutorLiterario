# -*- coding: utf-8 -*-
"""Controle de orçamento de tokens por agente.

Estimativa simples (sem dependências): ~1 token a cada 4 caracteres.
Se `tiktoken` estiver instalado, ele é usado para estimativas melhores
quando o modelo for da família OpenAI; caso contrário usa a heurística.

Persistência do escopo diário em `token_usage.json`:
{"date": "YYYY-MM-DD", "usage": {"<agent_key>": <tokens_usados>}}

Escopo por execução é mantido só em memória e zerado a cada pipeline.run().
"""
import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Dict

USAGE_FILE = "token_usage.json"


@dataclass
class TokenReport:
    """Uso de tokens de UMA chamada ao LLM.

    `source` é "api" quando os números vieram do campo de uso da API,
    ou "estimado" quando foram calculados localmente.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    source: str = "estimado"  # "api" | "estimado"

    @property
    def total_tokens(self) -> int:
        return int(self.input_tokens or 0) + int(self.output_tokens or 0)

    def label(self) -> str:
        if self.source == "api":
            return "via API"
        return "estimado"


def _as_int(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def parse_usage(usage, provider: str, system_prompt: str, user_prompt: str, output_text: str) -> TokenReport:
    """Extrai (entrada, saída) do campo de uso da API.

    Cobre os formatos conhecidos:
    - OpenAI-compatíveis (openai/openrouter/deepseek/mistral/nvidia/groq/grok/ollama):
      {"prompt_tokens": N, "completion_tokens": M, "total_tokens": T}
    - Gemini: {"promptTokenCount": N, "candidatesTokenCount": M, "totalTokenCount": T}
    Quando ausente/inválido, estima e marca como "estimado".
    """
    if isinstance(usage, dict):
        prov = (provider or "").lower().strip()
        if prov == "gemini":
            inp = _as_int(usage.get("promptTokenCount"))
            out = _as_int(usage.get("candidatesTokenCount"))
            if inp == 0 and out == 0:
                tot = _as_int(usage.get("totalTokenCount"))
                # sem divisão confiável: trata total como saída? não —
                # mantém coerência: entrada estimada? melhor: usa total como total
                # dividindo? Não há como dividir; usa tudo como saída+entrada via total.
                # Para não inventar divisão, registra total na saída se só total existir.
                if tot > 0:
                    return TokenReport(input_tokens=0, output_tokens=tot, source="api")
            elif inp > 0 or out > 0:
                return TokenReport(input_tokens=inp, output_tokens=out, source="api")
        else:
            inp = _as_int(usage.get("prompt_tokens"))
            out = _as_int(usage.get("completion_tokens"))
            if inp > 0 or out > 0:
                return TokenReport(input_tokens=inp, output_tokens=out, source="api")
            tot = _as_int(usage.get("total_tokens"))
            if tot > 0:
                # total sem divisão: estima a divisão pela proporção entrada/saída
                est_in = estimate_tokens((system_prompt or "") + "\n" + (user_prompt or ""))
                est_out = estimate_tokens(output_text or "")
                denom = est_in + est_out
                if denom > 0:
                    inp2 = round(tot * est_in / denom)
                    return TokenReport(input_tokens=inp2, output_tokens=tot - inp2, source="api")
                return TokenReport(input_tokens=0, output_tokens=tot, source="api")
    # Sem campo de uso válido -> estimativa
    return TokenReport(
        input_tokens=estimate_tokens((system_prompt or "") + "\n" + (user_prompt or "")),
        output_tokens=estimate_tokens(output_text or ""),
        source="estimado",
    )


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        import tiktoken  # type: ignore
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass
    except ImportError:
        pass
    # Heurística: ~4 caracteres por token (vale p/ PT/EN/ES; JP/RU aproximado)
    return max(1, len(text) // 4)


class TokenLimitExceeded(Exception):
    """Levantada quando o agente estouraria o orçamento."""

    def __init__(self, agent_name: str, needed: int, limit: int, scope: str):
        self.agent_name = agent_name
        self.needed = needed
        self.limit = limit
        self.scope = scope
        scope_txt = "por execução" if scope == "per_execution" else "por dia"
        super().__init__(
            f"Agente '{agent_name}' estourou o limite de tokens "
            f"({needed}/{limit} {scope_txt})."
        )


@dataclass
class AgentBudget:
    mode: str = "unlimited"       # "unlimited" | "limited"
    limit: int = 0                # 0 = sem limite
    scope: str = "per_execution"  # "per_execution" | "per_day"
    action: str = "stop"          # "stop" | "skip" | "fallback"

    def is_limited(self) -> bool:
        return self.mode == "limited" and (self.limit or 0) > 0


class TokenUsageManager:
    """Rastreia consumo por agente (execução + dia)."""

    def __init__(self, usage_file: str = USAGE_FILE):
        self.usage_file = usage_file
        self._exec_usage: Dict[str, int] = {}
        self._daily_usage: Dict[str, int] = {}
        self._exec_detail: Dict[str, Dict[str, object]] = {}
        self._exec_provider: Dict[str, Dict[str, int]] = {}
        self._today = date.today().isoformat()
        self._load()

    # -- persistência diária -------------------------------------------
    def _load(self):
        if os.path.exists(self.usage_file):
            try:
                with open(self.usage_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == self._today:
                    self._daily_usage = dict(data.get("usage", {}))
                else:
                    # dia novo -> zera
                    self._daily_usage = {}
                    self._save()
            except Exception:
                self._daily_usage = {}
        else:
            self._daily_usage = {}

    def _save(self):
        try:
            with open(self.usage_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"date": self._today, "usage": self._daily_usage},
                    f, indent=2, ensure_ascii=False,
                )
        except Exception:
            pass

    def _rollover_if_needed(self):
        today = date.today().isoformat()
        if today != self._today:
            self._today = today
            self._daily_usage = {}
            self._save()

    # -- API ------------------------------------------------------------
    def reset_execution(self):
        """Zera contadores por execução (chamar no início de cada pipeline.run)."""
        self._exec_usage = {}
        self._exec_detail = {}
        self._exec_provider = {}

    def reset_daily(self):
        self._rollover_if_needed()
        self._daily_usage = {}
        self._save()

    def get_used(self, agent_key: str, scope: str) -> int:
        self._rollover_if_needed()
        if scope == "per_day":
            return self._daily_usage.get(agent_key, 0)
        return self._exec_usage.get(agent_key, 0)

    def check(self, agent_key: str, agent_name: str, budget: AgentBudget, needed: int):
        """Verifica se `needed` cabe no orçamento; levanta TokenLimitExceeded se não."""
        if not budget.is_limited():
            return
        used = self.get_used(agent_key, budget.scope)
        if used + needed > budget.limit:
            raise TokenLimitExceeded(agent_name, used + needed, budget.limit, budget.scope)

    def consume(self, agent_key: str, scope: str, amount: int):
        self._rollover_if_needed()
        if amount <= 0:
            return
        self._exec_usage[agent_key] = self._exec_usage.get(agent_key, 0) + amount
        # consumo da execução também conta no total diário (p/ escopo diário coerente)
        self._daily_usage[agent_key] = self._daily_usage.get(agent_key, 0) + amount
        self._save()

    def consume_detailed(self, agent_key: str, scope: str, provider: str, report: "TokenReport"):
        """Registra entrada/saída separados + agregado por provedor."""
        self._rollover_if_needed()
        total = int(report.total_tokens or 0)
        if total <= 0:
            return
        self.consume(agent_key, scope, total)
        det = self._exec_detail.get(agent_key)
        if det is None:
            det = {"input": 0, "output": 0, "provider": provider, "estimated": False}
            self._exec_detail[agent_key] = det
        det["input"] = int(det.get("input", 0)) + int(report.input_tokens or 0)
        det["output"] = int(det.get("output", 0)) + int(report.output_tokens or 0)
        det["provider"] = provider
        if report.source != "api":
            det["estimated"] = True
        prov = self._exec_provider.get(provider)
        if prov is None:
            prov = {"input": 0, "output": 0}
            self._exec_provider[provider] = prov
        prov["input"] = int(prov.get("input", 0)) + int(report.input_tokens or 0)
        prov["output"] = int(prov.get("output", 0)) + int(report.output_tokens or 0)

    def exec_detail(self) -> Dict[str, Dict[str, object]]:
        self._rollover_if_needed()
        return {k: dict(v) for k, v in self._exec_detail.items()}

    def summary_by_provider(self) -> Dict[str, Dict[str, int]]:
        self._rollover_if_needed()
        out: Dict[str, Dict[str, int]] = {}
        for prov, vals in self._exec_provider.items():
            inp = int(vals.get("input", 0))
            oup = int(vals.get("output", 0))
            out[prov] = {"input": inp, "output": oup, "total": inp + oup}
        return out

    def totals_execution(self) -> Dict[str, int]:
        self._rollover_if_needed()
        inp = sum(int(v.get("input", 0)) for v in self._exec_detail.values())
        oup = sum(int(v.get("output", 0)) for v in self._exec_detail.values())
        return {"input": inp, "output": oup, "total": inp + oup}

    def summary(self) -> Dict[str, Dict[str, int]]:
        self._rollover_if_needed()
        keys = set(self._exec_usage) | set(self._daily_usage)
        return {
            k: {"execucao": self._exec_usage.get(k, 0), "hoje": self._daily_usage.get(k, 0)}
            for k in sorted(keys)
        }
