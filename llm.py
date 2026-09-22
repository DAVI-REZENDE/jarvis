import json

import requests

import actions
import settings
from config import OLLAMA_OPTIONS, OLLAMA_URL, SYSTEM_PROMPT

FACT_EXTRACTION_PROMPT = (
    "Leia a fala do usuário abaixo (ignore completamente a resposta do assistente, ela não "
    "importa aqui) e extraia fatos novos que o usuário afirmou sobre si mesmo (profissão, "
    "localização, preferências — inclusive preferências negativas genuínas como 'não gosto de "
    "X' —, nome preferido, etc).\n"
    "Cada fato deve ser uma frase COMPLETA, natural e AUTOCONTIDA em português (faz sentido "
    "sozinha, fora de contexto) — nunca use formato 'chave: valor' (ex: nunca escreva 'Nome: "
    "João', escreva 'se chama João' ou 'nome é João'). "
    "Agrupe em um único fato toda informação que pertence junta e faz parte da mesma ideia — "
    "por exemplo, bairro/setor e cidade formam UM fato de localização só, não dois fatos "
    "separados; nunca elimine parte da informação original (se o usuário disse bairro e cidade, "
    "o fato final deve conter os dois). Só separe em fatos diferentes quando forem sobre "
    "assuntos realmente distintos (ex: profissão é um fato separado de localização).\n"
    "Exemplo: para a fala \"Eu moro em Curitiba, no bairro Água Verde, trabalho como programador\", a "
    'resposta correta é ["mora no bairro Água Verde, em Curitiba", "trabalha como programador"] — note '
    "que o setor e a cidade viraram um fato só, e a resposta é uma frase natural, não um par "
    "chave:valor.\n"
    "Responda SOMENTE com uma lista JSON de strings. "
    "NUNCA invente um fato. NUNCA inclua frases sobre AUSÊNCIA de informação, tipo o assistente "
    '"não saber" ou "não ter" um dado sobre o usuário (ex: "não sabe a profissão do usuário") — '
    "isso não é um fato, é ausência de fato. Isso é diferente de uma preferência negativa "
    'genuína do próprio usuário (ex: "não gosto de café", "não como carne") — essas SÃO fatos '
    "válidos e devem ser mantidas. Se a fala do usuário não contiver nenhum fato novo, responda "
    "[].\n\n"
    "Fala do usuário:\n"
)

ACTION_KEYWORDS = (
    "abrir",
    "abra",
    "abre",
    "toca uma música",
    "toca uma musica",
    "tocar uma música",
    "tocar uma musica",
    "coloca uma música",
    "coloca uma musica",
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


def list_models() -> list[str]:
    """Lista os modelos já baixados no Ollama (ollama pull ...), pra popular
    o dropdown de Configurações na GUI."""
    tags_url = OLLAMA_URL.rsplit("/", 1)[0] + "/tags"
    try:
        response = requests.get(tags_url, timeout=5)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except requests.RequestException:
        return []


def _chat(messages: list[dict]) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": settings.get("ollama_model"),
            "messages": messages,
            "stream": False,
            "options": OLLAMA_OPTIONS,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def chat(user_text: str, facts: list[str] | None = None) -> str:
    action_reply = actions.handle(user_text)
    if action_reply is not None:
        return action_reply

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
