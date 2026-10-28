# -*- coding: utf-8 -*-
"""Sincronização com Google Drive (cópia fiel de gui.py)."""
import tkinter as tk
from tkinter import messagebox
try:
    from gdrive_integration import download_excel_from_gdrive
except Exception:  # dependência opcional (google-auth) pode faltar no python do sistema
    def download_excel_from_gdrive(*a, **k):
        raise RuntimeError("Google Drive indisponível: instale google-auth-oauthlib/google-api-python-client ou rode no venv do projeto.")
from knowledge_base import GlossaryManager, CharactersManager


class GDriveMixin:
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
            self.maybe_prompt_base_description("glossary", temp_path)
            try:
                self._autosave_session()
            except Exception:
                pass
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
            self.maybe_prompt_base_description("characters", temp_path)
            try:
                self._autosave_session()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Erro GDrive", f"Falha ao baixar Personagens do Google Drive:\n{e}")
            self.log_text.insert(tk.END, f"[❌ GDrive Erro] {e}\n")
