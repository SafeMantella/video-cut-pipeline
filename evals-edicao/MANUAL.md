# Eval de Edição — manual rápido

Artifact: https://claude.ai/artifact/NqVcLsVRQivvEDy9rHJNnr (o mesmo texto está no painel "Manual" da página)

## O fluxo
- Lista à direita: cada item é um chunk, um trecho de fala entre silêncios maiores que 0,7 s. O círculo tracejado é a sugestão do Claude, o cheio é a sua decisão, ✓ quer dizer que você concordou e ≠ que decidiu diferente.
- Ouça com espaço. Leia a sugestão do Claude e o motivo.
- Decida: teclas 1 manter · 2 remover · 3 motion · 4 imagem · 5 imagem + motion. Enter aceita a sugestão e vai pro próximo.
- Motion ou imagem: escreva no campo que aparece o que entraria ali. Pode enviar uma imagem sua.
- Por quê: marque as tags (retake, enchimento, erro de fala...) e deixe uma nota quando discordar. É isso que ensina o Claude.
- Terminou? Clique em “Concluir rodada” e avise o Claude no chat. Ele lê tudo direto daqui.

## A onda sonora (onde tem áudio)
- Barras escuras são som acima de −40 dB (fala, tosse, ruído). Barras claras e baixas são silêncio ou respiração. A linha âmbar é o ponto de reprodução.
- A faixa verde é o chunk. Os 1,2 s antes e depois aparecem sem faixa, pra você ver o que o corte automático deixou de fora.
- Ajustar as pontas: arraste as alças das extremidades, ou toque I (início) e O (fim) na posição do player. Dá pra esticar o chunk pra incluir uma palavra cortada.

## Cortar uma tosse, gaguejada ou erro dentro do chunk
- Dê zoom no trecho com + (ou os botões) e use ◀ ▶ pra andar pela onda.
- Arraste sobre a onda pra selecionar (fica âmbar). Clique sem arrastar só move o player.
- Ouvir seleção (S) confirma que é só aquilo. Depois Cortar seleção (X ou Delete). O trecho aparece listrado em vermelho.
- Faça quantos cortes quiser no mesmo chunk. Ajuste fino nos números da lista de cortes, ou remova um corte pelo botão.
- Deixe “pular cortes” ligado: o player toca o resultado como ficará. Desligado, você ouve o trecho cortado.

## Atalhos

| ← → | chunk anterior / próximo | espaço | tocar / pausar
| R | tocar do início do chunk | S | ouvir a seleção
| X | cortar a seleção (ou marcar começo e fim no player) | Delete | cortar a seleção
| + − 0 | zoom / chunk inteiro | I O | início / fim do chunk no player

Tudo salva sozinho (aparece “salvo” ao lado do título do chunk). Nada é renderizado nem publicado por causa disso.
