import threading

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


def handle_turn(user_text: str) -> str:
    memory.log_turn("user", user_text)

    facts = memory.get_facts()
    reply = llm.chat(user_text, facts=facts)
    memory.log_turn("assistant", reply)

    tts.speak(reply)
    _remember_async(user_text, reply)

    return reply


def run() -> None:
    print("Jarvis pronto. Fale algo (Ctrl+C pra sair).")
    for segment in speech_segments():
        text = stt.transcribe(segment)
        if not text:
            continue
        print(f"Você: {text}")
        reply = handle_turn(text)
        print(f"Jarvis: {reply}")


if __name__ == "__main__":
    run()
