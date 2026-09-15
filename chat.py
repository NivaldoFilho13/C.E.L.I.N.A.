import json
import os
import pickle
import sys

import faiss
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

INDEX_FILE = "data/index.faiss"
META_FILE = "data/docs.pkl"
IMAGES_INDEX_FILE = "data/images_index.json"
REGRAS_FILE = "regras.txt"
EMB_MODEL = "all-MiniLM-L6-v2"

MODELOS_DISPONIVEIS = {
    "Rápido (0.5B)": "Qwen/Qwen2.5-0.5B-Instruct",
    "Equilibrado (1.5B)": "Qwen/Qwen2.5-1.5B-Instruct",
    "Mais qualidade (3B)": "Qwen/Qwen2.5-3B-Instruct",
}
GEN_MODEL_PADRAO = MODELOS_DISPONIVEIS["Equilibrado (1.5B)"]

TOP_K = 4
MAX_NEW_TOKENS = 400
LIMIAR_CONFIANCA_PADRAO = 0.25


def carregar_recursos(gen_model: str = GEN_MODEL_PADRAO):
    if not os.path.exists(INDEX_FILE) or not os.path.exists(META_FILE):
        print(
            "ERRO: índice não encontrado. Rode nesta ordem:\n"
            "  1) python extract_pdfs.py\n"
            "  2) python build_index.py\n"
            "  3) python chat.py"
        )
        sys.exit(1)

    index = faiss.read_index(INDEX_FILE)
    with open(META_FILE, "rb") as f:
        meta = pickle.load(f)

    indice_imagens = {}
    if os.path.exists(IMAGES_INDEX_FILE):
        with open(IMAGES_INDEX_FILE, "r", encoding="utf-8") as f:
            indice_imagens = json.load(f)

    print(f"Carregando modelo de embeddings ({EMB_MODEL})...")
    embedder = SentenceTransformer(EMB_MODEL)

    print(f"Carregando modelo de geração ({gen_model})... (pode demorar na 1ª vez)")
    tokenizer = AutoTokenizer.from_pretrained(gen_model)
    model = AutoModelForCausalLM.from_pretrained(gen_model)
    model.eval()

    return (
        index,
        embedder,
        (tokenizer, model),
        meta["texts"],
        meta["metas"],
        indice_imagens,
    )


def gerar_resposta(
    gen_bundle, prompt: str, max_new_tokens: int = MAX_NEW_TOKENS
) -> str:
    tokenizer, model = gen_bundle

    mensagens = [{"role": "user", "content": prompt}]
    entrada_formatada = tokenizer.apply_chat_template(
        mensagens, tokenize=False, add_generation_prompt=True
    )
    entradas = tokenizer(
        entrada_formatada, return_tensors="pt", truncation=True, max_length=4096
    )

    saida = model.generate(
        **entradas,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
    )

    tokens_novos = saida[0][entradas["input_ids"].shape[1] :]
    texto = tokenizer.decode(tokens_novos, skip_special_tokens=True)
    return texto.strip()


def retrieve(
    index,
    embedder,
    texts,
    metas,
    query: str,
    k: int = TOP_K,
    fonte_filtro: str | None = None,
):
    k_busca = k if not fonte_filtro else max(k * 10, 50)

    q_emb = embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    distancias, indices = index.search(q_emb, min(k_busca, len(texts)))

    resultados = []
    for score, idx in zip(distancias[0], indices[0]):
        if idx == -1:
            continue
        if fonte_filtro and metas[idx]["source"] != fonte_filtro:
            continue
        resultados.append((texts[idx], metas[idx], float(score)))
        if len(resultados) >= k:
            break
    return resultados


def melhor_score(contexts) -> float:
    return max((score for _t, _m, score in contexts), default=0.0)


def carregar_regras(caminho: str = REGRAS_FILE) -> list[str]:
    if not os.path.exists(caminho):
        return []

    regras = []
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            regras.append(linha)
    return regras


def formatar_historico_recente(
    historico: list[dict] | None, max_turnos: int = 3
) -> str:
    if not historico:
        return ""

    mensagens = [m for m in historico if m.get("role") in ("user", "assistant")]
    mensagens = mensagens[-(max_turnos * 2) :]
    if not mensagens:
        return ""

    linhas = []
    for m in mensagens:
        quem = "Usuário" if m["role"] == "user" else "Celina"
        linhas.append(f"{quem}: {m['content']}")
    return (
        "\n\n### Conversa anterior (para contexto de perguntas de acompanhamento)\n"
        + "\n".join(linhas)
    )


