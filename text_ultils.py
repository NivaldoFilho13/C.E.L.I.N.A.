import re

CHUNK_SIZE = 800
CHUNK_OVERLAP = 200


def limpar_texto(texto: str) -> str:
    """Remove espaços/quebras de linha repetidos e normaliza o texto."""
    texto = texto.replace("\r", " ")
    texto = re.sub(r"\n{2,}", "\n", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"\n", " ", texto)
    return texto.strip()


def dividir_em_chunks(
    texto: str, tamanho: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """Divide um texto longo em pedaços menores, com sobreposição entre eles."""
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
