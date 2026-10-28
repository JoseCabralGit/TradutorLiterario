# -*- coding: utf-8 -*-
"""Teste temporario: update de linha RAG (banco isolado)."""
import os
from knowledge_base import InternalRAGManager

db = "_teste_ragedit_tmp.db"
try:
    os.remove(db)
except OSError:
    pass

m = InternalRAGManager(db_path=db)
m.create_new_base("B", ["Frase_Original", "Frase_Alvo"])
m.add_row_to_base("B", {"Frase_Original": "Hello world", "Frase_Alvo": "Ola mundo"})
df = m.get_base_data("B")
rid = int(df.iloc[0]["id"])
assert len(df) == 1

# Edita so 1 campo
m.update_row_in_base("B", rid, {"Frase_Original": "Hello world", "Frase_Alvo": "Olá, mundo!"})
df2 = m.get_base_data("B")
assert len(df2) == 1, "edicao nao pode criar/duplicar linha"
assert str(df2.iloc[0]["Frase_Alvo"]) == "Olá, mundo!", df2.iloc[0]["Frase_Alvo"]
assert str(df2.iloc[0]["Frase_Original"]) == "Hello world"
print("OK: edicao atualiza sem duplicar")

# Busca reflete a edicao
txt, n = m.get_reference_context("hello world", "B")
assert n >= 1 and "Ol" in txt, (txt, n)
print("OK: BM25 pos-edicao")

try:
    os.remove(db)
except OSError:
    pass
print("TUDO OK")
