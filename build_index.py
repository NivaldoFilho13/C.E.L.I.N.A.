"""
Lê data/documents.jsonl (gerado por extract_pdfs.py), cria embeddings
para cada trecho de texto e monta um índice FAISS para busca por
similaridade.
"""

import json
import os
import pickle
import sys

import faiss
from sentence_transformers import SentenceTransformer

DOCS_FILE = "data/documents.jsonl"
INDEX_FILE = "data/index.faiss"
META_FILE = "data/docs.pkl"
EMB_MODEL = "all-MiniLM-L6-v2"


def carregar_documentos(path: str) -> list[dict]:
    docs = []
    with open(path, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            docs.append(json.loads(linha))
    return docs


def main() -> int:
    if not os.path.exists(DOCS_FILE):
        print(f"ERRO: '{DOCS_FILE}' não encontrado. Rode 'python extract_pdfs.py' primeiro.")
        return 1

    docs = carregar_documentos(DOCS_FILE)
    if not docs:
        print(f"ERRO: '{DOCS_FILE}' está vazio.")
        return 1

    texts = []
    metas = []
    for d in docs:
        txt = d.get("text", "").strip()
        if len(txt) < 20:
            continue
        texts.append(txt)
        metas.append(
            {
                "source": d.get("source", "desconhecido"),
                "page": d.get("page", "?"),
                "chunk": d.get("chunk", 0),
            }
        )

    if not texts:
        print("ERRO: nenhum trecho de texto válido (>=20 caracteres) para indexar.")
        return 1

    print(f"Documentos a indexar: {len(texts)}")
    print(f"Carregando modelo de embeddings ({EMB_MODEL})...")
    model = SentenceTransformer(EMB_MODEL)

    embs = model.encode(
        texts,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embs)

    os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
    faiss.write_index(index, INDEX_FILE)

    with open(META_FILE, "wb") as f:
        pickle.dump({"texts": texts, "metas": metas}, f)

    print(f"Índice salvo em {INDEX_FILE} ({index.ntotal} vetores, dimensão {dim}).")
    print(f"Metadados salvos em {META_FILE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
