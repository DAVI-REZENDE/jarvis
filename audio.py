import queue
import threading
import time

import numpy as np
import sounddevice as sd

from config import CHANNELS, INPUT_DEVICE_NAME, SAMPLE_RATE, VAD_CHUNK_SAMPLES

# Setado enquanto o TTS está tocando, pra o VAD ignorar a própria voz do agente.
speaking_event = threading.Event()

# Setado quando o usuário aperta o botão de mudo na GUI.
muted_event = threading.Event()

_level_lock = threading.Lock()
_level = 0.0


def get_level() -> float:
    """Nível de áudio (RMS aproximado, 0-1) mais recente, pra visualização na GUI."""
    with _level_lock:
        return _level


def _set_level(value: float) -> None:
    global _level
    with _level_lock:
        _level = value


def _find_input_device(name: str):
    for index, device in enumerate(sd.query_devices()):
        if name.lower() in device["name"].lower() and device["max_input_channels"] > 0:
            return index
    return None


def mic_chunks():
    """Gera chunks de áudio (float32, mono) do microfone, do tamanho exigido pelo VAD.

    Ignora chunks capturados enquanto o agente está falando ou está mudo.
    """
    q: queue.Queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        q.put(indata[:, 0].copy())

    device = _find_input_device(INPUT_DEVICE_NAME)
    if device is None:
        print(f"Aviso: dispositivo '{INPUT_DEVICE_NAME}' não encontrado, usando o padrão.")

    with sd.InputStream(
        device=device,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        blocksize=VAD_CHUNK_SAMPLES,
        dtype="float32",
        callback=callback,
    ):
        while True:
            chunk = q.get()
            if speaking_event.is_set() or muted_event.is_set():
                _set_level(0.0)
                continue
            _set_level(float(np.sqrt(np.mean(chunk**2))))
            yield chunk


def play_audio(wav: np.ndarray, sample_rate: int):
    """Toca um array de áudio e bloqueia até terminar, sinalizando speaking_event.

    Enquanto toca, atualiza get_level() com o nível aproximado do áudio de saída,
    pra GUI poder reagir visualmente à fala do agente.
    """
    speaking_event.set()

    def report_levels():
        window = max(1, sample_rate // 20)  # ~50ms
        for i in range(0, len(wav), window):
            if not speaking_event.is_set():
                return
            segment = wav[i : i + window]
            _set_level(float(np.sqrt(np.mean(segment**2))))
            time.sleep(window / sample_rate)

    level_thread = threading.Thread(target=report_levels, daemon=True)
    level_thread.start()
    try:
        sd.play(wav, sample_rate)
        sd.wait()
    finally:
        speaking_event.clear()
        _set_level(0.0)
