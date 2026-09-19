import json

import requests

from config import OLLAMA_MODEL, OLLAMA_URL, SYSTEM_PROMPT

FACT_EXTRACTION_PROMPT = (
    "Leia a conversa abaixo e extraia fatos duráveis sobre o usuário (profissão, cidade, "
    "preferências, nome preferido, etc). Responda SOMENTE com uma lista JSON de strings, "
    'ex: ["mora em São Paulo", "prefere ser chamado de Davi"]. '
    "Se não houver fatos duráveis, responda [].\n\nConversa:\n"
)


def _chat(messages: list[dict]) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def chat(user_text: str, facts: list[str] | None = None) -> str:
    system = SYSTEM_PROMPT
    if facts:
        bullet_list = "\n".join(f"- {fact}" for fact in facts)
        system += f"\n\nCoisas que você sabe sobre o usuário:\n{bullet_list}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]
    return _chat(messages).strip()


def extract_facts(user_text: str, assistant_text: str) -> list[str]:
    prompt = (
        f"{FACT_EXTRACTION_PROMPT}Usuário: {user_text}\nAssistente: {assistant_text}"
    )
    messages = [{"role": "user", "content": prompt}]
    raw = _chat(messages).strip()

    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        facts = json.loads(raw)
        if isinstance(facts, list):
            return [str(f).strip() for f in facts if str(f).strip()]
    except json.JSONDecodeError:
        pass
    return []


if __name__ == "__main__":
    reply = chat("Qual seu nome e o que você faz?")
    print("Resposta:", reply)
    facts = extract_facts("Meu voo é às 14h amanhã.", reply)
    print("Fatos extraídos:", facts)
