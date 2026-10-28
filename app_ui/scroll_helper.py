# -*- coding: utf-8 -*-
"""Helpers de rolagem (Scrollbar + rodinha do mouse) reutilizáveis.

Sem mudar o visual: só acrescenta rolagem onde a janela estourava a tela.
"""
import tkinter as tk
from tkinter import ttk


def bind_mousewheel(widget, canvas):
    """Liga a rodinha do mouse ao canvas quando o cursor está sobre o widget."""
    def _on_enter(_e):
        canvas.bind_all("<MouseWheel>", _on_wheel, add="+")
        canvas.bind_all("<Button-4>", _on_wheel, add="+")
        canvas.bind_all("<Button-5>", _on_wheel, add="+")

    def _on_leave(_e):
        try:
            canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        try:
            canvas.unbind_all("<Button-4>")
        except Exception:
            pass
        try:
            canvas.unbind_all("<Button-5>")
        except Exception:
            pass

    def _on_wheel(e):
        try:
            if getattr(e, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(e, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            else:
                delta = int(getattr(e, "delta", 0) / 120)
                if delta:
                    canvas.yview_scroll(-delta, "units")
        except Exception:
            pass

    widget.bind("<Enter>", _on_enter, add="+")
    widget.bind("<Leave>", _on_leave, add="+")


def make_scrollable_frame(parent, height=None):
    """Cria (outer, canvas, scrollbar, inner) — o conteúdo vai no inner com pack.

    O botão de Salvar fica FORA (no parent), fixo embaixo.
    """
    outer = ttk.Frame(parent)
    if height is not None:
        outer.configure(height=height)
    outer.pack(fill=tk.BOTH, expand=True)
    canvas = tk.Canvas(outer, highlightthickness=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    inner = ttk.Frame(canvas)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _conf(_e=None):
        try:
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    def _width(e):
        try:
            canvas.itemconfig(win, width=e.width)
        except Exception:
            pass

    inner.bind("<Configure>", _conf, add="+")
    canvas.bind("<Configure>", _width, add="+")
    bind_mousewheel(inner, canvas)
    bind_mousewheel(canvas, canvas)
    return outer, canvas, scrollbar, inner


def add_text_scrollbar(text_widget):
    """Acrescenta barrinha vertical + rodinha num Text/ScrolledText existente.

    O widget precisa estar dentro de um Frame pai (cria o layout lado a lado
    sem mexer no resto da janela).
    """
    parent = text_widget.master
    try:
        info = text_widget.pack_info()
    except Exception:
        info = {}
    try:
        text_widget.pack_forget()
    except Exception:
        pass
    holder = ttk.Frame(parent)
    holder.pack(fill=info.get("fill", tk.BOTH) if isinstance(info, dict) else tk.BOTH,
                expand=info.get("expand", True) if isinstance(info, dict) else True,
                padx=info.get("padx", 5) if isinstance(info, dict) else 5,
                pady=info.get("pady", 5) if isinstance(info, dict) else 5)
    sb = ttk.Scrollbar(holder, orient="vertical", command=text_widget.yview)
    text_widget.configure(yscrollcommand=sb.set)
    text_widget.pack(in_=holder, side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(in_=holder, side=tk.RIGHT, fill=tk.Y)

    def _wheel(e):
        try:
            if getattr(e, "num", None) == 4:
                text_widget.yview_scroll(-1, "units")
            elif getattr(e, "num", None) == 5:
                text_widget.yview_scroll(1, "units")
            else:
                delta = int(getattr(e, "delta", 0) / 120)
                if delta:
                    text_widget.yview_scroll(-delta, "units")
            return "break"
        except Exception:
            return None

    text_widget.bind("<MouseWheel>", _wheel, add="+")
    text_widget.bind("<Button-4>", _wheel, add="+")
    text_widget.bind("<Button-5>", _wheel, add="+")
    return sb
