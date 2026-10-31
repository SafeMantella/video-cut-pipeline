# video-cut-pipeline

**Corta automaticamente silêncio e tomadas repetidas de vídeo falado, sem cortar palavra, e mede se o corte ficou bom.** Pensado pra quem grava vídeo vertical falando pra câmera, erra, repete a frase e não quer passar horas na timeline.

A ideia central: **vale a última gravação de cada fala.** O pipeline transcreve, acha pausas longas e retakes, monta uma lista de cortes (`edl.json`), gera uma prévia leve pra você aprovar e só então renderiza em qualidade máxima.

```text
vídeo + áudio limpo
   │ transcrever-ptbr (palavras com tempo)
   ▼
corte-silencio/cortes.py ──► edl.json ──► render.py ──► vídeo final (vídeo original sem escala + áudio limpo)
   │                                         └─ PREVIEW=1 -> 960 px, crf 24, pra revisão
   ▼
evals/        testa o corte contra regras e contra um corte feito à mão
evals-edicao/ página pra você revisar chunk a chunk e ensinar seu gosto
```

## O que tem aqui

| pasta | o que faz |
|---|---|
| [`corte-silencio`](corte-silencio) | `cortes.py` (transcrição → `edl.json`), `render.py` (EDL → mp4), `gerar_legendas.py` (palavras → cues e `.srt`), `transcrever_ambos.sh` (roda os dois motores) |
| [`evals`](evals) | testes do corte automático: casos em JSON, tabela de decisões, prévia 960p e checagens que reprovam (`retake_sobrou`, `fala_sumiu`, `silencio_longo`, `palavra_capada`…). [Detalhes](evals/README.md) |
| [`evals-edicao`](evals-edicao) | artifact HTML pra anotar o corte chunk a chunk com onda sonora, no lugar de marcar no editor. [Detalhes](evals-edicao/README.md) e [manual](evals-edicao/MANUAL.md) |

## Como o corte decide

- **Silêncio:** medido no áudio limpo (-50 dB, ≥ 0,7 s) e tirado, deixando respiro: 0,12 s antes de cada fala e 0,37 s depois. Pausas que sobram ficam em no máximo 0,30 s depois de fim de frase e 0,20 s no meio dela.
- **Retake:** prefixo de 3+ palavras ≥ 75% igual a uma fala posterior vira "tomada repetida"; fica a última. Entre 66% e 75% marca `REVISAR` e mantém no corte.
- **Garantias:** nenhuma palavra fica fora nem cortada ao meio; segmento sem palavra na transcrição (clique, ruído) é descartado; cada trecho é transcrito isolado pra o Whisper não fundir tomadas repetidas.
- **Quem manda é você:** o resultado é proposta (tabela + prévia). Nada é renderizado em resolução cheia sem sua aprovação.

## Uso

Estrutura de pasta esperada (uma pasta `edit/` ao lado dos clipes):

```text
gravacao/
├── CLIP.mp4                      <- original
└── edit/
    ├── audio/CLIP-enhanced.mp3   <- áudio limpo
    └── transcripts/CLIP.json     <- saída do transcrever-ptbr
```

```bash
python3 corte-silencio/cortes.py gravacao/edit CLIP               # -> edit/edl.json
PREVIEW=1 python3 corte-silencio/render.py gravacao/edit prev.mp4 # prévia leve
python3 corte-silencio/render.py gravacao/edit final.mp4          # máxima qualidade (x264 crf 14, áudio aac 320k)
python3 evals/evals.py run evals/casos/comandos-falsos.json               # testa o corte (A -> B -> C)
```

`render.py` usa `EDL=outro.json` pra renderizar outra lista e aceita ids de clipes no fim pra renderizar só eles.

## Requisitos

- Python 3.10+ (`numpy` nos scripts de legenda), `ffmpeg` e `ffprobe`.
- [`transcrever-ptbr`](https://github.com/SafeMantella/transcrever-ptbr) como **pasta irmã** (os evals e o `transcrever_ambos.sh` chamam `ferramentas/transcrever/transcrever.py`).
- [VoiceStudio](https://github.com/debpalash/VoiceStudio) rodando local (`http://127.0.0.1:3900`): é o ASR de todos os motores e da transcrição de trecho isolado (via `transcrever-ptbr/voicestudio.py`).
- Áudio limpo (tirar ruído antes melhora o corte e a transcrição): veja [Adobe-Podcast-for-Claude-Code](https://github.com/SafeMantella/Adobe-Podcast-for-Claude-Code).

## Antes de usar (honestidade)

- Foi feito pro projeto de redes sociais do autor, no macOS, com uma estrutura de pastas fixa (`ferramentas/`, `gravações/…/edit`). `evals.py` assume a raiz do projeto dois níveis acima. Se o VoiceStudio não estiver no endereço padrão, exporte `VOICESTUDIO_URL`.
- `gerar_legendas.py` é o script de um vídeo específico (lê `t.json` e `audio.wav` da pasta atual e tem correções de texto escritas à mão). Use como modelo, não como ferramenta pronta.
- `evals/casos/` traz o caso do autor como exemplo de formato; os vídeos dele não estão no repo.
- O detector de retake é heurístico: retake no meio de fala contínua (sem pausa ≥ 0,3 s) não é pego. Sempre leia a tabela `decisoes.md` e assista a prévia.
- Os números (-50 dB, 0,7 s, margens) são as preferências do autor para fala de câmera vertical; ajuste no topo de `cortes.py`.

## Repos relacionados

Do kit do [@SafeMantella](https://github.com/SafeMantella): [transcrever-ptbr](https://github.com/SafeMantella/transcrever-ptbr) (entrada), [video-tools](https://github.com/SafeMantella/video-tools) (camadas, zoom e sfx depois do corte), [sau-tools](https://github.com/SafeMantella/sau-tools) (postar o resultado), [social-toolbox](https://github.com/SafeMantella/social-toolbox), [token-kit](https://github.com/SafeMantella/token-kit).

## Licença

MIT. Veja [LICENSE](LICENSE).
