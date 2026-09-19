# Jarvis — Spec técnica do projeto

Este arquivo é a fonte de contexto para qualquer agente (humano ou IA) que for
mexer neste projeto. Leia tudo antes de alterar código. Se algo aqui divergir
do código real, **o código é a verdade** — atualize este documento.

## Visão geral

Jarvis é um assistente de voz local, inspirado no Jarvis de Homem de Ferro:
roda inteiramente offline (exceto o download inicial dos modelos), tem uma
GUI, escuta o microfone continuamente sem botão de push-to-talk, responde
falando, e acumula memória persistente sobre o usuário entre conversas.

Não há nenhum componente de nuvem no caminho de execução — STT, LLM e TTS
rodam todos localmente na máquina do usuário.

## Restrição mais importante: 8GB de RAM

**Máquina alvo:** MacBook Apple Silicon M1 com **apenas 8GB de RAM unificada**.
Essa é a restrição de projeto mais importante e molda praticamente toda
decisão de arquitetura abaixo.

Um teste anterior com **Chatterbox TTS** (removido do projeto, não reintroduzir)
mostrou o que acontece quando essa restrição é ignorada: sob pressão de
memória o macOS começa a fazer swap agressivo, e a latência de resposta
explodiu de <1s para 30-40s por passo. Isso é catastrófico para um assistente
de voz que precisa parecer responsivo.

Consequência prática: todo o pipeline roda como **um único processo Python
residente**, com todos os modelos (Silero VAD, faster-whisper, Kokoro TTS)
carregados **uma única vez** (padrão singleton) e mantidos em memória durante
toda a sessão — nunca recarregados por turno de conversa. O LLM (Ollama) roda
como processo separado porque o próprio Ollama já gerencia isso bem, mas
mesmo lá a escolha de modelo pesa RAM (ver seção do `llm.py`/Ollama abaixo).
Qualquer mudança futura deve considerar o custo de RAM antes de tudo — não
adicionar bibliotecas pesadas sem necessidade real.

## Arquitetura — fluxo de dados

```
microfone (HyperX Cloud Stinger 2 Wireless, fallback: dispositivo padrão)
  -> audio.mic_chunks()          [captura contínua, chunks de 512 amostras @16kHz]
  -> vad.speech_segments()       [Silero VAD, máquina de estados IDLE/RECORDING]
  -> stt.transcribe()            [faster-whisper "small", int8, pt-BR]
  -> orchestrator.handle_turn()
       -> memory.get_facts()     [fatos conhecidos do SQLite]
       -> llm.chat()             [actions.handle() determinístico -> ação real ou Ollama/phi4-mini]
       -> memory.log_turn()      [grava turno bruto no conversation_log]
  -> tts.speak()                 [Kokoro TTS, voz pm_alex pt-BR]
  -> audio.play_audio()          [alto-falante, seta speaking_event durante a fala]

  (em paralelo, após cada turno, em background thread)
  orchestrator._remember_async() -> llm.extract_facts() -> memory.add_fact()
```

A GUI (`gui.py`) roda o `orchestrator.run()` inteiro numa thread separada e
recebe atualizações via callbacks (`on_status`, `on_transcript`) que são
repassados para a thread principal do Qt através de `Signal`s (classe
`Bridge`), porque widgets Qt só podem ser atualizados na thread principal.

Dois mecanismos evitam problemas de eco/concorrência no áudio:
- `audio.speaking_event`: setado enquanto o TTS está tocando; o VAD ignora
  chunks de microfone capturados nesse período, para o agente não se
  auto-transcrever.
- `audio.muted_event`: controlado pelo botão de mudo da GUI; mesmo efeito,
  mas por decisão do usuário.

## Ambiente Python

- **Venv de produção:** `~/.venvs/jarvis-agent`, Python **3.12** (confirmado:
  `Python 3.12.14`). **Não usar Python 3.13** — a dependência `blis`/`spacy`
  (puxada transitivamente pelo Kokoro) ainda não tem wheel pré-compilada para
  Python 3.13 em macOS arm64 no momento em que este projeto foi criado.
- Pacotes principais: `faster-whisper`, `kokoro`, `soundfile`, `numpy`,
  `sounddevice`, `requests`, `PySide6`, `torch`, `torchaudio`.
- **Venvs legadas (não usar no pipeline principal, mas ainda existem no disco):**
  - `~/.venvs/whisper` — `openai-whisper`, usada só no teste inicial de STT
    antes de migrar para `faster-whisper`. Órfã, mantida por histórico.
  - `~/.venvs/kokoro` — usada apenas pelo alias de linha de comando `tts`
    (uso standalone do TTS fora do app, ver `tts.py` seção CLI).
- Todo o pipeline de produção (GUI e modo console) roda dentro de
  `~/.venvs/jarvis-agent`.

### Aliases (`~/.zshrc`)

| alias | comando | uso |
|---|---|---|
| `jarvis` | `~/.venvs/jarvis-agent/bin/python main.py` | abre a GUI (uso principal) |
| `jarvis-cli` | `~/.venvs/jarvis-agent/bin/python orchestrator.py` | modo console, sem GUI, bom para debug |
| `tts` | `~/.venvs/kokoro/bin/python tts.py` | TTS standalone via CLI, fora do app |

### Ollama

Instalado via Homebrew (`brew install ollama`), rodando como serviço em
background (`brew services start ollama`). API usada: HTTP local
(`http://localhost:11434/api/chat`) via `requests` — **não usar o pacote pip
`ollama`**, o cliente é feito à mão em `llm.py`.

**Modelo atual: `phi4-mini`.** Foi testado antes `qwen2.5:1.5b-instruct-q4_K_M`
(mais leve e mais rápido: ~1GB RAM / ~3.4s por resposta, contra ~2.76GB RAM /
~8.6s do phi4-mini), mas o usuário preferiu explicitamente o phi4-mini apesar
do trade-off de latência/RAM maior. Se otimizar RAM/latência global do
sistema virar prioridade no futuro, essa é uma alavanca conhecida — mas não
trocar sem pedido explícito do usuário, já foi decidido conscientemente.

