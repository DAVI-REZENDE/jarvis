#!/usr/bin/env python3
"""TTS via Kokoro.

Uso via CLI:
    python tts.py "Oi, tudo bem?" -o saida.wav
    python tts.py "Oi, tudo bem?" -o saida.wav --voice pm_alex
    python tts.py --text-file texto.txt -o saida.wav -l p

Uso como módulo (pipeline carregado uma única vez):
    from tts import speak
    speak("Oi, tudo bem?")  # gera e toca no alto-falante

Idiomas suportados (lang_code): a=en-us, b=en-gb, e=es, f=fr, h=hi,
i=it, j=ja, p=pt-br, z=zh. Vozes pt-br: pf_dora, pm_alex, pm_santa.
"""

import argparse
import sys

import numpy as np
from kokoro import KPipeline

from config import TTS_LANG_CODE, TTS_SAMPLE_RATE, TTS_VOICE

SAMPLE_RATE = TTS_SAMPLE_RATE

_pipeline = None


def _load_pipeline(lang_code: str = TTS_LANG_CODE, device: str | None = None) -> KPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = KPipeline(lang_code=lang_code, device=device)
    return _pipeline


def synthesize(text: str, voice: str = TTS_VOICE, speed: float = 1.0) -> np.ndarray:
    """Gera o áudio (array float32, SAMPLE_RATE) para o texto, sem tocar."""
    pipeline = _load_pipeline()
    chunks = [audio for _, _, audio in pipeline(text, voice=voice, speed=speed)]
    if not chunks:
        raise RuntimeError("Nenhum áudio gerado pelo Kokoro.")
    return np.concatenate(chunks)


def speak(text: str, voice: str = TTS_VOICE, speed: float = 1.0) -> None:
    """Gera e toca o áudio no alto-falante (bloqueia até terminar)."""
    from audio import play_audio

    wav = synthesize(text, voice=voice, speed=speed)
    play_audio(wav, SAMPLE_RATE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera áudio (TTS) com Kokoro.")
    text_group = parser.add_mutually_exclusive_group(required=True)
    text_group.add_argument("text", nargs="?", help="Texto a ser falado.")
    text_group.add_argument("--text-file", help="Arquivo .txt com o texto a ser falado.")

    parser.add_argument("-o", "--output", default="saida.wav", help="Caminho do .wav de saída (padrão: saida.wav).")
    parser.add_argument("-l", "--lang-code", default=TTS_LANG_CODE, help="Código do idioma.")
    parser.add_argument("--voice", default=TTS_VOICE, help=f"Voz a usar (padrão: {TTS_VOICE}).")
    parser.add_argument("--speed", type=float, default=1.0, help="Velocidade da fala (padrão: 1.0).")
    parser.add_argument("--device", default=None, help="Força um device (ex: cpu, mps, cuda). Padrão: automático.")

    return parser.parse_args()


def main() -> None:
    import soundfile as sf

    args = parse_args()

    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
    else:
        text = args.text

    if not text:
        sys.exit("Texto vazio.")

    _load_pipeline(lang_code=args.lang_code, device=args.device)
    wav = synthesize(text, voice=args.voice, speed=args.speed)
    sf.write(args.output, wav, SAMPLE_RATE)
    print(f"Áudio salvo em: {args.output}")


if __name__ == "__main__":
    main()
