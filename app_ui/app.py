# -*- coding: utf-8 -*-
"""Classe principal recomposta por mixins (mesma API de gui.py)."""
from .state import AppStateMixin
from .layout import LayoutMixin
from .gdrive_actions import GDriveMixin
from .narrator import NarratorMixin
from .drives_presets import DrivesMixin, PresetsMixin
from .agents_list import AgentsListMixin
from .settings import SettingsMixin
from .agent_editor import AgentEditorMixin
from .execution import ExecutionMixin
from .session import SessionMixin


class TranslationAppGUI(
    AppStateMixin,
    LayoutMixin,
    GDriveMixin,
    NarratorMixin,
    DrivesMixin,
    PresetsMixin,
    AgentsListMixin,
    SettingsMixin,
    AgentEditorMixin,
    ExecutionMixin,
    SessionMixin,
):
    def __init__(self, root):
        self.init_state(root)
        self.create_widgets()
        # Restaura ajustes da última sessão e arma o salvamento automático.
        try:
            self._setup_autosave()
        except Exception:
            pass
