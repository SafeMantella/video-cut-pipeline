# video-cut-pipeline

Corte automático de silêncio em vídeo falado e as ferramentas pra avaliar o corte.

| pasta | o que faz |
|---|---|
| `corte-silencio` | transcrição → `edl.json` (corta silêncio sem cortar palavra), render e legendas |
| `evals` | testes do corte automático (casos em JSON) |
| `evals-edicao` | artifact HTML pra anotar o corte chunk a chunk, no lugar do CapCut |

Depende de [`transcrever-ptbr`](https://github.com/SafeMantella/transcrever-ptbr) como pasta irmã.

> Feito pro meu projeto de redes sociais (macOS). Os scripts assumem a pasta `ferramentas/` do projeto e alguns têm caminho absoluto `/Volumes/1TB Mac/...`: ajuste antes de usar em outro lugar.
