import base64
import os

import streamlit as st

from chat import build_prompt, carregar_recursos, gerar_resposta, obter_imagens_dos_contextos, retrieve

TOP_K = 4

ASSETS_DIR = "assets"
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.svg")
LOGO_EMBLEMA_PATH = os.path.join(ASSETS_DIR, "logo-emblem.svg")
BANNER_PATH = os.path.join(ASSETS_DIR, "banner.png")

st.set_page_config(
    page_title="Celina",
    page_icon=LOGO_EMBLEMA_PATH if os.path.exists(LOGO_EMBLEMA_PATH) else "📚",
    layout="centered",
)

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


def main() -> None:
    aplicar_estilo()

    try:
        index, embedder, gen_bundle, texts, metas, indice_imagens = carregar()
    except SystemExit:
        st.error(
            "Índice não encontrado. Antes de usar a interface, rode no terminal, "
            "nesta ordem:\n\n"
            "1. `python extract_pdfs.py`\n"
            "2. `python build_index.py`\n\n"
            "Depois volte e recarregue esta página."
        )
        return

    if "historico" not in st.session_state:
        st.session_state.historico = []

    # Reexibe as mensagens já trocadas nesta sessão
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

    with st.sidebar:
        logo_uri = carregar_como_data_uri(LOGO_EMBLEMA_PATH)
        if logo_uri:
            st.markdown(
                f'<img src="{logo_uri}" style="width:64px;border-radius:50%;'
                f'box-shadow:0 0 16px rgba(159,123,255,0.5);margin-bottom:0.6rem;" />',
                unsafe_allow_html=True,
            )
        st.subheader("Sobre a Celina")
        st.write(
            "Busca os trechos mais relevantes dos seus PDFs e usa um modelo "
            "local para responder com base neles, mostrando também imagens "
            "ilustrativas das páginas usadas quando disponíveis."
        )
        if st.button("🗑️ Limpar conversa"):
            st.session_state.historico = []
            st.rerun()


if __name__ == "__main__":
    main()
