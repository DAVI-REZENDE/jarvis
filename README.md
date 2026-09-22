# Jarvis 🎙️

**Assistente de voz local, 100% offline** — inspirado no Jarvis de Homem de Ferro. Pipeline completo de voz (STT → LLM → TTS) rodando inteiramente na máquina, sem nenhum áudio ou texto saindo para a nuvem, com memória persistente sobre o usuário entre conversas.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/GUI-PySide6-41CD52?logo=qt&logoColor=white)
![Whisper](https://img.shields.io/badge/STT-faster--whisper-412991)
![Ollama](<https://img.shields.io/badge/LLM-Ollama%20(phi4--mini)-000000>)
![Kokoro](https://img.shields.io/badge/TTS-Kokoro-FF6F61)
![SQLite](https://img.shields.io/badge/Memória-SQLite-003B57?logo=sqlite&logoColor=white)
![Offline](https://img.shields.io/badge/Inferência-100%25%20local-success)

## Destaques técnicos

- **Pipeline de voz completo local**: captura de áudio → detecção de fala em tempo real (Silero VAD, máquina de estados) → transcrição (faster-whisper) → raciocínio (LLM via Ollama) → síntese de voz (Kokoro TTS), tudo rodando como processo único com modelos carregados uma única vez (padrão singleton).
- **Engenharia sob restrição real de recursos**: todo o pipeline foi desenhado em torno de um limite de 8GB de RAM (Apple Silicon M1) — decisões de arquitetura documentadas com números reais de latência e consumo de memória, incluindo a rejeição justificada de uma alternativa de TTS que causava swap agressivo do SO.
- **Concorrência e tempo real**: GUI em PySide6 rodando em thread separada do orquestrador de voz, comunicação segura entre threads via Qt Signals, mecanismo de troca de dispositivo de áudio em runtime sem reiniciar o processo (stream de microfone reaberto de forma transparente).
- **Execução de ações com guardrails de segurança**: o LLM nunca decide diretamente qual comando executar — abertura de aplicativos passa por whitelist + regex determinístico antes de qualquer `subprocess.run`, eliminando risco de injeção de comando via fala do usuário.
- **Memória persistente com extração de fatos via LLM**: fatos sobre o usuário são extraídos automaticamente da conversa (SQLite), com prompt engineering iterado e validado empiricamente — incluindo testes comparativos de estratégias de deduplicação (substring vs. similaridade textual) com casos reais que provaram os métodos "mais sofisticados" inseguros para este caso de uso.
- **Decisões orientadas a dados, não a intuição**: cada ajuste de prompt, parâmetro de LLM (temperature, repeat_penalty) e escolha de modelo foi validado com testes manuais registrados — incluindo tentativas que _não_ funcionaram e por quê, evitando retrabalho futuro.

## Como funciona

```
microfone → captura contínua (16kHz)
         → detecção de fala (Silero VAD)
         → transcrição (faster-whisper, pt-BR)
         → orquestrador: busca memória → LLM (Ollama/phi4-mini) → registra turno
         → síntese de voz (Kokoro TTS)
         → alto-falante
         → (em paralelo) extração de fatos novos → memória persistente (SQLite)
```

## Stack

| Camada                    | Tecnologia                                          |
| ------------------------- | --------------------------------------------------- |
| Detecção de fala (VAD)    | Silero VAD                                          |
| STT (voz → texto)         | faster-whisper                                      |
| LLM (raciocínio/conversa) | Ollama (phi4-mini, trocável)                        |
| TTS (texto → voz)         | Kokoro TTS                                          |
| Memória persistente       | SQLite                                              |
| Interface gráfica         | PySide6 (Qt), animações customizadas via `QPainter` |
| Áudio                     | `sounddevice`                                       |

## Instalação

### Requisitos

- **macOS em Apple Silicon** (testado num M1 com 8GB de RAM — veja [`CLAUDE.md`](./CLAUDE.md) para o raciocínio técnico completo por trás das escolhas de arquitetura)
- [Homebrew](https://brew.sh/)
- Python **3.12** (não 3.13 — uma dependência do Kokoro TTS ainda não tem wheel pré-compilada para 3.13 em macOS arm64)
- Um microfone (embutido ou externo)

### 1. Dependências de sistema

```bash
brew install python@3.12 espeak-ng ollama
```

### 2. Clonar o repositório e criar o ambiente virtual

```bash
git clone https://github.com/DAVI-REZENDE/jarvis.git
cd jarvis
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Subir o Ollama e baixar um modelo

```bash
brew services start ollama
ollama pull phi4-mini
```

Qualquer modelo de chat do Ollama funciona — `phi4-mini` é o padrão, trocável direto pela interface (veja Configurações abaixo).

### 4. (Opcional) Criar aliases

```bash
alias jarvis='/caminho/para/jarvis/.venv/bin/python /caminho/para/jarvis/main.py'
alias jarvis-cli='/caminho/para/jarvis/.venv/bin/python /caminho/para/jarvis/orchestrator.py'
```

## Uso

```bash
jarvis          # abre a interface gráfica (uso normal)
jarvis-cli       # modo console, sem GUI, bom para debug
```

Na primeira execução, o Kokoro (TTS) e o Silero VAD baixam seus modelos automaticamente. Depois disso, tudo roda localmente sem internet (exceto ao trocar de modelo do Ollama). Fale naturalmente perto do microfone — o Jarvis detecta início/fim de fala automaticamente, sem push-to-talk.

## Configurações

Pela janela do Jarvis, sem editar código:

- **Microfone** (aplica na hora)
- **Saída de áudio** (aplica na próxima fala)
- **Modelo do Ollama** (aplica na próxima resposta, entre os já baixados via `ollama pull`)

### Ações suportadas

Hoje o Jarvis executa: consultar hora/data atual e abrir um conjunto restrito de aplicativos do Mac (whitelist editável em `config.py`). Qualquer outro pedido de ação é recusado de forma explícita — por design, não é uma limitação escondida.

## Estrutura do projeto

| Arquivo           | Responsabilidade                                        |
| ----------------- | ------------------------------------------------------- |
| `main.py`         | Ponto de entrada, abre a GUI                            |
| `gui.py`          | Interface gráfica (PySide6)                             |
| `orchestrator.py` | Loop principal: ouvir → transcrever → responder → falar |
| `audio.py`        | Captura e reprodução de áudio                           |
| `vad.py`          | Detecção de fala (Silero VAD)                           |
| `stt.py`          | Transcrição de voz (faster-whisper)                     |
| `tts.py`          | Síntese de voz (Kokoro)                                 |
| `llm.py`          | Cliente do Ollama + extração de fatos                   |
| `actions.py`      | Ações reais suportadas (hora/data, abrir app)           |
| `memory.py`       | Memória persistente (SQLite)                            |
| `settings.py`     | Configurações editáveis pela GUI                        |
| `config.py`       | Constantes fixas do projeto                             |

📄 Documentação técnica completa — arquitetura, decisões de engenharia com dados reais de teste, bugs corrigidos e limitações conhecidas — em [`CLAUDE.md`](./CLAUDE.md).

## Limitações conhecidas

- Modelo de linguagem local pequeno: qualidade de conversa inferior a modelos de nuvem, por design (tudo roda offline).
- Conjunto pequeno e fixo de ações reais suportadas.
- Fixado em português do Brasil.
- Fatos conflitantes na memória (ex: mudança de cidade) não são atualizados automaticamente, apenas acumulados.

Detalhes completos em [`CLAUDE.md`](./CLAUDE.md#limitações-conhecidas).
