import json
import os
import re
import sys

from pypdf import PdfReader
from tqdm import tqdm

PDF_DIR = "pdfs"
OUT_FILE = "data/documents.jsonl"
IMAGES_DIR = "data/images"
IMAGES_INDEX_FILE = "data/images_index.json"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 200
IMAGEM_TAMANHO_MINIMO = 120


def limpar_texto(texto: str) -> str:
    """Remove espaços/quebras de linha repetidos e normaliza o texto."""
    texto = texto.replace("\r", " ")
    texto = re.sub(r"\n{2,}", "\n", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"\n", " ", texto)
    return texto.strip()


def dividir_em_chunks(texto: str, tamanho: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if len(texto) <= tamanho:
        return [texto] if texto else []

    chunks = []
    inicio = 0
    while inicio < len(texto):
        fim = inicio + tamanho
        pedaco = texto[inicio:fim]

        if fim < len(texto):
            ultimo_ponto = pedaco.rfind(". ")
            if ultimo_ponto > tamanho * 0.5: 
                pedaco = pedaco[: ultimo_ponto + 1]

        pedaco = pedaco.strip()
        if pedaco:
            chunks.append(pedaco)

        avanco = max(len(pedaco) - overlap, 1)
        inicio += avanco

    return chunks


def extrair_imagens_da_pagina(page, nome_base: str, page_num: int, out_dir: str) -> list[str]:
    """Salva em disco as imagens 'grandes o suficiente' de uma página do PDF."""
    caminhos: list[str] = []
    try:
        imagens = page.images
    except Exception:
        return caminhos

    for idx, img in enumerate(imagens):
        try:
            pil_img = img.image  
            largura, altura = pil_img.size
            if largura < IMAGEM_TAMANHO_MINIMO or altura < IMAGEM_TAMANHO_MINIMO:
                continue  

            ext = os.path.splitext(img.name)[1].lower() or ".png"
            if ext not in (".png", ".jpg", ".jpeg"):
                ext = ".png"
            nome_arquivo = f"{nome_base}_p{page_num}_{idx}{ext}"
            caminho = os.path.join(out_dir, nome_arquivo)
            pil_img.save(caminho)
            caminhos.append(caminho)
        except Exception:
            continue  

    return caminhos


def extract_from_pdf(path: str, images_dir: str) -> tuple[list[dict], dict]:
    """Extrai texto (em chunks) e imagens de um PDF, página por página."""
    try:
        reader = PdfReader(path)
    except Exception as e:
        print(f"  [aviso] não consegui abrir '{path}': {e}")
        return [], {}

    nome_arquivo = os.path.basename(path)
    nome_base = os.path.splitext(nome_arquivo)[0]

    resultados = []
    indice_imagens: dict[str, list[str]] = {}

    for i, page in enumerate(reader.pages):
        page_num = i + 1

        try:
            texto_bruto = page.extract_text() or ""
        except Exception as e:
            print(f"  [aviso] erro extraindo texto da página {page_num} de '{path}': {e}")
            texto_bruto = ""

        texto = limpar_texto(texto_bruto)
        if texto:
            for j, chunk in enumerate(dividir_em_chunks(texto)):
                if len(chunk) < 20:
                    continue
                resultados.append(
                    {
                        "source": nome_arquivo,
                        "page": page_num,
                        "chunk": j,
                        "text": chunk,
                    }
                )

        caminhos_imagens = extrair_imagens_da_pagina(page, nome_base, page_num, images_dir)
        if caminhos_imagens:
            chave = f"{nome_arquivo}::{page_num}"
            indice_imagens[chave] = caminhos_imagens

    return resultados, indice_imagens


def main() -> int:
    os.makedirs("data", exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    if not os.path.isdir(PDF_DIR):
        print(f"ERRO: pasta '{PDF_DIR}/' não existe. Crie-a e coloque seus PDFs lá.")
        return 1

    arquivos_pdf = sorted(f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf"))
    if not arquivos_pdf:
        print(f"ERRO: nenhum arquivo .pdf encontrado em '{PDF_DIR}/'.")
        return 1

    all_docs: list[dict] = []
    all_images: dict[str, list[str]] = {}

    for fname in tqdm(arquivos_pdf, desc="Processando PDFs"):
        path = os.path.join(PDF_DIR, fname)
        docs, imagens = extract_from_pdf(path, IMAGES_DIR)
        all_docs.extend(docs)
        all_images.update(imagens)

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

    with open(IMAGES_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(all_images, f, ensure_ascii=False, indent=2)

    fontes = {d["source"] for d in all_docs}
    total_imagens = sum(len(v) for v in all_images.values())
    print(f"\nExtraídos {len(all_docs)} blocos de {len(fontes)} PDF(s) para {OUT_FILE}")
    print(f"Extraídas {total_imagens} imagens ilustrativas para {IMAGES_DIR}/ ({IMAGES_INDEX_FILE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
