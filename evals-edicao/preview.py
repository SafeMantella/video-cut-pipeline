#!/usr/bin/env python3
"""Renderiza o preview (960p, só pra ver o resultado) a partir das decisões do artifact.
Uso: preview.py <pasta evals-edicao> <pasta com os reviews/*.json lidos via ArtifactData> [-o arquivo.mp4]
Saída padrão: `preview N.mp4` (próximo número livre na pasta; previews só com número, regra E do pipeline).
Regra: chunk com action != remover entra de trimIn a trimOut, menos os `cuts`. Não é o render final."""
import argparse, glob, json, pathlib, re, subprocess

FADE = 0.012  # fade de 12 ms em cada emenda de áudio, evita estalo


def segmentos(chunks, reviews):
    out = []
    for c in chunks:
        r = reviews.get(c["i"])
        if not r or r["action"] == "remover": continue
        a, b = r.get("trimIn", c["start"]), r.get("trimOut", c["end"]); cur = a
        for s, e in sorted(r.get("cuts", [])):
            if s - cur >= 0.03: out.append((cur, s))
            cur = max(cur, e)
        if b - cur >= 0.03: out.append((cur, b))
    return out


def main():
    p = argparse.ArgumentParser(); p.add_argument("pasta"); p.add_argument("reviews"); p.add_argument("-o", "--out")
    p.add_argument("--chop", action="store_true", help="corte final: resolução e FPS do raw, qualidade máxima, `<pasta do vídeo> chop.mp4` em edit/"); x = p.parse_args()
    pasta = pathlib.Path(x.pasta).resolve(); d = json.load(open(pasta / "chunks.json"))
    reviews = {r["i"]: r for r in (json.load(open(f)) for f in glob.glob(f"{x.reviews}/*.json"))}
    segs = segmentos(d["chunks"], reviews); video = pasta.parent / d["video"]
    fps = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout.strip().strip(",")
    esc = "setpts=PTS-STARTPTS" if x.chop else "setpts=PTS-STARTPTS,scale=-2:960"
    f = []
    for n, (a, b) in enumerate(segs):
        f.append(f"[0:v]trim={a:.3f}:{b:.3f},{esc}[v{n}]")
        f.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d={FADE},afade=t=out:st={max(0, b - a - FADE):.3f}:d={FADE}[a{n}]")
    f.append("".join(f"[v{n}][a{n}]" for n in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=1[v0][a]")
    f.append(f"[v0]fps={fps}[v]")  # raw é 30000/1001: o corte mantém exatamente esse FPS
    n = 1 + max([int(m.group(1)) for f in pasta.glob("preview *.mp4") if (m := re.fullmatch(r"preview (\d+)\.mp4", f.name))] or [0])
    out = pathlib.Path(x.out or (video.parent / f"{pasta.parent.parent.name} chop.mp4" if x.chop else pasta / f"preview {n}.mp4"))
    json.dump({"segments": segs}, open(out.with_suffix(".edl.json"), "w"))
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(video), "-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
                    *(["-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k"] if x.chop else
                    ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-c:a", "aac", "-b:a", "128k"]), "-movflags", "+faststart", str(out)], check=True)
    dur = sum(b - a for a, b in segs)
    print(f"{len(segs)} trechos, {dur:.1f}s (de {d['duration']:.1f}s) -> {out}")


if __name__ == "__main__": main()
