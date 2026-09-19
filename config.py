from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

SAMPLE_RATE = 16000
CHANNELS = 1
VAD_CHUNK_SAMPLES = 512  # janela exigida pelo Silero VAD em 16kHz

VAD_SPEECH_THRESHOLD = 0.5
VAD_MIN_SPEECH_CHUNKS = 3     # ~96ms de fala pra confirmar início
VAD_MIN_SILENCE_CHUNKS = 20   # ~640ms de silêncio pra confirmar fim

WHISPER_MODEL_SIZE = "small"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_LANGUAGE = "pt"

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:1.5b-instruct-q4_K_M"

TTS_LANG_CODE = "p"
TTS_VOICE = "pm_alex"
TTS_SAMPLE_RATE = 24000

MEMORY_DB_PATH = PROJECT_DIR / "memory.db"

SYSTEM_PROMPT = (
    "Você é Jarvis, um assistente de voz pessoal, direto e levemente formal. "
    "Responda sempre em português do Brasil, de forma curta (poucas frases), "
    "já que a resposta será falada em voz alta."
)
