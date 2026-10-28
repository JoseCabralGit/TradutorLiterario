# -*- coding: utf-8 -*-
"""Execução do pipeline (cópia fiel de gui.py + execução em thread de fundo).

A UI roda na thread principal do Tkinter; o pipeline (rede + CPU) roda numa
thread DAEMON. A thread worker NUNCA toca em widget: só enfileira mensagens
(("log", texto) / ("done", resultado) / ("error", exceção)) numa queue.Queue,
e um "pump" via root.after drena a fila em LOTE na thread principal —
1 único insert e 1 único redesenho por drenagem (importante em PC fraco,
onde cada redesenho de tela custa CPU; antes era 1 update_idletasks por linha
de log + bloqueio total do event loop durante cada chamada de rede).
"""
import copy
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox

from app_config import t
from models import PipelineConfig
from translation_pipeline import LiteraryTranslationPipeline

# Intervalo da drenagem da fila de logs (ms). Maior = menos redraws (PC fraco);
# menor = log mais "ao vivo". 150ms é imperceptível e custa quase nada.
_PUMP_MS = 150
# Limite do widget de log (chars). Acima disso corta o começo (uma única
# operação, rara) para o tk.Text não crescer sem limite em RAM/redraw.
_LOG_MAX_CHARS = 400_000
_LOG_KEEP_CHARS = 300_000


class ExecutionMixin:
    def _warn_base_desc(self, kind, excel_path, log_callback, lang):
        """Avisa (sem bloquear) se a descrição da base está faltando/desatualizada."""
        try:
            from base_schema import status as _base_desc_status
            if _base_desc_status(kind, excel_path) in ("missing", "stale"):
                log_callback(t("log_base_desc_missing", lang) + "\n")
        except Exception:
            pass

    # ------------------------------------------------------- guard / UI ---
    def _set_run_enabled(self, enabled: bool):
        """Liga/desliga o botão de execução (guard de reentrância durante o run)."""
        try:
            self.run_btn.config(state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _trim_log(self):
        """Corta o começo do log quando passa do limite (evita tk.Text gigante)."""
        try:
            n = len(self.log_text.get("1.0", "end-1c"))
            if n > _LOG_MAX_CHARS:
                self.log_text.delete("1.0", f"1.0 + {n - _LOG_KEEP_CHARS}c")
        except Exception:
            pass

    # ---------------------------------------------------------- execução ---
    def run_pipeline(self):
        if getattr(self, "_pipeline_running", False):
            return  # clique duplo / reentrância: já está rodando
        _L = getattr(self, "ui_lang", "Português")
        source_text = self.input_text.get("1.0", tk.END).strip()
        if not source_text:
            messagebox.showwarning(t("warn_title", _L), t("warn_no_text", _L))
            return
        active_base = self.rag_combo.get().strip() or "Banco_Frases_Padrao"
        self.log_text.delete("1.0", tk.END)
        self.output_text.delete("1.0", tk.END)

        # Snapshot de TUDO que vem dos widgets — feito na thread principal,
        # ANTES de iniciar a worker (a worker não lê widget nenhum).
        source_lang = self.source_lang_combo.get().strip() or "Inglês"
        target_lang = self.target_lang_combo.get().strip() or "Português do Brasil"
        pov = self.pov_combo.get().strip()
        narrator = self.narrator_combo.get().strip() if "Primeira" in pov else ""
        glossary_path = self.glossary_excel_path
        characters_path = self.characters_excel_path
        def _int_entry(widget_name, default):
            try:
                v = int((getattr(self, widget_name).get() or "").strip())
                return v if v >= 0 else default
            except Exception:
                return default
        pipeline_conf = PipelineConfig(
            source_language=source_lang,
            target_language=target_lang,
            pov_mode=pov,
            narrator_name=narrator,
            chunk_chars=_int_entry("chunk_chars_entry", 0),
            context_paragraphs=_int_entry("chunk_ctx_entry", 2),
        )
        # deepcopy = o run usa o estado dos agentes NO MOMENTO DO CLIQUE
        # (antes, a UI congelada garantia isso automaticamente).
        pipeline = LiteraryTranslationPipeline(
            agents=copy.deepcopy(self.agents_list),
            pipeline_config=pipeline_conf,
            active_rag_base=active_base,
            ui_lang=_L,
        )

        _q: queue.Queue = queue.Queue()
        self._log_queue = _q
        self._pipeline_running = True
        self._set_run_enabled(False)

        def log_callback(msg):
            # Chamado da thread worker: SÓ enfileia, nunca toca em widget.
            _q.put(("log", msg))

        def worker():
            try:
                if glossary_path and os.path.exists(glossary_path):
                    log_callback(pipeline.sync_glossary_from_excel(glossary_path))
                    self._warn_base_desc("glossary", glossary_path, log_callback, _L)
                if characters_path and os.path.exists(characters_path):
                    log_callback(pipeline.sync_characters_from_excel(characters_path))
                    self._warn_base_desc("characters", characters_path, log_callback, _L)
                result = pipeline.run(source_text, log_callback=log_callback)
                _q.put(("done", result))
            except Exception as e:
                _q.put(("error", e))

        threading.Thread(target=worker, daemon=True, name="pipeline-run").start()
        self.root.after(_PUMP_MS, self._pump_logs, _L)

    def _pump_logs(self, lang):
        """Drena a fila em lote na thread principal (1 redraw por drenagem)."""
        q = getattr(self, "_log_queue", None)
        if q is None:
            return
        logs, terminal = [], None
        try:
            while True:
                item = q.get_nowait()
                if item[0] == "log":
                    logs.append(item[1])
                else:
                    terminal = item  # "done"/"error" é o último item da worker
        except queue.Empty:
            pass
        if logs:
            self.log_text.insert(tk.END, "".join(logs))
            self._trim_log()
            self.log_text.see(tk.END)
        if terminal is not None:
            self._finish_run(terminal, lang)
            return
        self.root.after(_PUMP_MS, self._pump_logs, lang)

    def _finish_run(self, terminal, lang):
        """Resultado/erro chegam por aqui SEMPRE na thread principal."""
        self._log_queue = None
        self._pipeline_running = False
        self._set_run_enabled(True)
        kind, payload = terminal
        if kind == "done":
            self.output_text.insert(tk.END, payload.final_text)
            try:
                self._autosave_session()
            except Exception:
                pass
            messagebox.showinfo(t("success_title", lang), t("success_run", lang))
        else:
            messagebox.showerror(t("error_title", lang), f"{t('error_run', lang)}\n{payload}")
