# RAG Chat sobre PDFs (em Português) — Pipeline CPU grátis

Pipeline simples e gratuito para criar um chatbot que responde perguntas
sobre o conteúdo dos seus PDFs em português, usando RAG
(retrieval-augmented generation) e rodando em CPU.

Resumo rápido
- Coloque seus PDFs em `pdfs/`.
- Rode `python extract_pdfs.py` → gera `data/documents.jsonl` e `data/images/`.
- Rode `python build_index.py` → cria `data/index.faiss` e `data/docs.pkl`.
- Rode `python chat.py` (terminal) ou `streamlit run app.py` (interface web).

> **Se você já tinha rodado `extract_pdfs.py` numa versão anterior**, rode-o
> de novo — é nele que as imagens são extraídas pela primeira vez. Não
> precisa mexer nos PDFs, só rodar o script de novo.

## O que foi melhorado nesta versão

- **Chunking com overlap**: páginas longas agora são divididas em blocos de
  ~800 caracteres com 200 de sobreposição (tentando cortar em pontos finais
  de frase), em vez de indexar a página inteira de uma vez. Isso melhora
  bastante a precisão da busca.
- **Limpeza de texto**: remove quebras de linha e espaços repetidos que o
  `pypdf` costuma deixar na extração.
- **Prompt anti-alucinação**: o `chat.py` agora instrui explicitamente o
  modelo a dizer "não encontrei essa informação" quando os trechos
  recuperados não respondem à pergunta, em vez de inventar.
- **Fontes exibidas após cada resposta**: mostra de quais PDFs/páginas a
  resposta foi tirada, com a pontuação de relevância.
- **Tratamento de erros**: os três scripts agora avisam claramente quando
  faltam PDFs, o índice não foi gerado ainda, um PDF está corrompido, ou
  uma página não tem texto extraível (provavelmente escaneada).
- **Interface web (`app.py`)**: chat visual local via Streamlit, com
  histórico de conversa e fontes num menu expansível.
- **Imagens ilustrativas**: `extract_pdfs.py` agora também extrai as
  figuras/diagramas embutidos em cada página do PDF (ignorando ícones
  pequenos, como marcadores de lista). Quando uma resposta usa uma página
  que tem imagens, elas aparecem junto com a resposta na interface web
  (no terminal, o caminho do arquivo é mostrado em texto).

Requisitos
- Python 3.8+
- (Opcional) Virtualenv/venv
- Internet na primeira execução para baixar modelos

Estrutura dos arquivos
- `requirements.txt` — dependências.
- `extract_pdfs.py` — extrai texto das páginas dos PDFs, limpa, divide em
  chunks com overlap e salva em `data/documents.jsonl`.
- `build_index.py` — gera embeddings com `all-MiniLM-L6-v2` e cria índice
  FAISS (`data/index.faiss`) + metadados (`data/docs.pkl`).
- `chat.py` — loop de chat: recupera trechos relevantes, monta um prompt
  anti-alucinação e gera resposta com `google/flan-t5-small` (CPU),
  mostrando as fontes usadas.
- `pdfs/` — coloque aqui seus arquivos `.pdf`.
- `data/` — saída dos scripts (gerado automaticamente).

## Instalação (passo a passo)

1) Clone ou baixe os arquivos para uma pasta local.
2) Crie + ative um ambiente virtual:
- Linux/macOS:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```
- Windows (PowerShell):
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
3) Atualize pip e instale dependências:
```bash
pip install -U pip
pip install -r requirements.txt
```
Se `torch` demorar muito ou baixar uma versão gigante, veja a dica dentro
do `requirements.txt` para instalar a versão CPU-only primeiro.

## Uso

1) Coloque seus PDFs em `pdfs/` (crie a pasta se não existir).
2) Extrair PDFs:
```bash
python extract_pdfs.py
```
Saída: `data/documents.jsonl` com objetos `{"source", "page", "chunk", "text"}`.

3) Construir índice FAISS:
```bash
python build_index.py
```
Saída: `data/index.faiss` e `data/docs.pkl`.

4) Conversar (terminal):
```bash
python chat.py
```
- Digite perguntas em português.
- Cada resposta mostra as fontes (PDF + página) usadas.
- Para sair, digite `sair`, `exit` ou `quit`.

5) Ou conversar pela interface web (recomendado):
```bash
streamlit run app.py
```
Isso abre automaticamente uma aba no seu navegador com um chat visual —
com histórico da conversa na tela e as fontes de cada resposta num menu
expansível. Para encerrar, feche a aba e pressione `Ctrl+C` no terminal.

## Opções de modelo (trocas rápidas)

- Geração:
  - Rápido (recomendado para CPU): `google/flan-t5-small`
  - Mais qualidade (mais lento em CPU): `google/flan-t5-base`
  - Para GPU / maiores modelos: troque para outro checkpoint compatível
    com transformers.
- Embeddings:
  - Atual: `all-MiniLM-L6-v2` (rápido e gratuito)
  - Melhor semântica (se tiver recursos): modelos maiores de
    sentence-transformers ou embeddings da Hugging Face.
- Chunking:
  - Ajuste `CHUNK_SIZE` e `CHUNK_OVERLAP` no topo de `extract_pdfs.py`
    conforme o tipo de documento (textos mais técnicos costumam se
    beneficiar de chunks menores).

## Melhorias futuras possíveis

- OCR (Tesseract + pytesseract) para PDFs escaneados sem texto extraível.
- LangChain / LlamaIndex se quiser conversational memory e mais recursos.
- Modelos maiores/quantizados se tiver GPU disponível.
- Dockerfile para rodar tudo em container.

## Problemas comuns & solução rápida

- `Cannot import faiss` → instale `faiss-cpu` correto para seu sistema
  (pip pode falhar em Windows; use wheels pré-compilados ou use WSL).
- Textos em branco ao extrair PDFs → alguns PDFs são imagens (escaneados):
  use OCR antes de extrair. O script agora avisa quando isso acontece.
- Resultado incoerente → aumente `TOP_K` em `chat.py`, ou ajuste o
  `CHUNK_SIZE`/`CHUNK_OVERLAP` em `extract_pdfs.py`.

Licença
- Use livremente para fins pessoais/experimentais. Ajuste conforme sua
  necessidade.
