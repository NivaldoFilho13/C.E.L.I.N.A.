import streamlit as st

from chat import build_prompt, carregar_recursos, gerar_resposta, obter_imagens_dos_contextos, retrieve

TOP_K = 4

st.set_page_config(page_title="Celina", page_icon="📚", layout="centered")


@st.cache_resource(show_spinner="Carregando modelos do Celina... (pode demorar na 1ª vez)")
def carregar():
    return carregar_recursos()


def main() -> None:
    st.title("📚 Celina")
    st.caption("Chat sobre seus PDFs, rodando localmente no seu PC.")

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
        st.subheader("Sobre")
        st.write(
            "O Celina busca os trechos mais relevantes dos seus PDFs e usa um "
            "modelo local para responder com base neles, mostrando também "
            "imagens ilustrativas das páginas usadas quando disponíveis."
        )
        if st.button("Limpar conversa"):
            st.session_state.historico = []
            st.rerun()


if __name__ == "__main__":
    main()