## Módulos

### `main.py`
Entrypoint mínimo: importa `main` de `gui.py` e chama. Sem lógica própria.

### `gui.py`
Janela principal em PySide6 (`MainWindow`), estilo HUD escuro (paleta ciano/
âmbar/verde sobre fundo quase preto `#0a0e14`). Elementos:
- `status_label`: mostra "OUVINDO" (ciano), "PENSANDO" (âmbar) ou "FALANDO"
  (verde), conforme o status emitido pelo orchestrator. Tem um
  `QGraphicsDropShadowEffect` (glow) na cor do status atual, cujo
  `blurRadius` pulsa suavemente (oscilação senoidal entre ~15px e ~40px)
  a cada tick do `_level_timer` de 33ms — sem `QPropertyAnimation` nem timer
  extra, só um cálculo de `math.sin` sobre uma fase acumulada.
- `StatusRing` (Task 4): widget customizado (`QPainter`) abaixo do
  `status_label`, um anel/arco estilo "arc reactor": um anel base tênue na
  cor do status, um arco mais brilhante que gira continuamente
  (`drawArc` avançando a fase a cada frame), e um brilho interno que
  pulsa em raio e opacidade (seno). Também avançado pelo mesmo timer de
  33ms via `advance()` — nenhum timer/animação adicional.
- `Waveform`: widget customizado (`QPainter`) que desenha barras verticais a
  partir de um histórico (`deque`, 40 amostras) do nível de áudio, atualizado
  por um `QTimer` a cada 33ms via `audio.get_level()`. Desde a Task 4, os
  valores exibidos passam por um decaimento exponencial simples
  (`nivel_exibido = nivel_exibido * 0.7 + novo_nivel * 0.3`, aplicado em
  `push_level`) em vez de saltar direto pro novo valor bruto — o histórico
  guarda apenas os valores já suavizados. Cada barra é desenhada com um
  `QLinearGradient` vertical (mais opaco no topo, mais transparente na base)
  na cor do status atual (`set_color`), em vez de um ciano fixo — o waveform
  agora reage visualmente também à mudança de status, não só ao nível.
- `transcript`: `QTextEdit` somente leitura, mostra o histórico da conversa
  (usuário em cinza, Jarvis em verde).
- Botão de mudo (`mute_button`): alterna `audio.muted_event`.

Todos os efeitos visuais (glow, anel, gradiente do waveform) reutilizam o
`_level_timer` já existente (30fps/33ms) — nenhum timer novo foi adicionado,
e nenhuma dependência externa de animação (Qt/PySide6 puro:
`QGraphicsDropShadowEffect`, `QLinearGradient`, `QPainter.drawArc`,
`math.sin`), pra não pressionar ainda mais os 8GB de RAM compartilhados com
Whisper/Kokoro/Ollama.

O `orchestrator.run()` roda numa `threading.Thread` separada
(`_run_orchestrator`), e comunica com a UI via `Bridge(QObject)` com dois
`Signal`s (`status_changed`, `transcript_added`) — isso é necessário porque
widgets Qt não podem ser tocados fora da thread principal, e emitir um Signal
de outra thread é a forma correta de fazer essa ponte com segurança.

### `orchestrator.py`
Loop principal do assistente. Duas funções públicas:
- `handle_turn(user_text, on_transcript=None) -> str`: processa um turno de
  texto já transcrito — loga a fala do usuário, busca fatos conhecidos
  (`memory.get_facts()`), chama `llm.chat()`, loga a resposta, retorna o
  texto da resposta. Não lida com áudio.
- `run(on_status=None, on_transcript=None, should_stop=None)`: loop
  infinito (ou até `should_stop()` retornar `True`) que consome
  `vad.speech_segments()`, transcreve com `stt.transcribe()`, chama
  `handle_turn()`, fala a resposta com `tts.speak()`, e dispara
  `_remember_async()` em background.

`_remember_async(user_text, assistant_text)`: roda `llm.extract_facts()` e
`memory.add_fact()` numa thread daemon separada, **depois** da fala já ter
sido tocada — isso é deliberado, para a extração de fatos (uma chamada extra
ao LLM) não atrasar a resposta falada ao usuário. Note que `assistant_text`
ainda é passado para `_remember_async`, mas `llm.extract_facts` hoje ignora
esse parâmetro no prompt (ver seção `llm.py`).

Tem um bloco `__main__` que roda o loop imprimindo o transcript no console —
é o que o alias `jarvis-cli` executa.

### `audio.py`
Camada de I/O de áudio, usando `sounddevice`.
- `mic_chunks()`: generator que abre um `sd.InputStream` no dispositivo
  configurado (`INPUT_DEVICE_NAME`, com fallback para o dispositivo padrão do
  sistema se não encontrado por nome) e produz chunks float32 mono do tamanho
  exigido pelo VAD (`VAD_CHUNK_SAMPLES`). Ignora (não produz) chunks
  capturados enquanto `speaking_event` ou `muted_event` estiverem setados.
- `play_audio(wav, sample_rate)`: toca um array de áudio via `sd.play`/
  `sd.wait`, setando `speaking_event` durante a reprodução. Roda uma thread
  auxiliar (`report_levels`) que atualiza `get_level()` a partir do próprio
  áudio de saída, em janelas de ~50ms, para a GUI conseguir reagir
  visualmente à fala do agente (o waveform "responde" tanto ao mic quanto ao
  TTS, dependendo de quem está "falando" no momento).
- `speaking_event` / `muted_event`: `threading.Event`s globais, compartilhados
  entre os módulos — mecanismo central de evitar eco/auto-transcrição e de
  implementar o botão de mudo da GUI.
- `get_level()` / `_set_level()`: nível de áudio aproximado (RMS), protegido
  por lock, consumido pelo `Waveform` da GUI.

