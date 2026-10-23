# evals — testes do corte automático de vídeo

Spec: `docs/superpowers/specs/2026-10-17-evals-corte-design.md`. Memória: `memory/evals-corte-automatico.md`.

```bash
ferramentas/evals/evals run ferramentas/evals/casos/comandos-falsos.json
# ou por etapa: validar-raw | cortar | validar-corte
```

Pipeline testado: transcrever raw (whisperx + vad) → validar → cortar (silêncio >0,7s, retake, false-start; **vale a última gravação**) → preview 960p → transcrever o corte → validar.

Saídas em `<edit>/evals/`: `edl.json`, `decisoes.md` (tabela trecho/tempo/status), `preview.mp4`, `resultado.json`.

## O que reprova
`retake_sobrou` (tomada anterior ficou), `fala_sumiu` (trecho mantido não aparece no corte), `silencio_longo` (>0,7s no corte), `palavra_capada` (energia alta na emenda), `gabarito_falta`/`gabarito_sobra` (diferença contra o corte manual do Pedro, quando o caso tem `gabarito`).
`REVISAR` na tabela = última tentativa bem mais curta que a anterior; o agente decide e justifica (não reprova sozinho).

## Overrides do agente
`overrides` no caso: `cortar` {índice: motivo}, `manter` {índice: motivo}, `aparar_inicio` {índice: [n palavras, motivo, (tempo exato opcional)]}, `remover` [[ini, fim, motivo]] (segundos do raw, trecho no meio de uma unidade).

Pausas: `apertar()` (a -40 dB, respiração conta como silêncio) deixa no máximo 0,30s depois de fim de frase e 0,20s no meio dela. O índice é o `#` de `decisoes.md`. Toda decisão do agente vai com motivo e aparece na coluna nota.

## Casos
`casos/*.json` — campos: `edit`, `clip`, `video` (mp4 com áudio limpo), `audio` (mp3 limpo), `gabarito` (mp4 cortado pelo Pedro ou null). Cache de transcrição em `<edit>/transcripts/` e `<edit>/evals/`.

## Gotchas
- Transcrição whisperx é CPU: ~3-5 min por 2 min de áudio. Rodar em background.
- O texto de cada trecho é transcrito isolado (`evals/iso.json`, `evals/preview.iso.json`): o whisper do arquivo inteiro funde tomadas repetidas. Fragmento ≤3 palavras sai garbled; o agente decide por override.
- Heurística de retake = prefixo de até 6 palavras ≥75% igual a uma unidade posterior (≤8 à frente). Retake no meio de fala contínua (sem pausa ≥0,3s) não é pego.
