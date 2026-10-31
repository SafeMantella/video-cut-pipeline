#!/bin/zsh
# uso: transcrever_ambos.sh <pasta edit> <stem>...   (whisperx + vad no áudio limpo, via VoiceStudio rodando)
ed="$1"; shift
for s in "$@"; do
  python3 ferramentas/transcrever/transcrever.py "$ed/audio/$s-enhanced.mp3" -o "$ed/transcripts/$s.wx.json" > "$ed/transcripts/$s.wx.log" 2>&1
  python3 ferramentas/transcrever/transcrever.py "$ed/audio/$s-enhanced.mp3" -o "$ed/transcripts/$s.vad.json" --motor vad > "$ed/transcripts/$s.vad.log" 2>&1
done
touch "$ed/transcripts/done.flag"