### `vad.py`
Detecção de atividade de voz com **Silero VAD**, carregado via
`torch.hub.load("snakers4/silero-vad", ...)`, singleton em `_model`.
`speech_segments()` é uma máquina de estados simples sobre os chunks de
`audio.mic_chunks()`:
- `IDLE`: acumula chunks de fala consecutivos; após `VAD_MIN_SPEECH_CHUNKS`
  (3, ~96ms) chunks de fala seguidos, transiciona para `RECORDING`.
- `RECORDING`: continua bufferizando; conta silêncio consecutivo; após
  `VAD_MIN_SILENCE_CHUNKS` (20, ~640ms) chunks de silêncio, dá flush do
  buffer inteiro como um segmento de fala completo (`np.concatenate`) e volta
  para `IDLE`.

Tem um bloco `__main__` standalone (`python vad.py`) para testar detecção de
fala isoladamente, imprimindo a duração de cada segmento detectado — já
validado manualmente pelo usuário, sem falso-positivo em silêncio.

### `stt.py`
Wrapper fino sobre `faster_whisper.WhisperModel`, singleton em `_model`.
Configuração fixa: modelo `"small"`, `compute_type="int8"` (mais leve em
CPU/RAM, importante dado o limite de 8GB), `language="pt"` fixo (sem
detecção automática de idioma). `transcribe(audio)` aceita tanto um array
numpy (float32, mono, 16kHz) quanto um caminho de arquivo.

