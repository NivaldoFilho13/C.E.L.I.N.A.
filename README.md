# C.E.L.I.N.A.

Pipeline simples e gratuito para criar um chatbot que responde perguntas
sobre o conteúdo dos seus PDFs, textos, planilhas e páginas da web, em
português, usando RAG (retrieval-augmented generation) e rodando em CPU.

Resumo rápido
- Coloque seus PDFs em `pdfs/`.
- Coloque arquivos .txt, .md, .docx, .csv ou .xlsx em `outros/`.
- Liste links (um por linha) em `urls.txt`.
- Rode `python extract_pdfs.py` e/ou `python extract_outros.py`.
- Rode `python build_index.py` → cria `data/index.faiss` e `data/docs.pkl`.
- Rode `python chat.py` (terminal) ou `streamlit run app.py` (interface web).
- Ou dê um duplo clique em `iniciar_celina.bat` para um menu com tudo isso.
- Ou, mais fácil ainda: pela própria interface web, use **📄 Enviar fontes**
  na barra lateral (arquivo, link ou texto colado) — não precisa nem abrir
  o terminal.

## Fontes suportadas

| Fonte | Onde colocar | O que precisa |
|---|---|---|
| PDF | `pdfs/` | nada extra |
| Texto (.txt, .md) | `outros/` | nada extra |
| Legenda (.srt) | `outros/` | nada extra |
| Word (.docx) | `outros/` | `pip install python-docx` (já no requirements.txt) |
| Planilha (.csv, .xlsx) | `outros/` | `pip install openpyxl` (já no requirements.txt) |
| Página da web | uma URL por linha em `urls.txt` | `pip install requests beautifulsoup4` (já no requirements.txt) |
| Artigo da Wikipédia | pela interface web, aba "Wikipédia" (ou títulos em `wikipedia.txt`) | `pip install requests` (já no requirements.txt) |
| Texto colado | pela interface web, aba "Colar texto" | nada extra |

Planilhas são divididas em blocos de ~20 linhas (cada linha formatada como
`coluna: valor`), então funcionam melhor para dados tabulares simples do
que para cálculos — a Celina não soma nem filtra números, ela busca texto
relevante para responder à pergunta.

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
- **Identidade visual própria**: logo da Celina, banner de cabeçalho e um
  tema de cores (roxo/azul escuro) aplicados na interface web — veja
  `assets/` e `.streamlit/config.toml`.
- **Múltiplas conversas**: a interface web agora tem uma barra lateral com
  "➕ Novo chat" e a lista de conversas salvas anteriormente — clique numa
  para reabri-la, ou no 🗑️ para apagá-la. Cada conversa é salva em
  `data/chats/` e sobrevive mesmo se você fechar o navegador ou o terminal.
- **Múltiplas fontes de conteúdo**: além de PDF, a Celina agora lê texto
  (.txt/.md), Word (.docx), planilhas (.csv/.xlsx) e páginas da web — veja
  a tabela "Fontes suportadas" no topo deste arquivo.
- **Envio de fontes pela interface**: não precisa mais rodar scripts no
  terminal — na barra lateral, "📄 Enviar fontes" tem 4 abas (arquivo,
  link, Wikipédia, colar texto). A Celina extrai o conteúdo e reconstrói o
  índice de busca sozinha.
- **Imagens ilustrativas**: `extract_pdfs.py` agora também extrai as
  figuras/diagramas embutidos em cada página do PDF (ignorando ícones
  pequenos, como marcadores de lista). Quando uma resposta usa uma página
  que tem imagens, elas aparecem junto com a resposta na interface web
  (no terminal, o caminho do arquivo é mostrado em texto).
- **OCR para PDFs escaneados**: quando uma página não tem texto
  selecionável (PDF de imagem/digitalizado), a Celina tenta reconhecer o
  texto via OCR automaticamente. Precisa do Tesseract-OCR instalado no
  sistema — veja "OCR" mais abaixo.
