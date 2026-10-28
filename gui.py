# -*- coding: utf-8 -*-
"""Atalho de compatibilidade: reexporta TranslationAppGUI do pacote app_ui."""
import tkinter as tk
from app_ui import TranslationAppGUI

__all__ = ["TranslationAppGUI", "main"]


def main():
    root = tk.Tk()
    app = TranslationAppGUI(root)
    root.mainloop()
    return app


if __name__ == "__main__":
    main()