def build_prompt(
    contexts,
    question: str,
    regras: list[str] | None = None,
    historico: list[dict] | None = None,
) -> str:
    blocos = []
    for texto, meta, _score in contexts:
        fonte = f"{meta['source']} - página {meta['page']}"
        blocos.append(f"[Fonte: {fonte}]\n{texto}")
    ctx = "\n\n".join(blocos)

    regras = regras if regras is not None else carregar_regras()
    regras_texto = ""
    if regras:
        regras_formatadas = "\n".join(f"- {r}" for r in regras)
        regras_texto = f"\n\nRegras de formato a seguir:\n{regras_formatadas}"

    historico_texto = formatar_historico_recente(historico)

    prompt = (
        "Responda à pergunta abaixo no mesmo idioma em que ela foi escrita, "
        "usando apenas as informações dos trechos fornecidos. Se os trechos "
        "não tiverem a informação necessária, diga que não encontrou isso "
        "nos documentos — não invente. Se a pergunta parecer uma "
        "continuação da conversa anterior (ex: 'e sobre isso?', 'me fale "
        "mais'), use o histórico para entender o contexto, mas responda "
        "com base nos trechos."
        f"{regras_texto}"
        f"{historico_texto}\n\n"
        f"### Trechos\n{ctx}\n\n"
        f"### Pergunta\n{question}"
    )
    return prompt


def resposta_somente_citacao(contexts) -> str:
    blocos = []
    for texto, meta, _score in contexts:
        fonte = f"[{meta['source']} - página {meta['page']}]"
        blocos.append(f"{fonte}\n{texto}")
    return "\n\n---\n\n".join(blocos)


def formatar_fontes(contexts) -> str:
    vistos = set()
    linhas = []
    for _texto, meta, score in contexts:
        chave = (meta["source"], meta["page"])
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append(
            f"  - {meta['source']} (página {meta['page']}, relevância {score:.2f})"
        )
    return "\n".join(linhas)


def obter_imagens_dos_contextos(contexts, indice_imagens: dict) -> list[str]:
    vistos_paginas = set()
    caminhos: list[str] = []
    for _texto, meta, _score in contexts:
        chave_pagina = (meta["source"], meta["page"])
        if chave_pagina in vistos_paginas:
            continue
        vistos_paginas.add(chave_pagina)

        chave_indice = f"{meta['source']}::{meta['page']}"
        for caminho in indice_imagens.get(chave_indice, []):
            if caminho not in caminhos and os.path.exists(caminho):
                caminhos.append(caminho)
    return caminhos


def chat_loop():
    index, embedder, gen_bundle, texts, metas, indice_imagens = carregar_recursos()
    historico: list[dict] = []

    print("\nChat iniciado. Digite 'sair' para encerrar.\n")
    while True:
        try:
            q = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando.")
            break

        if not q:
            continue
        if q.lower() in ("sair", "exit", "quit"):
            print("Encerrando.")
            break

        contexts = retrieve(index, embedder, texts, metas, q, k=TOP_K)

        if not contexts or melhor_score(contexts) < LIMIAR_CONFIANCA_PADRAO:
            print(
                "\nAssistente: Não encontrei nada relevante nos documentos indexados.\n"
            )
            continue

        prompt = build_prompt(contexts, q, historico=historico)
        try:
            resp = gerar_resposta(gen_bundle, prompt)
        except Exception as e:
            print(f"\n[erro ao gerar resposta] {e}\n")
            continue

        historico.append({"role": "user", "content": q})
        historico.append({"role": "assistant", "content": resp})

        print(f"\nAssistente: {resp}")
        print("\nFontes consultadas:")
        print(formatar_fontes(contexts))

        imagens = obter_imagens_dos_contextos(contexts, indice_imagens)
        if imagens:
            print(
                "\nImagens ilustrativas das páginas usadas (abra manualmente para ver):"
            )
            for caminho in imagens:
                print(f"  - {caminho}")
            print(
                "(Dica: rode 'streamlit run app.py' para ver essas imagens direto na tela.)"
            )
        print()


if __name__ == "__main__":
    chat_loop()
