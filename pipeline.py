import os
import sqlite3
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class AgentConfig:
    name: str
    system_prompt: str = "Você é um tradutor literário especialista."
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 4000
    provider: str = "openai"

@dataclass
class PipelineConfig:
    source_language: str = "Inglês"
    target_language: str = "Português do Brasil"
    db_path: str = "local_knowledge.db"
    pov_mode: str = "Terceira Pessoa (ou Neutro)"
    narrator_name: str = ""

@dataclass
class PipelineResult:
    original_text: str
    target_language: str
    final_text: str
    steps_history: List[Dict[str, Any]] = field(default_factory=list)

class KnowledgeManager:
    """
    Gerencia a base de conhecimento local (SQLite) a partir de arquivos Excel.
    Implementa RAG Otimizado para Tradução (Busca inteligente por correspondência no texto).
    """
    def __init__(self, db_path: str = "local_knowledge.db"):
        self.db_path = db_path

    def reset_and_sync_from_excel(self, excel_path: str):
        print(f"\n[🔄 KnowledgeManager] Sincronizando com o arquivo Excel: {excel_path}")
        
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            print(f"   [🗑️] Banco de dados local antigo '{self.db_path}' resetado com sucesso.")

        try:
            xls = pd.ExcelFile(excel_path)
        except Exception as e:
            print(f"   [⚠️] Erro ao abrir arquivo Excel: {e}")
            self._create_empty_db()
            return

        conn = sqlite3.connect(self.db_path)
        
        if "Glossario" in xls.sheet_names:
            df_glossario = pd.read_excel(xls, sheet_name="Glossario")
            df_glossario.to_sql("glossario", conn, index=False, if_exists="replace")
            print(f"   [📚] Tabela 'glossario' recarregada com {len(df_glossario)} registros.")

        if "Personagens" in xls.sheet_names:
            df_personagens = pd.read_excel(xls, sheet_name="Personagens")
            df_personagens.to_sql("personagens", conn, index=False, if_exists="replace")
            print(f"   [👥] Tabela 'personagens' recarregada com {len(df_personagens)} registros.")

        conn.commit()
        conn.close()
        print("   [✨] Sincronização do Excel concluída com sucesso no banco local!")

    def _create_empty_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS glossario (termo_original TEXT, traducao_sugerida TEXT, contexto TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS personagens (nome TEXT, descricao TEXT, notas TEXT)")
        conn.commit()
        conn.close()

    def get_relevant_context(self, text_chunk: str) -> str:
        """
        RAG Otimizado: Busca apenas termos do glossário e personagens que aparecem 
        no texto do bloco/capítulo atual para economizar tokens.
        """
        if not os.path.exists(self.db_path):
            return "Nenhuma base de conhecimento carregada."

        conn = sqlite3.connect(self.db_path)
        text_lower = text_chunk.lower()
        relevant_summary = []
        matched_terms_count = 0
        matched_chars_count = 0

        # 1. Busca inteligente no Glossário (Verifica quais termos originais aparecem no texto)
        try:
            df_glossario = pd.read_sql("SELECT * FROM glossario", conn)
            matched_terms = []
            for _, row in df_glossario.iterrows():
                termo = str(row.get("termo_original", "")).strip()
                if termo and termo.lower() in text_lower:
                    matched_terms.append(f"- {termo} -> {row.get('traducao_sugerida', '')} (Contexto: {row.get('contexto', '')})")
                    matched_terms_count += 1
            
            if matched_terms:
                relevant_summary.append("--- GLOSSÁRIO FILTRADO (TERMOS IDENTIFICADOS NO TEXTO) ---")
                relevant_summary.extend(matched_terms)
        except Exception:
            pass

        # 2. Busca inteligente na Ficha de Personagens (Verifica quais nomes aparecem no texto)
        try:
            df_personagens = pd.read_sql("SELECT * FROM personagens", conn)
            matched_characters = []
            for _, row in df_personagens.iterrows():
                nome = str(row.get("nome", "")).strip()
                if nome and nome.lower() in text_lower:
                    matched_characters.append(f"- {nome}: {row.get('descricao', '')} | Notas: {row.get('notas', '')}")
                    matched_chars_count += 1
            
            if matched_characters:
                relevant_summary.append("\n--- FICHA DE PERSONAGENS IDENTIFICADOS ---")
                relevant_summary.extend(matched_characters)
        except Exception:
            pass

        conn.close()

        if not relevant_summary:
            return "Nenhum termo ou personagem específico do glossário/fichas foi detectado neste trecho."

        print(f"   [🔍 RAG Otimizado] Tokens economizados! Encontrados {matched_terms_count} termos de glossário e {matched_chars_count} personagens relevantes.")
        return "\n".join(relevant_summary)


class LLMProviderFactory:
    @staticmethod
    def call_llm(provider: str, model: str, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> str:
        provider_upper = provider.upper().strip()
        print(f"   [Provedor: {provider_upper}] Conectando ao modelo: {model} (Temp: {temperature})")
        return (
            f"[LLM Response | Provider: {provider_upper} | Model: {model}]\n"
            f"Prompt Analisado com RAG Contextual Otimizado.\n"
            f"Conteúdo processado:\n{user_prompt}"
        )


class TranslationAgent:
    def __init__(self, config: AgentConfig):
        self.config = config

    def execute(self, input_text: str, target_language: str, knowledge_context: str, original_source_text: str = "", pov_mode: str = "", narrator_name: str = "") -> str:
        print(f"\n[🔄 Agente: {self.config.name}]")
        print(f"   Model: {self.config.model} | Provider: {self.config.provider} | Target Lang: {target_language} | POV: {pov_mode} ({narrator_name})")
        
        strict_rule = (
            "REGRA ABSOLUTA E INQUEBRÁVEL DE FIDELIDADE: "
            "Você deve traduzir o texto mantendo rigorosamente a mesma estrutura de parágrafos, sem omitir nenhuma frase, "
            "termo ou informação essencial. A adaptação cultural de expressões idiomáticas, metáforas e coloquialismos para "
            "soar natural no idioma de destino é altamente encorajada e necessária, desde que o sentido e o enredo originais "
            "sejam perfeitamente preservados. Nunca invente fatos, personagens ou diálogos que não existam no original."
        )

        pov_instruction = ""
        if pov_mode and "Primeira" in pov_mode and narrator_name:
            pov_instruction = (
                f"\n=== ALERTA DE PONTO DE VISTA (POV) - 1ª PESSOA ===\n"
                f"Este texto é narrado em PRIMEIRA PESSOA pelo personagem: '{narrator_name}'. "
                f"Consulte atentamente a ficha deste personagem na Base de Conhecimento (gênero, tom, personalidade, concordância) "
                f"e garanta rigor absoluto na consistência de voz, pronomes e concordância gramatical para este narrador."
            )

        contextualized_prompt = (
            f"{self.config.system_prompt}\n\n"
            f"=== DIRETRIZ DE FIDELIDADE OBRIGATÓRIA ===\n"
            f"{strict_rule}"
            f"{pov_instruction}\n\n"
            f"=== BASE DE CONHECIMENTO RELEVANTE (RAG OTIMIZADO) ===\n"
            f"{knowledge_context}\n"
            f"====================================================\n"
            f"IMPORTANTE: O idioma de destino obrigatório para esta tradução é: {target_language}."
        )

        user_payload = input_text
        if original_source_text and original_source_text != input_text:
            user_payload = (
                f"=== TEXTO ORIGINAL DE REFERÊNCIA (ÂNCRAGEM OBRIGATÓRIA) ===\n"
                f"{original_source_text}\n\n"
                f"=== TEXTO/VERSÃO A SER PROCESSADO(A) NESTA ETAPA ===\n"
                f"{input_text}"
            )

        return LLMProviderFactory.call_llm(
            provider=self.config.provider,
            model=self.config.model,
            system_prompt=contextualized_prompt,
            user_prompt=user_payload,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens
        )


class LiteraryTranslationPipeline:
    def __init__(self, agents: List[AgentConfig], pipeline_config: Optional[PipelineConfig] = None):
        self.agents = [TranslationAgent(cfg) for cfg in agents]
        self.config = pipeline_config or PipelineConfig()
        self.knowledge_manager = KnowledgeManager(db_path=self.config.db_path)

    def sync_knowledge_from_excel(self, excel_path: str):
        self.knowledge_manager.reset_and_sync_from_excel(excel_path)

    def run(self, source_text: str) -> PipelineResult:
        knowledge_context = self.knowledge_manager.get_relevant_context(source_text)
        current_text = source_text
        history = []

        print(f"\n🚀 Iniciando Pipeline de Tradução Literária multi-provedor com RAG Otimizado")
        print(f"🎯 Idioma de Destino: {self.config.target_language}")
        print(f"🤖 Total de Agentes no Fluxo: {len(self.agents)}")
        print(f"📖 Texto Original:\n{source_text}\n" + "-"*50)

        for i, agent in enumerate(self.agents):
            step_input = current_text
            output_text = agent.execute(
                input_text=step_input, 
                target_language=self.config.target_language, 
                knowledge_context=knowledge_context,
                original_source_text=source_text,
                pov_mode=self.config.pov_mode,
                narrator_name=self.config.narrator_name
            )
            
            history.append({
                "step": i + 1,
                "agent_name": agent.config.name,
                "model": agent.config.model,
                "provider": agent.config.provider,
                "target_language": self.config.target_language,
                "input": step_input,
                "output": output_text
            })
            
            current_text = output_text

        print("\n" + "="*50)
        print("✨ Pipeline Multi-Agente com RAG Concluído com Sucesso!")
        return PipelineResult(
            original_text=source_text,
            target_language=self.config.target_language,
            final_text=current_text,
            steps_history=history
        )

if __name__ == "__main__":
    excel_filename = "livro_base_conhecimento.xlsx"
    with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
        pd.DataFrame({
            "termo_original": ["desolate valley", "forgotten empires", "crystal sword", "ancient dragon"],
            "traducao_sugerida": ["vale desolado", "impérios esquecidos", "espada de cristal", "dragão ancestral"],
            "contexto": ["Tom melancólico", "Maiúsculas", "Arma lendária", "Criatura mítica"]
        }).to_excel(writer, sheet_name="Glossario", index=False)
        
        pd.DataFrame({
            "nome": ["Narrador", "Elion", "Lyra"],
            "descricao": ["Voz reflexiva", "Guerreiro elfo corajoso", "Maga das sombras"],
            "notas": ["Impessoal", "Amigo do protagonista", "Guardiã do portal"]
        }).to_excel(writer, sheet_name="Personagens", index=False)

    agents = [
        AgentConfig(name="Agente 1: Tradução Inicial", model="deepseek-chat", provider="deepseek"),
        AgentConfig(name="Agente 2: Polimento", model="anthropic/claude-3.5-sonnet", provider="openrouter", temperature=0.7),
        AgentConfig(name="Agente 3: Revisão", model="gpt-4o", provider="openai", temperature=0.1)
    ]

    pipeline = LiteraryTranslationPipeline(agents=agents, pipeline_config=PipelineConfig(target_language="Português do Brasil"))
    pipeline.sync_knowledge_from_excel(excel_filename)
    
    book_excerpt = "The autumn wind whispered through the desolate valley, carrying memories of forgotten empires, while the Narrador watched in silence."
    result = pipeline.run(book_excerpt)
    
    print("\n📜 RESULTADO FINAL:\n", result.final_text)
