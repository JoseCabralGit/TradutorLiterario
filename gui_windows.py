# -*- coding: utf-8 -*-
"""Janelas secundárias da interface gráfica (Construtor de Banco de Frases e Configurações).

Modulo extraído de gui.py (arquivo original monolítico) durante a modularização.
"""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app_config import load_persistent_config, save_persistent_config
import base_schema
from knowledge_base import InternalRAGManager

class RAGBuilderWindow:
    def __init__(self, parent, on_update_callback):
        self.top = tk.Toplevel(parent)
        self.top.title("🛠️ Construtor de Banco de Frases de Referência (Naturalidade)")
        self.top.geometry("850x600")
        self.top.transient(parent)
        self.top.grab_set()

        self.on_update_callback = on_update_callback
        self.rag_mgr = InternalRAGManager()
        self.bases = self.rag_mgr.get_all_bases()
        self.current_base = self.bases[0] if self.bases else "Banco_Frases_Padrao"

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.top, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(main_frame)
        top_bar.pack(fill=tk.X, pady=5)

        ttk.Label(top_bar, text="Selecionar Banco de Frases:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        self.base_combo = ttk.Combobox(top_bar, values=self.bases, state="readonly", width=25)
        self.base_combo.pack(side=tk.LEFT, padx=5)
        if self.current_base in self.bases:
            self.base_combo.set(self.current_base)
        self.base_combo.bind("<<ComboboxSelected>>", self.on_base_selected)

        ttk.Button(top_bar, text="➕ Novo Banco", command=self.create_new_base_dialog).pack(side=tk.LEFT, padx=10)
        ttk.Button(top_bar, text="🗑️ Excluir Banco", command=self.delete_current_base).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="⚙️ Configurar uso do banco", command=self.open_settings_dialog).pack(side=tk.LEFT, padx=5)

        self.table_frame = ttk.LabelFrame(main_frame, text=f" Registros do Banco: {self.current_base} ", padding=10)
        self.table_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.refresh_table_view()

    def refresh_table_view(self):
        for widget in self.table_frame.winfo_children():
            widget.destroy()

        columns = self.rag_mgr.get_base_columns(self.current_base)
        df = self.rag_mgr.get_base_data(self.current_base)

        tree_scroll = ttk.Scrollbar(self.table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tree_cols = ["id"] + columns
        self.tree = ttk.Treeview(self.table_frame, columns=tree_cols, show="headings", yscrollcommand=tree_scroll.set, height=12)
        tree_scroll.config(command=self.tree.yview)

        self.tree.heading("id", text="ID")
        self.tree.column("id", width=40, anchor=tk.CENTER)

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150, anchor=tk.W)

        self.tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected_row())

        for _, row in df.iterrows():
            values = [row.get("id", "")] + [row.get(col, "") for col in columns]
            self.tree.insert("", tk.END, values=values)

        btn_frame = ttk.Frame(self.table_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text="➕ Adicionar Frase de Referência", command=self.add_row_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="✏️ Editar Frase Selecionada", command=self.edit_selected_row).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🗑️ Excluir Frase Selecionada", command=self.delete_selected_row).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📤 Exportar Excel", command=self.export_current_base_excel).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📥 Importar Excel", command=self.import_base_excel_dialog).pack(side=tk.LEFT, padx=5)

    def export_current_base_excel(self):
        """ADICAO: exporta a base atual para Excel (nao altera nada)."""
        path = filedialog.asksaveasfilename(
            parent=self.top, title="Exportar base RAG para Excel",
            defaultextension=".xlsx",
            initialfile=f"{self.current_base}.xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return
        try:
            res = self.rag_mgr.export_base_to_excel(self.current_base, path)
            messagebox.showinfo("Sucesso",
                f"Base '{self.current_base}' exportada com {res['rows']} linha(s).\n{path}",
                parent=self.top)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar:\n{e}", parent=self.top)

    def import_base_excel_dialog(self):
        """ADICAO: importa Excel para base RAG (padrao: acrescentar)."""
        path = filedialog.askopenfilename(
            parent=self.top, title="Importar base RAG de Excel",
            filetypes=[("Excel", "*.xlsx *.xls")],
        )
        if not path:
            return
        # Destino: base atual ou nova a partir do arquivo.
        use_current = messagebox.askyesno(
            "Importar Excel",
            f"Acrescentar na base atual '{self.current_base}'?\n\n"
            "Sim = acrescenta na atual (pula duplicadas).\n"
            "Não = cria base nova a partir do nome do arquivo.",
            parent=self.top)
        dest = self.current_base if use_current else None
        replace = False
        if use_current:
            replace = messagebox.askyesno(
                "Importar Excel",
                "Substituir TODO o conteúdo da base atual?\n\n"
                "Sim = apaga as frases atuais e importa (config preservada).\n"
                "Não = só acrescenta as novas (seguro).",
                parent=self.top)
        try:
            res = self.rag_mgr.import_base_from_excel(
                path, base_name=dest, mode=("replace" if replace else "append"))
            self.bases = self.rag_mgr.get_all_bases()
            self.base_combo['values'] = self.bases
            if res["base"] in self.bases:
                self.base_combo.set(res["base"])
                self.current_base = res["base"]
                self.table_frame.config(text=f" Registros do Banco: {self.current_base} ")
            self.refresh_table_view()
            if self.on_update_callback:
                self.on_update_callback()
            messagebox.showinfo("Sucesso",
                f"Base '{res['base']}': {res['new']} nova(s), {res['skipped']} ignorada(s).",
                parent=self.top)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao importar:\n{e}", parent=self.top)

    def on_base_selected(self, event):
        self.current_base = self.base_combo.get()
        self.table_frame.config(text=f" Registros do Banco: {self.current_base} ")
        self.refresh_table_view()

    def create_new_base_dialog(self):
        dialog = tk.Toplevel(self.top)
        dialog.title("Criar Novo Banco de Frases")
        dialog.geometry("450x300")
        dialog.transient(self.top)
        dialog.grab_set()

        ttk.Label(dialog, text="Nome do Novo Banco:").pack(anchor=tk.W, padx=10, pady=5)
        name_entry = ttk.Entry(dialog, width=45)
        name_entry.pack(padx=10, pady=5)

        ttk.Label(dialog, text="Colunas (separadas por vírgula):").pack(anchor=tk.W, padx=10, pady=5)
        col_entry = ttk.Entry(dialog, width=45)
        col_entry.insert(0, "Frase_Original, Frase_Alvo, Contexto_Referencia")
        col_entry.pack(padx=10, pady=5)

        def save_new():
            name = name_entry.get().strip()
            cols = [c.strip() for c in col_entry.get().split(",") if c.strip()]
            if not name or not cols:
                return
            self.rag_mgr.create_new_base(name, cols)
            self.bases = self.rag_mgr.get_all_bases()
            self.base_combo['values'] = self.bases
            self.base_combo.set(name)
            self.current_base = name
            self.refresh_table_view()
            dialog.destroy()

        ttk.Button(dialog, text="✨ Criar Banco", command=save_new).pack(pady=15)

    def open_settings_dialog(self):
        """Como a IA usa ESTA base (tudo opcional; sem configurar = comportamento padrão)."""
        base = self.current_base
        columns = self.rag_mgr.get_base_columns(base)
        cur = self.rag_mgr.get_base_settings(base)

        dlg = tk.Toplevel(self.top)
        dlg.title(f"Configurar uso do banco: {base}")
        dlg.transient(self.top)
        dlg.grab_set()
        dlg.resizable(False, False)

        footer = ttk.Frame(dlg)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)

        mode_frame = ttk.LabelFrame(body, text=" Modo de uso ", padding=8)
        mode_frame.pack(fill=tk.X, pady=4)
        mode_var = tk.StringVar(value=cur["mode"])
        ttk.Radiobutton(mode_frame, variable=mode_var, value="support",
                        text="Apoio linguístico (a IA NÃO copia nem insere as frases; só se inspira em vocabulário/tom)").pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, variable=mode_var, value="classic",
                        text="Clássico (referência de frases, como era antes)").pack(anchor=tk.W)

        def _checks(parent, title, hint, selected):
            frame = ttk.LabelFrame(parent, text=f" {title} ", padding=8)
            frame.pack(fill=tk.X, pady=4)
            ttk.Label(frame, text=hint, foreground="gray").pack(anchor=tk.W)
            vars_ = {}
            row = ttk.Frame(frame)
            row.pack(fill=tk.X)
            for i, col in enumerate(columns):
                v = tk.BooleanVar(value=col in selected)
                vars_[col] = v
                ttk.Checkbutton(row, text=col, variable=v).grid(row=i // 3, column=i % 3, sticky="w", padx=6, pady=2)
            return vars_

        prompt_vars = _checks(
            body, "Colunas que vão para o prompt da IA",
            "Nenhuma marcada = todas. Ex.: marque só a coluna do idioma-alvo para a IA não ver o par original→tradução.",
            cur["prompt_columns"])
        search_vars = _checks(
            body, "Colunas usadas para BUSCAR o que é relevante",
            "Nenhuma marcada = todas. A busca compara o texto (e a tradução parcial dos agentes anteriores) com estas colunas.",
            cur["search_columns"])

        lim = ttk.LabelFrame(body, text=" Limites e filtros (opcionais — 0 = sem limite) ", padding=8)
        lim.pack(fill=tk.X, pady=4)

        def _spin(row, label, key, lo, hi, hint=""):
            ttk.Label(lim, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.IntVar(value=cur[key])
            ttk.Spinbox(lim, from_=lo, to=hi, width=8, textvariable=var).grid(row=row, column=1, padx=6, pady=2)
            if hint:
                ttk.Label(lim, text=hint, foreground="gray").grid(row=row, column=2, sticky="w")
            return var

        k_var = _spin(0, "Máx. de itens enviados à IA por agente:", "top_k", 0, 100000, "0 = todos os relevantes")
        chars_var = _spin(1, "Máx. de caracteres do bloco inteiro:", "max_chars", 0, 10000000, "0 = sem limite")
        clip_var = _spin(2, "Cortar cada célula em N caracteres:", "cell_clip", 0, 100000, "0 = não cortar")
        minlen_var = _spin(3, "Tamanho mínimo da palavra na busca:", "min_word_len", 1, 20, "palavras menores são ignoradas")
        common_var = _spin(4, "Ignorar termos presentes em mais de N% das linhas:", "common_pct", 0, 100, "0 = não ignorar (só vale com 8+ linhas)")
        stop_var = tk.BooleanVar(value=cur["use_stopwords"])
        ttk.Checkbutton(lim, text="Ignorar palavras muito comuns (de, que, with, that...)", variable=stop_var).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=2)

        def save():
            def _i(var, default):
                try:
                    return int(var.get())
                except (tk.TclError, ValueError):
                    return default
            self.rag_mgr.save_base_settings(base, {
                "mode": mode_var.get(),
                "prompt_columns": [c for c, v in prompt_vars.items() if v.get()],
                "search_columns": [c for c, v in search_vars.items() if v.get()],
                "top_k": _i(k_var, 0),
                "max_chars": _i(chars_var, 0),
                "cell_clip": _i(clip_var, 0),
                "min_word_len": _i(minlen_var, 4),
                "common_pct": _i(common_var, 50),
                "use_stopwords": bool(stop_var.get()),
            })
            dlg.destroy()

        ttk.Button(footer, text="💾 Salvar configuração", command=save).pack()

    def delete_current_base(self):
        if len(self.bases) <= 1:
            return
        if messagebox.askyesno("Confirmar", f"Excluir banco '{self.current_base}'?", parent=self.top):
            self.rag_mgr.delete_base(self.current_base)
            self.bases = self.rag_mgr.get_all_bases()
            self.base_combo['values'] = self.bases
            self.base_combo.set(self.bases[0])
            self.current_base = self.bases[0]
            self.refresh_table_view()

    def add_row_dialog(self):
        columns = self.rag_mgr.get_base_columns(self.current_base)
        dialog = tk.Toplevel(self.top)
        dialog.title("Adicionar Frase de Referência")
        dialog.geometry("450x400")
        dialog.transient(self.top)
        dialog.grab_set()

        entries = {}
        row = 0
        for col in columns:
            ttk.Label(dialog, text=f"{col}:").grid(row=row, column=0, sticky=tk.W, padx=10, pady=5)
            e = ttk.Entry(dialog, width=35)
            e.grid(row=row, column=1, padx=10, pady=5)
            entries[col] = e
            row += 1

        def save_row():
            vals = {col: entries[col].get().strip() for col in columns}
            self.rag_mgr.add_row_to_base(self.current_base, vals)
            self.refresh_table_view()
            dialog.destroy()

        ttk.Button(dialog, text="💾 Salvar", command=save_row).grid(row=row, column=0, columnspan=2, pady=15)

    def delete_selected_row(self):
        selected = self.tree.selection()
        if not selected:
            return
        row_id = self.tree.item(selected[0])['values'][0]
        if messagebox.askyesno("Confirmar", "Excluir frase?", parent=self.top):
            self.rag_mgr.delete_row_from_base(self.current_base, row_id)
            self.refresh_table_view()

    def edit_selected_row(self):
        """ADICAO: edita a frase selecionada (abre com valores atuais)."""
        try:
            selected = self.tree.selection()
        except Exception:
            selected = None
        if not selected:
            messagebox.showwarning("Aviso", "Selecione uma frase na lista para editar.",
                                   parent=self.top)
            return
        values = self.tree.item(selected[0])['values']
        try:
            row_id = int(values[0])
        except (TypeError, ValueError, IndexError):
            return
        columns = self.rag_mgr.get_base_columns(self.current_base)
        current = {col: (str(values[i + 1]) if i + 1 < len(values) else "")
                   for i, col in enumerate(columns)}
        dialog = tk.Toplevel(self.top)
        dialog.title("Editar Frase de Referência")
        dialog.geometry("450x400")
        dialog.transient(self.top)
        dialog.grab_set()

        entries = {}
        row = 0
        for col in columns:
            ttk.Label(dialog, text=f"{col}:").grid(row=row, column=0, sticky=tk.W, padx=10, pady=5)
            e = ttk.Entry(dialog, width=35)
            e.insert(0, current.get(col, ""))
            e.grid(row=row, column=1, padx=10, pady=5)
            entries[col] = e
            row += 1

        def save_edit():
            vals = {col: entries[col].get().strip() for col in columns}
            self.rag_mgr.update_row_in_base(self.current_base, row_id, vals)
            self.refresh_table_view()
            dialog.destroy()

        ttk.Button(dialog, text="💾 Salvar", command=save_edit).grid(row=row, column=0, columnspan=2, pady=15)

    def destroy(self):
        if self.on_update_callback:
            self.on_update_callback()
        self.top.destroy()
class ConfigManagerWindow:
    def __init__(self, parent, on_save_callback):
        self.top = tk.Toplevel(parent)
        self.top.title("⚙️ Gerenciamento de Chaves e Modelos")
        self.top.geometry("700x550")
        self.top.transient(parent)
        self.top.grab_set()

        self.on_save_callback = on_save_callback
        self.config_data = load_persistent_config()
        self.create_widgets()

    def _scrollable_tab(self, notebook, title):
        """Aba com rolagem (rodinha) — o conteúdo vai no frame retornado."""
        from app_ui.scroll_helper import make_scrollable_frame
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text=title)
        _o, _c, _s, body = make_scrollable_frame(tab)
        return body

    def create_widgets(self):
        notebook = ttk.Notebook(self.top)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        keys_frame = self._scrollable_tab(notebook, "🔑 Chaves de API")

        gdrive_frame = self._scrollable_tab(notebook, "📁 Google Drive & UI")

        # UI Language selection
        ttk.Label(gdrive_frame, text="Idioma da Interface (UI Language):").grid(row=0, column=0, sticky=tk.W, pady=5, padx=5)
        self.ui_lang_combo = ttk.Combobox(gdrive_frame, values=["Português", "Inglês", "Espanhol", "Japonês", "Russo"], width=20, state="readonly")
        current_ui_lang = self.config_data.get("interface_language", "Português")
        self.ui_lang_combo.set(current_ui_lang)
        self.ui_lang_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)

        ttk.Separator(gdrive_frame, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=10)

        gdrive_cfg = self.config_data.get("gdrive_config", {
            "credentials_json_path": "credentials.json",
            "glossary_link_or_id": "",
            "characters_link_or_id": ""
        })

        ttk.Label(gdrive_frame, text="Caminho credentials.json:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=5)
        self.cred_entry = ttk.Entry(gdrive_frame, width=45)
        self.cred_entry.insert(0, gdrive_cfg.get("credentials_json_path", "credentials.json"))
        self.cred_entry.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)
        ttk.Button(gdrive_frame, text="Procurar...", command=self.browse_credentials).grid(row=2, column=2, padx=5)

        ttk.Label(gdrive_frame, text="Link/ID Glossário (Drive 1):").grid(row=3, column=0, sticky=tk.W, pady=5, padx=5)
        self.g_glossary_entry = ttk.Entry(gdrive_frame, width=45)
        self.g_glossary_entry.insert(0, gdrive_cfg.get("glossary_link_or_id", ""))
        self.g_glossary_entry.grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)

        ttk.Label(gdrive_frame, text="Link/ID Personagens (Drive 2):").grid(row=4, column=0, sticky=tk.W, pady=5, padx=5)
        self.g_characters_entry = ttk.Entry(gdrive_frame, width=45)
        self.g_characters_entry.insert(0, gdrive_cfg.get("characters_link_or_id", ""))
        self.g_characters_entry.grid(row=4, column=1, sticky=tk.W, pady=5, padx=5)

        ttk.Label(gdrive_frame, text="ℹ️ Nota: Para usar o Google Drive, coloque o arquivo 'credentials.json'\nda sua API do Google Cloud na pasta do projeto e insira os links ou IDs das planilhas.", foreground="gray").grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=10, padx=5)

        self.key_entries = {}
        self.key_texts = {}
        row = 0
        for provider, key_val in self.config_data.get("api_keys", {}).items():
            ttk.Label(keys_frame, text=f"{provider.upper()}:", width=15).grid(row=row, column=0, sticky=tk.NW, pady=5, padx=5)
            # Multi-chaves: uma por linha. [0] = padrao (legado: string vira 1 linha).
            if isinstance(key_val, list):
                initial = "\n".join([k for k in key_val if isinstance(k, str)])
            else:
                initial = key_val or ""
            txt = tk.Text(keys_frame, width=52, height=3, wrap=tk.NONE)
            txt.insert("1.0", initial)
            txt.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
            self.key_texts[provider] = txt
            ttk.Label(keys_frame, text="(1 por linha;\n1ª = padrão)", foreground="gray").grid(row=row, column=2, sticky=tk.W, padx=5)
            row += 1

        models_frame = self._scrollable_tab(notebook, "🤖 Modelos Dinâmicos")

        prov_sel_frame = ttk.Frame(models_frame)
        prov_sel_frame.pack(fill=tk.X, pady=5)

        ttk.Label(prov_sel_frame, text="Provedor:").pack(side=tk.LEFT, padx=5)
        self.model_prov_combo = ttk.Combobox(prov_sel_frame, values=list(self.config_data.get("custom_models", {}).keys()), state="readonly", width=20)
        self.model_prov_combo.pack(side=tk.LEFT, padx=5)
        if self.model_prov_combo['values']:
            self.model_prov_combo.current(0)
        self.model_prov_combo.bind("<<ComboboxSelected>>", self.update_models_list)

        self.models_listbox = tk.Listbox(models_frame, height=10, width=60)
        self.models_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.update_models_list()

        add_model_frame = ttk.Frame(models_frame)
        add_model_frame.pack(fill=tk.X, pady=5)

        ttk.Label(add_model_frame, text="Novo Modelo:").pack(side=tk.LEFT, padx=5)
        self.new_model_entry = ttk.Entry(add_model_frame, width=30)
        self.new_model_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(add_model_frame, text="➕ Adicionar", command=self.add_model).pack(side=tk.LEFT, padx=5)
        ttk.Button(add_model_frame, text="🗑️ Remover", command=self.remove_model).pack(side=tk.LEFT, padx=5)

        footer = ttk.Frame(self.top)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=8)
        ttk.Separator(footer, orient="horizontal").pack(fill=tk.X, pady=(0, 8))
        ttk.Button(footer, text="💾 Salvar", command=self.save_all).pack()

    def update_models_list(self, event=None):
        self.models_listbox.delete(0, tk.END)
        prov = self.model_prov_combo.get()
        models = self.config_data.get("custom_models", {}).get(prov, [])
        for m in models:
            self.models_listbox.insert(tk.END, m)

    def add_model(self):
        prov = self.model_prov_combo.get()
        new_model = self.new_model_entry.get().strip()
        if not new_model:
            return
        models = self.config_data.setdefault("custom_models", {}).setdefault(prov, [])
        if new_model not in models:
            models.append(new_model)
            self.update_models_list()
            self.new_model_entry.delete(0, tk.END)

    def remove_model(self):
        try:
            selection = self.models_listbox.curselection()
            if not selection:
                return
            idx = selection[0]
            prov = self.model_prov_combo.get()
            self.config_data.get("custom_models", {}).get(prov, []).pop(idx)
            self.update_models_list()
        except Exception:
            pass

    def browse_credentials(self):
        file_path = filedialog.askopenfilename(
            title="Selecionar credentials.json do Google Cloud",
            filetypes=[("Arquivos JSON", "*.json")]
        )
        if file_path:
            self.cred_entry.delete(0, tk.END)
            self.cred_entry.insert(0, file_path)

    def save_all(self):
        # Multi-chaves globais: 1 por linha, 1a = padrao. Compativel: 1 chave vira lista de 1.
        for prov, txt in (getattr(self, "key_texts", {}) or {}).items():
            try:
                raw = txt.get("1.0", tk.END)
            except Exception:
                raw = ""
            keys = [l.strip() for l in raw.splitlines() if l.strip()]
            # Mantem compat com codigo antigo que espera string quando ha 1 chave:
            # salva lista sempre; leitura aceita str ou lista.
            self.config_data.setdefault("api_keys", {})[prov] = keys
        # Legado (caso a tela antiga ainda exista em algum backup): ignora.
        # BUGFIX: o combo de idioma existia na tela mas nunca era salvo,
        # por isso a troca de idioma "nao funcionava".
        try:
            new_lang = self.ui_lang_combo.get().strip()
        except Exception:
            new_lang = ""
        if new_lang:
            self.config_data["interface_language"] = new_lang
        # BUGFIX: campos do GDrive tambem nao eram salvos.
        try:
            gd = self.config_data.setdefault("gdrive_config", {})
            gd["credentials_json_path"] = self.cred_entry.get().strip() or "credentials.json"
            gd["glossary_link_or_id"] = self.g_glossary_entry.get().strip()
            gd["characters_link_or_id"] = self.g_characters_entry.get().strip()
        except Exception:
            pass
        save_persistent_config(self.config_data)
        try:
            msg = {"Português": "Configurações salvas!",
                   "Inglês": "Settings saved!",
                   "Espanhol": "¡Ajustes guardados!",
                   "Japonês": "設定を保存しました！",
                   "Russo": "Настройки сохранены!"}.get(new_lang or self.config_data.get("interface_language", "Português"),
                                                                      "Configurações salvas!")
        except Exception:
            msg = "Configurações salvas!"
        messagebox.showinfo("Sucesso", msg, parent=self.top)
        if self.on_save_callback:
            self.on_save_callback()
        self.top.destroy()


