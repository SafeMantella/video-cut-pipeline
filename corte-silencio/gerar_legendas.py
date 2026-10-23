#!/usr/bin/env python3
"""t.json (whisperx + glossário) -> palavras.json, cues.json, legendas.srt
Correções validadas por isolamento de janela + 2 modelos. Tempos refinados pela energia do áudio:
fim de cue = onde a energia cai (o .end do whisperx é inflado); início = onset real da 1ª palavra."""
import json, subprocess, math, re
import numpy as np
w = json.load(open("t.json"))["words"]
# --- correções de texto ---
out = []
for x in w:
    if x["text"] == "e" and 87.2 < x["start"] < 87.5: continue          # CTA: "comentários. Segue aí." (2 modelos + isolada)
    if x["text"] == "comentários" and x["start"] > 86: x = dict(x, text="comentários.")
    if x["text"] == "segue" and x["start"] > 87: x = dict(x, text="Segue")
    out.append(dict(x))
w = out
# --- energia ---
a = subprocess.run(["ffmpeg","-nostdin","-v","error","-i","audio.wav","-ac","1","-ar","16000","-f","f32le","-"],capture_output=True).stdout
x = np.frombuffer(a, dtype=np.float32); SR = 16000
def db(t0, t1):
    s = x[int(max(t0,0)*SR):int(t1*SR)]
    return 20*np.log10(np.sqrt((s**2).mean())+1e-9) if len(s) else -99
def onset(t):                       # 1º frame de 20ms acima de -42 dB perto do início marcado
    for k in range(-5, 30):
        tt = t + k*0.02
        if db(tt, tt+0.02) > -42: return round(tt, 2)
    return t
def offset(t_start, t_end):         # fim da fala: energia < -45 dB por 80 ms, a partir do início da palavra
    tt = t_start + 0.1; lim = min(t_end, t_start + 1.6)
    while tt < lim:
        if db(tt, tt+0.08) < -45: return round(tt, 2)
        tt += 0.02
    return round(lim, 2)
# --- palavra com pausa dentro (whisperx marca o início cedo demais, ex: "brainstorms" 69.03 -> fala em 69.45) ---
def late_onset(p):
    t = p["start"] + 0.08; end = min(p["end"], p["start"] + 1.5); run0 = None
    while t < end:
        low = db(t, t+0.02) < -42
        if low and run0 is None: run0 = t
        if not low and run0 is not None:
            if t - run0 >= 0.22: return round(t, 2)
            run0 = None
        t += 0.02
    return None
for p in w:
    lo = late_onset(p)
    if lo and lo - p["start"] > 0.2:
        print(f"  ajuste início '{p['text']}': {p['start']:.2f} -> {lo:.2f}"); p["start"] = lo
# --- sentenças ---
sents, cur = [], []
for i, p in enumerate(w):
    cur.append(i)
    if p["text"][-1] in ".?!": sents.append(cur); cur = []
if cur: sents.append(cur)
# --- cues <= 5 palavras, quebrando em vírgula/pausa quando der ---
def split(idx):
    """<=5 palavras por cue; DP minimiza custo: prefere cortar em vírgula/pausa e cues de tamanho parecido"""
    n = len(idx)
    if n <= 5: return [idx]
    if n == 6 and w[idx[-1]]["end"] - w[idx[0]]["start"] <= 1.8: return [idx]   # frase curta e rápida: 1 cue só (6 palavras)
    k = math.ceil(n/5)
    STOP = {"a","o","as","os","um","uma","de","do","da","dos","das","em","no","na","com","para","pra","por","que","e","é","ao","se","ou","mas","mais","eu","ele","você","isso"}
    def brk(ct):                     # bônus de quebrar depois da palavra ct-1
        wd = w[idx[ct-1]]; nx = w[idx[ct]]
        pen = 1.6 if (wd["text"][-1] not in ".,;:?!" and wd["text"].lower().strip(".,;:?!") in STOP) else 0
        return (1.5 if wd["text"][-1] in ",;:" else 0) + min(max(nx["start"] - wd["end"], 0), 0.6)*2 - pen
    INF = 1e9
    best = {(0, 0): (0.0, None)}      # (posição, nº de cues) -> (custo, anterior)
    for pos in range(1, n+1):
        for c in range(1, k+2):
            cand = []
            for ln in range(1, 6):
                p = pos - ln
                if (p, c-1) in best:
                    dur = w[idx[pos-1]]["end"] - w[idx[p]]["start"]
                    cost = best[(p, c-1)][0] + abs(ln - n/k) - (brk(pos) if pos < n else 0) + max(0.6 - dur, 0)*3   # cue relâmpago atrapalha leitura
                    cand.append((cost, p))
            if cand: best[(pos, c)] = (min(cand)[0], min(cand)[1])
    c = min((cc for cc in range(1, k+2) if (n, cc) in best), key=lambda cc: best[(n, cc)][0] + (0 if cc == k else 2))
    cuts, pos = [], n
    while pos > 0:
        p = best[(pos, c)][1]; cuts.append((p, pos)); pos, c = p, c-1
    return [idx[a:b] for a, b in reversed(cuts)]
cues = []
for s in sents:
    for ch in split(s):
        txt = " ".join(w[i]["text"] for i in ch)
        st = onset(w[ch[0]]["start"]); en = offset(w[ch[-1]]["start"], w[ch[-1]]["end"])
        cues.append({"start": st, "end": en, "text": txt})
for a_, b_ in zip(cues, cues[1:]):   # fala contínua -> cue segura até o próximo; pausa real (>=0.25s) -> fim pela energia
    gap = b_["start"] - a_["end"]
    if gap < 0.25 or a_["end"] > b_["start"]: a_["end"] = round(b_["start"] - 0.01, 2)
    else: a_["end"] = round(a_["end"] + 0.06, 2)
json.dump(w, open("palavras.json","w"), ensure_ascii=False, indent=1)
json.dump(cues, open("cues.json","w"), ensure_ascii=False, indent=1)
def ts(t): h=int(t//3600); m=int(t%3600//60); s=t%60; return f"{h:02}:{m:02}:{s:06.3f}".replace(".",",")
open("legendas.srt","w").write("\n".join(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n" for i, c in enumerate(cues, 1)))
for i, c in enumerate(cues, 1): print(f"{i:2} {c['start']:6.2f} → {c['end']:6.2f}  {c['text']}")
