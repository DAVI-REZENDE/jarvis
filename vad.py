import time

import numpy as np
import torch

from audio import mic_chunks
from config import (
    SAMPLE_RATE,
    VAD_MIN_SILENCE_CHUNKS,
    VAD_MIN_SPEECH_CHUNKS,
    VAD_SPEECH_THRESHOLD,
)

_model = None


def _load_model():
    global _model
    if _model is None:
        _model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad", model="silero_vad", trust_repo=True
        )
    return _model


def _speech_prob(model, chunk: np.ndarray) -> float:
    tensor = torch.from_numpy(chunk)
    with torch.no_grad():
        return model(tensor, SAMPLE_RATE).item()


def speech_segments():
    """Gera segmentos de fala completos (arrays float32) a partir do microfone.

    Máquina de estados simples: IDLE -> (N chunks de fala) -> RECORDING ->
    (M chunks de silêncio) -> flush do segmento -> IDLE.
    """
    model = _load_model()

    state = "IDLE"
    speech_run = 0
    silence_run = 0
    buffer: list[np.ndarray] = []

    for chunk in mic_chunks():
        prob = _speech_prob(model, chunk)
        is_speech = prob >= VAD_SPEECH_THRESHOLD

        if state == "IDLE":
            if is_speech:
                speech_run += 1
                buffer.append(chunk)
                if speech_run >= VAD_MIN_SPEECH_CHUNKS:
                    state = "RECORDING"
                    silence_run = 0
            else:
                speech_run = 0
                buffer.clear()
        else:  # RECORDING
            buffer.append(chunk)
            if is_speech:
                silence_run = 0
            else:
                silence_run += 1
                if silence_run >= VAD_MIN_SILENCE_CHUNKS:
                    segment = np.concatenate(buffer)
                    yield segment
                    state = "IDLE"
                    speech_run = 0
                    silence_run = 0
                    buffer = []


if __name__ == "__main__":
    print("Escutando... fale algo (Ctrl+C pra sair)")
    start = None
    for segment in speech_segments():
        duration = len(segment) / SAMPLE_RATE
        print(f"[fala detectada, duração {duration:.2f}s]")