- **Memória de conversa**: perguntas de acompanhamento ("e sobre isso, o
  que mais diz?") agora usam as últimas trocas da conversa como contexto.
- **Threshold de confiança**: se a busca não encontrar nada realmente
  relevante, a Celina admite que não sabe em vez de forçar uma resposta
  fraca.
- **Modo "só citação"**: ative em ⚙️ Configurações da busca para receber o
  trecho original tal como está no documento, sem reescrita — útil quando
  a fidelidade exata ao texto importa.
- **Filtro por fonte**: restrinja a busca a um único PDF/arquivo/link
  específico, em vez de todas as fontes indexadas.
- **Seletor de modelo**: escolha entre um modelo mais rápido (0.5B), o
  equilibrado padrão (1.5B) ou um de mais qualidade (3B, mais lento).
- **Resposta no idioma da pergunta**: não força mais português — responde
  no mesmo idioma em que a pergunta foi feita.
- **Feedback 👍/👎**: avalie cada resposta; fica salvo em
  `data/feedback.jsonl` para você revisar depois.
- **Comandos de chat**: digite `/limpar` para começar do zero, ou
  `/fontes` para listar tudo que está indexado no momento.
- **Painel de estatísticas**: quantas perguntas você já fez e quais fontes
  são mais consultadas, na barra lateral.
- **Backup em um clique**: baixe um `.zip` com PDFs, outras fontes,
  conversas, regras e índice — útil pra levar pra outro PC.
- **Gerador de quiz**: escolha uma fonte na barra lateral e gere 5
  perguntas de múltipla escolha pra revisar o conteúdo.

- **Wikipédia como fonte**: na aba "Wikipédia" (dentro de "📄 Enviar
  fontes"), busque um termo, escolha os artigos encontrados e adicione-os
  permanentemente ao índice — igual a qualquer outra fonte.
- **Busca ao vivo na Wikipédia**: ative "Buscar na Wikipédia quando não
  achar nas fontes locais" em ⚙️ Configurações da busca — quando suas
  fontes locais não tiverem a resposta, a Celina busca ao vivo (precisa de
  internet) e deixa claro na fonte que a informação veio de fora dos seus
  documentos, não salvando nada automaticamente.
- **Gerador de quiz melhorado**: as perguntas agora são geradas a partir de
  uma janela contínua de trechos (na ordem original do documento, não mais
  espalhados aleatoriamente), e cada pergunta vem com 1-2 frases de
  contexto antes dela — pra fazer sentido mesmo sem ter lido o texto
  original.

Requisitos
- Python 3.8+
- (Opcional) Virtualenv/venv
- Internet na primeira execução para baixar modelos, e para as fontes que
  buscam da web (links, Wikipédia)

## OCR (PDFs escaneados)

O reconhecimento de texto em si (`pytesseract`) depende do **Tesseract-OCR**,
um programa separado que não vem pelo `pip` — precisa instalar à parte:

- **Windows**: baixe o instalador em
  https://github.com/UB-Mannheim/tesseract/wiki e marque a opção de
  adicionar ao PATH durante a instalação (ou adicione manualmente depois).
  Para reconhecer português, marque o pacote de idioma "Portuguese"
  durante a instalação.
- Depois de instalado, `python extract_pdfs.py` já tenta OCR
  automaticamente em páginas sem texto — não precisa configurar nada no
  código.
- Sem o Tesseract instalado, o OCR é simplesmente pulado (com um aviso no
  terminal) e o resto continua funcionando normalmente.

## O que NÃO foi incluído (e por quê)

Para manter o que foi entregue funcionando de forma confiável, ficaram de
fora por ora:

- **Reranking dos resultados** (um segundo modelo reordenando a busca) —
  precisa de mais um modelo e mais tempo de resposta; posso adicionar
  depois se fizer falta na prática.
- **Coleções separadas** (ex: índice só de Genética, outro só de Física) —
  mudança estrutural maior nos scripts; posso montar isso numa próxima
  rodada.
- **Indexação incremental** (só reprocessar o que é novo, em vez de tudo)
  — hoje `build_index.py` reconstrói o índice inteiro a cada vez; funciona
  bem até algumas centenas de páginas, mas fica lento em bases muito
  grandes.
- **Destacar o trecho exato dentro da imagem da página** — não é
  confiável sem mapear a posição exata do texto na imagem (precisaria de
  OCR com coordenadas), risco de marcar o lugar errado.
- **Tema claro/escuro**: não precisa de código — já vem pronto no menu
  "⋮" (canto superior direito) → **Settings** → **Choose app theme**.
- **Acesso de outros dispositivos na sua rede**: também não precisa de
  código, só rodar com um parâmetro extra:
  `streamlit run app.py --server.address 0.0.0.0` — depois acesse pelo
  IP do seu PC (ex: `http://192.168.0.x:8501`) a partir do celular/outro
  PC na mesma rede Wi-Fi.

Estrutura dos arquivos
- `requirements.txt` — dependências.
- `text_utils.py` — limpeza e divisão de texto em chunks (compartilhado).
- `extract_pdfs.py` — extrai texto/imagens dos PDFs (com OCR de apoio).
- `extract_outros.py` — extrai texto, Word, planilhas e páginas da web.
- `build_index.py` — gera embeddings e cria o índice FAISS.
- `chat.py` — funções principais do chat (busca, prompt, geração) e o
  loop de terminal.
- `app.py` — interface web (Streamlit) com todos os recursos.
- `pdfs/` — coloque aqui seus arquivos `.pdf`.
- `outros/` — coloque aqui `.txt`, `.md`, `.docx`, `.csv`, `.xlsx`.
- `urls.txt` — uma URL por linha, para páginas da web.
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

## Regras de formato das respostas

Edite o arquivo `regras.txt` (na raiz do projeto) para mudar como a Celina
formata as respostas — tamanho, estilo, se cita fonte, se usa listas, etc.
Cada linha do arquivo é uma regra; linhas em branco ou começando com `#`
são ignoradas. Exemplo do arquivo padrão:

```
Responda de forma objetiva, em poucas frases (no máximo 1 parágrafo curto).
Sempre cite a fonte entre colchetes (ex: [nome.pdf - página 3]) quando usar um trecho.
Use listas com marcadores quando a resposta tiver vários itens.
```

Essas regras são recarregadas a cada pergunta — você pode editar o arquivo
e testar na hora, sem reiniciar `chat.py` nem o Streamlit.

**Editar pela interface web:** na barra lateral do `app.py`, abra
"⚙️ Regras de formato das respostas" — dá pra editar o texto ali mesmo e
clicar em "💾 Salvar" (ou "↺ Padrão" para restaurar as regras originais),
sem precisar abrir nenhum editor de texto separado.

## Identidade visual

- `assets/logo.svg` — logo completa (com o nome "Celina"), usada como
  referência de marca.
- `assets/logo-emblem.svg` — versão só do emblema (sem texto), usada como
  ícone da aba do navegador e na barra lateral.
- `assets/banner.png` — imagem de fundo do cabeçalho da interface web.
- `.streamlit/config.toml` — define as cores do tema (roxo/azul escuro)
  usadas em toda a interface (botões, fundo, texto).

Para trocar a logo ou o banner, basta substituir os arquivos em `assets/`
mantendo os mesmos nomes — a interface lê esses arquivos automaticamente
ao iniciar.

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
