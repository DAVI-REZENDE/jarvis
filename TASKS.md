# Jarvis — Backlog orquestrado

Cada task é executada por um agente dedicado, um de cada vez, em ordem. Todo
agente deve ler `CLAUDE.md` (depois que a Task 1 criá-lo) antes de começar,
pra ter contexto do projeto sem precisar reperguntar nada. Ao final de cada
task, o agente deve: rodar os testes/validações manuais possíveis, atualizar
`CLAUDE.md` se o comportamento do sistema mudou, e reportar um resumo claro
do que mudou e o que ficou pendente/quebrado (se algo ficou).

Status: `[ ]` pendente · `[~]` em andamento · `[x]` concluída

---

## [x] Task 1 — Escrever CLAUDE.md com a spec completa do projeto
Documentar en detalhe: objetivo do projeto, arquitetura (todos os módulos e
o que cada um faz), decisões técnicas e o porquê (venv única, faster-whisper,
Silero VAD, Ollama+phi4-mini, PySide6, SQLite), restrições da máquina (M1,
8GB RAM), como rodar (aliases `jarvis`/`jarvis-cli`), estado atual de cada
parte, bugs já corrigidos e o raciocínio por trás (prolixidade do prompt,
ação determinística vs LLM, extração de fatos desacoplada), e limitações
conhecidas. Este arquivo é a fonte de contexto pra todos os agentes seguintes.

## [x] Task 2 — Melhorar naturalidade das respostas do LLM
O phi4-mini às vezes responde de forma estranha/repetitiva/mistura idioma
(ex: "Perim de Goiânia, você está?", "Puedo ajudá-lo"). Investigar e ajustar:
revisar `SYSTEM_PROMPT`, testar variações de instrução e (se necessário)
few-shot examples curtos no prompt, ajustar parâmetros de geração da chamada
ao Ollama (temperature, top_p, repeat_penalty) via `/api/chat` `options`.
Validar com uma bateria de ~15 perguntas/frases variadas (saudação, pergunta
factual, pedido de ação, fato pessoal, pergunta ambígua) comparando respostas
antes/depois. Não regredir o comportamento já corrigido (recusa determinística
de ações, extração de fatos).

## [x] Task 3 — Capacidade real de ação (com guardrails de segurança)
Hoje o agente só recusa qualquer pedido de ação. Implementar um conjunto
pequeno e seguro de ações reais, com **detecção determinística em código**
(não deixar o LLM gerar comandos livres — risco de injeção/segurança):
- Ver hora/data atual (sem LLM, resposta local formatada).
- Abrir um aplicativo do Mac por nome, via `open -a "<nome>"`, restrito a uma
  **whitelist** configurável de apps permitidos (ex: Spotify, Safari, Notas).
Estender `llm.py`/`orchestrator.py` com uma camada de "intent" que primeiro
tenta casar a fala do usuário com uma ação conhecida (regex/keywords) antes
de cair no chat normal; se a ação não estiver na whitelist ou não for
reconhecida, manter a resposta "Ainda não consigo fazer isso." Testar: pedir
a hora, pedir a data, abrir um app da whitelist, abrir um app fora da
whitelist (deve recusar), e uma frase comum que não é pedido de ação (não
pode ser confundida com uma).

## [x] Task 4 — Polimento visual da GUI (estética Jarvis/HUD)
Hoje a GUI é funcional mas simples (barras retas, sem animação). Melhorar:
efeito de brilho/pulsação no indicador de status conforme o estado, waveform
mais suave (interpolação/decaimento em vez de saltos bruscos), talvez um
anel circular pulsante ao redor do status lembrando um "arc reactor". Manter
performance leve (o processo já compartilha RAM com Whisper/Kokoro/Ollama —
não introduzir libs pesadas de animação). Validar visualmente rodando o app
por alguns minutos e descrevendo o resultado (não há como capturar
screenshot automaticamente; documentar o que foi implementado pro usuário
conferir).

## [x] Task 5 — Melhorar granularidade/qualidade da extração de fatos
Hoje fatos relacionados saem fragmentados (ex: "mora em Goiânia" e "no setor
Perim" como duas entradas separadas em vez de uma). Revisar
`FACT_EXTRACTION_PROMPT` em `llm.py` pra produzir fatos mais completos e
autocontidos (uma frase por fato, mas com contexto suficiente pra fazer
sentido sozinha), e revisar a deduplicação em `memory.py` (hoje é
substring-match simples, que pode ser frágil). Testar com frases compostas
reais (endereço com bairro+cidade, nome+profissão+preferência na mesma
frase) e confirmar que os fatos salvos ficam coerentes e não duplicados.

## [ ] Task 6 — QA final e fechamento
Revisar todas as mudanças das tasks 2-5 funcionando juntas (rodar uma
conversa real ponta a ponta cobrindo: saudação, pergunta factual, pedido de
hora/data, pedido de abrir app da whitelist, fato pessoal novo, e reiniciar
o app pra confirmar que o fato persistiu). Atualizar `CLAUDE.md` com o
estado final e qualquer decisão nova tomada nas tasks anteriores. Commit
final de fechamento do backlog.
