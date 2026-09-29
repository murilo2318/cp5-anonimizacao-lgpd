# CP5 · FIAP Bank · Anonimização de dados para exportação externa (LGPD)

Murilo Benhossi · RM 562358 · Tecnólogo em Inteligência Artificial · RPA aplicado com IA

Última etapa da esteira do robô do FIAP Bank: lê as manifestações, extrai campos estruturados com LLM (Gemini, com fallback para Groq), persiste tudo em SQLite e gera uma versão anonimizada do texto e do resumo, em colunas próprias, para exportação a uma consultoria externa. O dado original continua no banco.

## Estrutura

```
.
├── anonimizar_texto.py          # função com assinatura fixa (testada pelo professor)
├── CP5_Anonimizacao_LGPD.ipynb  # pipeline completo + auditoria + governança
├── rotulagem_manual.json        # rotulagem manual de PII dos 40 ids públicos
├── auditoria_resultado.json     # gerado pelo notebook (seção 8.5)
├── fiap_bank_cp5.db             # banco gerado pela execução (com fallback forçado)
├── data/manifestacoes_clientes_cp5.csv
├── tests/test_anonimizar_texto.py
├── requirements.txt
├── .env.example
└── .gitignore
```

## Como rodar do zero (local)

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m spacy download pt_core_news_lg

cp .env.example .env      # preencha GEMINI_API_KEY e GROQ_API_KEY
python3 -m pytest -q      # testes da função de anonimização
jupyter notebook CP5_Anonimizacao_LGPD.ipynb   # Run All
```

Para gerar o banco do zero, apague `fiap_bank_cp5.db` antes de rodar. Com o banco já existente, o pipeline não reprocessa nada (idempotência) e não gasta cota.

## Como rodar no Colab

1. Em **Secrets** (ícone de chave), crie `GEMINI_API_KEY` e `GROQ_API_KEY` e libere o acesso ao notebook.
2. Abra o notebook pelo GitHub e rode tudo. A primeira célula clona o repositório, instala as dependências e baixa o modelo do spaCy.

## Chaves de API

As chaves são lidas por `userdata.get()` no Colab ou por variável de ambiente / `.env` local. Nenhuma chave aparece no código, e `.env` está no `.gitignore`.

## Demonstração do fallback

Com `DEMONSTRAR_FALLBACK = True` (seção 1 do notebook), o Gemini falha de propósito, antes da chamada de rede, para os ids múltiplos de 3. Esses ids caem no Groq. A seção 5.2 comprova pelo próprio banco:

```sql
SELECT provedor, COUNT(*) FROM manifestacoes GROUP BY provedor;
```

## Modelo do spaCy

`anonimizar_texto.py` tenta, nesta ordem: variável `SPACY_MODEL`, `pt_core_news_lg`, `pt_core_news_md`, `pt_core_news_sm`. Se o spaCy não estiver instalado, a função não quebra: cai para regras de contexto e regex (qualidade menor para nomes).
