# -*- coding: utf-8 -*-
"""Estado inicial da janela principal (extraído de gui.py sem alteração de lógica)."""
from typing import List

from app_config import load_persistent_config, t
from knowledge_base import InternalRAGManager
from models import AgentConfig
from session_autosave import agent_from_dict, load_snapshot


class AppStateMixin:
    def init_state(self, root):
        self.root = root
        self.persistent_config = load_persistent_config()
        self.ui_lang = self.persistent_config.get("interface_language", "Português")
        self.root.title(t("app_title", self.ui_lang))
        self.root.geometry("1200x850")

        self.glossary_excel_path = None
        self.characters_excel_path = None
        self.rag_mgr = InternalRAGManager()
        self.persistent_config = load_persistent_config()

        self.agents_list: List[AgentConfig] = [
            AgentConfig(
                name="Agente 1: Tradução Inicial",
                system_prompt="Você é um tradutor literário especialista consultando o glossário, fichas e o banco de frases de referência.",
                model="deepseek-chat",
                temperature=0.3,
                provider="deepseek"
            ),
            AgentConfig(
                name="Agente 2: Polimento Estilístico",
                system_prompt="Você é um escritor renomado especialista em prosa poética.",
                model="anthropic/claude-3.5-sonnet",
                temperature=0.7,
                provider="openrouter"
            ),
            AgentConfig(
                name="Agente 3: Revisão Editorial",
                system_prompt="Você é um editor sênior rigoroso com gramática e fluidez.",
                model="gpt-4o",
                temperature=0.1,
                provider="openai"
            )
        ]
        # Restaura a última sessão salva automaticamente (se existir).
        # Arquivo ausente/corrompido = mantém o padrão acima.
        try:
            snapshot = load_snapshot()
            saved_agents = (snapshot or {}).get("agents") or []
            if isinstance(saved_agents, list) and saved_agents:
                restored = []
                for item in saved_agents:
                    if isinstance(item, dict):
                        try:
                            restored.append(agent_from_dict(item, AgentConfig))
                        except Exception:
                            continue
                if restored:
                    self.agents_list = restored
            self._restored_session = snapshot or {}
        except Exception:
            self._restored_session = {}
        # O salvamento automático só vale depois da janela pronta
        # (evita gravar estado parcial durante a construção dos widgets).
        self._autosave_ready = False
