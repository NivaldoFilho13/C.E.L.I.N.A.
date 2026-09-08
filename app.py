import base64
import json
import os
import uuid
from datetime import datetime

import streamlit as st

import build_index
import extract_outros
import extract_pdfs
from chat import (
    REGRAS_FILE,
    build_prompt,
    carregar_recursos,
    gerar_resposta,
    obter_imagens_dos_contextos,
    retrieve,
)

TOP_K = 4
PDF_DIR = "pdfs"
OUTROS_DIR = "outros"
URLS_FILE = "urls.txt"

ASSETS_DIR = "assets"
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.svg")
LOGO_EMBLEMA_PATH = os.path.join(ASSETS_DIR, "logo-emblem.svg")
BANNER_PATH = os.path.join(ASSETS_DIR, "banner.png")

CHATS_DIR = os.path.join("data", "chats")

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
    """Devolve [{id, title, updated_at}, ...] dos chats salvos, mais recente primeiro."""
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
    """Lê o conteúdo bruto do regras.txt (com comentários e formatação),
    para edição na interface. Se o arquivo não existir, devolve um modelo."""
    if not os.path.exists(REGRAS_FILE):
        return REGRAS_PADRAO
    with open(REGRAS_FILE, "r", encoding="utf-8") as f:
        return f.read()


def salvar_regras_raw(texto: str) -> None:
    with open(REGRAS_FILE, "w", encoding="utf-8") as f:
        f.write(texto)


EXTENSOES_OUTROS = (".txt", ".md", ".docx", ".csv", ".xlsx")


def salvar_arquivos_enviados(arquivos) -> tuple[int, int]:
    """Salva os arquivos enviados na pasta certa conforme a extensão
    (pdfs/ ou outros/). Devolve (qtd_pdfs, qtd_outros) salvos."""
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
    """Acrescenta os links colados (um por linha) ao urls.txt, sem duplicar
    os que já estavam lá. Devolve quantos links novos foram adicionados."""
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
    """Salva um texto colado como um arquivo .txt dentro de outros/."""
    os.makedirs(OUTROS_DIR, exist_ok=True)
    nome_base = "".join(c for c in titulo.strip() if c.isalnum() or c in " -_").strip()
    nome_base = nome_base.replace(" ", "_") or "texto_colado"
    nome_arquivo = f"{nome_base}.txt"
    caminho = os.path.join(OUTROS_DIR, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return nome_arquivo


def processar_fontes() -> tuple[bool, str]:
    """Extrai o que houver em pdfs/, outros/ e urls.txt, e reconstrói o
    índice de busca. Devolve (sucesso, mensagem)."""
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
    if tem_outros or tem_urls:
        if extract_outros.main() == 0:
            algo_processado = True
        else:
            avisos.append("houve um problema extraindo os outros arquivos/links")

    if not algo_processado:
        return False, "Nenhuma fonte nova encontrada para processar."

    if build_index.main() != 0:
        return False, "Falha ao construir o índice de busca (veja o terminal para detalhes)."

    if avisos:
        return True, "Índice atualizado, mas " + " e ".join(avisos) + " (veja o terminal)."
    return True, "Fontes processadas e índice atualizado com sucesso!"


@st.cache_data
def carregar_como_data_uri(caminho: str) -> str | None:
    """Lê um arquivo local (svg/png/jpg) e devolve como data URI base64,
    para poder usá-lo em CSS/HTML sem depender de um servidor de estáticos."""
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
    """Injeta CSS para o cabeçalho (hero banner) e pequenos ajustes visuais."""
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
        /* Cabeçalho ("hero") com o banner de fundo, a logo e o título */
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

        /* Bolhas do chat com leve acento na cor da marca */
        div[data-testid="stChatMessage"] {{
            border-radius: 14px;
            border: 1px solid rgba(159, 123, 255, 0.15);
        }}

        /* Botões com gradiente da marca */
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

        /* Item de chat na barra lateral (não selecionado) fica mais discreto */
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
            <div class="celina-hero-title">CELINA</div>
            <div class="celina-hero-subtitle">Inteligência Artificial · Chat sobre seus PDFs</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner="Carregando modelos do Celina... (pode demorar na 1ª vez)")
def carregar():
    return carregar_recursos()

