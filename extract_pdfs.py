"""
Extrai texto de todos os PDFs em pdfs/, limpa e divide em blocos (chunks)
com sobreposição (overlap), salvando em data/documents.jsonl.

Cada linha do jsonl é um objeto:
    {"source": "arquivo.pdf", "page": 3, "chunk": 0, "text": "..."}
"""

import json
import os
import re
import sys

from pypdf import PdfReader
from tqdm import tqdm

PDF_DIR = "pdfs"
OUT_FILE = "data/documents.jsonl"

# Tamanho alvo de cada chunk (em caracteres) e quanto texto se repete
# entre um chunk e o próximo, para não cortar frases importantes ao meio.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 200


def limpar_texto(texto: str) -> str:
    """Remove espaços/quebras de linha repetidos e normaliza o texto."""
    texto = texto.replace("\r", " ")
    texto = re.sub(r"\n{2,}", "\n", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"\n", " ", texto)
    return texto.strip()


def dividir_em_chunks(texto: str, tamanho: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Divide um texto longo em pedaços menores, com sobreposição entre eles."""
    if len(texto) <= tamanho:
        return [texto] if texto else []

    chunks = []
    inicio = 0
    while inicio < len(texto):
        fim = inicio + tamanho
        pedaco = texto[inicio:fim]

        # Tenta terminar o chunk num ponto final, para não cortar frase ao meio
        if fim < len(texto):
            ultimo_ponto = pedaco.rfind(". ")
            if ultimo_ponto > tamanho * 0.5:  # só corta ali se não perder muito texto
                pedaco = pedaco[: ultimo_ponto + 1]

        pedaco = pedaco.strip()
        if pedaco:
            chunks.append(pedaco)

        avanco = max(len(pedaco) - overlap, 1)
        inicio += avanco

    return chunks


def extract_text_from_pdf(path: str) -> list[dict]:
    """Extrai e faz chunking do texto de um PDF, página por página."""
    try:
        reader = PdfReader(path)
    except Exception as e:
        print(f"  [aviso] não consegui abrir '{path}': {e}")
        return []

    resultados = []
    for i, page in enumerate(reader.pages):
        try:
            texto_bruto = page.extract_text() or ""
        except Exception as e:
            print(f"  [aviso] erro extraindo página {i + 1} de '{path}': {e}")
            continue

        texto = limpar_texto(texto_bruto)
        if not texto:
            continue  # provavelmente página escaneada/sem texto (precisaria de OCR)

        for j, chunk in enumerate(dividir_em_chunks(texto)):
            if len(chunk) < 20:
                continue
            resultados.append(
                {
                    "source": os.path.basename(path),
                    "page": i + 1,
                    "chunk": j,
                    "text": chunk,
                }
            )
    return resultados


def main() -> int:
    os.makedirs("data", exist_ok=True)

    if not os.path.isdir(PDF_DIR):
        print(f"ERRO: pasta '{PDF_DIR}/' não existe. Crie-a e coloque seus PDFs lá.")
        return 1

    arquivos_pdf = sorted(f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf"))
    if not arquivos_pdf:
        print(f"ERRO: nenhum arquivo .pdf encontrado em '{PDF_DIR}/'.")
        return 1

    all_docs: list[dict] = []
    paginas_sem_texto = 0

    for fname in tqdm(arquivos_pdf, desc="Processando PDFs"):
        path = os.path.join(PDF_DIR, fname)
        docs = extract_text_from_pdf(path)
        all_docs.extend(docs)

    if not all_docs:
        print(
            "AVISO: nenhum texto foi extraído de nenhum PDF. "
            "Eles podem ser digitalizados/escaneados (imagem) — nesse caso "
            "seria necessário OCR (ex: Tesseract + pytesseract) antes disso."
        )
        return 1

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for d in all_docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    fontes = {d["source"] for d in all_docs}
    print(f"\nExtraídos {len(all_docs)} blocos de {len(fontes)} PDF(s) para {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
