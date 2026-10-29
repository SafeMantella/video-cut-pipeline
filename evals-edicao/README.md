# evals-edicao — anotar o corte do vídeo num artifact (substitui o CapCut pras anotações)

Decidido por Pedro em 22/10/2026: as anotações de corte (o que manter, remover, onde entra motion/imagem) deixam de ser feitas no CapCut e passam a ser feitas aqui. O Pedro revisa **chunk a chunk** numa interface fora do terminal; o Claude lê as decisões direto do banco do artifact (sem copiar nada pro chat), gera um preview e aprende o gosto dele. Manual do usuário: [`MANUAL.md`](MANUAL.md) (o mesmo texto está no painel "Manual" da página). Aprendizados acumulados: `memory/evals-edicao-manual.md`.

- **Artifact:** https://claude.ai/artifact/NqVcLsVRQivvEDy9rHJNnr (privado; capabilities `db` + `assets`). Um artifact só serve todos os vídeos: cada vídeo é um doc em `videos/` e a página tem um seletor quando há mais de um.
- **Fonte da página:** `artifact.html` (HTML único, sem build). Editar e republicar com `Artifact publish` no **mesmo caminho** (mantém a URL e o banco).
- Não substitui o corte automático por texto (`ferramentas/evals/`, `memory/evals-corte-automatico.md`): aquele detecta retakes pela transcrição; este é a revisão manual com onda sonora.

## Fluxo (o agente executa; slash commands `/edicao` (abre o artifact; com um vídeo, prepara e abre já com ele) e `/avaliar-edicao` (o fluxo completo))
Pastas: `<edit>` = pasta `edit/` do vídeo; `<pasta>` = `<edit>/evals-edicao/`.

1. **Preparar** — `python3 ferramentas/evals-edicao/preparar.py <video.mp4> -a <audio.mp3> -o <pasta>`
   Detecta silêncio >0,7 s a −40 dB (`--min-sil` muda), monta os chunks (cada chunk = fala entre silêncios, com 0,08 s de respiro), calcula a onda e faz o proxy 480p. Saída: `chunks.json` (inclui `peaks`), `proxy.mp4`. `--texto` transcreve cada chunk isolado (whisper-cli large-v3, lento); **por padrão não transcreve** (a legenda só nasce depois do corte final, Pedro 22/10/2026). Sem texto, as sugestões de retake por conteúdo ficam sem base: usar `--texto` quando for preciso eu sugerir retakes.
2. **Sugestões** — o agente escreve `<pasta>/sugestoes.json`: `{"1": {"action": "manter", "why": "motivo curto", "detail": "o que entra (opcional)"}}`. Ações: `manter`, `remover`, `motion`, `imagem`, `imagem+motion`. Aplicar os aprendizados de `memory/evals-edicao-manual.md` (pausa interna, tomada truncada, imagem sempre com motion).
2b. **Imagens (proativo)** — pra cada chunk com `imagem`/`imagem+motion`, rodar a busca de `ferramentas/buscar-imagens/README.md`, subir os assets e `juntar` em `sugestoes.json` (`images`). A página mostra as opções; o Pedro escolhe.
2c. **Opções de motion (Pedro, 26/10/2026)** — pra cada chunk `motion`/`imagem+motion`, escrever em `sugestoes.json` `motions`: 4 opções `{label, desc, timing}` (formatos diferentes entre si; ilustração, não só pill de texto; `desc` diz o que aparece; `timing` ancora os beats na fala do chunk, ex. "0–1 s desenha; 2 s X"; respeitar a zona livre acima da cabeça e o hook sem tela cheia). A página mostra 4 cartões; o Pedro escolhe (teclas 6–9) e a escolha volta em `reviews`: `motionChoice` (0–3), `motionLabel`, `motionDesc`. `anotar.py` copia pra `anotacoes.*`. Substitui a entrevista de motion no chat.
3. **Semear** — `python3 ferramentas/evals-edicao/semear.py <pasta> --vid <slug> --titulo "Nome" --asset <id>`.
   Antes: subir o proxy com `Artifact` (`url` do artifact, `asset: true`, `file_path` = `proxy.mp4`) e pegar o `id` do resultado. Depois: `ArtifactData batch` com o conteúdo de `<pasta>/seed/writes.json` (até 50 escritas por chamada; mais de 49 chunks = mais de uma chamada).
