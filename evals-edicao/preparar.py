#!/usr/bin/env python3
"""Prepara um vídeo pro eval manual de edição: corta silêncios >0,7s em chunks, transcreve cada chunk isolado
(o whisper do arquivo inteiro funde retakes) e gera um proxy 480p leve pro artifact.
Uso: preparar.py video.mp4 [-a audio.mp3] [-o pasta] [--min-sil 0.7]
Saída: <pasta>/proxy.mp4 + <pasta>/chunks.json  (evals-edicao/publicar.py sobe isso pro artifact)"""
import argparse, array, base64, json, math, os, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "transcrever-ptbr"))  # repo irmão
from voicestudio import transcrever_wav  # ASR local (VoiceStudio), motor ativo = whisperx
PAD = 0.08  # respiro de cada lado do chunk; as bordas ficam ajustáveis na interface


def sh(c): return subprocess.run(c, capture_output=True, text=True, check=True)


def duracao(f): return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]).stdout)


def silencios(audio, d, noise="-40dB"):  # -40 dB: respiração conta como silêncio (memory/evals-corte-automatico.md)
    log = subprocess.run(["ffmpeg", "-nostdin", "-i", str(audio), "-af", f"silencedetect=noise={noise}:d={d}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    fim = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    return list(zip(ini, fim))  # silêncio final sem silence_end é descartado: o último chunk vai até o fim


PEAK_HZ = 100  # 1 pico por 10 ms; a página lê o mesmo valor (PR)


def peaks(audio):
    """Envelope do áudio em dB, 1 byte por 10 ms (0 = -60 dB ou menos, 255 = 0 dB), em base64. A página desenha a onda com isso."""
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    s = array.array("h"); s.frombytes(raw[:len(raw) // 2 * 2]); w = 8000 // PEAK_HZ
    out = bytearray()
    for i in range(0, len(s) - w + 1, w):
        m = max(max(s[i:i + w]), -min(s[i:i + w])) / 32768
        out.append(max(0, min(255, round((20 * math.log10(m + 1e-5) + 60) / 60 * 255))))
    return base64.b64encode(bytes(out)).decode()  # ~41 KB por 5 min; o doc do banco aceita 256 KB (~30 min)


def chunks(audio, total, min_sil):
    out, cur = [], 0.0
    for s, e in silencios(audio, min_sil):
        if s - cur > 0.15: out.append((max(0.0, cur - PAD), min(total, s + PAD)))
        cur = e
    if total - cur > 0.15: out.append((max(0.0, cur - PAD), total))
    return out


def transcrever(audio, a, b, wav):
    sh(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(audio), "-ar", "16000", "-ac", "1", str(wav)])
    return " ".join(transcrever_wav(pathlib.Path(wav))[1].split())


def main():
    p = argparse.ArgumentParser(); p.add_argument("video"); p.add_argument("-a", "--audio"); p.add_argument("-o", "--out")
    p.add_argument("--min-sil", type=float, default=0.7); p.add_argument("--texto", action="store_true", help="transcreve cada chunk (lento, large-v3)"); x = p.parse_args()
    video = pathlib.Path(x.video); out = pathlib.Path(x.out or video.parent / "evals-edicao"); out.mkdir(parents=True, exist_ok=True)
    audio = pathlib.Path(x.audio) if x.audio else out / "audio.wav"
    if not x.audio: sh(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(video), "-vn", "-ar", "16000", "-ac", "1", str(audio)])
    total = duracao(video); spans = chunks(audio, total, x.min_sil)
    cache = out / "iso.json"; memo = json.load(open(cache)) if cache.exists() else {}
    for a, b in spans:
        k = f"{a:.2f}-{b:.2f}"
        if x.texto and not memo.get(k):  # legenda só nasce depois do corte final; o texto aqui serve só pra eu sugerir retakes
            memo[k] = transcrever(audio, a, b, out / "tmp.wav"); json.dump(memo, open(cache, "w"), ensure_ascii=False)
            print(k, memo[k][:70], flush=True)
    (out / "tmp.wav").unlink(missing_ok=True)
    rows = [{"i": n + 1, "start": round(a, 2), "end": round(b, 2), "text": memo.get(f"{a:.2f}-{b:.2f}", "")} for n, (a, b) in enumerate(spans)]
    json.dump({"video": video.name, "duration": round(total, 2), "min_sil": x.min_sil, "peaks": peaks(audio), "chunks": rows}, open(out / "chunks.json", "w"), ensure_ascii=False, indent=1)
    proxy = out / "proxy.mp4"  # ponytail: um proxy só; acima de ~20 MB (teto do asset) vira vídeos longos -> dividir em partes
    if not proxy.exists():
        sh(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(video), "-vf", "scale=-2:480", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "31", "-g", "12", "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", str(proxy)])
    kept = sum(b - a for a, b in spans)
    print(f"{len(rows)} chunks, {kept:.1f}s de {total:.1f}s ({kept / total:.0%}); proxy {proxy.stat().st_size / 1e6:.1f} MB -> {out}")


if __name__ == "__main__": main()
