import base64
import io
import json
import os
import random
import re
import uuid
import zipfile
from collections import Counter
from datetime import datetime

import streamlit as st

import build_index
import extract_outros
import extract_pdfs
import imagens_web
from chat import (
    GEN_MODEL_PADRAO,
    LIMIAR_CONFIANCA_PADRAO,
    MODELOS_DISPONIVEIS,
    REGRAS_FILE,
    build_prompt,
    carregar_recursos,
    formatar_fontes,
    gerar_resposta,
    melhor_score,
    obter_imagens_dos_contextos,
    resposta_somente_citacao,
    retrieve,
)

TOP_K = 4
PDF_DIR = "pdfs"
OUTROS_DIR = "outros"
URLS_FILE = "urls.txt"
WIKI_FILE = "wikipedia.txt"
EXTENSOES_OUTROS = (".txt", ".md", ".docx", ".csv", ".xlsx", ".srt")

ASSETS_DIR = "assets"
LOGO_EMBLEMA_PATH = os.path.join(ASSETS_DIR, "logo-emblem.svg")
BANNER_PATH = os.path.join(ASSETS_DIR, "banner.png")

CHATS_DIR = os.path.join("data", "chats")
FEEDBACK_FILE = os.path.join("data", "feedback.jsonl")
STATS_FILE = os.path.join("data", "estatisticas.jsonl")

st.set_page_config(
    page_title="Celina",
    page_icon=LOGO_EMBLEMA_PATH if os.path.exists(LOGO_EMBLEMA_PATH) else "📚",
    layout="centered",
)


def _caminho_chat(chat_id: str) -> str:
    return os.path.join(CHATS_DIR, f"{chat_id}.json")


def novo_chat_id() -> str:
    return uuid.uuid4().hex[:12]


def gerar_titulo(mensagens: list[dict]) -> str:
    for msg in mensagens:
        if msg["role"] == "user":
            texto = msg["content"].strip()
            return texto[:40] + ("…" if len(texto) > 40 else "")
    return "Nova conversa"


def salvar_chat(chat_id: str, mensagens: list[dict]) -> None:
    os.makedirs(CHATS_DIR, exist_ok=True)
    dados = {
        "id": chat_id,
        "title": gerar_titulo(mensagens),
        "updated_at": datetime.now().isoformat(),
        "messages": mensagens,
    }
    with open(_caminho_chat(chat_id), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def carregar_chat(chat_id: str) -> list[dict]:
    caminho = _caminho_chat(chat_id)
    if not os.path.exists(caminho):
        return []
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f).get("messages", [])


def apagar_chat(chat_id: str) -> None:
    caminho = _caminho_chat(chat_id)
    if os.path.exists(caminho):
        os.remove(caminho)


def listar_chats() -> list[dict]:
    if not os.path.isdir(CHATS_DIR):
        return []

    resultado = []
    for fname in os.listdir(CHATS_DIR):
        if not fname.endswith(".json"):
            continue
        caminho = os.path.join(CHATS_DIR, fname)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
            resultado.append(
                {
                    "id": dados.get("id", fname[:-5]),
                    "title": dados.get("title") or "Nova conversa",
                    "updated_at": dados.get("updated_at", ""),
                }
            )
        except Exception:
            continue

    resultado.sort(key=lambda c: c["updated_at"], reverse=True)
    return resultado


REGRAS_PADRAO = (
    "Responda de forma objetiva, em poucas frases (no máximo 1 parágrafo curto).\n"
    "Sempre cite a fonte entre colchetes (ex: [nome.pdf - página 3]) quando usar um trecho.\n"
    "Use listas com marcadores quando a resposta tiver vários itens.\n"
)


def ler_regras_raw() -> str:
    if not os.path.exists(REGRAS_FILE):
        return REGRAS_PADRAO
    with open(REGRAS_FILE, "r", encoding="utf-8") as f:
        return f.read()


def salvar_regras_raw(texto: str) -> None:
    with open(REGRAS_FILE, "w", encoding="utf-8") as f:
        f.write(texto)


def salvar_arquivos_enviados(arquivos) -> tuple[int, int]:
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(OUTROS_DIR, exist_ok=True)

    qtd_pdfs = 0
    qtd_outros = 0
    for arquivo in arquivos:
        ext = os.path.splitext(arquivo.name)[1].lower()
        pasta = PDF_DIR if ext == ".pdf" else OUTROS_DIR
        caminho = os.path.join(pasta, arquivo.name)
        with open(caminho, "wb") as f:
            f.write(arquivo.getbuffer())
        if ext == ".pdf":
            qtd_pdfs += 1
        else:
            qtd_outros += 1

    return qtd_pdfs, qtd_outros


def salvar_links(texto_links: str) -> int:
    linhas_novas = [l.strip() for l in texto_links.splitlines() if l.strip()]
    if not linhas_novas:
        return 0

    existentes = set()
    if os.path.exists(URLS_FILE):
        with open(URLS_FILE, "r", encoding="utf-8") as f:
            existentes = {l.strip() for l in f if l.strip()}

    novos = [l for l in linhas_novas if l not in existentes]
    if novos:
        with open(URLS_FILE, "a", encoding="utf-8") as f:
            for link in novos:
                f.write(link + "\n")

    return len(novos)


