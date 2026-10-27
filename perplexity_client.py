import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("PERPLEXITY_API_KEY")
API_URL = "https://api.perplexity.ai/chat/completions"
MODELO_PADRAO = "sonar"


def perplexity_disponivel() -> bool:
    return bool(API_KEY)


def perguntar_perplexity(
    pergunta: str, historico: list[dict] | None = None, modelo: str = MODELO_PADRAO
) -> tuple[str, list[str]]:
    if not API_KEY:
        raise RuntimeError(
            "PERPLEXITY_API_KEY não configurada. Crie um arquivo .env na raiz "
            "do projeto (pode copiar o .env.example) com sua chave."
        )

    mensagens = [
        {
            "role": "system",
            "content": "Responda de forma objetiva e direta, no mesmo idioma da pergunta.",
        }
    ]
    if historico:
        for msg in historico[-6:]:
            mensagens.append({"role": msg["role"], "content": msg["content"]})
    mensagens.append({"role": "user", "content": pergunta})

    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": modelo, "messages": mensagens},
        timeout=30,
    )
    resp.raise_for_status()
    dados = resp.json()

    resposta = dados["choices"][0]["message"]["content"]
    citacoes = dados.get("citations", []) or []
    return resposta, citacoes
