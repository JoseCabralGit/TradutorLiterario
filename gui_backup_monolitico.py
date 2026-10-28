# -*- coding: utf-8 -*-
"""Interface gráfica principal do Pipeline de Tradução Literária Multi-Agente & RAG Híbrido.

Este arquivo foi modularizado: a lógica de apoio foi movida para os módulos
app_config, text_utils, models, knowledge_base, llm_client, translation_pipeline
e gui_windows. A execução continua sendo feita por: python gui.py
"""
import json
import os
import sqlite3

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import List, Optional

from gdrive_integration import download_excel_from_gdrive, get_drive_service

from app_config import load_persistent_config, t
from gui_windows import ConfigManagerWindow, RAGBuilderWindow
from knowledge_base import CharactersManager, GlossaryManager, InternalRAGManager
from models import AgentConfig, PipelineConfig
from translation_pipeline import LiteraryTranslationPipeline

class TranslationAppGUI:
    def __init__(self, root):
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

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = ttk.LabelFrame(main_frame, text=f" {t("settings_title", self.ui_lang)} ", padding=10)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        # Linha 0: Idiomas e Banco de Frases
        ttk.Label(top_frame, text=t("lang_source", self.ui_lang)).grid(row=0, column=0, sticky=tk.W, padx=3, pady=3)
        self.source_lang_combo = ttk.Combobox(top_frame, values=["Inglês", "Espanhol", "Francês", "Alemão", "Italiano", "Russo", "Latim", "Outro"], width=12)
        self.source_lang_combo.set("Inglês")
        self.source_lang_combo.grid(row=0, column=1, sticky=tk.W, padx=3, pady=3)

        ttk.Label(top_frame, text=t("lang_target", self.ui_lang)).grid(row=0, column=2, sticky=tk.W, padx=3, pady=3)
        self.target_lang_combo = ttk.Combobox(top_frame, values=["Português do Brasil", "Português de Portugal", "Inglês", "Espanhol", "Francês", "Alemão", "Italiano"], width=15)
        self.target_lang_combo.set("Português do Brasil")
        self.target_lang_combo.grid(row=0, column=3, sticky=tk.W, padx=3, pady=3)

        ttk.Label(top_frame, text=t("rag_base", self.ui_lang)).grid(row=0, column=4, sticky=tk.W, padx=3, pady=3)
        self.rag_combo = ttk.Combobox(top_frame, state="readonly", width=12)
        self.update_rag_bases_dropdown()
        self.rag_combo.grid(row=0, column=5, sticky=tk.W, padx=3, pady=3)

        ttk.Button(top_frame, text=t("rag_builder", self.ui_lang), command=self.open_rag_builder).grid(row=0, column=6, padx=5, pady=3)
        ttk.Button(top_frame, text=t("keys_gdrive", self.ui_lang), command=self.open_config_window).grid(row=0, column=7, padx=5, pady=3)

        # Linha 1: Drives (Glossário e Personagens)
        self.glossary_btn = ttk.Button(top_frame, text=t("d1_glossary", self.ui_lang), command=self.select_glossary_excel)
        self.glossary_btn.grid(row=1, column=0, columnspan=2, sticky=tk.W+tk.E, padx=3, pady=4)
        ttk.Button(top_frame, text=t("d1_gdrive", self.ui_lang), command=self.sync_glossary_gdrive).grid(row=1, column=2, sticky=tk.W+tk.E, padx=3, pady=4)
        self.glossary_label = ttk.Label(top_frame, text=t("no_glossary", self.ui_lang), foreground="gray")
        self.glossary_label.grid(row=1, column=3, columnspan=2, sticky=tk.W, padx=3, pady=4)

        self.characters_btn = ttk.Button(top_frame, text=t("d2_characters", self.ui_lang), command=self.select_characters_excel)
        self.characters_btn.grid(row=1, column=5, columnspan=2, sticky=tk.W+tk.E, padx=3, pady=4)
        ttk.Button(top_frame, text=t("d2_gdrive", self.ui_lang), command=self.sync_characters_gdrive).grid(row=1, column=7, sticky=tk.W+tk.E, padx=3, pady=4)
        self.characters_label = ttk.Label(top_frame, text=t("no_characters", self.ui_lang), foreground="gray")
        self.characters_label.grid(row=1, column=8, columnspan=3, sticky=tk.W, padx=3, pady=4)

        # Linha POV (Ponto de Vista / Narrador)
        pov_frame = ttk.Frame(main_frame, padding=2)
        pov_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(pov_frame, text=t("pov_label", self.ui_lang)).pack(side=tk.LEFT, padx=2)
        self.pov_combo = ttk.Combobox(pov_frame, values=["Terceira Pessoa (ou Neutro)", "Primeira Pessoa (1ª Pessoa)"], width=25, state="readonly")
        self.pov_combo.set("Terceira Pessoa (ou Neutro)")
        self.pov_combo.pack(side=tk.LEFT, padx=5)
        self.pov_combo.bind("<<ComboboxSelected>>", self.toggle_narrator_field)

        ttk.Label(pov_frame, text=t("narrator_label", self.ui_lang)).pack(side=tk.LEFT, padx=5)
        self.narrator_combo = ttk.Combobox(pov_frame, values=self.get_characters_list(), width=25, state="disabled")
        self.narrator_combo.pack(side=tk.LEFT, padx=5)

        agents_frame = ttk.LabelFrame(main_frame, text=t("agents_frame", self.ui_lang), padding=10)
        agents_frame.pack(fill=tk.X, padx=5, pady=5)

        self.agents_listbox = tk.Listbox(agents_frame, height=4, width=110)
        self.agents_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.update_agents_listbox()

        agents_btn_frame = ttk.Frame(agents_frame)
        agents_btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)

        ttk.Button(agents_btn_frame, text="➕ Adicionar Agente", command=self.add_new_agent).pack(fill=tk.X, pady=2)
        ttk.Button(agents_btn_frame, text="✏️ Editar Agente", command=self.edit_selected_agent).pack(fill=tk.X, pady=2)
        ttk.Button(agents_btn_frame, text="🗑️ Excluir Agente", command=self.delete_selected_agent).pack(fill=tk.X, pady=2)
        ttk.Separator(agents_btn_frame, orient="horizontal").pack(fill=tk.X, pady=5)
        ttk.Button(agents_btn_frame, text="💾 Salvar Pipeline", command=self.save_agents_preset).pack(fill=tk.X, pady=2)
        ttk.Button(agents_btn_frame, text="📂 Carregar Pipeline", command=self.load_agents_preset).pack(fill=tk.X, pady=2)

        split_frame = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        split_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_pane = ttk.Frame(split_frame, padding=5)
        split_frame.add(left_pane, weight=1)

        ttk.Label(left_pane, text="📖 Texto Original para Tradução:").pack(anchor=tk.W, padx=5)
        self.run_btn = ttk.Button(left_pane, text="🚀 Executar Pipeline Completo", command=self.run_pipeline)
        self.run_btn.pack(fill=tk.X, padx=5, pady=5)
        self.input_text = scrolledtext.Text(left_pane, height=14, width=45, wrap=tk.WORD)
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.input_text.insert(tk.END, "The autumn wind whispered through the desolate valley, while Reginald watched in silence.")

        right_pane = ttk.Frame(split_frame, padding=5)
        split_frame.add(right_pane, weight=1)

        notebook = ttk.Notebook(right_pane)
        notebook.pack(fill=tk.BOTH, expand=True)

        result_tab = ttk.Frame(notebook, padding=5)
        notebook.add(result_tab, text="✨ Resultado Final")
        
        ttk.Label(result_tab, text="Texto Traduzido Final:").pack(anchor=tk.W, padx=5)
        self.output_text = scrolledtext.Text(result_tab, height=12, width=45, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        log_tab = ttk.Frame(notebook, padding=5)
        notebook.add(log_tab, text="📋 Logs de Execução")

        self.log_text = scrolledtext.Text(log_tab, height=12, width=45, wrap=tk.WORD, background="#1e1e1e", foreground="#00ff00")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def update_rag_bases_dropdown(self):
        bases = self.rag_mgr.get_all_bases()
        self.rag_combo['values'] = bases
        if bases:
            self.rag_combo.set(bases[0])

    def open_rag_builder(self):
        RAGBuilderWindow(self.root, on_update_callback=self.update_rag_bases_dropdown)

    def sync_glossary_gdrive(self):
        gdrive_cfg = self.persistent_config.get("gdrive_config", {})
        link_or_id = gdrive_cfg.get("glossary_link_or_id", "").strip()
        if not link_or_id:
            messagebox.showwarning("Aviso", "Nenhum Link ou ID do Glossário configurado nas Configurações do Google Drive!")
            return
        
        try:
            self.log_text.insert(tk.END, "[☁️ GDrive] Baixando Glossário do Google Drive...\n")
            self.root.update_idletasks()
            temp_path = download_excel_from_gdrive(link_or_id, output_path="temp_gdrive_glossary.xlsx")
            self.glossary_excel_path = temp_path
            self.glossary_label.config(text="☁️ Glossário (Google Drive)", foreground="blue")
            
            gm = GlossaryManager()
            log_result = gm.reset_and_sync_from_excel(temp_path)
            self.log_text.insert(tk.END, log_result + "\n")
            messagebox.showinfo("Sucesso", "Drive 1 (Glossário) sincronizado do Google Drive com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro GDrive", f"Falha ao baixar Glossário do Google Drive:\n{e}")
            self.log_text.insert(tk.END, f"[❌ GDrive Erro] {e}\n")

    def sync_characters_gdrive(self):
        gdrive_cfg = self.persistent_config.get("gdrive_config", {})
        link_or_id = gdrive_cfg.get("characters_link_or_id", "").strip()
        if not link_or_id:
            messagebox.showwarning("Aviso", "Nenhum Link ou ID de Personagens configurado nas Configurações do Google Drive!")
            return
        
        try:
            self.log_text.insert(tk.END, "[☁️ GDrive] Baixando Personagens do Google Drive...\n")
            self.root.update_idletasks()
            temp_path = download_excel_from_gdrive(link_or_id, output_path="temp_gdrive_characters.xlsx")
            self.characters_excel_path = temp_path
            self.characters_label.config(text="☁️ Personagens (Google Drive)", foreground="blue")
            
            cm = CharactersManager()
            log_result = cm.reset_and_sync_from_excel(temp_path)
            self.log_text.insert(tk.END, log_result + "\n")
            self.update_narrator_dropdown()
            messagebox.showinfo("Sucesso", "Drive 2 (Personagens) sincronizado do Google Drive com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro GDrive", f"Falha ao baixar Personagens do Google Drive:\n{e}")
            self.log_text.insert(tk.END, f"[❌ GDrive Erro] {e}\n")

    def get_characters_list(self) -> List[str]:
        """Lista os nomes para o menu de narrador, sem depender do nome da coluna:
        usa a primeira coluna que contém texto (ignora colunas de ID/números)."""
        cm = CharactersManager()
        if not os.path.exists(cm.db_path):
            return ["(Nenhum personagem na base)"]
        try:
            conn = sqlite3.connect(cm.db_path)
            df = pd.read_sql("SELECT * FROM personagens", conn)
            conn.close()
            if df.empty or len(df.columns) == 0:
                return ["(Nenhum personagem cadastrado)"]

            name_col = df.columns[0]
            for col in df.columns:
                vals = df[col].dropna().astype(str).str.strip()
                vals = vals[vals != ""]
                if len(vals) and (~vals.str.replace(r"[.\-]", "", regex=True).str.isdigit()).mean() > 0.5:
                    name_col = col
                    break

            names = []
            for v in df[name_col].dropna().astype(str):
                v = v.strip()
                if v and v not in names:
                    names.append(v)
            return names if names else ["(Nenhum personagem cadastrado)"]
        except Exception as e:
            return [f"(Erro ao carregar personagens: {e})"]

    def update_narrator_dropdown(self):
        chars = self.get_characters_list()
        self.narrator_combo['values'] = chars
        if chars and not chars[0].startswith("(") :
            self.narrator_combo.set(chars[0])
        else:
            self.narrator_combo.set("")

    def toggle_narrator_field(self, event=None):
        pov = self.pov_combo.get()
        if "Primeira" in pov:
            self.update_narrator_dropdown()
            self.narrator_combo.config(state="normal")
        else:
            self.narrator_combo.set("")
            self.narrator_combo.config(state="disabled")

    def save_agents_preset(self):
        file_path = filedialog.asksaveasfilename(
            title="Salvar Pipeline de Agentes",
            defaultextension=".json",
            filetypes=[("Arquivos JSON", "*.json")]
        )
        if not file_path:
            return
        
        data = []
        for agent in self.agents_list:
            data.append({
                "name": agent.name,
                "system_prompt": agent.system_prompt,
                "model": agent.model,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "provider": agent.provider
            })
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Sucesso", "Pipeline de agentes salvo com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar arquivo:\n{e}")

    def load_agents_preset(self):
        file_path = filedialog.askopenfilename(
            title="Carregar Pipeline de Agentes",
            filetypes=[("Arquivos JSON", "*.json")]
        )
        if not file_path:
            return
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                raise ValueError("O formato do arquivo JSON de agentes é inválido.")
            
            loaded_agents = []
            for item in data:
                loaded_agents.append(AgentConfig(
                    name=item.get("name", "Agente"),
                    system_prompt=item.get("system_prompt", "Você é um tradutor literário especialista."),
                    model=item.get("model", "gpt-4o"),
                    temperature=float(item.get("temperature", 0.3)),
                    max_tokens=int(item.get("max_tokens", 4000)),
                    provider=item.get("provider", "openai")
                ))
            
            if loaded_agents:
                self.agents_list = loaded_agents
                self.update_agents_listbox()
                messagebox.showinfo("Sucesso", f"Pipeline carregado com {len(loaded_agents)} agentes!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao carregar arquivo:\n{e}")

    def select_glossary_excel(self):
        file_path = filedialog.askopenfilename(
            title="Selecionar Planilha Excel de Glossário (Drive 1)",
            filetypes=[("Arquivos Excel", "*.xlsx *.xls")]
        )
        if file_path:
            self.glossary_excel_path = file_path
            self.glossary_label.config(text=os.path.basename(file_path), foreground="green")
            
            gm = GlossaryManager()
            log_result = gm.reset_and_sync_from_excel(file_path)
            self.log_text.insert(tk.END, log_result + "\n")
            messagebox.showinfo("Sucesso", "Drive 1 (Glossário) sincronizado e banco local resetado!")

    def select_characters_excel(self):
        file_path = filedialog.askopenfilename(
            title="Selecionar Planilha Excel de Personagens (Drive 2)",
            filetypes=[("Arquivos Excel", "*.xlsx *.xls")]
        )
        if file_path:
            self.characters_excel_path = file_path
            self.characters_label.config(text=os.path.basename(file_path), foreground="green")
            
            cm = CharactersManager()
            log_result = cm.reset_and_sync_from_excel(file_path)
            self.log_text.insert(tk.END, log_result + "\n")
            self.update_narrator_dropdown()
            messagebox.showinfo("Sucesso", "Drive 2 (Personagens) sincronizado e banco local resetado!")

    def update_agents_listbox(self):
        self.agents_listbox.delete(0, tk.END)
        for i, agent in enumerate(self.agents_list):
            info = f"[{i+1}] {agent.name} | Provedor: {agent.provider.upper()} | Modelo: {agent.model} | Temp: {agent.temperature}"
            self.agents_listbox.insert(tk.END, info)

    def open_config_window(self):
        ConfigManagerWindow(self.root, on_save_callback=self.reload_persistent_config)

    def reload_persistent_config(self):
        self.persistent_config = load_persistent_config()
        self.ui_lang = self.persistent_config.get("interface_language", "Português")
        self.root.title(t("app_title", self.ui_lang))
        # Recreate main widgets to reflect new UI language
        for widget in self.root.winfo_children():
            widget.destroy()
        self.create_widgets()

    def edit_selected_agent(self):
        selection = self.agents_listbox.curselection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecione um agente na lista para editar.")
            return
        idx = selection[0]
        self.open_agent_editor(self.agents_list[idx], index=idx)

    def add_new_agent(self):
        self.open_agent_editor(AgentConfig(name=f"Agente {len(self.agents_list)+1}: Novo Agente"), index=None)

    def delete_selected_agent(self):
        selection = self.agents_listbox.curselection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecione um agente para excluir.")
            return
        idx = selection[0]
        if len(self.agents_list) <= 1:
            messagebox.showwarning("Aviso", "O pipeline precisa ter pelo menos um agente.")
            return
        if messagebox.askyesno("Confirmar", f"Excluir agente '{self.agents_list[idx].name}'?"):
            self.agents_list.pop(idx)
            self.update_agents_listbox()

    def open_agent_editor(self, agent: AgentConfig, index: Optional[int] = None):
        editor = tk.Toplevel(self.root)
        editor.title("Configuração do Agente")
        editor.geometry("500x500")
        editor.transient(self.root)
        editor.grab_set()

        ttk.Label(editor, text="Nome do Agente:").pack(anchor=tk.W, padx=10, pady=5)
        name_entry = ttk.Entry(editor, width=50)
        name_entry.insert(0, agent.name)
        name_entry.pack(padx=10, pady=5)

        ttk.Label(editor, text="Provedor:").pack(anchor=tk.W, padx=10, pady=5)
        providers = list(self.persistent_config.get("custom_models", {}).keys())
        prov_combo = ttk.Combobox(editor, values=providers, state="readonly", width=47)
        if agent.provider in providers:
            prov_combo.set(agent.provider)
        elif providers:
            prov_combo.current(0)
        prov_combo.pack(padx=10, pady=5)

        ttk.Label(editor, text="Modelo:").pack(anchor=tk.W, padx=10, pady=5)
        model_combo = ttk.Combobox(editor, width=47)
        model_combo.pack(padx=10, pady=5)

        def update_models(event=None):
            p = prov_combo.get()
            m_list = self.persistent_config.get("custom_models", {}).get(p, [])
            model_combo['values'] = m_list
            if agent.model in m_list:
                model_combo.set(agent.model)
            elif m_list:
                model_combo.current(0)

        prov_combo.bind("<<ComboboxSelected>>", update_models)
        update_models()

        ttk.Label(editor, text="Temperatura:").pack(anchor=tk.W, padx=10, pady=5)
        temp_entry = ttk.Entry(editor, width=50)
        temp_entry.insert(0, str(agent.temperature))
        temp_entry.pack(padx=10, pady=5)

        ttk.Label(editor, text="System Prompt:").pack(anchor=tk.W, padx=10, pady=5)
        prompt_text = scrolledtext.Text(editor, height=8, width=55, wrap=tk.WORD)
        prompt_text.insert(tk.END, agent.system_prompt)
        prompt_text.pack(padx=10, pady=5)

        def save():
            try:
                agent.name = name_entry.get().strip()
                agent.provider = prov_combo.get().strip()
                agent.model = model_combo.get().strip()
                agent.temperature = float(temp_entry.get().strip())
                agent.system_prompt = prompt_text.get("1.0", tk.END).strip()

                if index is not None:
                    self.agents_list[index] = agent
                else:
                    self.agents_list.append(agent)
                self.update_agents_listbox()
                editor.destroy()
            except ValueError:
                messagebox.showerror("Erro", "Temperatura inválida.", parent=editor)

        ttk.Button(editor, text="💾 Salvar Agente", command=save).pack(pady=10)

    def run_pipeline(self):
        source_text = self.input_text.get("1.0", tk.END).strip()
        if not source_text:
            messagebox.showwarning("Aviso", "Insira o texto original.")
            return

        active_base = self.rag_combo.get().strip() or "Banco_Frases_Padrao"

        self.log_text.delete("1.0", tk.END)
        self.output_text.delete("1.0", tk.END)

        def log_callback(msg):
            self.log_text.insert(tk.END, msg)
            self.log_text.see(tk.END)
            self.root.update_idletasks()

        source_lang = self.source_lang_combo.get().strip() or "Inglês"
        target_lang = self.target_lang_combo.get().strip() or "Português do Brasil"
        pov = self.pov_combo.get().strip()
        narrator = self.narrator_combo.get().strip() if "Primeira" in pov else ""
        pipeline_conf = PipelineConfig(
            source_language=source_lang, 
            target_language=target_lang,
            pov_mode=pov,
            narrator_name=narrator
        )
        pipeline = LiteraryTranslationPipeline(
            agents=self.agents_list, 
            pipeline_config=pipeline_conf, 
            active_rag_base=active_base
        )

        if self.glossary_excel_path and os.path.exists(self.glossary_excel_path):
            sync_log1 = pipeline.sync_glossary_from_excel(self.glossary_excel_path)
            log_callback(sync_log1)

        if self.characters_excel_path and os.path.exists(self.characters_excel_path):
            sync_log2 = pipeline.sync_characters_from_excel(self.characters_excel_path)
            log_callback(sync_log2)

        try:
            result = pipeline.run(source_text, log_callback=log_callback)
            self.output_text.insert(tk.END, result.final_text)
            messagebox.showinfo("Sucesso", "Pipeline executado com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro na execução:\n{e}")
if __name__ == "__main__":
    root = tk.Tk()
    app = TranslationAppGUI(root)
    root.mainloop()