Bloco `__main__`: `python stt.py [caminho.wav]`, com `hello.m4a` como
default — arquivo de fixture de teste (~8s, "Olá Jarvis, quero que você
consulte como está o clima para o voo hoje.").

### `tts.py`
Wrapper sobre **Kokoro TTS** (`KPipeline`), singleton em `_pipeline`.
Configuração padrão: `lang_code="p"` (pt-BR), voz `pm_alex` (português,
masculina), `sample_rate=24000`.
- `synthesize(text, voice, speed) -> np.ndarray`: gera o áudio sem tocar.
- `speak(text, voice, speed)`: gera e toca via `audio.play_audio`
  (import feito dentro da função para evitar import circular com `audio.py`).
- Também mantém o uso original como script CLI standalone
  (`if __name__ == "__main__"`, com `argparse`), que é o que o alias `tts`
  executa fora do pipeline principal — permite gerar um `.wav` a partir de
  texto ou arquivo de texto, escolhendo voz/idioma/velocidade/device.

### `llm.py`
Cliente HTTP puro (via `requests`) para a API local do Ollama — sem o pacote
pip `ollama`. `_chat` envia sempre um campo `options` no payload do
`/api/chat` com `OLLAMA_OPTIONS` (`config.py`): `temperature=0.2` e
`repeat_penalty=1.1`. Isso foi ajustado na Task 2 (ver seção de decisões
técnicas) depois de testar empiricamente várias combinações — `temperature`
baixa reduz divagação e mistura de idioma; `repeat_penalty` alto demais
(testado 1.3) piora bastante a coerência e faz o modelo ignorar a instrução
de resposta curta, então foi mantido moderado (1.1). Duas funções principais:

- `chat(user_text, facts=None) -> str`: primeiro chama `actions.handle(user_text)`
  (Task 3) — se `user_text` casar com uma das ações reais suportadas (ver
  `actions.py` abaixo), a ação já foi executada e sua resposta é retornada
  direto, sem nenhuma chamada ao LLM. Se `actions.handle` retornar `None`
  (não é uma dessas ações), cai na checagem antiga:
  `_is_action_request(user_text)` contra `ACTION_KEYWORDS` (uma tupla de
  palavras/frases como "abrir", "que horas", "liga pra" etc.); se der match,
  retorna `CANT_DO_IT_REPLY = "Ainda não consigo fazer isso."` sem chamar o
  LLM (agora essa recusa cobre só pedidos de ação **fora** do pequeno
  conjunto suportado, ex: "manda uma mensagem", "abrir" um app fora da
  whitelist). Caso contrário, monta o system prompt normalmente e segue pro
  chat comum.

  **Por quê a decisão de ação está em código e não no prompt/LLM:** foi
  tentado primeiro resolver via instrução condicional no system prompt ("só
  recuse quando for um pedido de ação real"), mas o phi4-mini (modelo
  pequeno) não seguia essa regra de forma confiável — ou recusava demais
  (ficando prolixo/repetitivo) ou não recusava quando devia. Mover a decisão
  para uma checagem determinística em código eliminou essa inconsistência.
  A mesma lógica se aplica à Task 3: o LLM **nunca** decide qual app abrir
  nem gera o comando — isso seria abrir espaço pra injeção de comando via
  fala do usuário. Toda decisão de intent (hora/data vs abrir app vs
  nenhuma ação) é regex/keyword em `actions.py`, e o nome do app só chega em
  `subprocess.run` depois de validado contra uma whitelist fixa. Ver também a
  seção de bugs corrigidos, item 2.

### `actions.py` (Task 3)
Módulo novo com as únicas ações reais que o Jarvis executa hoje, chamado por
`llm.chat()` antes de qualquer chamada ao LLM. Ponto de entrada único:
`handle(text) -> str | None` — retorna a resposta já pronta se `text` casar
com uma ação suportada (a ação já foi executada), ou `None` se não for
nenhuma delas (nesse caso `llm.chat` decide entre a recusa padrão ou o chat
normal).

Duas ações suportadas, ambas com detecção 100% determinística (regex, sem
LLM envolvido na decisão):
- **Ver hora atual**: `_TIME_PATTERN` (`r"\bque\s+horas\b"`) casa "que
  horas"; resposta 100% local via `datetime.now()`, formatada por extenso
  pra soar natural no TTS (ex: "Agora são 14h32."). Nenhuma chamada ao
  Ollama acontece nesse caminho.
- **Ver data atual**: `_DATE_PATTERN` casa "que dia"/"que data"/"data de
  hoje"/"dia de hoje"; resposta também 100% local, com dia da semana e mês
  por extenso (ex: "Hoje é quinta-feira, 19 de setembro de 2026."). Também
  sem chamada ao LLM.
- **Abrir um app do Mac**: `_OPEN_APP_PATTERN` casa "abrir/abra/abre" (+
  opcionalmente "o/a", "app/aplicativo") e captura o resto da frase como
  candidato a nome de app — esse candidato **nunca** vai direto pro
  `subprocess`. `_match_allowed_app(candidate)` primeiro remove frases de
  preenchimento comuns ("por favor", "pra mim", "agora" etc.), depois checa
  se alguma chave de `ALLOWED_APPS` (`config.py`) está contida no texto
  limpo, e só se não achar nada tenta um fuzzy-match conservador
  (`difflib.get_close_matches`, cutoff 0.7) contra as chaves da whitelist —
  isso existe pra tolerar variações de fala tipo "abre o spotify pra mim"
  sem nunca abrir algo fora da lista. Se e só se houver match, executa
  `subprocess.run(["open", "-a", app_name], check=False)` — sempre como
  lista de argumentos, nunca `shell=True` nem concatenação de string, pra
  eliminar risco de shell injection. Se não houver match (app não
  reconhecido ou fora da whitelist), retorna `None` e quem decide o que
  fazer é `llm.chat` (cai na recusa padrão, porque "abrir" ainda está em
  `ACTION_KEYWORDS`).

  **Nota de nomes de app no macOS:** confirmado manualmente que `open -a`
  precisa do nome real do bundle do app, que continua em inglês mesmo com o
  macOS em pt-BR (ex: `open -a Notes` funciona, `open -a Notas` falha com
  "Unable to find application named 'Notas'"). Por isso `ALLOWED_APPS` em
  `config.py` mapeia a chave em português (o que o usuário fala) pro nome
  real em inglês usado no `open -a`.

Nenhuma outra ação foi implementada (nada de internet, mensagens, volume
etc — fora de escopo da Task 3, deliberadamente).

- `extract_facts(user_text, assistant_text="") -> list[str]`: extrai fatos
  novos usando **somente a fala do usuário** — o parâmetro `assistant_text`
  existe na assinatura (e ainda é passado por `orchestrator._remember_async`)
  mas **não é usado no prompt de extração** (`FACT_EXTRACTION_PROMPT`
  inclusive instrui explicitamente "ignore completamente a resposta do
  assistente"). Isso foi uma correção deliberada: antes a extração
  considerava a resposta do assistente, e quando essa resposta era a recusa
  fixa (`CANT_DO_IT_REPLY`), o extrator concluía erroneamente que nada tinha
  sido confirmado e descartava fatos reais ditos pelo usuário. Ver bug 3.

  A função também filtra manualmente qualquer fato que contenha
  `negation_markers` ("não sabe", "não tem", "não conhece", "não possui",
  "sem informação") como uma segunda camada de defesa além da instrução no
  prompt (ver bug 1). Parse é feito esperando uma lista JSON de strings na
  resposta do modelo, com tratamento de blocos ```` ```json ```` e fallback
  para lista vazia em caso de JSON inválido.

  **Task 5 — granularidade/qualidade da extração.** `FACT_EXTRACTION_PROMPT`
  foi revisado porque a extração fragmentava informação relacionada (ex: a
  frase "moro em Goiânia, no setor Perim, trabalho como programador" perdia
  completamente "no setor Perim", produzindo só `['Moro em Goiânia',
  'Trabalho como programador']`). O prompt agora instrui explicitamente a
  **agrupar** informação que pertence junta num único fato coeso (ex:
  bairro/setor + cidade = um fato só), a produzir frases naturais e
  autocontidas (proibindo formato "chave: valor" tipo "Nome: Davi"), e a
  distinguir claramente dois tipos de negação: (1) ausência de informação
  ("não sabe X") — continua descartado — vs (2) preferência negativa genuína
  do usuário ("não gosto de café") — agora explicitamente mantida como fato
  válido (o texto antigo do prompt dizia "NUNCA inclua frases negativas", o
  que fazia o modelo descartar até preferências negativas reais; teste
  manual confirmou "Eu não gosto de café." zerava para `[]` antes da
  correção). `negation_markers` em código não precisou mudar — já era restrito
  a marcadores de ausência de informação ("não sabe", "não tem" etc.), nunca
  batia com "não gosta"/"não gosto".

  **Few-shot funcionou bem aqui, ao contrário do `SYSTEM_PROMPT` geral (Task
  2).** Foi testado explicitamente por instrução deste backlog, já que a Task
  2 tinha descartado few-shot no prompt de chat aberto. Resultado real: sem
  nenhum exemplo no prompt, o phi4-mini continuava fragmentando/alucinando
  (`['Moro em Goiânia', 'Perigo de Goiânia', 'Trabalho como Programador']` —
  chegou a inventar "Perigo de Goiânia" a partir de "setor Perim"). Com **um**
  exemplo rico no prompt (a própria frase do setor Perim, mostrando o
  agrupamento correto), o resultado ficou estável e correto em repetições:
  `['moro no setor Perim, em Goiânia', 'trabalho como programador']`. Uma
  variante com **dois** exemplos foi testada e piorou a estabilidade (erro de
  parse de JSON numa repetição, fato de preferência negativa sumindo em outra
  repetição) — provavelmente por o modelo pequeno "seguir demais" o padrão de
  frase composta dos exemplos e se confundir com entradas mais simples que não
  se encaixam nesse padrão. Conclusão: few-shot ajuda numa tarefa mecânica/
  estruturada como extração de JSON (diferente de gerar uma resposta de chat
  aberta), mas só com **um único exemplo bem escolhido** — mais que isso
  reintroduz instabilidade, mesmo aqui.

Bloco `__main__`: `python llm.py` testa `chat()` e `extract_facts()` em
sequência, imprimindo os resultados.

### `memory.py`
Persistência em SQLite (`memory.db`, na raiz do projeto — **gitignored**,
nunca commitar). Duas tabelas:
- `facts (id, fact UNIQUE, created_at)`: fatos extraídos sobre o usuário.
  `add_fact()` faz uma checagem de deduplicação manual em Python (não
  depende só do `UNIQUE` do SQL): compara o fato novo contra todos os
  existentes, case-insensitive, e descarta se houver correspondência exata
  **ou substring em qualquer direção** (fato novo contido em um existente, ou
  vice-versa). Essa checagem substring é intencionalmente simples/conservadora
  e é conhecida por ser frágil com fatos fragmentados (ver limitações).
- `conversation_log (id, role, content, timestamp)`: histórico bruto de
  turnos (não usado para montar o prompt do LLM — o prompt usa apenas
  `facts`, não o histórico bruto).

  **Task 5 — dedup foi avaliada e mantida como substring simples,
  deliberadamente.** Foram testados dois substitutos por similaridade —
  `difflib.SequenceMatcher.ratio()` (caractere a caractere) e Jaccard sobre
  conjunto de palavras (sem stopwords) — com pares reais de teste. Resultado
  real, não hipotético: nenhum dos dois separa de forma confiável duplicata
  real de fato genuinamente diferente com um único threshold. Exemplos
  medidos: `SequenceMatcher` deu 0.836 para `"prefere ser chamado de Chefe"`
  vs `"prefere ser chamado de Davi"` (nomes **diferentes**, não deveria ser
  duplicata) — mais alto que 0.700 para o par que **é** duplicata real
  (`"mora em Goiânia"` vs `"mora na cidade de Goiânia"`). Jaccard por palavra
  foi ainda mais perigoso: deu 0.667 para `"gosta de café"` vs `"não gosta de
  café"` — **fatos opostos**, mesma pontuação do par de duplicata real. Usar
  qualquer um desses com threshold fixo arriscaria descartar silenciosamente
  um fato genuinamente nono (ex: perder que o usuário passou a não gostar de
  algo que antes gostava) — pior que o problema atual (raramente, duas
  entradas quase-duplicatas coexistindo). Por isso a dedup em `memory.py`
  continua substring case-insensitive simples; a fragmentação de fatos (causa
  raiz da maioria dos quase-duplicados) já foi atacada na origem via
  `FACT_EXTRACTION_PROMPT` (ver seção `llm.py`), o que reduz bastante a
  frequência do problema sem precisar de uma dedup mais arriscada.

`get_facts(limit=50)` retorna os mais recentes primeiro (`ORDER BY
created_at DESC`).

Bloco `__main__`: insere um fato de teste duas vezes seguidas pra confirmar
que a deduplicação funciona, e imprime `get_facts()`.

### `config.py`
Todas as constantes do projeto centralizadas num único lugar — nenhum outro
módulo deve hardcodar esses valores:
- Áudio: `SAMPLE_RATE=16000`, `CHANNELS=1`,
  `INPUT_DEVICE_NAME="HyperX Cloud Stinger 2 Wireless"` (o usuário trocou do
  microfone embutido do Mac para esse headset porque a qualidade do STT
  estava ruim com o mic embutido — ver bug 4), `VAD_CHUNK_SAMPLES=512`.
- VAD: `VAD_SPEECH_THRESHOLD=0.5`, `VAD_MIN_SPEECH_CHUNKS=3` (~96ms),
  `VAD_MIN_SILENCE_CHUNKS=20` (~640ms).
- STT: `WHISPER_MODEL_SIZE="small"`, `WHISPER_COMPUTE_TYPE="int8"`,
  `WHISPER_LANGUAGE="pt"`.
- LLM: `OLLAMA_URL="http://localhost:11434/api/chat"`,
  `OLLAMA_MODEL="phi4-mini"`.
- `ALLOWED_APPS` (Task 3): dict de apps que `actions.py` tem permissão de
  abrir via `open -a`, chave em português (o que o usuário fala, comparado
  em minúsculas) -> valor com o nome real do app no macOS (ver nota em
  `actions.py` sobre nomes ficarem em inglês mesmo em sistema pt-BR). Hoje:
  `spotify`, `safari`, `notas` (Notes), `calculadora` (Calculator),
  `mensagens` (Messages). Editável livremente pelo usuário — é a única fonte
  de apps permitidos, nada fora dela é executado.
- TTS: `TTS_LANG_CODE="p"`, `TTS_VOICE="pm_alex"`, `TTS_SAMPLE_RATE=24000`.
- `MEMORY_DB_PATH`: `memory.db` na raiz do projeto.
- `SYSTEM_PROMPT`: prompt curto e direto ("responda somente em português do
  Brasil, nunca misture palavras de outro idioma... 1 frase curta, direto ao
  ponto, sem ressalvas ou avisos extras") — **não** contém mais nenhuma
  instrução sobre recusar ações; essa lógica foi removida do prompt e virou
  checagem determinística em `llm.py` (ver bug 2 e seção `llm.py`). A frase
  de guarda contra mistura de idioma foi adicionada na Task 2 (ver decisões
  técnicas) — reduz mas não elimina totalmente a mistura de espanhol, que é
  parcialmente uma limitação inerente do phi4-mini (ver limitações
  conhecidas).
- `OLLAMA_OPTIONS`: dict `{"temperature": 0.2, "repeat_penalty": 1.1}` passado
  em toda chamada ao `/api/chat` (Task 2). Ver seção `llm.py` para o
  raciocínio por trás dos valores escolhidos.

### `TASKS.md`
Backlog ativo de melhorias em andamento, executado por agentes dedicados um
de cada vez em ordem. Não duplicar esse conteúdo aqui — consultar o arquivo
diretamente para saber o que está planejado a seguir e o protocolo que cada
agente deve seguir ao concluir uma task (rodar validações, atualizar este
CLAUDE.md se o comportamento mudou, reportar um resumo).

### `hello.m4a`
Fixture de áudio de teste (~8s, fala: "Olá Jarvis, quero que você consulte
como está o clima para o voo hoje."), usada como argumento default em
`stt.py` para teste manual rápido do STT sem precisar gravar nada.

## Decisões técnicas e o porquê (resumo)

| Decisão | Porquê |
|---|---|
| Processo único, modelos singleton | Evitar recarregar modelos por turno; evitar picos de RAM/swap (ver seção 8GB) |
| Python 3.12, não 3.13 | `blis`/`spacy` (dependência do Kokoro) sem wheel pra 3.13 em macOS arm64 |
| faster-whisper em vez de openai-whisper | Mais leve/rápido em CPU, melhor fit para 8GB RAM |
| Silero VAD via torch.hub | Leve, roda em CPU, sem depender de serviço externo |
| Ollama HTTP direto (sem pacote pip `ollama`) | Cliente simples via `requests`, menos uma dependência |
| phi4-mini em vez de qwen2.5:1.5b | Usuário preferiu qualidade de resposta apesar do custo maior de RAM/latência (decisão consciente, não reverter sem pedido) |
| Recusa de ação determinística em código, não no prompt | Modelo pequeno não seguia de forma confiável uma regra condicional no prompt (ver bug 2) |
| Extração de fatos usa só a fala do usuário | Acoplamento com a resposta do assistente causava perda de fatos reais quando a resposta era a recusa fixa (ver bug 3) |
| Extração de fatos roda async após a resposta falada | Não atrasar a latência percebida pelo usuário com uma chamada extra ao LLM |
| Headset HyperX em vez do mic embutido | Qualidade de STT ruim com o mic embutido do Mac (ruído/reverb) |
| Prompt de fatos ignora explicitamente frases negativas | Extração gerava fatos inúteis tipo "não sabe profissão do usuário" (ver bug 1) |
| `temperature=0.2`, `repeat_penalty=1.1` no Ollama (Task 2) | Testado empiricamente: reduz divagação/mistura de idioma sem quebrar a instrução de resposta curta. `repeat_penalty=1.3` foi testado e piorou muito a coerência (respostas longas e desconexas) — descartado |
| Não usar few-shot examples no `SYSTEM_PROMPT` (Task 2) | Testado: few-shot fez o modelo ignorar a instrução de "1 frase curta" em perguntas abertas (chegou a responder com lista numerada de 5 itens) — pior que sem few-shot |
| Usar **um** few-shot example no `FACT_EXTRACTION_PROMPT` (Task 5) | Testado: sem exemplo o modelo fragmentava/alucinava fatos compostos; com um exemplo rico ficou estável; com dois exemplos a estabilidade piorou (erro de parse JSON, fato sumindo em repetição) — diferente da conclusão da Task 2 porque extração de JSON é tarefa mais mecânica/estruturada que resposta de chat aberta |
| Manter dedup por substring simples em `memory.py` (Task 5) | Testado `SequenceMatcher.ratio()` e Jaccard por palavra como alternativas — ambos deram falsos positivos perigosos (ex: nomes preferidos diferentes, ou fato oposto "não gosta de X" vs "gosta de X" pontuando tão "similar" quanto duplicata real) sem um threshold confiável; risco de descartar fato genuinamente novo é pior que o problema atual |

## Bugs corrigidos / lições aprendidas

1. **Fatos negativos inúteis na memória.** A extração de fatos gerava
   entradas como "Não sabe profissão do usuário" em vez de só fatos
   positivos. Corrigido no prompt de extração (`FACT_EXTRACTION_PROMPT`
   instrui explicitamente a ignorar ausência de informação) + um filtro de
   palavras de negação em código (`negation_markers` em `llm.py`, camada de
   defesa redundante ao prompt).

2. **Alucinação de ações.** O modelo dizia ter executado ações que não tinha
   capacidade de fazer (ex.: "abri o Spotify" quando pedido, sem nenhuma
   integração real por trás). Primeira tentativa de correção foi via
   instrução condicional no `SYSTEM_PROMPT` ("só recuse quando for realmente
   um pedido de ação") — não funcionou bem: o phi4-mini (modelo pequeno) ou
   recusava demais (ficando prolixo/repetitivo) ou não seguia a regra.
   Solução definitiva: mover a decisão para **fora do LLM**, com checagem
   determinística de palavras-chave em código antes de sequer chamar o
   modelo (`_is_action_request` em `llm.py`). Lição: não confiar em modelos
   pequenos para seguir regras condicionais importantes — quando a decisão é
   binária e crítica, resolver em código.

3. **Memória vazia por acoplamento indevido.** Como consequência do bug 2
   (antes da correção final), quase toda resposta do assistente virava a
   recusa fixa, e a extração de fatos — que na época também considerava a
   resposta do assistente — passou a sempre concluir que "nada foi
   confirmado", retornando lista vazia. `memory.db` ficou completamente vazio
   apesar de fatos claros terem sido ditos pelo usuário. Corrigido
   desacoplando a extração da resposta do assistente (`extract_facts` usa só
   `user_text` no prompt, ver `llm.py`). Lição: cuidado com dependências
   implícitas entre a saída de um LLM e a lógica de outro passo do pipeline —
   uma mudança de comportamento no primeiro pode quebrar o segundo em
   silêncio.

4. **Qualidade ruim de STT com o mic embutido.** O microfone embutido do
   MacBook captava ruído de ambiente/reverb que prejudicava a transcrição.
   Resolvido selecionando o headset HyperX por nome (`INPUT_DEVICE_NAME` em
   `config.py`, busca por substring case-insensitive em `audio._find_input_device`),
   com fallback para o dispositivo padrão do sistema se não for encontrado.

5. **Teste automatizado de loop fechado não é confiável neste ambiente.** Uma
   tentativa de testar o VAD/áudio de ponta a ponta de forma automatizada
   (tocar áudio gerado pelos alto-falantes via `afplay` e verificar se o
   próprio microfone captava, via `sounddevice.rec`, num processo não
   interativo) não mostrou variação de nível de áudio perceptível. Conclusão:
   esse tipo de teste sofre com permissões de áudio/roteamento em processos
   não-interativos no macOS e não é confiável. Testes de VAD/áudio real
   exigem validação manual por uma pessoa falando de verdade — não tentar
   automatizar isso sem repensar a abordagem.

## Limitações conhecidas

- O agente executa apenas um conjunto pequeno e fixo de ações reais (Task 3):
  ver hora atual, ver data atual, e abrir um app do Mac restrito à whitelist
  `ALLOWED_APPS` (`config.py`). Qualquer outro pedido de ação (mandar
  mensagem, acessar internet, ligar pra alguém, controlar volume, abrir um
  app fora da whitelist, etc) continua recebendo a recusa fixa "Ainda não
  consigo fazer isso." — isso é deliberado e fora de escopo, não um bug. Note
  que isso já não é mais "recusa qualquer pedido de ação": desde a Task 3 há
  duas ações reais suportadas (hora/data e abrir app da whitelist).
- **(Descoberto na Task 6 — QA final) Fatos conflitantes não são resolvidos
  nem versionados.** `memory.py` só adiciona e deduplica por substring; não
  existe conceito de "atualizar" ou "substituir" um fato antigo quando o
  usuário diz algo nele contraditório (ex: usuário disse "moro em Goiânia"
  numa sessão e depois "moro em Belo Horizonte e trabalho como designer" em
  outra — ambos os fatos de localização ficam salvos, coexistindo). Testado
  manualmente: com os dois fatos de cidade no banco, `llm.chat("Onde eu
  moro?", facts=facts)` respondeu com a cidade mais antiga (Goiânia), não a
  mais recente — o LLM escolhe arbitrariamente entre fatos conflitantes, sem
  garantia de preferir o mais novo. Isso é uma limitação real, não corrigida
  nesta task (fora do escopo do QA, seria uma nova feature de "atualização de
  fato" com sua própria lógica de detecção de conflito) — mas documentada
  aqui para qualquer trabalho futuro nessa área.
- **(Confirmado na Task 6) Mistura de idioma residual.** Mesmo com a guarda
  no `SYSTEM_PROMPT` e `OLLAMA_OPTIONS` da Task 2, o phi4-mini ainda comete
  deslizes ocasionais — no QA desta task, a pergunta "Qual a capital da
  França?" retornou "París" (grafia espanhola; em português seria "Paris").
  Consistente com a limitação já documentada abaixo; apenas reforça que não
  foi eliminada, só reduzida.
- `phi4-mini` às vezes produz respostas um pouco estranhas ou mistura idioma
  (ex.: uma palavra em espanhol no meio de uma frase em português) — é um
  modelo pequeno rodando local, qualidade inferior a modelos de nuvem maiores.
  Na Task 2, ajustar `SYSTEM_PROMPT` (guarda explícita contra mistura de
  idioma) e `OLLAMA_OPTIONS` (`temperature=0.2`, `repeat_penalty=1.1`) reduziu
  a frequência do problema nos testes manuais, mas não eliminou por completo
  — é considerada uma limitação residual e aceitável do modelo, não algo a
  perseguir mais agressivamente (tentativas mais fortes, como
  `repeat_penalty=1.3`, pioraram a coerência geral). Também foi observado que
  o modelo às vezes interpreta mal um termo isolado incomum (ex.: "setor
  Perim" confundido com "perímetro") — não é mistura de idioma, é limitação
  de compreensão do modelo pequeno em geral.
- (Resolvido na Task 5) A extração de fatos fragmentava informação
  relacionada em entradas separadas em vez de uma frase coesa (ex.: "mora em
  Goiânia" e "no setor Perim" como duas entradas em vez de uma) — corrigido
  no `FACT_EXTRACTION_PROMPT` com instrução explícita de agrupamento + um
  único few-shot example. A deduplicação em `memory.py` continua sendo
  substring match simples (decisão deliberada, ver seção `memory.py`) —
  ainda pode deixar passar duas entradas com fraseamento bem diferente para
  o mesmo fato (ex.: "mora em Goiânia" vs "mora na cidade de Goiânia" em
  turnos separados), mas isso é raro na prática agora que a causa raiz
  (fragmentação numa única extração) foi corrigida, e alternativas por
  similaridade testadas se mostraram mais arriscadas (ver `memory.py`).
- Sem suporte a múltiplos idiomas simultâneos — fixado em português (pt-BR)
  em vários pontos (`WHISPER_LANGUAGE="pt"` em `stt.py`/`config.py`,
  `TTS_LANG_CODE="p"` em `tts.py`/`config.py`).
- (Resolvido na Task 4) GUI agora tem waveform suavizado (decaimento
  exponencial), glow pulsante no status e anel "arc reactor" — ver seção
  `gui.py`.

## Coisas já tentadas e que NÃO funcionaram (não repetir)

Registrado aqui pra qualquer agente futuro não perder tempo testando de novo
algo que já foi tentado e descartado com evidência real:

- **Few-shot examples no `SYSTEM_PROMPT` do chat geral (Task 2).** Adicionar
  exemplos de pergunta/resposta ao prompt de chat aberto fez o phi4-mini
  ignorar a instrução de "1 frase curta" — chegou a responder com lista
  numerada de 5 itens numa pergunta simples. Pior que sem few-shot. Não
  confundir com o caso de `FACT_EXTRACTION_PROMPT` abaixo, que é diferente.
- **`repeat_penalty` alto (1.3) no Ollama (Task 2).** Testado como tentativa
  de reduzir ainda mais divagação/repetição. Resultado: piorou bastante a
  coerência geral (respostas longas e desconexas) e o modelo passou a ignorar
  a instrução de resposta curta. Valor final mantido em `1.1` (moderado).
- **Dedup de fatos por similaridade em `memory.py` (Task 5).** Testados
  `difflib.SequenceMatcher.ratio()` e Jaccard por palavras (sem stopwords)
  como substitutos do substring match simples. Ambos deram falsos positivos
  perigosos com um único threshold fixo: `SequenceMatcher` pontuou mais alto
  (0.836) para dois nomes preferidos **diferentes** ("Chefe" vs "Davi") do que
  para uma duplicata real (0.700, "mora em Goiânia" vs "mora na cidade de
  Goiânia"); Jaccard pontuou 0.667 tanto pra duplicata quanto pra um par de
  fatos **opostos** ("gosta de café" vs "não gosta de café"). Risco de perder
  silenciosamente um fato genuinamente novo/atualizado é pior que o problema
  atual (raras quase-duplicatas). Mantido substring simples.
- **Mais de um few-shot example no `FACT_EXTRACTION_PROMPT` (Task 5).**
  Diferente do chat geral, um único exemplo rico ajudou bastante na extração
  (tarefa mais mecânica/estruturada). Mas dois exemplos pioraram a
  estabilidade: erro de parse de JSON numa repetição, fato de preferência
  negativa sumindo em outra. Mantido exatamente **um** exemplo.
- **Testar VAD/áudio de ponta a ponta de forma 100% automatizada** (tocar
  áudio via `afplay` e gravar de volta via `sounddevice.rec` num processo não
  interativo) — não mostrou variação de nível perceptível, provavelmente por
  permissões de áudio/roteamento do macOS em processo não-interativo. Não
  confiável; testes de VAD/áudio real exigem uma pessoa falando de verdade.

## QA final (Task 6)

Executado em 2026-09-19. Toda a bateria abaixo foi validada chamando as
funções Python diretamente (sem microfone real disponível no ambiente do
agente), simulando o que a fala transcrita produziria:

- Saudação ("Oi, tudo bem?") → resposta curta e coerente via `llm.chat`. OK.
- Pergunta factual ("Qual a capital da França?") → resposta curta, mas com o
  deslize de idioma residual já conhecido ("París" em vez de "Paris" — ver
  Limitações conhecidas). Comportamento aceito, não é regressão nova.
- Pedido de hora e de data → resposta 100% determinística via `actions.py`,
  confirmado por tempo de resposta ~0ms (sem chamada HTTP ao Ollama) tanto
  via `llm.chat` quanto chamando `actions.handle` direto.
- Abrir app da whitelist ("Abre a calculadora pra mim") → `Calculator.app`
  abriu de verdade (confirmado via `ps aux`), e foi fechado ao final do teste
  (`osascript -e 'quit app "Calculator"'`), sem processo residual.
- Abrir app fora da whitelist ("Abre o Chrome pra mim") → recusa fixa
  corretamente ("Ainda não consigo fazer isso."), nenhum processo novo
  aberto.
- Fato pessoal novo ("Moro em Belo Horizonte e trabalho como designer.") →
  `extract_facts` retornou `['mora em Belo Horizonte', 'trabalha como
  designer']` corretamente separado por assunto (localização vs profissão,
  como o prompt instrui). `memory.add_fact` + `memory.get_facts()` refletiram
  os dois fatos.
- Persistência entre "sessões": fatos gravados foram lidos de volta com uma
  conexão SQLite nova, em um processo Python novo, confirmando que
  `memory.db` em disco reflete os dados (sem depender de estado em memória do
  processo). Os fatos persistidos também apareceram corretamente no contexto
  passado para `llm.chat(..., facts=memory.get_facts())` — o LLM usou um dos
  fatos de localização salvos pra responder "Onde eu moro?" (ver limitação
  nova sobre fatos conflitantes acima: escolheu o fato mais antigo, não o
  recém-adicionado, porque havia dois fatos de cidade no banco de testes
  anteriores). Os dois fatos fabricados pra este teste (Belo Horizonte/
  designer) foram removidos do `memory.db` ao final, pra não poluir a memória
  real do projeto com dados de teste.
- `jarvis` (GUI) subiu em background por ~10s sem erro (só um
  `FutureWarning` benigno do `torch.jit.load`, não relacionado a nenhuma
  mudança deste backlog) e foi encerrado ao final sem deixar processo
  residual.
- Revisão de consistência entre Tasks 2/3/5 em `llm.py`/`config.py`: nenhuma
  mudança de uma task sobrescreveu ou quebrou silenciosamente outra —
  `OLLAMA_OPTIONS` (Task 2) é usado tanto no chat quanto na extração de fatos
  sem prejudicar o resultado da Task 5 (reconfirmado com testes de "não gosto
  de café" e "não sei minha profissão", ambos com o comportamento correto
  documentado na Task 5). Nenhuma correção de código foi necessária nesta
  task — o backlog chegou coeso ao final.

## Como rodar / testar

```sh
jarvis                    # abre a GUI (uso normal)
jarvis-cli                 # modo console, sem GUI (bom pra debug, mostra transcript)

# Testar componentes isoladamente (sempre com a venv jarvis-agent):
~/.venvs/jarvis-agent/bin/python vad.py            # só detecção de fala
~/.venvs/jarvis-agent/bin/python stt.py [wav]      # só transcrição (default: hello.m4a)
~/.venvs/jarvis-agent/bin/python llm.py            # só cliente Ollama (chat + extração de fatos)
~/.venvs/jarvis-agent/bin/python memory.py         # só armazenamento de fatos

# Inspecionar memória persistida:
sqlite3 memory.db "SELECT * FROM facts;"

# Confirmar que o Ollama está rodando e com o modelo certo:
ollama list
brew services list
```

## Backlog (concluído)

O backlog orquestrado de melhorias em `TASKS.md` foi **concluído em
2026-09-19** (Task 1: este arquivo; Task 2: naturalidade das respostas do
LLM; Task 3: capacidade real de ação com guardrails; Task 4: polimento visual
da GUI; Task 5: granularidade da extração de fatos; Task 6: QA final —
documentada na seção "QA final (Task 6)" acima). Consulte `TASKS.md` para o
resumo de cada task. Não há mais tasks pendentes nesse backlog; qualquer
trabalho novo deve ser tratado como uma demanda separada, não uma
continuação implícita dele.
