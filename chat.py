"""
Loop de chat: busca os trechos mais relevantes dos PDFs indexados e gera
uma resposta em português citando as fontes usadas.
"""

import os
import pickle
import sys

import faiss
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

INDEX_FILE = "data/index.faiss"
META_FILE = "data/docs.pkl"
EMB_MODEL = "all-MiniLM-L6-v2"

# Qwen2.5-1.5B-Instruct: modelo multilíngue de verdade (bem melhor em
# português que o FLAN-T5, que é treinado majoritariamente em inglês).
# ~3GB de download na primeira vez; roda em CPU, mas é mais lento que o
# flan-t5-small. Se seu PC for fraco, veja a alternativa comentada abaixo.
GEN_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

# Alternativa mais leve (menor qualidade em português, mas mais rápida):
# GEN_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"

TOP_K = 4  # quantos trechos recuperar por pergunta
MAX_NEW_TOKENS = 400


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

    print(f"Carregando modelo de geração ({GEN_MODEL})... (pode demorar na 1ª vez)")
    tokenizer = AutoTokenizer.from_pretrained(GEN_MODEL)
    model = AutoModelForCausalLM.from_pretrained(GEN_MODEL)
    model.eval()

    return index, embedder, (tokenizer, model), meta["texts"], meta["metas"]


def gerar_resposta(gen_bundle, prompt: str, max_new_tokens: int = MAX_NEW_TOKENS) -> str:
    """Gera texto usando um modelo causal via chat template (mais robusto e
    com muito mais qualidade em português do que os antigos FLAN-T5)."""
    tokenizer, model = gen_bundle

    mensagens = [{"role": "user", "content": prompt}]
    entrada_formatada = tokenizer.apply_chat_template(
        mensagens, tokenize=False, add_generation_prompt=True
    )
    entradas = tokenizer(entrada_formatada, return_tensors="pt", truncation=True, max_length=4096)

    saida = model.generate(
        **entradas,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
    )

    # Pega só os tokens gerados a mais (a resposta), sem repetir o prompt
    tokens_novos = saida[0][entradas["input_ids"].shape[1]:]
    texto = tokenizer.decode(tokens_novos, skip_special_tokens=True)
    return texto.strip()


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
        "Responda à pergunta abaixo em português, usando apenas as informações "
        "dos trechos fornecidos. Seja objetivo e cite a fonte entre colchetes "
        "(ex: [nome.pdf - página 3]) quando usar um trecho. Se os trechos não "
        "tiverem a informação necessária, diga que não encontrou isso nos "
        "documentos — não invente.\n\n"
        f"### Trechos\n{ctx}\n\n"
        f"### Pergunta\n{question}"
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
    index, embedder, gen_bundle, texts, metas = carregar_recursos()

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
            resp = gerar_resposta(gen_bundle, prompt)
        except Exception as e:
            print(f"\n[erro ao gerar resposta] {e}\n")
            continue

        print(f"\nAssistente: {resp}")
        print("\nFontes consultadas:")
        print(formatar_fontes(contexts))
        print()


if __name__ == "__main__":
    chat_loop()
