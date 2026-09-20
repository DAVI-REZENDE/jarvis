import math
import sys
import threading
from collections import deque

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import audio
import llm
import orchestrator
import settings

SYSTEM_DEFAULT = "Padrão do sistema"

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
    """Waveform HUD: barras com decaimento exponencial (sem saltos bruscos) e
    cor sincronizada com o status atual do assistente."""

    # Fator de suavização: quanto maior, mais "grudento"/lento o movimento.
    _SMOOTHING = 0.7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        # Valores já suavizados, prontos pra desenhar (não os níveis brutos).
        self._levels = deque([0.0] * 40, maxlen=40)
        self._color = QColor(STATUS_COLORS["listening"])

    def set_color(self, color_hex: str) -> None:
        self._color = QColor(color_hex)
        self.update()

    def push_level(self, level: float) -> None:
        raw = min(level * 8, 1.0)
        prev = self._levels[-1] if self._levels else 0.0
        # Decaimento exponencial simples: mistura o valor anterior exibido
        # com o novo valor bruto, em vez de pular direto pro novo nível.
        smoothed = prev * self._SMOOTHING + raw * (1 - self._SMOOTHING)
        self._levels.append(smoothed)
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

        for i, level in enumerate(self._levels):
            bar_height = max(2, level * (height - 8))
            x = i * bar_width
            y = (height - bar_height) / 2

            gradient = QLinearGradient(x, y, x, y + bar_height)
            bright = QColor(self._color)
            bright.setAlphaF(min(0.4 + level * 0.6, 1.0))
            dim = QColor(self._color)
            dim.setAlphaF(0.25)
            gradient.setColorAt(0.0, bright)
            gradient.setColorAt(1.0, dim)
            painter.setBrush(gradient)
            painter.drawRoundedRect(x + 1, y, bar_width - 2, bar_height, 2, 2)


