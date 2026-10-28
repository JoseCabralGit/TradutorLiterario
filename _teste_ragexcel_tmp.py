# -*- coding: utf-8 -*-
"""Teste temporario: export/import RAG (banco isolado)."""
import os
import pandas as pd
from knowledge_base import InternalRAGManager

db = "_teste_rag_tmp.db"
xlsx = "_teste_rag_tmp.xlsx"
for f in (db, xlsx):
    try:
        os.remove(f)
    except OSError:
        pass

m = InternalRAGManager(db_path=db)
m.create_new_base("Base_Teste", ["Frase_Original", "Frase_Alvo"])
m.save_base_settings("Base_Teste", {"mode": "support", "top_k": 7})
m.add_row_to_base("Base_Teste", {"Frase_Original": "Hello world", "Frase_Alvo": "Ola mundo"})
m.add_row_to_base("Base_Teste", {"Frase_Original": "Good night", "Frase_Alvo": "Boa noite"})

# 1) Export
res = m.export_base_to_excel("Base_Teste", xlsx)
assert res["rows"] == 2, res
xl = pd.ExcelFile(xlsx)
assert "frases" in xl.sheet_names and "_settings" in xl.sheet_names, xl.sheet_names
print("OK: export 2 linhas + aba _settings")

# 2) Import append na mesma base: tudo duplicado -> 0 novas
res2 = m.import_base_from_excel(xlsx, base_name="Base_Teste", mode="append")
assert res2 == {"base": "Base_Teste", "new": 0, "skipped": 2}, res2
print("OK: reimport pula duplicadas")

# 3) Import em base nova a partir do arquivo + settings restaurados
res3 = m.import_base_from_excel(xlsx, base_name="Base_Nova", mode="append")
assert res3["new"] == 2 and res3["skipped"] == 0, res3
s = m.get_base_settings("Base_Nova")
assert s["mode"] == "support" and s["top_k"] == 7, s
print("OK: base nova + settings restaurados")

# 4) Linha vazia ignorada; dado original intacto
df = pd.DataFrame([{"Frase_Original": "  ", "Frase_Alvo": ""},
                   {"Frase_Original": "Good morning", "Frase_Alvo": "Bom dia"}])
with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
    df.to_excel(w, sheet_name="frases", index=False)
res4 = m.import_base_from_excel(xlsx, base_name="Base_Teste", mode="append")
assert res4["new"] == 1 and res4["skipped"] == 1, res4
assert len(m.get_base_data("Base_Teste")) == 3
print("OK: linha vazia ignorada, originais intactos")

# 5) Busca continua funcionando apos import
txt, n = m.get_reference_context("good morning everyone", "Base_Teste")
assert n >= 1, (txt, n)
print("OK: BM25 pos-import")

for f in (db, xlsx):
    try:
        os.remove(f)
    except OSError:
        pass
print("TUDO OK")
