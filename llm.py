import json

import requests

from config import OLLAMA_MODEL, OLLAMA_OPTIONS, OLLAMA_URL, SYSTEM_PROMPT

FACT_EXTRACTION_PROMPT = (
    "Leia a fala do usuário abaixo (ignore completamente a resposta do assistente, ela não "
    "importa aqui) e extraia SOMENTE fatos novos e positivos que o usuário afirmou sobre si "
    "mesmo (profissão, cidade, preferências, nome preferido, etc). "
    'Responda SOMENTE com uma lista JSON de strings, ex: ["mora em São Paulo", "prefere ser chamado de Davi"]. '
    "NUNCA invente um fato, e NUNCA inclua frases negativas ou sobre falta de informação "
    '(ex: "não sabe X", "não tem Y") — isso não é um fato, é ausência de fato, e deve ser '
    "ignorado. Se a fala do usuário não contiver nenhum fato novo, responda [].\n\n"
    "Fala do usuário:\n"
)

ACTION_KEYWORDS = (
    "abrir",
    "abra",
    "abre",
    "que horas",
    "que dia",
    "que data",
    "data de hoje",
    "acessa a internet",
    "acessar a internet",
    "pesquisa na internet",
    "pesquisar na internet",
    "manda uma mensagem",
    "envia uma mensagem",
    "liga pra",
    "liga para",
)

CANT_DO_IT_REPLY = "Ainda não consigo fazer isso."


def _is_action_request(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ACTION_KEYWORDS)


def _chat(messages: list[dict]) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "options": OLLAMA_OPTIONS,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def chat(user_text: str, facts: list[str] | None = None) -> str:
    if _is_action_request(user_text):
        return CANT_DO_IT_REPLY

    system = SYSTEM_PROMPT
    if facts:
        bullet_list = "\n".join(f"- {fact}" for fact in facts)
        system += f"\n\nCoisas que você sabe sobre o usuário:\n{bullet_list}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]
    return _chat(messages).strip()


def extract_facts(user_text: str, assistant_text: str = "") -> list[str]:
    prompt = f"{FACT_EXTRACTION_PROMPT}{user_text}"
    messages = [{"role": "user", "content": prompt}]
    raw = _chat(messages).strip()

    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    negation_markers = ("não sabe", "não tem", "não conhece", "não possui", "sem informação")

    try:
        facts = json.loads(raw)
        if isinstance(facts, list):
            return [
                str(f).strip()
                for f in facts
                if str(f).strip()
                and not any(marker in str(f).lower() for marker in negation_markers)
            ]
    except json.JSONDecodeError:
        pass
    return []


if __name__ == "__main__":
    reply = chat("Qual seu nome e o que você faz?")
    print("Resposta:", reply)
    facts = extract_facts("Meu voo é às 14h amanhã.", reply)
    print("Fatos extraídos:", facts)
