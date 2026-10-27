# evals — testes do corte automático de vídeo

Spec: `docs/superpowers/specs/2026-10-17-evals-corte-design.md`. Os aprendizados das rodadas estão no fim deste arquivo.

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

## Regra de uso
O corte automático pode remover sozinho silêncio/pausa >0,7 s, retakes e false-starts/autocorreção. Isso vale **só dentro dos evals e propostas**: o resultado vira EDL + tabela + preview 960p, e nada é renderizado em resolução cheia nem publicado sem o OK do dono do vídeo. Regra central: a última gravação de cada fala é a que fica. Exceção (a última tem problema e uma anterior está perfeita): o agente decide e justifica na tabela; a ferramenta só marca `REVISAR`.

## Aprendizados das rodadas (17–22/10/2026)
- Prefixo de 2 palavras ("E isso,") dá falso positivo e deixa frase órfã: retake por prefixo só com ≥3 palavras e similaridade ≥75%; entre 66% e 75% vira `REVISAR` e fica no corte.
- Retake que recomeça com outra abertura dentro de uma frase maior exige regra de contenção.
- Recomeço no fim do trecho ("...então o comando" / "Então o comando secreto"): cortar o rabo ancorando no vale de energia (o início de palavra do whisperx erra ~50 ms e o corte caiu dentro de "então"). O vale mais fundo pode cair DENTRO da palavra anterior; em fala colada, testar 3 ou 4 pontos com whisper isolado.
- O raw pode transcrever a mesma frase diferente ("Este é de PT" vs "Ei, chat GPT"): o detector por texto não pega; o check `repeticao_no_corte` (frases ≥60% iguais no corte) é a rede de segurança. `fala_sumiu` ignora troca de grafia. Ler o texto do corte continua valendo.
- **Nunca validar repetição só pela transcrição do arquivo inteiro:** o whisper funde ou engole tomadas repetidas ("Primeiro de tudo, pesquisa sobre a documentação infe..." saiu como "Primeiro"). O detector usa o texto de cada trecho transcrito isolado (`iso()`, cache em `evals/iso.json`) e confere o corte trecho a trecho (`evals/preview.iso.json`). Fragmento ≤3 palavras sai garbled; o agente corta por override depois de ler.
- `silencio_longo` mede a -40 dB e >0,45 s (a -50 dB a respiração contava como fala e deixou passar pausas de ~1 s). `apertar()` deixa no máximo 0,30 s de pausa depois de fim de frase (.?!) e 0,20 s no meio, cortando o miolo do silêncio, nunca a palavra.
- Overrides novos: `remover` [[ini, fim, motivo]] pra tirar trecho no meio de uma unidade; `aparar_inicio` aceita 3º campo = tempo exato (fala colada sem vale).
- Revisão manual (22/10): apertar pausas internas ≥0,22 s deixando ~0,12 s (mais que o `apertar()` atual) e manter a cláusula completa de tomadas truncadas. O código ainda não foi ajustado a isso. Esse fluxo manual vive em `evals-edicao/`.

