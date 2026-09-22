"""Ações reais e seguras que o Jarvis pode executar, fora do LLM.

Toda decisão de "qual ação executar" é determinística (regex/keywords) e vive
neste módulo — o LLM nunca escolhe o app a abrir nem gera o comando. Isso é
proposital: deixar o modelo decidir o que rodar em `subprocess` seria um risco
de injeção de comando (o usuário controla o texto que chega até aqui via
fala). Ver CLAUDE.md, seção `actions.py`, pra mais contexto.

`handle(text)` é o único ponto de entrada usado por `llm.chat()`: retorna a
resposta pronta se `text` casar com uma ação suportada e executável, ou
`None` se não for uma ação conhecida (nesse caso quem chama decide: recusa
padrão ou chat normal).
"""

import difflib
import re
import subprocess
from datetime import datetime

from config import ALLOWED_APPS

_WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

_MONTHS = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)

_TIME_PATTERN = re.compile(r"\bque\s+horas\b", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"\b(que\s+dia|que\s+data|data\s+de\s+hoje|dia\s+de\s+hoje)\b", re.IGNORECASE)

# Casa "abrir/abra/abre" (ou verbos equivalentes que na prática só conseguem
# abrir o app, não tocar uma faixa específica: "tocar/toca/coloca/põe/bota")
# + opcionalmente "o/a" + opcionalmente "app/aplicativo" e captura o resto da
# frase como candidato a nome de app. O candidato NUNCA é usado direto em
# subprocess — só depois de passar por `_match_allowed_app`. Frases como
# "toca uma música no Spotify" caem aqui: o app abre, mas nenhuma faixa
# específica é tocada (isso exigiria integração com a API do app, fora de
# escopo) — a resposta ("Abrindo Spotify.") é honesta sobre isso.
_OPEN_APP_PATTERN = re.compile(
    r"\b(?:abrir|abra|abre|tocar|toca|toque|coloca|colocar|põe|bota)\b"
    r"\s*(?:o\s+|a\s+|uma\s+|um\s+)?(?:aplicativo\s+|app\s+|música\s+|musica\s+|som\s+)*(.+)",
    re.IGNORECASE,
)

_FILLER_PHRASES = ("por favor", "pra mim", "para mim", "agora", " aí", " ai")


def _current_time_reply() -> str:
    now = datetime.now()
    return f"Agora são {now.hour}h{now.minute:02d}."


def _current_date_reply() -> str:
    now = datetime.now()
    weekday = _WEEKDAYS[now.weekday()]
    month = _MONTHS[now.month - 1]
    return f"Hoje é {weekday}, {now.day} de {month} de {now.year}."


def _match_allowed_app(candidate: str) -> str | None:
    """Compara `candidate` (texto livre vindo da fala) contra a whitelist.

    Retorna o nome exato do app (valor de ALLOWED_APPS) se houver match
    razoável, ou None caso contrário — nunca retorna o texto original.
    """
    cleaned = candidate.strip().strip(".,!?").lower()
    if not cleaned:
        return None

    for phrase in _FILLER_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    cleaned = cleaned.strip()
    if not cleaned:
        return None

    for key, app_name in ALLOWED_APPS.items():
        if key in cleaned:
            return app_name

    close = difflib.get_close_matches(cleaned, ALLOWED_APPS.keys(), n=1, cutoff=0.7)
    if close:
        return ALLOWED_APPS[close[0]]

    first_words = " ".join(cleaned.split()[:2])
    if first_words and first_words != cleaned:
        close = difflib.get_close_matches(first_words, ALLOWED_APPS.keys(), n=1, cutoff=0.7)
        if close:
            return ALLOWED_APPS[close[0]]

    return None


def _open_app_reply(text: str) -> str | None:
    match = _OPEN_APP_PATTERN.search(text)
    if not match:
        return None

    app_name = _match_allowed_app(match.group(1))
    if not app_name:
        return None

    subprocess.run(["open", "-a", app_name], check=False)
    return f"Abrindo {app_name}."


def handle(text: str) -> str | None:
    """Tenta executar uma ação real e determinística a partir de `text`.

    Retorna a resposta pronta (já executada a ação, se houver) ou None se
    `text` não casar com nenhuma das ações suportadas — nesse caso o chamador
    decide entre a recusa padrão (se for claramente outro pedido de ação) ou
    o chat normal.
    """
    if _TIME_PATTERN.search(text):
        return _current_time_reply()
    if _DATE_PATTERN.search(text):
        return _current_date_reply()
    return _open_app_reply(text)
