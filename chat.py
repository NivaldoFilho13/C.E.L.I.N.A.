"""
Loop de chat: busca os trechos mais relevantes dos PDFs indexados e gera
uma resposta em português citando as fontes usadas.
"""

import os
import pickle
import sys

import faiss
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, pipeline

INDEX_FILE = "data/index.faiss"
META_FILE = "data/docs.pkl"
EMB_MODEL = "all-MiniLM-L6-v2"
GEN_MODEL = "google/flan-t5-small"  # troque para "google/flan-t5-base" p/ mais qualidade (mais lento em CPU)

TOP_K = 4  # quantos trechos recuperar por pergunta


def carregar_recursos():
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

    print(f"Carregando modelo de embeddings ({EMB_MODEL})...")
    embedder = SentenceTransformer(EMB_MODEL)

    print(f"Carregando modelo de geração ({GEN_MODEL})...")
    tokenizer = AutoTokenizer.from_pretrained(GEN_MODEL)
    model = AutoModelForSeq2SeqLM.from_pretrained(GEN_MODEL)
    generator = pipeline("text2text-generation", model=model, tokenizer=tokenizer, device=-1)

    return index, embedder, generator, meta["texts"], meta["metas"]


def retrieve(index, embedder, texts, metas, query: str, k: int = TOP_K):
    q_emb = embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    distancias, indices = index.search(q_emb, k)

    resultados = []
    for score, idx in zip(distancias[0], indices[0]):
        if idx == -1:
            continue
        resultados.append((texts[idx], metas[idx], float(score)))
    return resultados


def build_prompt(contexts, question: str) -> str:
    blocos = []
    for texto, meta, _score in contexts:
        fonte = f"{meta['source']} - página {meta['page']}"
        blocos.append(f"[Fonte: {fonte}]\n{texto}")
    ctx = "\n\n".join(blocos)

    prompt = (
        "Você é um assistente que responde SOMENTE com base nos trechos abaixo.\n"
        "Regras:\n"
        "- Responda em português, de forma objetiva.\n"
        "- Cite a fonte entre colchetes (ex: [nome.pdf - página 3]) sempre que usar um trecho.\n"
        "- Se os trechos não contiverem a informação necessária para responder, "
        "diga claramente que não encontrou essa informação nos documentos — "
        "não invente uma resposta.\n\n"
        f"Trechos:\n{ctx}\n\n"
        f"Pergunta: {question}\n"
        "Resposta:"
    )
    return prompt


def formatar_fontes(contexts) -> str:
    vistos = set()
    linhas = []
    for _texto, meta, score in contexts:
        chave = (meta["source"], meta["page"])
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append(f"  - {meta['source']} (página {meta['page']}, relevância {score:.2f})")
    return "\n".join(linhas)


def chat_loop():
    index, embedder, generator, texts, metas = carregar_recursos()

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

        if not contexts:
            print("\nAssistente: Não encontrei nada relevante nos documentos indexados.\n")
            continue

        prompt = build_prompt(contexts, q)
        try:
            resp = generator(prompt, max_length=256, do_sample=False)[0]["generated_text"]
        except Exception as e:
            print(f"\n[erro ao gerar resposta] {e}\n")
            continue

        print(f"\nAssistente: {resp}")
        print("\nFontes consultadas:")
        print(formatar_fontes(contexts))
        print()


if __name__ == "__main__":
    chat_loop()
