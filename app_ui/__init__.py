# -*- coding: utf-8 -*-
"""Pacote de interface gráfica modularizada.

Mantém compatibilidade: `from app_ui import TranslationAppGUI`
e `import gui` continuam funcionando.
"""
from .app import TranslationAppGUI

__all__ = ["TranslationAppGUI"]
