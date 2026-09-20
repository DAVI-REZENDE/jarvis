"""Configurações editáveis em runtime (pela GUI), persistidas em disco.

Diferente de config.py (constantes fixas do projeto), este módulo guarda
valores que o usuário pode trocar sem editar código: dispositivo de entrada/
saída de áudio e o modelo do Ollama. Outros módulos devem ler esses valores
via get() a cada uso (nunca cachear num import), pra uma troca feita na GUI
valer imediatamente.
"""

import json
import threading

import config

SETTINGS_PATH = config.PROJECT_DIR / "settings.json"

_DEFAULTS = {
    "input_device": config.INPUT_DEVICE_NAME,
    "output_device": None,  # None = dispositivo padrão do sistema
    "ollama_model": config.OLLAMA_MODEL,
}

_lock = threading.Lock()


def _load() -> dict:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text())
            return {**_DEFAULTS, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULTS)


_current = _load()


def get(key: str):
    with _lock:
        return _current.get(key, _DEFAULTS.get(key))


def set(key: str, value) -> None:
    with _lock:
        _current[key] = value
        SETTINGS_PATH.write_text(json.dumps(_current, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    print(_current)
