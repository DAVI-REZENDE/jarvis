from faster_whisper import WhisperModel

from config import WHISPER_COMPUTE_TYPE, WHISPER_LANGUAGE, WHISPER_MODEL_SIZE

_model = None


def _load_model():
    global _model
    if _model is None:
        _model = WhisperModel(WHISPER_MODEL_SIZE, compute_type=WHISPER_COMPUTE_TYPE)
    return _model


def transcribe(audio) -> str:
    """Transcreve um array numpy (float32, mono, 16kHz) ou um caminho de arquivo de áudio."""
    model = _load_model()
    segments, _ = model.transcribe(audio, language=WHISPER_LANGUAGE)
    return " ".join(segment.text.strip() for segment in segments).strip()


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "hello.m4a"
    print(transcribe(path))