4. **Pedro revisa** na página e avisa no chat ("terminei"). Ele não precisa clicar em "Concluir rodada" (grava `videos/<vid>.doneAt`, opcional).
5. **Ler** — `ArtifactData query` em `reviews` com `where vid == <vid>` e `out_dir=<pasta>/db` (grava `<pasta>/db/reviews/*.json`). Comparar com `sug`, anotar os padrões em `memory/evals-edicao-manual.md` (seção Aprendizados).
6. **Preview** (sob pedido) — `python3 ferramentas/evals-edicao/preview.py <pasta> <pasta>/db/reviews` → `preview N.mp4` (próximo número, só número: regra E) e `preview N.edl.json`. 960 de altura, crf 24. Não é o render final (regra D: só com autorização).
7. **Chop** (quando o Pedro diz que aplicou as edições) — `python3 ferramentas/evals-edicao/preview.py <pasta> <pasta>/db/reviews --chop` → `edit/<nome da pasta do vídeo> chop.mp4`: mesmo corte do preview, mas na resolução e no FPS exatos do raw (`fps=` lido do ffprobe, ex. 30000/1001), x264 `slow` crf 12, yuv420p, áudio aac 320k. Rotação do raw é aplicada pelo ffmpeg (raw 3840x2160 com rotate 90 sai 2160x3840). Demora (~10 min pra 129 s em 4K).

## Modelo de dados (banco do artifact)
- `videos/<vid>`: `title, assetId` (proxy), `duration, minSil, peaks` (base64, 1 byte por 10 ms, 0 = −60 dB e 255 = 0 dB), `createdAt, n, doneAt?`.
- `chunks/<vid>_NNN` (escrito pelo Claude): `vid, i, start, end, text, sug: {action, why, detail?, images?: [{assetId, label}], motions?: [{label, desc, timing?}]}`. Tempos em segundos do raw.
- `reviews/<vid>_NNN` (escrito pela página): `vid, i, action, agree, trimIn, trimOut, cuts: [[ini, fim]], tags[], detail, note, imageChoice?, imageAsset?, motionChoice?, motionLabel?, motionDesc?, at`. `agree` = ação igual à sugestão **e** sem ajuste de borda **e** sem corte. Chunk sem `review` = não revisado.
- Um doc por chunk, nunca arrays grandes (limite de 256 KiB por doc; `peaks` cabe até ~30 min de vídeo).

## O que a página faz
- Lista de chunks (sugestão tracejada, decisão cheia, ✓ concordou / ≠ diferente), progresso, % de concordância, duração final estimada.
- Player com o proxy, que toca só o chunk, pula os cortes e pode seguir pro próximo sozinho.
- **Onda sonora** em canvas: som acima de −40 dB em escuro, silêncio/respiração em claro; 1,2 s de contexto de cada lado; zoom (`+`/`−`/`0`) e pan.
- Ajustar início/fim do chunk (alças, `I`/`O`, números); **vários cortes por chunk** arrastando sobre a onda (`X`/`Delete`), "ouvir seleção" (`S`), "ouvir ao redor", números de ajuste fino e desfazer.
- 5 ações (`1`–`5`), `Enter` aceita a sugestão, tags de motivo e nota (opcionais), campo "qual motion/imagem", upload de imagem própria.
- Salva sozinho (500 ms) em `reviews/`; escrita serializada por doc.

## Arquivos
`preparar.py`, `semear.py`, `preview.py` (CLIs, só stdlib + ffmpeg/whisper-cli), `artifact.html`, `MANUAL.md`, este README. Por vídeo, em `<edit>/evals-edicao/`: `chunks.json`, `iso.json` (cache de texto), `proxy.mp4`, `sugestoes.json`, `seed/`, `db/reviews/`, `preview N.mp4`.

## Limites e gotchas
- O raw pode ter rotação nos metadados (o vertical do iPhone vem 3840×2160 + rotation=90): o ffmpeg já corrige; a página recebe o proxy girado.
- Proxy acima de ~20 MB (teto do asset) não sobe: vídeos longos = dividir em partes ou baixar a qualidade (`-crf`). Com `-g 12` o seek é preciso, o preço é o tamanho.
- Em silêncio o whisper alucina ("Itália", "Tchau, tchau"): nunca transcrever trecho de pausa.
- Silêncio medido a −40 dB (respiração conta como silêncio). A página usa o mesmo limiar (85 na escala 0–255).
- O artifact é privado e só o dono grava. A página precisa do login do claude.ai pra ler o banco.
- Depois de publicar uma versão nova da página, quem está com ela aberta recarrega sozinho; os dados ficam.
- Preview e EDL pulam chunk `remover` e aplicam `trimIn/trimOut` menos `cuts`; motion e imagem **não** entram no preview (só marcam o chunk).