def renderizar_sidebar() -> None:
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

        with st.expander("Enviar fontes", expanded=not os.path.exists("data/index.faiss")):
            aba_arquivo, aba_link, aba_texto = st.tabs(["Arquivo", "Link", "Colar texto"])

            with aba_arquivo:
                arquivos = st.file_uploader(
                    "PDF, TXT, MD, DOCX, CSV ou XLSX",
                    type=["pdf", "txt", "md", "docx", "csv", "xlsx"],
                    accept_multiple_files=True,
                    key="upload_arquivos",
                )
                if st.button("Processar arquivos", use_container_width=True, disabled=not arquivos):
                    qtd_pdfs, qtd_outros = salvar_arquivos_enviados(arquivos)
                    with st.spinner(f"Processando {qtd_pdfs + qtd_outros} arquivo(s)..."):
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
                if st.button("Processar links", use_container_width=True, disabled=not texto_links.strip()):
                    qtd_novos = salvar_links(texto_links)
                    if qtd_novos == 0:
                        st.warning("Nenhum link novo (já estavam salvos ou o campo está vazio).")
                    else:
                        with st.spinner(f"Baixando e processando {qtd_novos} link(s)..."):
                            sucesso, mensagem = processar_fontes()
                        if sucesso:
                            carregar.clear()
                            st.success(mensagem)
                            st.rerun()
                        else:
                            st.error(mensagem)

            with aba_texto:
                titulo_texto = st.text_input("Nome para essa fonte", placeholder="ex: anotacoes-aula-5")
                texto_colado = st.text_area("Cole o texto aqui", height=140, key="input_texto_colado")
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
                    if st.button(rotulo, key=f"abrir_{chat['id']}", use_container_width=True):
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

        st.divider()
        st.subheader("Sobre a Celina")
        st.write(
            "Busca os trechos mais relevantes dos seus PDFs e usa um modelo "
            "local para responder com base neles, mostrando também imagens "
            "ilustrativas das páginas usadas quando disponíveis."
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

 
    renderizar_sidebar()

    try:
        index, embedder, gen_bundle, texts, metas, indice_imagens = carregar()
    except SystemExit:
        st.info(
            "Nenhuma fonte indexada ainda. Use **📄 Enviar fontes**, na barra "
            "lateral, para enviar PDFs, textos, planilhas ou links e criar o índice de busca."
        )
        return

   
    for msg in st.session_state.historico:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("imagens"):
                cols = st.columns(min(len(msg["imagens"]), 3))
                for i, caminho in enumerate(msg["imagens"]):
                    with cols[i % len(cols)]:
                        st.image(caminho, use_container_width=True)
            if msg.get("fontes"):
                with st.expander("Fontes consultadas"):
                    for fonte in msg["fontes"]:
                        st.markdown(f"- {fonte}")

    pergunta = st.chat_input("Pergunte algo sobre seus PDFs...")

    if pergunta:
        st.session_state.historico.append({"role": "user", "content": pergunta})
        with st.chat_message("user"):
            st.markdown(pergunta)

        with st.chat_message("assistant"):
            with st.spinner("Buscando nos documentos e gerando resposta..."):
                contextos = retrieve(index, embedder, texts, metas, pergunta, k=TOP_K)

                if not contextos:
                    resposta = "Não encontrei nada relevante nos documentos indexados."
                    fontes = []
                    imagens = []
                else:
                    prompt = build_prompt(contextos, pergunta)
                    try:
                        resposta = gerar_resposta(gen_bundle, prompt)
                    except Exception as e:
                        resposta = f"Tive um problema ao gerar a resposta: {e}"

                    vistos = set()
                    fontes = []
                    for _texto, meta, score in contextos:
                        chave = (meta["source"], meta["page"])
                        if chave in vistos:
                            continue
                        vistos.add(chave)
                        fontes.append(f"{meta['source']} (página {meta['page']}, relevância {score:.2f})")

                    imagens = obter_imagens_dos_contextos(contextos, indice_imagens)

            st.markdown(resposta)
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
            {"role": "assistant", "content": resposta, "fontes": fontes, "imagens": imagens}
        )


        salvar_chat(st.session_state.chat_id, st.session_state.historico)
        st.rerun() 


if __name__ == "__main__":
    main()
