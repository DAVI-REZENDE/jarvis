import queue
import threading
import time

import numpy as np
import sounddevice as sd

import settings
from config import CHANNELS, SAMPLE_RATE, VAD_CHUNK_SAMPLES

# Setado enquanto o TTS está tocando, pra o VAD ignorar a própria voz do agente.
speaking_event = threading.Event()

# Setado quando o usuário aperta o botão de mudo na GUI.
muted_event = threading.Event()

# Setado pela GUI (via request_input_restart) quando o usuário troca o
# microfone nas Configurações — mic_chunks() detecta isso e reabre o
# InputStream com o novo dispositivo, sem precisar reiniciar o app.
_restart_input_event = threading.Event()

_level_lock = threading.Lock()
_level = 0.0


def request_input_restart() -> None:
    """Sinaliza pra mic_chunks() fechar o stream atual e reabrir com o
    dispositivo de entrada configurado em settings.py agora."""
    _restart_input_event.set()


def get_level() -> float:
    """Nível de áudio (RMS aproximado, 0-1) mais recente, pra visualização na GUI."""
    with _level_lock:
        return _level


def _set_level(value: float) -> None:
    global _level
    with _level_lock:
        _level = value


def _find_device(name, kind: str):
    """kind: 'input' ou 'output'. Retorna o índice do dispositivo por nome
    (substring case-insensitive), ou None se não encontrado (usa o padrão)."""
    if not name:
        return None
    channels_key = "max_input_channels" if kind == "input" else "max_output_channels"
    for index, device in enumerate(sd.query_devices()):
        if name.lower() in device["name"].lower() and device[channels_key] > 0:
            return index
    return None


def list_devices(kind: str) -> list[str]:
    """Lista nomes de dispositivos disponíveis (kind: 'input' ou 'output'),
    pra popular os dropdowns de Configurações na GUI."""
    channels_key = "max_input_channels" if kind == "input" else "max_output_channels"
    return [d["name"] for d in sd.query_devices() if d[channels_key] > 0]


def mic_chunks():
    """Gera chunks de áudio (float32, mono) do microfone, do tamanho exigido pelo VAD.

    Ignora chunks capturados enquanto o agente está falando ou está mudo. Se o
    dispositivo de entrada mudar em settings.py (via request_input_restart),
    fecha o stream atual e abre um novo com o dispositivo atualizado, sem
    interromper o generator — quem consome (vad.speech_segments) não percebe
    a troca, só um pequeno gap de áudio durante a reabertura.
    """
    while True:
        _restart_input_event.clear()
        q: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            q.put(indata[:, 0].copy())

        input_name = settings.get("input_device")
        device = _find_device(input_name, "input")
        if device is None and input_name:
            print(f"Aviso: dispositivo de entrada '{input_name}' não encontrado, usando o padrão.")

        with sd.InputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            blocksize=VAD_CHUNK_SAMPLES,
            dtype="float32",
            callback=callback,
        ):
            while not _restart_input_event.is_set():
                try:
                    chunk = q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if speaking_event.is_set() or muted_event.is_set():
                    _set_level(0.0)
                    continue
                _set_level(float(np.sqrt(np.mean(chunk**2))))
                yield chunk


def play_audio(wav: np.ndarray, sample_rate: int):
    """Toca um array de áudio e bloqueia até terminar, sinalizando speaking_event.

    Resolve o dispositivo de saída em settings.py a cada chamada, então uma
    troca feita na GUI já vale na próxima fala, sem precisar de restart.
    Enquanto toca, atualiza get_level() com o nível aproximado do áudio de
    saída, pra GUI poder reagir visualmente à fala do agente.
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
        output_device = _find_device(settings.get("output_device"), "output")
        sd.play(wav, sample_rate, device=output_device)
        sd.wait()
    finally:
        speaking_event.clear()
        _set_level(0.0)
