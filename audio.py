import queue
import threading

import numpy as np
import sounddevice as sd

from config import CHANNELS, SAMPLE_RATE, VAD_CHUNK_SAMPLES

# Setado enquanto o TTS está tocando, pra o VAD ignorar a própria voz do agente.
speaking_event = threading.Event()


def mic_chunks():
    """Gera chunks de áudio (float32, mono) do microfone, do tamanho exigido pelo VAD.

    Ignora chunks capturados enquanto o agente está falando (speaking_event setado).
    """
    q: queue.Queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        q.put(indata[:, 0].copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        blocksize=VAD_CHUNK_SAMPLES,
        dtype="float32",
        callback=callback,
    ):
        while True:
            chunk = q.get()
            if speaking_event.is_set():
                continue
            yield chunk


def play_audio(wav: np.ndarray, sample_rate: int):
    """Toca um array de áudio e bloqueia até terminar, sinalizando speaking_event."""
    speaking_event.set()
    try:
        sd.play(wav, sample_rate)
        sd.wait()
    finally:
        speaking_event.clear()
