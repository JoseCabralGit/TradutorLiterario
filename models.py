# -*- coding: utf-8 -*-
"""Dataclasses de configuração e resultado do pipeline de tradução.

Modulo extraído de gui.py (arquivo original monolítico) durante a modularização.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from app_config import INTERNAL_RAG_DB, LOCAL_CHARACTERS_DB, LOCAL_GLOSSARY_DB


@dataclass
class AgentConfig:
    name: str
    system_prompt: str = "Você é um tradutor literário especialista."
    model: str = "gpt-4o"
    temperature: float = 0.3
    # --- Limites da chamada: NADA é imposto pelo programa; tudo é escolha do usuário ---
    # Máximo de tokens da RESPOSTA. 0 = sem limite (não envia o parâmetro; vale o padrão do modelo).
    max_tokens: int = 0
    # Tempo máximo de espera pela API, em segundos. 0 = sem limite de tempo.
    timeout_s: int = 300
    # Raciocínio dos modelos que "pensam" (Groq/OpenAI/OpenRouter): "" = padrão do modelo | "low" | "medium" | "high".
    reasoning_effort: str = ""
    # Se a resposta for cortada pelo max_tokens definido: False = só avisa no log; True = tenta de novo com o dobro.
    truncation_retry: bool = False
    # Pausa APÓS este agente, em segundos, antes do próximo. 0 = sem pausa.
    pause_after_s: int = 0
    provider: str = "openai"
    # --- Orçamento de tokens (por agente) ---
    budget_mode: str = "unlimited"  # "unlimited" | "limited"
    token_limit: int = 0  # 0 = sem limite
    budget_scope: str = "per_execution"  # "per_execution" | "per_day"
    budget_action: str = "stop"  # "stop" | "skip" | "fallback"
    fallback_model: str = ""
    fallback_provider: str = ""
    # --- Multi-chaves + fallback configuravel (por agente) ---
    # Lista de chaves do provedor principal. [] = usa a global de api_keys.
    # A chave [default_key_index] e a padrao; as demais sao fallback.
    api_keys: List[str] = field(default_factory=list)
    default_key_index: int = 0
    # Chaves do provedor RESERVA (quando fallback_provider != provider).
    # [] = usa a global de api_keys do provedor reserva.
    fallback_api_keys: List[str] = field(default_factory=list)
    fallback_default_key_index: int = 0
    # Ordem do fallback quando der 429/cota:
    #  "model_first" = tenta modelo reserva antes de outras chaves (padrao)
    #  "key_first"   = tenta outras chaves antes do modelo reserva
    #  "keys_only"   = so roda as chaves, nunca troca de modelo
    #  "model_only"  = so troca de modelo, nunca roda outras chaves
    fallback_strategy: str = "model_first"
    # --- Banco de apoio linguístico (RAG de frases/vocabulário) ---
    # True = este agente recebe o bloco do RAG no prompt; False = não recebe.
    # (Glossário e personagens continuam sendo enviados a todos os agentes.)
    use_rag: bool = True
    # True = a partir do 2o agente, o texto ORIGINAL é reenviado junto da versão anterior (âncora de
    # fidelidade). False = só a versão anterior (economiza tokens em IA gratuita). Opção do usuário.
    send_original: bool = True
    # --- Modo janela pequena (EXTRA, por agente) ---
    # False = comportamento atual, sem nenhuma mudança. True = o programa configura este agente
    # para um modelo de contexto curto (não reenvia o original, limita o RAG, ajusta o trecho
    # pela janela e avisa no log). Glossário e fichas NUNCA são cortados.
    small_window: bool = False
    window_tokens: int = 8192   # janela de contexto do modelo deste agente (tokens)

@dataclass
class PipelineConfig:
    source_language: str = "Inglês"
    target_language: str = "Português do Brasil"
    db_path: str = INTERNAL_RAG_DB
    glossary_db_path: str = LOCAL_GLOSSARY_DB
    characters_db_path: str = LOCAL_CHARACTERS_DB
    pov_mode: str = "Terceira Pessoa (ou Neutro)"
    narrator_name: str = ""
    # Divisão em trechos (IAs com janela pequena). 0 = sem divisão (capítulo inteiro). Opção do usuário.
    chunk_chars: int = 0
    # Quantos parágrafos do trecho anterior (original + tradução) vão como contexto somente de leitura.
    context_paragraphs: int = 2
    # Pronome de 1a pessoa: True = o programa corrige sozinho (SEM IA, só troca o pronome errado pelo
    # da ficha, e registra cada troca no log). False = só avisa no log.
    pronoun_autofix: bool = True

@dataclass
class PipelineResult:
    original_text: str
    target_language: str
    final_text: str
    steps_history: List[Dict[str, Any]] = field(default_factory=list)
