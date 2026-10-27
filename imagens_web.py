import re
from urllib.parse import quote

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MIMES_ACEITOS = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
LARGURA_MINIMA = 200

_STOPWORDS = {
    "a",
    "o",
    "as",
    "os",
    "um",
    "uma",
    "uns",
    "umas",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "para",
    "com",
    "sem",
    "sobre",
    "e",
    "ou",
    "que",
    "qual",
    "quais",
    "quem",
    "como",
    "quando",
    "onde",
    "porque",
    "por que",
    "é",
    "são",
    "foi",
    "era",
    "ser",
    "seu",
    "sua",
    "seus",
    "suas",
    "me",
    "fale",
    "explique",
    "diga",
    "defina",
    "mostre",
    "pode",
    "poderia",
    "isso",
    "esse",
    "essa",
    "este",
    "esta",
    "se",
    "ao",
    "aos",
    "à",
    "às",
    "mais",
    "muito",
    "what",
    "is",
    "are",
    "the",
    "of",
    "in",
    "on",
    "and",
    "how",
    "why",
    "explain",
}


def extrair_termo_busca(texto: str, max_palavras: int = 4) -> str:
    palavras = re.findall(r"[\wÀ-ÿ-]+", texto.lower())
    chaves = [p for p in palavras if p not in _STOPWORDS and len(p) > 2]
    return " ".join(chaves[:max_palavras])


def _limpar_html(texto: str) -> str:
    return re.sub(r"<[^>]+>", "", texto or "").strip()


def buscar_imagens(termo: str, limite: int = 2, largura: int = 640) -> list[dict]:
    termo = (termo or "").strip()
    if not termo:
        return []

    try:
        import requests

        resp = requests.get(
            COMMONS_API,
            params={
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": termo,
                "gsrnamespace": 6,
                "gsrlimit": max(limite * 4, 8),
                "prop": "imageinfo",
                "iiprop": "url|mime|size|extmetadata",
                "iiurlwidth": largura,
            },
            headers={"User-Agent": "Celina/1.0 (assistente de estudos local)"},
            timeout=10,
        )
        resp.raise_for_status()
        paginas = resp.json().get("query", {}).get("pages", {})
    except Exception as e:
        print(f"  [aviso] busca de imagens falhou: {e}")
        return []

    resultados = []
    for pagina in sorted(paginas.values(), key=lambda p: p.get("index", 0)):
        info = (pagina.get("imageinfo") or [{}])[0]
        if info.get("mime") not in MIMES_ACEITOS:
            continue
        if info.get("width", 0) < LARGURA_MINIMA:
            continue

        url = info.get("thumburl") or info.get("url")
        if not url:
            continue

        meta = info.get("extmetadata", {})
        titulo = pagina.get("title", "").removeprefix("File:")
        titulo = re.sub(r"\.\w{3,4}$", "", titulo).replace("_", " ")

        resultados.append(
            {
                "url": url,
                "titulo": titulo,
                "autor": _limpar_html(meta.get("Artist", {}).get("value", ""))
                or "autor não informado",
                "licenca": _limpar_html(
                    meta.get("LicenseShortName", {}).get("value", "")
                )
                or "licença não informada",
                "pagina": info.get("descriptionurl", ""),
            }
        )
        if len(resultados) >= limite:
            break

    return resultados


def legenda(img: dict) -> str:
    return f"{img['titulo']} — {img['autor']} ({img['licenca']}), via Wikimedia Commons"


def imagem_em_markdown(img: dict) -> str:
    alt = re.sub(r"[\[\]()]", "", img["titulo"])
    url = quote(img["url"], safe=":/?&=%#")
    pagina = quote(img["pagina"], safe=":/?&=%#") if img["pagina"] else ""
    credito = f"*Imagem: {re.sub(r'[\[\]()]', '', img['autor'])} ({img['licenca']}), Wikimedia Commons*"
    if pagina:
        credito = f"[{credito}]({pagina})"
    return f"![{alt}]({url})\n\n{credito}"
