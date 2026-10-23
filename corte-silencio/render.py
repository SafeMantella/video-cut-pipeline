#!/usr/bin/env python3
"""edl.json -> final em qualidade máxima: vídeo do mp4 original (4K, sem escala) + áudio LIMPO (Adobe)."""
import json, sys, os, pathlib, subprocess
ed = pathlib.Path(sys.argv[1]).resolve(); out = ed/sys.argv[2]
sel = sys.argv[3:]   # opcional: só estes clipes (um final por take)
edl = [c for c in json.load(open(ed/os.environ.get("EDL","edl.json"))) if not sel or c["clip"] in sel]; root = ed.parent
PREVIEW = bool(os.environ.get("PREVIEW"))   # PREVIEW=1 -> 960 de largura, crf 24 (Regra D: revisão)
PREV_SCALE = ",scale=960:-2" if PREVIEW else ""
inputs, parts, labels, n = [], [], [], 0
for i, c in enumerate(edl):
    inputs += ["-i", str(root/f"{c['clip']}.mp4"), "-i", str(ed/"audio"/f"{c['clip']}-enhanced.mp3")]
    for s, e in c["segments"]:
        parts.append(f"[{2*i}:v]trim={s}:{e},setpts=PTS-STARTPTS,fps=30000/1001{PREV_SCALE}[v{n}]")
        d = e - s
        parts.append(f"[{2*i+1}:a]atrim={s}:{e},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.008,afade=t=out:st={d-0.008:.3f}:d=0.008[a{n}]")
        labels.append(f"[v{n}][a{n}]"); n += 1
parts.append("".join(labels) + f"concat=n={n}:v=1:a=1[v][a]")
cmd = ["ffmpeg","-nostdin","-y","-hide_banner",*inputs,"-filter_complex",";".join(parts),"-map","[v]","-map","[a]",
       "-c:v","libx264","-preset",("veryfast" if PREVIEW else "slow"),"-crf",("24" if PREVIEW else "14"),"-pix_fmt","yuv420p","-colorspace","bt709","-color_primaries","bt709","-color_trc","bt709",
       "-c:a","aac","-b:a",("160k" if PREVIEW else "320k"),"-movflags","+faststart",str(out)]
print(n, "segmentos"); subprocess.run(cmd, check=True)