def salvar_texto_colado(titulo: str, texto: str) -> str:
    os.makedirs(OUTROS_DIR, exist_ok=True)
    nome_base = "".join(c for c in titulo.strip() if c.isalnum() or c in " -_").strip()
    nome_base = nome_base.replace(" ", "_") or "texto_colado"
    nome_arquivo = f"{nome_base}.txt"
    caminho = os.path.join(OUTROS_DIR, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return nome_arquivo


def salvar_titulos_wikipedia(titulos: list[str]) -> int:
    """Acrescenta títulos de artigos da Wikipédia ao wikipedia.txt, sem duplicar."""
    if not titulos:
        return 0

    existentes = set()
    if os.path.exists(WIKI_FILE):
        with open(WIKI_FILE, "r", encoding="utf-8") as f:
            existentes = {l.strip() for l in f if l.strip()}

    novos = [t for t in titulos if t not in existentes]
    if novos:
        with open(WIKI_FILE, "a", encoding="utf-8") as f:
            for titulo in novos:
                f.write(titulo + "\n")

    return len(novos)


def processar_fontes() -> tuple[bool, str]:
    avisos = []
    algo_processado = False

    tem_pdfs = os.path.isdir(PDF_DIR) and any(
        f.lower().endswith(".pdf") for f in os.listdir(PDF_DIR)
    )
    if tem_pdfs:
        if extract_pdfs.main() == 0:
            algo_processado = True
        else:
            avisos.append("houve um problema extraindo os PDFs")

    tem_outros = os.path.isdir(OUTROS_DIR) and any(
        f.lower().endswith(EXTENSOES_OUTROS) for f in os.listdir(OUTROS_DIR)
    )
    tem_urls = os.path.exists(URLS_FILE) and any(
        l.strip() for l in open(URLS_FILE, encoding="utf-8")
    )
    tem_wiki = os.path.exists(WIKI_FILE) and any(
        l.strip() for l in open(WIKI_FILE, encoding="utf-8")
    )
    if tem_outros or tem_urls or tem_wiki:
        if extract_outros.main() == 0:
            algo_processado = True
        else:
            avisos.append(
                "houve um problema extraindo os outros arquivos/links/artigos"
            )

    if not algo_processado:
        return False, "Nenhuma fonte nova encontrada para processar."

    if build_index.main() != 0:
        return (
            False,
            "Falha ao construir o índice de busca (veja o terminal para detalhes).",
        )

    if avisos:
        return True, "Índice atualizado, mas " + " e ".join(
            avisos
        ) + " (veja o terminal)."
    return True, "Fontes processadas e índice atualizado com sucesso!"


def salvar_feedback(pergunta: str, resposta: str, nota: str) -> None:
    os.makedirs("data", exist_ok=True)
    registro = {
        "timestamp": datetime.now().isoformat(),
        "pergunta": pergunta,
        "resposta": resposta,
        "nota": nota,
    }
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def registrar_pergunta(pergunta: str, fontes: list[str]) -> None:
    os.makedirs("data", exist_ok=True)
    registro = {
        "timestamp": datetime.now().isoformat(),
        "pergunta": pergunta,
        "fontes": fontes,
    }
    with open(STATS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def carregar_estatisticas() -> dict:
    if not os.path.exists(STATS_FILE):
        return {"total_perguntas": 0, "fontes_mais_usadas": []}

    total = 0
    contador_fontes = Counter()
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registro = json.loads(linha)
            except json.JSONDecodeError:
                continue
            total += 1
            for fonte in registro.get("fontes", []):
                contador_fontes[fonte] += 1

    return {
        "total_perguntas": total,
        "fontes_mais_usadas": contador_fontes.most_common(5),
    }


def gerar_zip_backup() -> bytes:
    buffer = io.BytesIO()
    pastas = [PDF_DIR, OUTROS_DIR, "data", ASSETS_DIR]
    arquivos_soltos = [URLS_FILE, REGRAS_FILE, "requirements.txt"]

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for pasta in pastas:
            if not os.path.isdir(pasta):
                continue
            for raiz, _dirs, arquivos in os.walk(pasta):
                for nome in arquivos:
                    caminho_completo = os.path.join(raiz, nome)
                    zf.write(caminho_completo, caminho_completo)

        for arquivo in arquivos_soltos:
            if os.path.exists(arquivo):
                zf.write(arquivo, arquivo)

    return buffer.getvalue()


def buscar_resposta_wikipedia_ao_vivo(pergunta: str, max_chars: int = 3000):
    titulos = extract_outros.buscar_titulos_wikipedia(pergunta, limite=1)
    if not titulos:
        return []

    titulo = titulos[0]
    texto = extract_outros.extrair_wikipedia(titulo)
    if not texto:
        return []

    meta = {
        "source": f"Wikipédia: {titulo} (busca ao vivo, não verificado)",
        "page": 1,
        "chunk": 0,
    }
    return [(texto[:max_chars], meta, 1.0)]


def buscar_resposta_web_ao_vivo(
    pergunta: str, max_paginas: int = 2, max_chars_por_pagina: int = 2500
):
    urls = extract_outros.buscar_urls_duckduckgo(pergunta, limite=max_paginas)
    contextos = []
    for url in urls:
        texto = extract_outros.extrair_pagina_web(url)
        if texto:
            meta = {
                "source": f"Web: {url} (busca ao vivo, não verificado)",
                "page": 1,
                "chunk": 0,
            }
            contextos.append((texto[:max_chars_por_pagina], meta, 1.0))
    return contextos


def inserir_imagens_no_quiz(quiz_md: str, fonte: str) -> str:
    padrao = re.compile(r"^\*\*Imagem:\*\*[ \t]*(.*)$", re.MULTILINE | re.IGNORECASE)
    encontrou = {"n": 0}

    def trocar(m: re.Match) -> str:
        encontrou["n"] += 1
        termo = m.group(1).strip(" .()\"'")
        if not termo or termo.lower().startswith(("nenhum", "n/a", "sem imagem")):
            return ""
        imgs = imagens_web.buscar_imagens(termo, limite=1)
        return imagens_web.imagem_em_markdown(imgs[0]) if imgs else ""

    resultado = padrao.sub(trocar, quiz_md)

    if encontrou["n"] == 0:
        nome_fonte = os.path.splitext(fonte)[0]
        imgs = imagens_web.buscar_imagens(
            imagens_web.extrair_termo_busca(nome_fonte), limite=1
        )
        if imgs:
            resultado = (
                imagens_web.imagem_em_markdown(imgs[0]) + "\n\n---\n\n" + resultado
            )

    return resultado


def exibir_imagens_web(imagens: list[dict]) -> None:
    if not imagens:
        return
    cols = st.columns(min(len(imagens), 3))
    for i, img in enumerate(imagens):
        with cols[i % len(cols)]:
            st.image(
                img["url"], caption=imagens_web.legenda(img), use_container_width=True
            )


def gerar_quiz(
    gen_bundle,
    texts: list[str],
    metas: list[dict],
    fonte: str,
    n_perguntas: int = 5,
    com_imagens: bool = False,
) -> str:
    indices_fonte = [i for i, m in enumerate(metas) if m["source"] == fonte]
    indices_fonte.sort(key=lambda i: (metas[i]["page"], metas[i].get("chunk", 0)))

    if not indices_fonte:
        return "Não encontrei trechos dessa fonte para gerar o quiz."

    JANELA = min(len(indices_fonte), 12)
    inicio = random.randint(0, len(indices_fonte) - JANELA)
    janela_indices = indices_fonte[inicio : inicio + JANELA]
    trechos = "\n\n".join(texts[i] for i in janela_indices)

    linha_imagem = (
        "**Imagem:** (2 a 4 palavras-chave em português para buscar uma foto, "
        "mapa, gráfico ou diagrama que ilustre a questão; escreva 'nenhuma' "
        "se não fizer sentido)\n\n"
        if com_imagens
        else ""
    )

    prompt = (
        "Você é um elaborador de questões do ENEM (Exame Nacional do Ensino "
        f"Médio). Com base no texto abaixo, crie {n_perguntas} questões de "
        "múltipla escolha no ESTILO ENEM, seguindo estas regras obrigatórias:\n\n"
        "1. Cada questão começa com um TEXTO DE APOIO/CONTEXTUALIZAÇÃO de "
        "3-5 frases (uma situação-problema, uma citação, um cenário aplicado, "
        "ou uma síntese do trecho) que situe quem vai responder — nunca "
        "pergunte um fato isolado sem esse contexto.\n"
        "2. Depois do texto de apoio, escreva o COMANDO da questão (o que se "
        "pede), cobrando interpretação, relação de causa-efeito ou aplicação "
        "do conteúdo — não apenas memorização literal de uma frase do texto.\n"
        "3. Cada questão tem 5 alternativas, de (A) a (E), com APENAS UMA "
        "correta. As alternativas erradas devem ser plausíveis (erros "
        "conceituais comuns ou meias-verdades), nunca absurdas ou óbvias.\n"
        "4. Escreva no mesmo idioma do texto original.\n\n"
        "Formate cada questão em Markdown exatamente assim:\n\n"
        "**Questão N**\n\n"
        f"(texto de apoio/contextualização)\n\n{linha_imagem}"
        "(comando da questão)\n\n"
        "(A) ...\n(B) ...\n(C) ...\n(D) ...\n(E) ...\n\n"
        "**Gabarito:** (letra) — (justificativa breve, explicando também por "
        "que as principais alternativas erradas não servem)\n\n"
        "---\n\n"
        f"### Texto\n{trechos}"
    )

    try:
        quiz = gerar_resposta(gen_bundle, prompt, max_new_tokens=1500)
    except Exception as e:
        return f"Não consegui gerar o quiz: {e}"

    if com_imagens:
        quiz = inserir_imagens_no_quiz(quiz, fonte)
    return quiz


def corrigir_redacao(gen_bundle, tema: str, texto_redacao: str) -> str:
    prompt = (
        "Você é um corretor de redações do ENEM (Exame Nacional do Ensino "
        "Médio), avaliando um texto dissertativo-argumentativo. Avalie a "
        "redação abaixo seguindo os critérios oficiais das 5 competências do "
        "ENEM, cada uma valendo de 0 a 200 pontos (total de 0 a 1000):\n\n"
        "- Competência 1: domínio da norma culta da língua escrita (gramática, "
        "ortografia, pontuação, registro formal).\n"
        "- Competência 2: compreensão da proposta e desenvolvimento do tema "
        "dentro da estrutura dissertativo-argumentativa, usando repertório "
        "sociocultural.\n"
        "- Competência 3: seleção, organização e interpretação de "
        "informações, fatos, opiniões e argumentos em defesa de um ponto de "
        "vista.\n"
        "- Competência 4: uso de mecanismos linguísticos para construir a "
        "argumentação (coesão textual, conectivos, articulação entre "
        "parágrafos).\n"
        "- Competência 5: proposta de intervenção para o problema abordado, "
        "detalhada (agente, ação, meio/modo, efeito, finalidade) e que "
        "respeite os direitos humanos.\n\n"
        f"Tema da redação: {tema}\n\n"
        f"### Redação do candidato\n{texto_redacao}\n\n"
        "Responda em português, em Markdown, EXATAMENTE nesta estrutura:\n\n"
        "## Competência 1 — Norma culta\n**Nota:** X/200\n(justificativa, "
        "citando trechos problemáticos se houver)\n\n"
        "## Competência 2 — Compreensão do tema\n**Nota:** X/200\n"
        "(justificativa)\n\n"
        "## Competência 3 — Argumentação\n**Nota:** X/200\n(justificativa)\n\n"
        "## Competência 4 — Coesão textual\n**Nota:** X/200\n(justificativa)\n\n"
        "## Competência 5 — Proposta de intervenção\n**Nota:** X/200\n"
        "(justificativa; se não houver proposta de intervenção, isso deve "
        "reduzir bastante essa nota)\n\n"
        "## Nota final\n**X/1000**\n\n"
        "## Pontos fortes\n(lista com marcadores)\n\n"
        "## Sugestões de melhoria\n(lista com marcadores, específica e prática)"
    )

    try:
        return gerar_resposta(gen_bundle, prompt, max_new_tokens=1600)
    except Exception as e:
        return f"Não consegui corrigir a redação: {e}"


@st.cache_data
def carregar_como_data_uri(caminho: str) -> str | None:
    if not os.path.exists(caminho):
        return None

    ext = os.path.splitext(caminho)[1].lower()
    tipo_mime = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "application/octet-stream")

    with open(caminho, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{tipo_mime};base64,{b64}"


def aplicar_estilo() -> None:
    logo_uri = carregar_como_data_uri(LOGO_EMBLEMA_PATH)
    banner_uri = carregar_como_data_uri(BANNER_PATH)

    banner_css = (
        f"background-image: linear-gradient(180deg, rgba(27,16,48,0.35) 0%, "
        f"rgba(27,16,48,0.92) 100%), url('{banner_uri}');"
        if banner_uri
        else "background: linear-gradient(135deg, #1B1030 0%, #3A1A5C 100%);"
    )

    logo_html = (
        f'<img src="{logo_uri}" class="celina-hero-logo" />' if logo_uri else "📚"
    )

    st.markdown(
        f"""
        <style>
        .celina-hero {{
            {banner_css}
            background-size: cover;
            background-position: center 65%;
            border-radius: 18px;
            padding: 2.6rem 1.5rem 2rem 1.5rem;
            text-align: center;
            margin-bottom: 1.8rem;
            border: 1px solid rgba(159, 123, 255, 0.25);
            box-shadow: 0 8px 30px rgba(58, 26, 92, 0.35);
        }}
        .celina-hero-logo {{
            width: 76px;
            height: 76px;
            border-radius: 50%;
            box-shadow: 0 0 24px rgba(159, 123, 255, 0.55);
            margin-bottom: 0.8rem;
        }}
        .celina-hero-title {{
            font-size: 2.4rem;
            font-weight: 700;
            color: #F3EEFF;
            letter-spacing: 2px;
            margin: 0;
        }}
        .celina-hero-subtitle {{
            font-size: 0.95rem;
            color: #C9A8FF;
            letter-spacing: 3px;
            text-transform: uppercase;
            margin-top: 0.3rem;
        }}
        div[data-testid="stChatMessage"] {{
            border-radius: 14px;
            border: 1px solid rgba(159, 123, 255, 0.15);
        }}
        .stButton > button {{
            background: linear-gradient(135deg, #9F7BFF 0%, #5B8DEF 100%);
            color: #F3EEFF;
            border: none;
            border-radius: 10px;
        }}
        .stButton > button:hover {{
            background: linear-gradient(135deg, #6FD8FF 0%, #9F7BFF 100%);
            color: #1B1030;
        }}
        section[data-testid="stSidebar"] .stButton > button {{
            background: transparent;
            color: #F3EEFF;
            border: 1px solid rgba(159, 123, 255, 0.25);
            text-align: left;
            font-weight: 400;
        }}
        section[data-testid="stSidebar"] .stButton > button:hover {{
            background: rgba(159, 123, 255, 0.15);
            color: #F3EEFF;
        }}
        </style>

        <div class="celina-hero">
            {logo_html}
            <div class="celina-hero-title">C.E.L.I.N.A.</div>
            <div class="celina-hero-subtitle">Inteligência Artificial · Nivaldo Filho &copy; 2026</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(
    show_spinner="Carregando modelos do Celina... (pode demorar na 1ª vez)"
)
def carregar(gen_model: str):
    return carregar_recursos(gen_model)


def renderizar_sidebar(fontes_disponiveis: list[str]) -> None:
    with st.sidebar:
        logo_uri = carregar_como_data_uri(LOGO_EMBLEMA_PATH)
        if logo_uri:
            st.markdown(
                f'<img src="{logo_uri}" style="width:56px;border-radius:50%;'
                f'box-shadow:0 0 16px rgba(159,123,255,0.5);margin-bottom:0.6rem;" />',
                unsafe_allow_html=True,
            )

        if st.button("➕ Novo chat", use_container_width=True):
            st.session_state.chat_id = novo_chat_id()
            st.session_state.historico = []
            st.rerun()

        with st.expander(
            "Enviar fontes", expanded=not os.path.exists("data/index.faiss")
        ):
            aba_arquivo, aba_link, aba_wiki, aba_texto = st.tabs(
                ["Arquivo", "Link", "Wikipédia", "Colar texto"]
            )

            with aba_arquivo:
                arquivos = st.file_uploader(
                    "PDF, TXT, MD, DOCX, CSV, XLSX ou SRT",
                    type=["pdf", "txt", "md", "docx", "csv", "xlsx", "srt"],
                    accept_multiple_files=True,
                    key="upload_arquivos",
                )
                if st.button(
                    "Processar arquivos",
                    use_container_width=True,
                    disabled=not arquivos,
                ):
                    salvar_arquivos_enviados(arquivos)
                    with st.spinner("Processando arquivo(s)..."):
                        sucesso, mensagem = processar_fontes()
                    if sucesso:
                        carregar.clear()
                        st.success(mensagem)
                        st.rerun()
                    else:
                        st.error(mensagem)

            with aba_link:
                texto_links = st.text_area(
                    "Um link por linha",
                    placeholder="https://exemplo.com/artigo\nhttps://exemplo.com/outra-pagina",
                    key="input_links",
                )
                if st.button(
                    "Processar links",
                    use_container_width=True,
                    disabled=not texto_links.strip(),
                ):
                    qtd_novos = salvar_links(texto_links)
                    if qtd_novos == 0:
                        st.warning(
                            "Nenhum link novo (já estavam salvos ou o campo está vazio)."
                        )
                    else:
                        with st.spinner(
                            f"Baixando e processando {qtd_novos} link(s)..."
                        ):
                            sucesso, mensagem = processar_fontes()
                        if sucesso:
                            carregar.clear()
                            st.success(mensagem)
                            st.rerun()
                        else:
                            st.error(mensagem)

            with aba_wiki:
                termo_busca = st.text_input(
                    "Buscar na Wikipédia",
                    placeholder="ex: fotossíntese",
                    key="busca_wiki_termo",
                )
                if st.button(
                    "🔍 Buscar",
                    use_container_width=True,
                    disabled=not termo_busca.strip(),
                ):
                    with st.spinner("Buscando na Wikipédia..."):
                        st.session_state["resultados_wiki"] = (
                            extract_outros.buscar_titulos_wikipedia(termo_busca)
                        )

                resultados_wiki = st.session_state.get("resultados_wiki", [])
                if resultados_wiki:
                    selecionados = st.multiselect(
                        "Artigos encontrados — escolha quais adicionar", resultados_wiki
                    )
                    if st.button(
                        "Adicionar e processar",
                        use_container_width=True,
                        disabled=not selecionados,
                    ):
                        qtd_novos = salvar_titulos_wikipedia(selecionados)
                        if qtd_novos == 0:
                            st.warning("Esses artigos já estavam salvos.")
                        else:
                            with st.spinner(
                                f"Baixando e processando {qtd_novos} artigo(s)..."
                            ):
                                sucesso, mensagem = processar_fontes()
                            if sucesso:
                                carregar.clear()
                                st.success(mensagem)
                                st.session_state.pop("resultados_wiki", None)
                                st.rerun()
                            else:
                                st.error(mensagem)
                elif termo_busca:
                    st.caption("Clique em Buscar para ver os artigos disponíveis.")

            with aba_texto:
                titulo_texto = st.text_input(
                    "Nome para essa fonte", placeholder="ex: anotacoes-aula-5"
                )
                texto_colado = st.text_area(
                    "Cole o texto aqui", height=140, key="input_texto_colado"
                )
                if st.button(
                    "Processar texto",
                    use_container_width=True,
                    disabled=not texto_colado.strip() or not titulo_texto.strip(),
                ):
                    salvar_texto_colado(titulo_texto, texto_colado)
                    with st.spinner("Processando texto..."):
                        sucesso, mensagem = processar_fontes()
                    if sucesso:
                        carregar.clear()
                        st.success(mensagem)
                        st.rerun()
                    else:
                        st.error(mensagem)

        st.divider()
        st.markdown("**Conversas**")
        chats = listar_chats()

        if not chats:
            st.caption("Nenhuma conversa salva ainda.")
        else:
            for chat in chats:
                col_titulo, col_apagar = st.columns([5, 1])
                selecionado = chat["id"] == st.session_state.get("chat_id")
                rotulo = ("➤ " if selecionado else "") + chat["title"]

                with col_titulo:
                    if st.button(
                        rotulo, key=f"abrir_{chat['id']}", use_container_width=True
                    ):
                        st.session_state.chat_id = chat["id"]
                        st.session_state.historico = carregar_chat(chat["id"])
                        st.rerun()

                with col_apagar:
                    if st.button("🗑️", key=f"apagar_{chat['id']}"):
                        apagar_chat(chat["id"])
                        if st.session_state.get("chat_id") == chat["id"]:
                            st.session_state.chat_id = novo_chat_id()
                            st.session_state.historico = []
                        st.rerun()

        st.divider()
        with st.expander("Configurações da busca"):
            nomes_modelos = list(MODELOS_DISPONIVEIS.keys())
            modelo_atual = st.session_state.get("modelo_nome", nomes_modelos[1])
            escolha = st.selectbox(
                "Modelo de geração",
                nomes_modelos,
                index=nomes_modelos.index(modelo_atual),
            )
            st.session_state.modelo_nome = escolha
            st.session_state.gen_model = MODELOS_DISPONIVEIS[escolha]

            opcoes_fonte = ["Todas as fontes"] + fontes_disponiveis
            fonte_escolhida = st.selectbox("Restringir busca a uma fonte", opcoes_fonte)
            st.session_state.fonte_filtro = (
                None if fonte_escolhida == "Todas as fontes" else fonte_escolhida
            )

            st.session_state.modo_citacao = st.toggle(
                "Modo 'só citação' (devolve o trecho original, sem reescrever)",
                value=st.session_state.get("modo_citacao", False),
            )

            st.session_state.imagens_web = st.toggle(
                "Trazer imagens da internet nas respostas",
                value=st.session_state.get("imagens_web", False),
                help="Busca imagens relacionadas à sua pergunta no Wikimedia Commons "
                "(grátis, com crédito do autor). Precisa de internet.",
            )

            opcoes_fallback = ["Nenhuma", "Wikipédia (grátis)", "Busca na web (grátis)"]
            padrao_fallback = st.session_state.get("fallback_externo", "Nenhuma")
            st.session_state.fallback_externo = st.selectbox(
                "Buscar externamente quando não achar nas fontes locais",
                opcoes_fallback,
                index=opcoes_fallback.index(padrao_fallback)
                if padrao_fallback in opcoes_fallback
                else 0,
                help="Wikipédia busca só um artigo. 'Busca na web' pesquisa no "
                "DuckDuckGo e lê as páginas mais relevantes — bom para temas amplos "
                "e atuais (geoeconomia, atualidades, temas sociais). Ambas são "
                "gratuitas, sem precisar de chave de API, mas precisam de internet.",
            )

        with st.expander("Regras de formato das respostas"):
            texto_regras = st.text_area(
                "Uma regra por linha (linhas com # são ignoradas):",
                value=ler_regras_raw(),
                height=180,
                key="editor_regras",
            )
            col_salvar, col_restaurar = st.columns(2)
            with col_salvar:
                if st.button("Salvar", use_container_width=True):
                    salvar_regras_raw(texto_regras)
                    st.success("Regras salvas!")
            with col_restaurar:
                if st.button("↺ Padrão", use_container_width=True):
                    salvar_regras_raw(REGRAS_PADRAO)
                    st.rerun()

        if fontes_disponiveis:
            with st.expander("Gerar quiz (estilo Enem)"):
                fonte_quiz = st.selectbox("Fonte", fontes_disponiveis, key="fonte_quiz")
                n_perguntas_quiz = st.slider(
                    "Quantidade de questões", 1, 10, 5, key="n_quiz"
                )
                quiz_com_imagens = st.checkbox(
                    "Ilustrar questões com imagens da internet",
                    value=True,
                    key="quiz_imagens",
                    help="Busca imagens no Wikimedia Commons (grátis). Precisa de internet; "
                    "sem conexão, o quiz sai normal, só sem imagens.",
                )
                if st.button(
                    "Gerar quiz", use_container_width=True, key="btn_gerar_quiz"
                ):
                    with st.spinner("Gerando questões no estilo Enem..."):
                        quiz = gerar_quiz(
                            st.session_state["_gen_bundle"],
                            st.session_state["_texts"],
                            st.session_state["_metas"],
                            fonte_quiz,
                            n_perguntas=n_perguntas_quiz,
                            com_imagens=quiz_com_imagens,
                        )
                    st.session_state.historico.append(
                        {
                            "role": "user",
                            "content": f"🧠 Gerar quiz estilo Enem sobre: {fonte_quiz}",
                        }
                    )
                    st.session_state.historico.append(
                        {"role": "assistant", "content": quiz}
                    )
                    salvar_chat(st.session_state.chat_id, st.session_state.historico)
                    st.rerun()

        with st.expander("Corrigir redação (estilo Enem)"):
            gen_bundle_pronto = "_gen_bundle" in st.session_state
            st.caption(
                "Correção automática com o modelo local, seguindo as 5 competências "
                "oficiais do Enem (0 a 200 pontos cada, total até 1000). É um apoio "
                "de estudo — não substitui a avaliação de um professor."
            )
            if not gen_bundle_pronto:
                st.caption(
                    "⚠️ Processe pelo menos uma fonte primeiro para habilitar esta função."
                )

            tema_redacao = st.text_input(
                "Tema/proposta da redação",
                placeholder="ex: Desafios para a valorização de comunidades tradicionais no Brasil",
                key="tema_redacao",
                disabled=not gen_bundle_pronto,
            )
            texto_redacao = st.text_area(
                "Cole o texto da redação",
                height=200,
                key="texto_redacao",
                disabled=not gen_bundle_pronto,
            )
            if st.button(
                "Corrigir redação",
                use_container_width=True,
                key="btn_corrigir_redacao",
                disabled=not gen_bundle_pronto
                or not tema_redacao.strip()
                or not texto_redacao.strip(),
            ):
                with st.spinner("Corrigindo pelas 5 competências do Enem..."):
                    correcao = corrigir_redacao(
                        st.session_state["_gen_bundle"], tema_redacao, texto_redacao
                    )
                st.session_state.historico.append(
                    {
                        "role": "user",
                        "content": f"Corrigir redação — Tema: {tema_redacao}\n\n{texto_redacao}",
                    }
                )
                st.session_state.historico.append(
                    {"role": "assistant", "content": correcao}
                )
                salvar_chat(st.session_state.chat_id, st.session_state.historico)
                st.rerun()

        with st.expander("Estatísticas"):
            stats = carregar_estatisticas()
            st.metric("Perguntas feitas", stats["total_perguntas"])
            if stats["fontes_mais_usadas"]:
                st.caption("Fontes mais consultadas:")
                for fonte, qtd in stats["fontes_mais_usadas"]:
                    st.write(f"- {fonte} ({qtd}x)")

        with st.expander("Backup"):
            st.caption(
                "Baixe seus PDFs, outras fontes, conversas, regras e índice num único .zip."
            )
            if st.button("Gerar arquivo de backup", use_container_width=True):
                dados_zip = gerar_zip_backup()
                st.download_button(
                    "⬇Baixar backup.zip",
                    data=dados_zip,
                    file_name=f"celina_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        st.divider()
        st.subheader("Sobre a Celina")
        st.write(
            "Busca os trechos mais relevantes das suas fontes e usa um modelo "
            "local para responder com base neles. Comandos: `/limpar`, `/fontes`."
        )


def main() -> None:
    aplicar_estilo()

    if "chat_id" not in st.session_state:
        chats_existentes = listar_chats()
        if chats_existentes:
            st.session_state.chat_id = chats_existentes[0]["id"]
            st.session_state.historico = carregar_chat(st.session_state.chat_id)
        else:
            st.session_state.chat_id = novo_chat_id()
            st.session_state.historico = []

    gen_model = st.session_state.get("gen_model", GEN_MODEL_PADRAO)

    try:
        index, embedder, gen_bundle, texts, metas, indice_imagens = carregar(gen_model)
    except SystemExit:
        renderizar_sidebar([])
        st.info(
            "Nenhuma fonte indexada ainda. Use **📄 Enviar fontes**, na barra "
            "lateral, para enviar PDFs, textos, planilhas ou links e criar o índice de busca."
        )
        return

    st.session_state["_gen_bundle"] = gen_bundle
    st.session_state["_texts"] = texts
    st.session_state["_metas"] = metas

    fontes_disponiveis = sorted({m["source"] for m in metas})
    renderizar_sidebar(fontes_disponiveis)

    fonte_filtro = st.session_state.get("fonte_filtro")
    modo_citacao = st.session_state.get("modo_citacao", False)
    for idx, msg in enumerate(st.session_state.historico):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("imagens"):
                cols = st.columns(min(len(msg["imagens"]), 3))
                for i, caminho in enumerate(msg["imagens"]):
                    with cols[i % len(cols)]:
                        st.image(caminho, use_container_width=True)
            exibir_imagens_web(msg.get("imagens_web", []))
            if msg.get("fontes"):
                with st.expander("Fontes consultadas"):
                    for fonte in msg["fontes"]:
                        st.markdown(f"- {fonte}")
            if msg["role"] == "assistant" and not msg.get("feedback_dado"):
                col_up, col_down, _resto = st.columns([1, 1, 8])
                with col_up:
                    if st.button("👍", key=f"up_{idx}"):
                        pergunta_anterior = (
                            st.session_state.historico[idx - 1]["content"]
                            if idx > 0
                            else ""
                        )
                        salvar_feedback(pergunta_anterior, msg["content"], "positiva")
                        msg["feedback_dado"] = True
                        salvar_chat(
                            st.session_state.chat_id, st.session_state.historico
                        )
                        st.rerun()
                with col_down:
                    if st.button("👎", key=f"down_{idx}"):
                        pergunta_anterior = (
                            st.session_state.historico[idx - 1]["content"]
                            if idx > 0
                            else ""
                        )
                        salvar_feedback(pergunta_anterior, msg["content"], "negativa")
                        msg["feedback_dado"] = True
                        salvar_chat(
                            st.session_state.chat_id, st.session_state.historico
                        )
                        st.rerun()

    pergunta = st.chat_input("Pergunte algo, ou use /limpar, /fontes...")

    if pergunta:
        comando = pergunta.strip().lower()

        if comando == "/limpar":
            st.session_state.historico = []
            salvar_chat(st.session_state.chat_id, st.session_state.historico)
            st.rerun()

        if comando == "/fontes":
            st.session_state.historico.append({"role": "user", "content": pergunta})
            lista = (
                "\n".join(f"- {f}" for f in fontes_disponiveis)
                or "Nenhuma fonte indexada."
            )
            st.session_state.historico.append(
                {
                    "role": "assistant",
                    "content": f"Fontes indexadas atualmente:\n{lista}",
                }
            )
            salvar_chat(st.session_state.chat_id, st.session_state.historico)
            st.rerun()

        st.session_state.historico.append({"role": "user", "content": pergunta})
        with st.chat_message("user"):
            st.markdown(pergunta)

        with st.chat_message("assistant"):
            with st.spinner("Buscando nas fontes e gerando resposta..."):
                contextos = retrieve(
                    index,
                    embedder,
                    texts,
                    metas,
                    pergunta,
                    k=TOP_K,
                    fonte_filtro=fonte_filtro,
                )
                usar_local = (
                    bool(contextos)
                    and melhor_score(contextos) >= LIMIAR_CONFIANCA_PADRAO
                )

                resposta = None
                fontes: list[str] = []
                imagens: list[str] = []

                if usar_local:
                    if modo_citacao:
                        resposta = resposta_somente_citacao(contextos)
                        fontes = formatar_fontes(contextos).split("\n")
                    else:
                        prompt = build_prompt(
                            contextos,
                            pergunta,
                            historico=st.session_state.historico[:-1],
                        )
                        try:
                            resposta = gerar_resposta(gen_bundle, prompt)
                        except Exception as e:
                            resposta = f"Tive um problema ao gerar a resposta: {e}"

                        vistos = set()
                        for _texto, meta, score in contextos:
                            chave = (meta["source"], meta["page"])
                            if chave in vistos:
                                continue
                            vistos.add(chave)
                            fontes.append(
                                f"{meta['source']} (página {meta['page']}, relevância {score:.2f})"
                            )

                    imagens = obter_imagens_dos_contextos(contextos, indice_imagens)
                    fontes_para_stats = [m["source"] for _t, m, _s in contextos]

                else:
                    modo_fallback = st.session_state.get("fallback_externo", "Nenhuma")
                    fontes_para_stats = []

                    if modo_fallback.startswith("Wikipédia"):
                        contextos_wiki = buscar_resposta_wikipedia_ao_vivo(pergunta)
                        if contextos_wiki:
                            if modo_citacao:
                                resposta = resposta_somente_citacao(contextos_wiki)
                                fontes = formatar_fontes(contextos_wiki).split("\n")
                            else:
                                prompt = build_prompt(
                                    contextos_wiki,
                                    pergunta,
                                    historico=st.session_state.historico[:-1],
                                )
                                try:
                                    resposta = gerar_resposta(gen_bundle, prompt)
                                except Exception as e:
                                    resposta = (
                                        f"Tive um problema ao gerar a resposta: {e}"
                                    )
                                fontes = [m["source"] for _t, m, _s in contextos_wiki]
                            fontes_para_stats = fontes

                    elif modo_fallback.startswith("Busca na web"):
                        contextos_web = buscar_resposta_web_ao_vivo(pergunta)
                        if contextos_web:
                            if modo_citacao:
                                resposta = resposta_somente_citacao(contextos_web)
                                fontes = formatar_fontes(contextos_web).split("\n")
                            else:
                                prompt = build_prompt(
                                    contextos_web,
                                    pergunta,
                                    historico=st.session_state.historico[:-1],
                                )
                                try:
                                    resposta = gerar_resposta(gen_bundle, prompt)
                                except Exception as e:
                                    resposta = (
                                        f"Tive um problema ao gerar a resposta: {e}"
                                    )
                                fontes = [m["source"] for _t, m, _s in contextos_web]
                            fontes_para_stats = fontes

                    if resposta is None:
                        resposta = "Não encontrei nada relevante o bastante nas fontes indexadas."

                registrar_pergunta(pergunta, fontes_para_stats)

                imagens_da_web: list[dict] = []
                resposta_valida = not resposta.startswith(
                    ("Não encontrei", "Tive um problema")
                )
                if st.session_state.get("imagens_web", False) and resposta_valida:
                    termo_img = imagens_web.extrair_termo_busca(pergunta)
                    imagens_da_web = imagens_web.buscar_imagens(termo_img, limite=2)

            st.markdown(resposta)
            exibir_imagens_web(imagens_da_web)
            if imagens:
                cols = st.columns(min(len(imagens), 3))
                for i, caminho in enumerate(imagens):
                    with cols[i % len(cols)]:
                        st.image(caminho, use_container_width=True)
            if fontes:
                with st.expander("Fontes consultadas"):
                    for fonte in fontes:
                        st.markdown(f"- {fonte}")

        st.session_state.historico.append(
            {
                "role": "assistant",
                "content": resposta,
                "fontes": fontes,
                "imagens": imagens,
                "imagens_web": imagens_da_web,
            }
        )

        salvar_chat(st.session_state.chat_id, st.session_state.historico)
        st.rerun()


if __name__ == "__main__":
    main()
