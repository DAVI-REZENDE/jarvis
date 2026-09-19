import threading
from typing import Callable, Optional

import llm
import memory
import stt
import tts
from vad import speech_segments


def _remember_async(user_text: str, assistant_text: str) -> None:
    def worker():
        for fact in llm.extract_facts(user_text, assistant_text):
            memory.add_fact(fact)

    threading.Thread(target=worker, daemon=True).start()


def handle_turn(user_text: str, on_transcript: Optional[Callable[[str, str], None]] = None) -> str:
    memory.log_turn("user", user_text)
    if on_transcript:
        on_transcript("user", user_text)

    facts = memory.get_facts()
    reply = llm.chat(user_text, facts=facts)
    memory.log_turn("assistant", reply)
    if on_transcript:
        on_transcript("assistant", reply)

    return reply


def run(
    on_status: Optional[Callable[[str], None]] = None,
    on_transcript: Optional[Callable[[str, str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> None:
    """Loop principal: escuta -> transcreve -> responde -> fala.

    on_status(status): chamado com "listening" | "thinking" | "speaking".
    on_transcript(role, text): chamado com role "user" | "assistant".
    should_stop(): se fornecido e retornar True, encerra o loop após o turno atual.
    """

    def status(s: str) -> None:
        if on_status:
            on_status(s)

    status("listening")
    for segment in speech_segments():
        if should_stop and should_stop():
            break

        status("thinking")
        text = stt.transcribe(segment)
        if not text:
            status("listening")
            continue

        reply = handle_turn(text, on_transcript=on_transcript)

        status("speaking")
        tts.speak(reply)
        _remember_async(text, reply)

        status("listening")
        if should_stop and should_stop():
            break


if __name__ == "__main__":

    def _print_transcript(role: str, text: str) -> None:
        label = "Você" if role == "user" else "Jarvis"
        print(f"{label}: {text}")

    print("Jarvis pronto. Fale algo (Ctrl+C pra sair).")
    run(on_transcript=_print_transcript)
