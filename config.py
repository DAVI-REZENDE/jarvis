from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

SAMPLE_RATE = 16000
CHANNELS = 1
INPUT_DEVICE_NAME = "HyperX Cloud Stinger 2 Wireless"
VAD_CHUNK_SAMPLES = 512  # janela exigida pelo Silero VAD em 16kHz

VAD_SPEECH_THRESHOLD = 0.5
VAD_MIN_SPEECH_CHUNKS = 3     # ~96ms de fala pra confirmar início
VAD_MIN_SILENCE_CHUNKS = 20   # ~640ms de silêncio pra confirmar fim

WHISPER_MODEL_SIZE = "small"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_LANGUAGE = "pt"

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "phi4-mini"

TTS_LANG_CODE = "p"
TTS_VOICE = "pm_alex"
TTS_SAMPLE_RATE = 24000

MEMORY_DB_PATH = PROJECT_DIR / "memory.db"

SYSTEM_PROMPT = (
    "Você é Jarvis, um assistente de voz pessoal. Responda somente em português "
    "do Brasil, nunca misture palavras de outro idioma. Responda em 1 frase curta, "
    "direto ao ponto, sem ressalvas ou avisos extras."
)

# Parâmetros de geração passados em "options" no payload do /api/chat do Ollama.
# temperature mais baixa e repeat_penalty levemente acima do default reduzem
# divagação e mistura de idioma do phi4-mini sem prejudicar a extração de fatos
# (testado manualmente, ver Task 2 em TASKS.md / CLAUDE.md).
OLLAMA_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.1,
}