class StatusRing(QWidget):
    """Anel circular pulsante ao redor do status, estilo 'arc reactor':
    um arco brilhante gira continuamente e um brilho interno pulsa, ambos
    na cor do status atual. Avançado externamente (mesmo timer de 33ms do
    waveform), sem QPropertyAnimation nem timer próprio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 120)
        self._color = QColor(STATUS_COLORS["listening"])
        self._phase = 0.0

    def set_color(self, color_hex: str) -> None:
        self._color = QColor(color_hex)
        self.update()

    def advance(self, step: float = 0.012) -> None:
        self._phase = (self._phase + step) % 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)

        pulse = (math.sin(self._phase * 2 * math.pi) + 1) / 2  # 0..1

        # Anel base, tênue.
        dim_pen = QPen(QColor(self._color))
        dim_color = QColor(self._color)
        dim_color.setAlpha(50)
        dim_pen.setColor(dim_color)
        dim_pen.setWidth(2)
        painter.setPen(dim_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # Arco brilhante girando.
        arc_color = QColor(self._color)
        arc_color.setAlpha(230)
        arc_pen = QPen(arc_color)
        arc_pen.setWidth(3)
        arc_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(arc_pen)
        span_angle = 70 * 16
        start_angle = int(self._phase * 360 * 16)
        painter.drawArc(rect, start_angle, span_angle)

        # Brilho interno pulsando (expande/contrai e varia opacidade).
        glow_color = QColor(self._color)
        glow_color.setAlphaF(0.12 + 0.28 * pulse)
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow_color)
        inset = 22 + 8 * pulse
        painter.drawEllipse(rect.adjusted(inset, inset, -inset, -inset))


class SettingsDialog(QDialog):
    """Diálogo de Configurações: escolher microfone, saída de áudio e modelo
    do Ollama sem editar código. Microfone e saída aplicam imediatamente
    (audio.py resolve o dispositivo a cada stream/reprodução); o modelo do
    Ollama também aplica na próxima chamada ao LLM."""

    _DIALOG_STYLE = (
        "QDialog { background-color: #0a0e14; }"
        "QLabel { color: #e2e8f0; font-size: 13px; }"
        "QComboBox { background-color: #11151c; color: #e2e8f0; border: 1px solid #1f2937; "
        "border-radius: 6px; padding: 6px; }"
        "QPushButton { background-color: #1f2937; color: #e2e8f0; border-radius: 6px; "
        "padding: 8px 16px; }"
        "QPushButton:hover { background-color: #334155; }"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.setStyleSheet(self._DIALOG_STYLE)
        self.resize(360, 220)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Microfone (entrada de áudio)"))
        self.input_combo = QComboBox()
        self.input_combo.addItems(audio.list_devices("input"))
        current_input = settings.get("input_device")
        if current_input in [self.input_combo.itemText(i) for i in range(self.input_combo.count())]:
            self.input_combo.setCurrentText(current_input)
        layout.addWidget(self.input_combo)

        layout.addWidget(QLabel("Saída de áudio (alto-falante)"))
        self.output_combo = QComboBox()
        self.output_combo.addItem(SYSTEM_DEFAULT)
        self.output_combo.addItems(audio.list_devices("output"))
        current_output = settings.get("output_device")
        self.output_combo.setCurrentText(current_output if current_output else SYSTEM_DEFAULT)
        layout.addWidget(self.output_combo)

        layout.addWidget(QLabel("Modelo do Ollama"))
        self.model_combo = QComboBox()
        models = llm.list_models()
        current_model = settings.get("ollama_model")
        if current_model and current_model not in models:
            models = [current_model] + models
        self.model_combo.addItems(models)
        if current_model:
            self.model_combo.setCurrentText(current_model)
        layout.addWidget(self.model_combo)

        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #fbbf24; font-size: 12px;")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        buttons = QHBoxLayout()
        save_button = QPushButton("Salvar")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    def _save(self):
        new_input = self.input_combo.currentText()
        new_output = self.output_combo.currentText()
        new_model = self.model_combo.currentText()

        input_changed = new_input != settings.get("input_device")

        settings.set("input_device", new_input)
        settings.set("output_device", None if new_output == SYSTEM_DEFAULT else new_output)
        settings.set("ollama_model", new_model)

        if input_changed:
            audio.request_input_restart()

        self.accept()


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
        # Glow colorido conforme o status, com blur pulsando suavemente.
        self._glow = QGraphicsDropShadowEffect()
        self._glow.setOffset(0, 0)
        self._glow.setColor(QColor(STATUS_COLORS["listening"]))
        self._glow.setBlurRadius(20)
        self.status_label.setGraphicsEffect(self._glow)
        self._glow_phase = 0.0
        layout.addWidget(self.status_label)

        self.status_ring = StatusRing()
        ring_row = QHBoxLayout()
        ring_row.addStretch()
        ring_row.addWidget(self.status_ring)
        ring_row.addStretch()
        layout.addLayout(ring_row)

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

        self.settings_button = QPushButton("Configurações")
        self.settings_button.clicked.connect(self._open_settings)
        self.settings_button.setStyleSheet(
            "QPushButton { background-color: #1f2937; color: #e2e8f0; border-radius: 6px; "
            "padding: 8px; } QPushButton:hover { background-color: #334155; }"
        )
        controls.addWidget(self.settings_button)

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

    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def _poll_level(self):
        self.waveform.push_level(audio.get_level())
        self.status_ring.advance()

        # Pulsar o glow do status_label (blur oscilando entre ~15 e ~40px)
        # via seno sobre o mesmo timer de 33ms, sem QPropertyAnimation extra.
        self._glow_phase = (self._glow_phase + 0.02) % 1.0
        pulse = (math.sin(self._glow_phase * 2 * math.pi) + 1) / 2
        self._glow.setBlurRadius(15 + pulse * 25)

    def _on_status(self, status: str):
        color = STATUS_COLORS.get(status, "#e2e8f0")
        label = STATUS_LABELS.get(status, status.upper())
        self.status_label.setStyleSheet(
            f"color: {color}; font-size: 22px; font-weight: bold; letter-spacing: 4px;"
        )
        self.status_label.setText(label)
        self._glow.setColor(QColor(color))
        self.status_ring.set_color(color)
        self.waveform.set_color(color)

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