class BaseDescriptionWindow:
    """Popup de descrição de como a base (D1 Glossário / D2 Personagens) está
    organizada. O texto é do USUÁRIO; a IA só gera rascunho (nunca salva
    sozinha). Persistência e hash: base_schema.py."""

    def __init__(self, parent, glossary_path=None, characters_path=None,
                 on_saved=None, initial_kind="characters", reason=""):
        self.top = tk.Toplevel(parent)
        self.top.title("📝 Descrição da Base")
        self.top.geometry("640x520")
        self.top.transient(parent)
        self.top.grab_set()
        self.on_saved = on_saved
        self.glossary_path = glossary_path
        self.characters_path = characters_path
        self.reason = reason or ""
        cfg = load_persistent_config()
        self.schema_llm = cfg.get("base_schema_llm") or {}
        self.custom_models = cfg.get("custom_models") or {}
        self._orig_text = ""
        self._saved_text = ""
        self._draft_origin = "manual"
        self._building = False
        self._create_widgets()
        self.kind_combo.set(base_schema.KIND_LABELS.get(initial_kind, base_schema.KIND_LABELS["characters"]))
        self._load_kind()
        self.top.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- UI ---
    def _create_widgets(self):
        main = ttk.Frame(self.top, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(main)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Base:").pack(side=tk.LEFT)
        labels = [base_schema.KIND_LABELS["glossary"], base_schema.KIND_LABELS["characters"]]
        self.kind_combo = ttk.Combobox(top, values=labels, state="readonly", width=22)
        self.kind_combo.pack(side=tk.LEFT, padx=6)
        self.kind_combo.bind("<<ComboboxSelected>>", lambda e: self._load_kind())
        self.status_label = ttk.Label(top, text="", foreground="gray")
        self.status_label.pack(side=tk.LEFT, padx=8)

        ttk.Label(main, text=f"Descreva em poucas linhas o que cada coluna significa (máx. "
                             f"{base_schema.DESC_MAX_CHARS} caracteres). Este texto é repassado à IA "
                             "como ORIENTAÇÃO; as regras fixas do programa continuam valendo.",
                 foreground="gray", wraplength=600, justify=tk.LEFT).pack(fill=tk.X, pady=(8, 2))

        txt_frame = ttk.Frame(main)
        txt_frame.pack(fill=tk.BOTH, expand=True, pady=4)
        self.text = tk.Text(txt_frame, wrap=tk.WORD, height=10)
        scroll = ttk.Scrollbar(txt_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.bind("<<Modified>>", self._on_modified)

        self.counter_label = ttk.Label(main, text=f"0/{base_schema.DESC_MAX_CHARS}")
        self.counter_label.pack(anchor=tk.W)

        llm_frame = ttk.LabelFrame(main, text=" Rascunho com IA (opcional) ", padding=6)
        llm_frame.pack(fill=tk.X, pady=6)
        ttk.Label(llm_frame, text="Provedor:").pack(side=tk.LEFT)
        provs = list(self.custom_models.keys())
        self.prov_combo = ttk.Combobox(llm_frame, values=provs, state="readonly", width=16)
        self.prov_combo.pack(side=tk.LEFT, padx=4)
        ttk.Label(llm_frame, text="Modelo:").pack(side=tk.LEFT, padx=(8, 0))
        self.model_combo = ttk.Combobox(llm_frame, state="readonly", width=30)
        self.model_combo.pack(side=tk.LEFT, padx=4)
        self.prov_combo.bind("<<ComboboxSelected>>", self._on_prov_selected)
        self.draft_btn = ttk.Button(llm_frame, text="🤖 Gerar rascunho", command=self._generate_draft)
        self.draft_btn.pack(side=tk.LEFT, padx=8)
        if provs:
            saved_p = self.schema_llm.get("provider") or ""
            # Prefere o último usado; se ele não tem chave, cai no primeiro COM chave
            # (senão o "Gerar rascunho" abriria aviso de chave mesmo tendo outra válida).
            if saved_p in provs and base_schema.has_api_key(saved_p):
                start_p = saved_p
            else:
                start_p = next((p for p in provs if base_schema.has_api_key(p)), provs[0])
            self.prov_combo.set(start_p)
            self._on_prov_selected()

        btns = ttk.Frame(main)
        btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btns, text="💾 Salvar", command=self._save).pack(side=tk.LEFT)
        ttk.Button(btns, text="🗑️ Limpar descrição", command=self._clear).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Fechar", command=self._on_close).pack(side=tk.RIGHT)

    # ------------------------------------------------------------ lógica ---
    def _current_kind(self) -> str:
        label = self.kind_combo.get().strip()
        for k, v in base_schema.KIND_LABELS.items():
            if v == label:
                return k
        return "characters"

    def _current_path(self):
        return self.glossary_path if self._current_kind() == "glossary" else self.characters_path

    def _set_text(self, value: str):
        self._building = True
        try:
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", value or "")
        finally:
            self._building = False
        self._update_counter()

    def _update_counter(self):
        n = len(self.text.get("1.0", "end-1c"))
        maxc = base_schema.DESC_MAX_CHARS
        self.counter_label.config(text=f"{n}/{maxc}", foreground=("red" if n > maxc else "black"))

    def _on_modified(self, event=None):
        if self._building:
            return
        try:
            self.text.edit_modified(False)
        except Exception:
            pass
        self._update_counter()

    def _load_kind(self):
        kind = self._current_kind()
        path = self._current_path()
        st = base_schema.status(kind, path)
        texts = {
            "ok": ("✅ Descrição salva para esta planilha.", "green"),
            "missing": ("ℹ️ Sem descrição para esta planilha ainda.", "gray"),
            "stale": ("⚠️ A estrutura da planilha mudou desde a última descrição — revise e salve de novo.", "orange"),
            "no_sheet": ("⚠️ Nenhuma planilha deste tipo está carregada (selecione em 📁 D1/D2).", "orange"),
        }
        msg, color = texts.get(st, ("", "gray"))
        self.status_label.config(text=msg, foreground=color)
        desc = base_schema.get_description(kind, path) or {}
        self._saved_text = str(desc.get("text") or "")
        self._set_text(self._saved_text)
        self._orig_text = self._saved_text
        self._draft_origin = "manual"

    def _on_prov_selected(self, event=None):
        prov = self.prov_combo.get().strip()
        models = self.custom_models.get(prov) or []
        self.model_combo.config(values=list(models))
        saved_m = self.schema_llm.get("model") or ""
        self.model_combo.set(saved_m if saved_m in models else (models[0] if models else ""))

    def _generate_draft(self):
        kind = self._current_kind()
        path = self._current_path()
        if not path:
            messagebox.showwarning("Aviso", "Carregue primeiro uma planilha deste tipo (📁 D1/D2).",
                                   parent=self.top)
            return
        prov = self.prov_combo.get().strip()
        model = self.model_combo.get().strip()
        if not prov or not model:
            messagebox.showwarning("Aviso", "Escolha provedor e modelo para gerar o rascunho.",
                                   parent=self.top)
            return
        if not base_schema.has_api_key(prov):
            messagebox.showwarning("Aviso",
                                   f"Nenhuma chave configurada para '{prov}'.\n"
                                   "Adicione em ⚙️ Chaves & GDrive ou escreva a descrição manualmente.",
                                   parent=self.top)
            return
        self.draft_btn.config(state="disabled", text="Gerando…")
        self.top.update_idletasks()
        try:
            draft = base_schema.build_draft(kind, path, prov, model)
            if draft:
                self._set_text(draft)
                self._draft_origin = "ai"
                self.schema_llm = {"provider": prov, "model": model}
            else:
                messagebox.showwarning("Aviso",
                                       "A IA não retornou texto. Tente de novo ou escreva manualmente.",
                                       parent=self.top)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao gerar rascunho com a IA:\n{e}", parent=self.top)
        finally:
            self.draft_btn.config(state="normal", text="🤖 Gerar rascunho")

    def _save(self):
        kind = self._current_kind()
        path = self._current_path()
        text = self.text.get("1.0", "end-1c").strip()
        if len(text) > base_schema.DESC_MAX_CHARS:
            messagebox.showwarning("Aviso",
                                   f"O texto tem {len(text)} caracteres; o máximo é "
                                   f"{base_schema.DESC_MAX_CHARS}. Encurte antes de salvar.",
                                   parent=self.top)
            return
        if not path:
            messagebox.showwarning("Aviso", "Carregue primeiro uma planilha deste tipo (📁 D1/D2).",
                                   parent=self.top)
            return
        origin = "ai" if (self._draft_origin == "ai" and text == self.text.get("1.0", "end-1c").strip()) else "manual"
        log_msg = base_schema.save_description(kind, path, text, origin=origin)
        try:
            cfg = load_persistent_config()
            cfg["base_schema_llm"] = {"provider": self.prov_combo.get().strip(),
                                      "model": self.model_combo.get().strip()}
            save_persistent_config(cfg)
        except Exception:
            pass
        self._saved_text = text
        self._orig_text = text
        if self.on_saved:
            try:
                self.on_saved(log_msg)
            except Exception:
                pass
        self.top.destroy()

    def _clear(self):
        kind = self._current_kind()
        path = self._current_path()
        if not path:
            messagebox.showwarning("Aviso", "Carregue primeiro uma planilha deste tipo (📁 D1/D2).",
                                   parent=self.top)
            return
        if not messagebox.askyesno("Confirmar", "Remover a descrição salva desta planilha?",
                                   parent=self.top):
            return
        log_msg = base_schema.clear_description(kind, path)
        if self.on_saved:
            try:
                self.on_saved(log_msg)
            except Exception:
                pass
        self._load_kind()

    def _on_close(self):
        current = self.text.get("1.0", "end-1c").strip()
        if current != self._orig_text.strip() and not messagebox.askyesno(
                "Confirmar", "Há alterações não salvas. Fechar mesmo assim?", parent=self.top):
            return
        self.top.destroy()

