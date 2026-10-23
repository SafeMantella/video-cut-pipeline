#!/bin/zsh
# uso: transcrever_ambos.sh <pasta edit> <stem>...   (whisperx + vad no áudio limpo; paths do whisper.cpp deste Mac)
export WHISPER_CPP_BIN=/opt/homebrew/bin/whisper-cli
export WHISPER_CPP_MODEL="/Volumes/1TB Mac/Code/Skills/local-video-use/models/ggml-large-v3.bin"
export WHISPER_VAD_MODEL="/Volumes/1TB Mac/Code/Skills/local-video-use/models/ggml-silero-v5.1.2.bin"
ed="$1"; shift
for s in "$@"; do
  python3 ferramentas/transcrever/transcrever.py "$ed/audio/$s-enhanced.mp3" -o "$ed/transcripts/$s.wx.json" > "$ed/transcripts/$s.wx.log" 2>&1
  python3 ferramentas/transcrever/transcrever.py "$ed/audio/$s-enhanced.mp3" -o "$ed/transcripts/$s.vad.json" --motor vad > "$ed/transcripts/$s.vad.log" 2>&1
done
touch "$ed/transcripts/done.flag"
