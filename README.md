# Jarvis

Assistente de voz local, inspirado no Jarvis de Homem de Ferro: roda
inteiramente offline (exceto o download inicial dos modelos), tem uma
interface gráfica estilo HUD, escuta o microfone continuamente sem botão de
push-to-talk, responde falando, e acumula memória persistente sobre você
entre conversas.

STT (reconhecimento de fala), LLM (conversa) e TTS (síntese de voz) rodam
todos localmente na sua máquina — nenhum áudio ou texto sai para a nuvem.

## Requisitos

- **macOS em Apple Silicon** (testado num M1 com 8GB de RAM — veja
  [`CLAUDE.md`](./CLAUDE.md) para o raciocínio por trás das escolhas feitas
  pensando nesse limite de memória).
- [Homebrew](https://brew.sh/)
- Python **3.12** (não 3.13 — uma dependência do Kokoro TTS ainda não tem
  wheel pré-compilada para 3.13 em macOS arm64 no momento em que este
  projeto foi criado)
- Um microfone (embutido ou externo)

## Instalação

### 1. Dependências de sistema

```sh
brew install python@3.12 espeak-ng ollama
```

### 2. Clonar o repositório e criar o ambiente virtual

```sh
git clone https://github.com/DAVI-REZENDE/jarvis.git
cd jarvis
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Subir o Ollama e baixar um modelo

```sh
brew services start ollama
ollama pull phi4-mini
```

Você pode usar qualquer modelo de chat do Ollama — `phi4-mini` é o padrão do
projeto, mas dá pra trocar depois direto pela interface (veja
[Configurações](#configurações) abaixo). Modelos menores (ex:
`qwen2.5:1.5b-instruct-q4_K_M`) respondem mais rápido e usam menos RAM, à
custa de qualidade de resposta.

### 4. (Opcional) Criar aliases

Pra não ter que digitar o caminho completo toda vez, adicione ao seu
`~/.zshrc` (ajuste o caminho pro seu clone):

```sh
alias jarvis='/caminho/para/jarvis/.venv/bin/python /caminho/para/jarvis/main.py'
alias jarvis-cli='/caminho/para/jarvis/.venv/bin/python /caminho/para/jarvis/orchestrator.py'
```

## Uso

Com o Ollama rodando (`brew services list` pra conferir):

```sh
jarvis          # abre a interface gráfica (uso normal)
# ou, sem os aliases:
.venv/bin/python main.py
```

Na primeira execução, o Kokoro (TTS) e o Silero VAD baixam seus modelos
automaticamente (alguns MB) — pode demorar um pouco. Depois disso, tudo roda
localmente sem precisar de internet (exceto se você trocar de modelo do
Ollama e precisar baixar um novo).

Fale naturalmente perto do microfone — o Jarvis detecta automaticamente
quando você começa e para de falar (sem precisar apertar nada), transcreve,
responde, e fala de volta.

Existe também um modo console, sem interface gráfica, bom pra debug:

```sh
jarvis-cli
# ou:
.venv/bin/python orchestrator.py
```

## Configurações

Clique em **Configurações** na janela do Jarvis pra escolher, sem precisar
editar código:

- **Microfone** (aplica na hora, sem precisar reiniciar o app)
- **Saída de áudio** (aplica na próxima fala)
- **Modelo do Ollama** (aplica na próxima resposta — só aparecem modelos já
  baixados com `ollama pull`)

Essas escolhas ficam salvas em `settings.json` (não versionado).

### Apps que o Jarvis pode abrir

O Jarvis consegue ver a hora/data atual e abrir um pequeno conjunto de
aplicativos do Mac quando pedido por voz (ex: "abre o Spotify"), restrito a
uma whitelist editável em `config.py` (`ALLOWED_APPS`). Qualquer outro pedido
de ação (mandar mensagem, acessar a internet, etc.) ainda não é suportado.

## Estrutura do projeto

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Ponto de entrada, abre a GUI |
| `gui.py` | Interface gráfica (PySide6) |
| `orchestrator.py` | Loop principal: ouvir → transcrever → responder → falar |
| `audio.py` | Captura e reprodução de áudio |
| `vad.py` | Detecção de fala (Silero VAD) |
| `stt.py` | Transcrição de voz (faster-whisper) |
| `tts.py` | Síntese de voz (Kokoro) |
| `llm.py` | Cliente do Ollama + extração de fatos |
| `actions.py` | Ações reais suportadas (hora/data, abrir app) |
| `memory.py` | Memória persistente (SQLite) |
| `settings.py` | Configurações editáveis pela GUI |
| `config.py` | Constantes fixas do projeto |

Para a documentação técnica completa — arquitetura, decisões de projeto e o
porquê de cada uma, bugs já corrigidos e limitações conhecidas — veja
[`CLAUDE.md`](./CLAUDE.md).

## Limitações conhecidas

- Modelo de linguagem local pequeno: qualidade de conversa inferior a
  modelos de nuvem (ChatGPT, Claude, etc.), por design — tudo roda offline.
- Só executa um conjunto pequeno e fixo de ações reais (ver acima).
- Fixado em português do Brasil.
- Fatos conflitantes na memória (ex: você mudar de cidade) não são
  atualizados automaticamente, apenas acumulados.

Detalhes completos em [`CLAUDE.md`](./CLAUDE.md#limitações-conhecidas).
