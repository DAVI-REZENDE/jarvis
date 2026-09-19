import sys
import threading
from collections import deque

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import audio
import orchestrator

STATUS_COLORS = {
    "listening": "#38bdf8",  # ciano
    "thinking": "#fbbf24",  # âmbar
    "speaking": "#34d399",  # verde
}
STATUS_LABELS = {
    "listening": "OUVINDO",
    "thinking": "PENSANDO",
    "speaking": "FALANDO",
}


class Bridge(QObject):
    status_changed = Signal(str)
    transcript_added = Signal(str, str)


class Waveform(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self._levels = deque([0.0] * 40, maxlen=40)

    def push_level(self, level: float) -> None:
        self._levels.append(min(level * 8, 1.0))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0a0e14"))

        width = self.width()
        height = self.height()
        n = len(self._levels)
        bar_width = width / n
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#38bdf8"))

        for i, level in enumerate(self._levels):
            bar_height = max(2, level * (height - 8))
            x = i * bar_width
            y = (height - bar_height) / 2
            painter.drawRoundedRect(x + 1, y, bar_width - 2, bar_height, 2, 2)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis")
        self.resize(480, 640)

        self.bridge = Bridge()
        self.bridge.status_changed.connect(self._on_status)
        self.bridge.transcript_added.connect(self._on_transcript)

        self._build_ui()

        self._level_timer = QTimer(self)
        self._level_timer.timeout.connect(self._poll_level)
        self._level_timer.start(33)

        self._worker_thread = threading.Thread(target=self._run_orchestrator, daemon=True)
        self._worker_thread.start()

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.status_label = QLabel("OUVINDO")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            f"color: {STATUS_COLORS['listening']}; font-size: 22px; font-weight: bold; "
            "letter-spacing: 4px;"
        )
        layout.addWidget(self.status_label)

        self.waveform = Waveform()
        layout.addWidget(self.waveform)

        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setStyleSheet(
            "background-color: #11151c; color: #e2e8f0; border: 1px solid #1f2937; "
            "border-radius: 8px; padding: 8px; font-size: 14px;"
        )
        layout.addWidget(self.transcript, stretch=1)

        controls = QHBoxLayout()
        self.mute_button = QPushButton("Mudo: desligado")
        self.mute_button.setCheckable(True)
        self.mute_button.clicked.connect(self._toggle_mute)
        self.mute_button.setStyleSheet(
            "QPushButton { background-color: #1f2937; color: #e2e8f0; border-radius: 6px; "
            "padding: 8px; } QPushButton:checked { background-color: #7f1d1d; }"
        )
        controls.addWidget(self.mute_button)
        layout.addLayout(controls)

        self.setCentralWidget(central)
        self.setStyleSheet("background-color: #0a0e14;")

    def _toggle_mute(self):
        if self.mute_button.isChecked():
            audio.muted_event.set()
            self.mute_button.setText("Mudo: ligado")
        else:
            audio.muted_event.clear()
            self.mute_button.setText("Mudo: desligado")

    def _poll_level(self):
        self.waveform.push_level(audio.get_level())

    def _on_status(self, status: str):
        color = STATUS_COLORS.get(status, "#e2e8f0")
        label = STATUS_LABELS.get(status, status.upper())
        self.status_label.setStyleSheet(
            f"color: {color}; font-size: 22px; font-weight: bold; letter-spacing: 4px;"
        )
        self.status_label.setText(label)

    def _on_transcript(self, role: str, text: str):
        speaker = "Você" if role == "user" else "Jarvis"
        color = "#94a3b8" if role == "user" else "#34d399"
        self.transcript.append(f'<span style="color:{color};"><b>{speaker}:</b> {text}</span>')

    def _run_orchestrator(self):
        orchestrator.run(
            on_status=self.bridge.status_changed.emit,
            on_transcript=self.bridge.transcript_added.emit,
        )


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
