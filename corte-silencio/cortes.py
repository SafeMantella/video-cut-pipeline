#!/usr/bin/env python3
"""Corte de silêncio -> edl.json. Uso: cortes.py <pasta edit> <id_clip> [<id_clip>...]
Silêncio medido no áudio LIMPO (-50dB, >=0.7s). Margem fim = +0.37s (0.25 espectro + 0.12 padrão),
início = -0.12s. Segmento sem palavra da transcrição (clique/ruído) é descartado.
Valida: nenhuma palavra fica fora/cortada."""
import sys, re, json, subprocess, pathlib
ed = pathlib.Path(sys.argv[1]); ids = sys.argv[2:]
NOISE, MIN_SIL, END_PAD, START_PAD = "-50dB", 0.7, 0.37, 0.12
edl = []
for cid in ids:
    aud = ed/"audio"/f"{cid}-enhanced.mp3"
    words = json.load(open(ed/"transcripts"/f"{cid}.json"))["words"]
    dur = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(aud)]))
    out = subprocess.run(["ffmpeg","-nostdin","-hide_banner","-i",str(aud),"-af",f"silencedetect=noise={NOISE}:d={MIN_SIL}","-f","null","-"],capture_output=True,text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    sil = list(zip(starts, ends + [dur]*(len(starts)-len(ends))))
    # fala bruta = complemento dos silêncios
    cur, speech = 0.0, []
    for s, e in sil:
        if s > cur: speech.append([cur, s])
        cur = e
    if cur < dur: speech.append([cur, dur])
    segs = []
    for a, b in speech:
        ws = [w for w in words if a - 0.3 <= w["start"] <= b + 0.05]   # por INÍCIO: o .end do whisperx é inflado
        if not ws: continue                      # ruído sem fala
        s = max(0.0, a - START_PAD)
        e = min(dur, b + END_PAD)
        segs.append([round(s,3), round(e,3)])
    # une segmentos que ficariam sobrepostos/colados
    merged = []
    for s, e in segs:
        if merged and s <= merged[-1][1] + 0.02: merged[-1][1] = max(merged[-1][1], e)
        else: merged.append([s, e])
    # validação: toda palavra inteira dentro de algum segmento
    # início da palavra tem que cair num segmento (whisperx marca o início até ~0.25s cedo)
    bad = [w for w in words if not any(s - 0.25 <= w["start"] <= e for s, e in merged)]
    print(f"{cid}: {len(merged)} segmentos, {sum(e-s for s,e in merged):.1f}s de {dur:.1f}s; palavras fora: {len(bad)}")
    for w in bad: print("   FORA:", w)
    edl.append({"clip": cid, "segments": merged})
json.dump(edl, open(ed/"edl.json","w"), indent=1)
