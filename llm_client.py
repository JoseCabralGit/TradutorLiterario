# -*- coding: utf-8 -*-
"""Fábrica de chamadas a modelos de linguagem (LLMs) com endpoints OpenAI-compatíveis.

Modulo extraído de gui.py (arquivo original monolítico) durante a modularização.
"""
import json

from app_config import load_persistent_config
from token_usage import TokenReport, estimate_tokens, parse_usage


class LLMProviderFactory:
    # Endpoints compatíveis com o formato OpenAI (/chat/completions)
    OPENAI_COMPATIBLE = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "deepseek": "https://api.deepseek.com/chat/completions",
        "mistral": "https://api.mistral.ai/v1/chat/completions",
        "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "grok": "https://api.x.ai/v1/chat/completions",
        "ollama": "http://localhost:11434/v1/chat/completions",
    }

    # Palavras que indicam limite de taxa / cota esgotada (429 etc).
    RATE_LIMIT_MARKERS = (
        "429", "rate limit", "rate_limit", "rate-limit",
        "too many requests", "quota", "insufficient_quota",
        "quota_exceeded", "exceeded your current quota",
        "daily limit", "daily_quota", "billing", "credit",
        "resource_exhausted", "limit exceeded",
    )

    @staticmethod
    def is_rate_limit_error(err: Exception) -> bool:
        try:
            msg = str(err or "").lower()
        except Exception:
            return False
        return any(m in msg for m in LLMProviderFactory.RATE_LIMIT_MARKERS)

    @staticmethod
    def mask_key(key: str) -> str:
        k = (key or "").strip()
        if not k:
            return "(sem chave)"
        if len(k) <= 8:
            return "***"
        return f"{k[:3]}...{k[-4:]}"

    @staticmethod
    def _post_json(url: str, payload: dict, headers: dict, timeout: int = 300) -> dict:
        import urllib.request, urllib.error
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) TradutorInteligente/1.0", **headers})
        try:
            with urllib.request.urlopen(req, timeout=(timeout if timeout and timeout > 0 else None)) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:800]
            raise RuntimeError(f"HTTP {e.code} em {url}: {body}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Falha de conexão com {url}: {e.reason}")

    @staticmethod
    def call_llm(provider: str, model: str, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int, api_key: str = "",
                 reasoning_effort: str = "", retry_on_truncation: bool = False, timeout: int = 300) -> tuple[str, str, "TokenReport"]:
        """Chama o LLM e devolve (texto, log, relatório de tokens).

        Nada aqui limita o usuário: todo limite vem da configuração do agente.
        - max_tokens <= 0  -> NÃO envia limite (vale o padrão do modelo/provedor).
        - timeout    <= 0  -> espera sem limite de tempo.
        - reasoning_effort -> "" = padrão do modelo; "low"/"medium"/"high" só se o usuário escolheu.
        - Se a resposta vier CORTADA (finish_reason "length" / "MAX_TOKENS"), o log sempre avisa.
          Só se o usuário ligou `retry_on_truncation` e definiu um limite, tenta UMA vez de novo
          com o dobro desse limite.
        """
        F = LLMProviderFactory
        opts = dict(reasoning_effort=reasoning_effort, timeout=timeout)
        text, log, report, truncated = F._call_once(provider, model, system_prompt, user_prompt, temperature, max_tokens, api_key, **opts)
        if not truncated:
            return text, log, report
        cur = int(max_tokens or 0)
        if cur > 0:
            what = f"A resposta atingiu o limite de {cur} tokens deste agente"
        else:
            what = "O próprio modelo/provedor encerrou a resposta antes do fim (limite deles, não do programa)"
        if not retry_on_truncation or cur <= 0:
            log += (f"   [⚠️ SAÍDA CORTADA] {what}. Aumente o limite do agente (0 = sem limite) "
                    f"ou ative \"tentar de novo com o dobro\".\n")
            return text, log, report
        bigger = cur * 2
        log += f"   [⚠️ Saída cortada pelo limite de {cur} tokens] Tentando de novo com {bigger} (opção do agente)...\n"
        text2, log2, report2, truncated2 = F._call_once(provider, model, system_prompt, user_prompt, temperature, bigger, api_key, **opts)
        log += log2
        if truncated2:
            log += f"   [⚠️ SAÍDA CORTADA] Continua incompleta mesmo com {bigger} tokens.\n"
        combined = TokenReport(
            input_tokens=int(report.input_tokens or 0) + int(report2.input_tokens or 0),
            output_tokens=int(report.output_tokens or 0) + int(report2.output_tokens or 0),
            source="api" if (report.source == "api" and report2.source == "api") else "estimado",
        )
        return text2, log, combined

    @staticmethod
    def _call_once(provider: str, model: str, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int, api_key: str = "",
                   reasoning_effort: str = "", timeout: int = 300):
        """Uma chamada ao LLM. Devolve (texto, log, relatório, truncated).

        O relatório traz os números reais do campo `usage` da API quando
        disponível; caso contrário, estimativa marcada como "estimado".

        `api_key`: quando informada, usa ela em vez da global do config
        (é assim que o rodízio multi-chaves funciona).
        """
        provider_lower = provider.lower().strip()
        provider_upper = provider.upper().strip()

        if (api_key or "").strip():
            api_key = api_key.strip()
        else:
            config = load_persistent_config()
            api_key = config.get("api_keys", {}).get(provider_lower, "")
            # Compat: api_keys[prov] pode ser lista (novo formato multi-chaves).
            # A checagem tem que vir ANTES do strip — strip em lista daria AttributeError.
            if isinstance(api_key, list):
                api_key = next((str(k).strip() for k in api_key
                                if isinstance(k, str) and k.strip()), "")
            else:
                api_key = str(api_key or "").strip()
        if not api_key and provider_lower != "ollama":
            raise RuntimeError(f"Chave de API ausente para o provedor '{provider_upper}'. Configure em Configurações > Chaves de API.")

        log = f"   [Provedor: {provider_upper}] Modelo: {model} | Temp: {temperature} | Chamando API real...\n"

        if provider_lower == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            gen_cfg = {"temperature": temperature}
            if max_tokens and int(max_tokens) > 0:  # 0 = sem limite: não envia
                gen_cfg["maxOutputTokens"] = int(max_tokens)
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": gen_cfg,
            }
            result = LLMProviderFactory._post_json(url, payload, {"x-goog-api-key": api_key}, timeout=timeout)
            try:
                parts = result["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts)
                truncated = str(result["candidates"][0].get("finishReason", "")).upper() == "MAX_TOKENS"
            except (KeyError, IndexError):
                raise RuntimeError(f"Resposta inesperada do Gemini: {str(result)[:500]}")
            report = parse_usage(result.get("usageMetadata"), provider_lower, system_prompt, user_prompt, text)
            return text.strip(), log, report, truncated

        url = LLMProviderFactory.OPENAI_COMPATIBLE.get(provider_lower)
        if not url:
            raise RuntimeError(f"Provedor '{provider}' não suportado.")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if max_tokens and int(max_tokens) > 0:  # 0 = sem limite: não envia
            payload["max_tokens"] = int(max_tokens)
        # Raciocínio (modelos que "pensam"): só é enviado se o USUÁRIO escolheu no agente.
        effort = (reasoning_effort or "").strip().lower()
        reasoning_keys = []
        if effort in ("low", "medium", "high"):
            if provider_lower in ("groq", "openai"):
                payload["reasoning_effort"] = effort
                reasoning_keys.append("reasoning_effort")
            elif provider_lower == "openrouter":
                payload["reasoning"] = {"effort": effort}
                reasoning_keys.append("reasoning")
        try:
            result = LLMProviderFactory._post_json(url, payload, headers, timeout=timeout)
        except RuntimeError as exc:
            # Se a API recusar o parâmetro de raciocínio (HTTP 400 citando reasoning), repete sem ele.
            if reasoning_keys and "HTTP 400" in str(exc) and "reasoning" in str(exc).lower():
                for k in reasoning_keys:
                    payload.pop(k, None)
                log += "   [ℹ️ Este modelo não aceita o parâmetro de raciocínio; repetindo sem ele.]\n"
                result = LLMProviderFactory._post_json(url, payload, headers, timeout=timeout)
            else:
                raise
        try:
            text = result["choices"][0]["message"]["content"]
            truncated = str(result["choices"][0].get("finish_reason", "")).lower() == "length"
        except (KeyError, IndexError):
            raise RuntimeError(f"Resposta inesperada de {provider_upper}: {str(result)[:500]}")
        text = (text or "").strip()
        report = parse_usage(result.get("usage"), provider_lower, system_prompt, user_prompt, text)
        return text, log, report, truncated
