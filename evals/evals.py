#!/usr/bin/env python3
"""Evals do corte automático (silêncio + retake + false-start; vale a ÚLTIMA gravação de cada fala).

    evals.py validar-raw   <caso.json>   # etapa A: 2 motores + grupos de retake
    evals.py cortar        <caso.json>   # etapa B: edl.json + decisoes.md + preview 960p
    evals.py validar-corte <caso.json>   # etapa C: transcreve o preview e confere as regras (+ gabarito)
    evals.py run           <caso.json>   # A -> B -> C

Caso (JSON): {"nome", "edit": pasta edit, "clip": stem, "video": mp4 com áudio limpo, "audio": mp3 limpo,
              "gabarito": mp4 cortado pelo Pedro | null}   (caminhos relativos à raiz do projeto)
Specs/gotchas: ferramentas/evals/README.md"""
import sys, re, json, os, subprocess, pathlib, array, math
from difflib import SequenceMatcher

ROOT = pathlib.Path(__file__).resolve().parents[2]
TRANSCREVER = ROOT / "ferramentas/transcrever/transcrever.py"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "transcrever-ptbr"))  # repo irmão
from voicestudio import transcrever_wav  # ASR local (VoiceStudio), motor ativo = whisperx

# mesmos números do corte-silencio/cortes.py (regras fixas do Pedro)
NOISE, MIN_SIL, FINE_SIL, END_PAD, START_PAD = "-50dB", 0.7, 0.3, 0.37, 0.12
SIM_RETAKE, SIM_DUVIDA, LOOKAHEAD = 0.75, 0.66, 8         # prefixo de L palavras >= 75% igual a uma unidade até 8 unidades depois
# ponytail: heurística de prefixo; retake no meio de frase contínua (sem pausa >=0.3s) não é pego. Evoluir se o eval mostrar.
SIL_APERTO, PAUSA_FRASE, PAUSA_MEIO = "-40dB", (0.18, 0.12), (0.12, 0.08)   # (sobra depois da fala, sobra antes da próxima)
MARCADORES = re.compile(r"\b(vamos de novo|desde o começo|de novo|pera[ií]|errei|opa|vou repetir|começando de novo|volta aqui)\b", re.I)


# ---------------------------------------------------------------- utilidades
def norm(t): return re.sub(r"[^\wáàâãéêíóôõúçñ]", "", t.lower())

def caso(p):
    c = json.load(open(p)); c["_dir"] = ROOT / c["edit"]; (c["_dir"] / "evals").mkdir(exist_ok=True); return c

def sh(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, **kw)

def dur(f): return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]).stdout)

def transcrever(src, out, motor=None):
    out = pathlib.Path(out)
    if not out.exists():
        cmd = [sys.executable, str(TRANSCREVER), str(src), "-o", str(out)] + (["--motor", motor] if motor else [])
        r = sh(cmd); out.with_suffix(".log").write_text(r.stdout + r.stderr)
        if not out.exists(): sys.exit(f"transcrição falhou, ver {out.with_suffix('.log')}")
    return json.load(open(out))["words"]

def silencios(audio, d, noise=NOISE):
    o = sh(["ffmpeg", "-nostdin", "-hide_banner", "-i", str(audio), "-af", f"silencedetect=noise={noise}:d={d}", "-f", "null", "-"]).stderr
    s = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", o)]
    e = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", o)]
    return list(zip(s, e + [dur(audio)] * (len(s) - len(e))))

def fala(audio, d):
    """complemento dos silêncios >= d: [[ini, fim], ...]"""
    total, cur, out = dur(audio), 0.0, []
    for s, e in silencios(audio, d):
        if s > cur: out.append([cur, s])
        cur = e
    if cur < total: out.append([cur, total])
    return out


def iso(src, spans, cache):
    """Transcreve CADA trecho isolado (VoiceStudio). O whisperx do arquivo inteiro funde/engole tomadas repetidas
    (ex.: 'Primeiro de tudo, pesquisa sobre a documentação infe...' virou só 'Primeiro'); isolado não tem como fundir."""
    cache = pathlib.Path(cache); memo = json.load(open(cache)) if cache.exists() else {}
    for a, b in spans:
        k = f"{a:.2f}-{b:.2f}"
        if k in memo: continue
        wav = cache.with_suffix(".tmp.wav")
        sh(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{max(0, a - 0.05):.3f}", "-t", f"{b - a + 0.15:.3f}", "-i", str(src), "-ar", "16000", "-ac", "1", str(wav)])
        memo[k] = " ".join(transcrever_wav(wav)[1].split())
        json.dump(memo, open(cache, "w"), ensure_ascii=False)
    wav = cache.with_suffix(".tmp.wav"); wav.unlink(missing_ok=True)
    return [memo[f"{a:.2f}-{b:.2f}"] for a, b in spans]

def partes(video, d=0.18, noise="-42dB"):
    """trechos de fala de um arquivo (entre pausas >= d)"""
    total, cur, sp = dur(video), 0.0, []
    for s, e in silencios(video, d, noise):
        if s - cur > 0.25: sp.append((max(0.0, cur - 0.05), s + 0.1))
        cur = e
    if total - cur > 0.25: sp.append((max(0.0, cur - 0.05), total))
    return sp

# ---------------------------------------------------------------- detecção (o coração)
def unidades(words, audio):
    """Uma unidade = trecho de fala entre silêncios >= 0.3s; palavra entra pelo INÍCIO (o .end do whisperx é inflado)."""
    us = []
    for a, b in fala(audio, FINE_SIL):
        ws = [w for w in words if a - 0.3 <= w["start"] <= b + 0.05]
        if ws: us.append({"a": a, "b": b, "words": ws, "text": " ".join(w["text"] for w in ws)})
    return us

def toks(u): return [x for x in (norm(w) for w in (u.get("iso") or u["text"]).split()) if x]

def decidir(us, snd, over=None):
    """status por unidade: 'manter' | 'retake' (superada por tomada posterior) | 'autocorrecao'. Mais flags de revisão."""
    for i, u in enumerate(us):
        u["status"], u["nota"] = "manter", ""
    for i, u in enumerate(us):
        k = toks(u)
        if len(k) <= 6 and MARCADORES.search(u.get("iso") or u["text"]):
            u["status"], u["nota"] = "autocorrecao", "marcador de recomeço"; continue
        for j in range(i + 1, min(len(us), i + 1 + LOOKAHEAD)):
            k2 = toks(us[j])
            L = min(len(k), len(k2), 6)
            r = SequenceMatcher(a=k[:L], b=k2[:L], autojunk=False).ratio() if L >= 3 else 0
            # contenção: o começo da unidade (>=3 palavras) reaparece, em ordem, dentro do começo da posterior (recomeço com outra abertura)
            m = SequenceMatcher(a=k, b=k2[:25], autojunk=False).find_longest_match(0, len(k), 0, min(len(k2), 25))
            contida = m.size >= max(3, 0.6 * len(k)) and m.a <= 1
            if r >= SIM_RETAKE or contida:
                u["status"], u["nota"] = "retake", f"refeita em {us[j]['a']:.1f}s"
                # última tentativa bem mais curta que a anterior -> pode estar truncada: o agente decide
                if len(k2) < 0.7 * len(k): us[j]["nota"] = f"REVISAR: última tem {len(k2)} palavras, anterior {len(k)}"
                break
            inteira = SequenceMatcher(a=k, b=k2, autojunk=False).ratio() if min(len(k), len(k2)) >= 5 else 0
            if (r >= SIM_DUVIDA or inteira >= 0.5) and not u["nota"]:
                u["nota"] = f"REVISAR: parecida com a fala de {us[j]['a']:.1f}s (mantida)"
    for i in range(len(us) - 1):    # recomeço no fim: as últimas 2-4 palavras de i abrem a unidade seguinte -> corta o rabo de i
        a, b = us[i], us[i + 1]
        if a["status"] != "manter" or b["status"] != "manter": continue
        ka, kb = [norm(w["text"]) for w in a["words"]], [norm(w["text"]) for w in b["words"]]
        for m in (4, 3, 2):
            if len(ka) > m + 2 and ka[-m:] == kb[:m]:
                t0 = a["words"][-m]["start"]    # início do whisperx erra ~50ms: ancora no vale de energia mais fundo ao redor
                vale = min((t0 - 0.35 + i * 0.01 for i in range(46)), key=lambda x: db(snd, x, x + 0.03))
                a["fim"] = vale + 0.015; a["words"] = a["words"][:-m]
                a["nota"] = f"recomeço no fim: cortei as últimas {m} palavras (refeitas em {b['a']:.1f}s)"; break
    for i, why in (over or {}).get("cortar", {}).items():
        us[int(i)]["status"], us[int(i)]["nota"] = "retake", f"agente: {why}"
    for i, (n, why, *t) in (over or {}).get("aparar_inicio", {}).items():   # corta as n primeiras palavras da unidade (abertura solta)
        u = us[int(i)]; t0 = u["words"][n]["start"]
        # whisperx erra ~50ms: ancora no vale; 3º campo = tempo exato escolhido pelo agente (fala colada, sem vale)
        vale = t[0] if t else min((t0 - 0.3 + k * 0.01 for k in range(41)), key=lambda x: db(snd, x, x + 0.03))
        u["ini"] = vale; u["words"] = u["words"][n:]; u["nota"] = f"agente: aparei {n} palavras do início ({why})"
    for i, why in (over or {}).get("manter", {}).items():
        us[int(i)]["status"], us[int(i)]["nota"] = "manter", f"agente: {why}"
    return us

def edl_de(us, audio):
    segs = []
    total = dur(audio)
    for i, u in enumerate(us):
        if u["status"] != "manter": continue
        s, e = (u["ini"] if "ini" in u else max(0.0, u["a"] - START_PAD)), (u["fim"] if "fim" in u else min(total, u["b"] + END_PAD))
        if i + 1 < len(us) and us[i + 1]["status"] != "manter": e = min(e, us[i + 1]["a"] - 0.02)   # não invadir fala descartada
        if i > 0 and us[i - 1]["status"] != "manter": s = max(s, us[i - 1]["b"] + 0.02)
        segs.append([round(s, 3), round(e, 3)])
    merged = []
    for s, e in segs:
        if merged and s <= merged[-1][1] + 0.02: merged[-1][1] = max(merged[-1][1], e)
        else: merged.append([s, e])
    # pausa interna >= 0.7s já vira emenda: os silêncios fine < 0.7 ficam dentro do trecho (unidades coladas), >= 0.7 separam
    return merged

def remover(segs, faixas):
    """tira [ini, fim, motivo] (segundos do raw) dos segmentos: corte pedido no meio de uma unidade"""
    for a, b, _ in faixas:
        segs = [p for s, e in segs for p in ([[s, e]] if b <= s or a >= e else [[s, a]] * (a > s) + [[b, e]] * (e > b))]
    return segs

def apertar(segs, audio, words):
    """Pausa (com respiração, medida a -40dB: a -50dB a respiração conta como fala) fica com no máximo
    0.30s depois de fim de frase e 0.20s no meio dela. Corta o miolo do silêncio, nunca a palavra (Pedro, 18/10/2026)."""
    sil = silencios(audio, 0.1, SIL_APERTO)
    def cap(t):     # (sobra antes, sobra depois) conforme a pontuação da última palavra antes de t
        w = [x for x in words if x["start"] < t]
        return PAUSA_FRASE if w and w[-1]["text"][-1:] in ".?!" else PAUSA_MEIO
    out = []
    for s, e in segs:
        for a, b in sil:
            if b <= s or a >= e: continue
            if a <= s: s = max(s, b - cap(out[-1][1] if out else s)[1])        # trecho começa em silêncio
            elif b >= e: e = min(e, a + cap(a)[0])                              # trecho termina em silêncio
            elif b - a > sum(cap(a)): out.append([s, a + cap(a)[0]]); s = b - cap(a)[1]   # pausa interna
        out.append([s, e])
    return [[round(s, 3), round(e, 3)] for s, e in out if e - s > 0.05]


# ---------------------------------------------------------------- etapa A
def validar_raw(c):
    d = c["_dir"] / "transcripts"; d.mkdir(exist_ok=True)
    wx = transcrever(ROOT / c["audio"], d / f"{c['clip']}.wx.json")
    vad = transcrever(ROOT / c["audio"], d / f"{c['clip']}.vad.json", "vad")
    sm = SequenceMatcher(a=[norm(w["text"]) for w in wx], b=[norm(w["text"]) for w in vad], autojunk=False)
    perdas = [(wx[i1]["start"] if i1 < len(wx) else 0, " ".join(w["text"] for w in vad[j1:j2]))
              for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ("insert", "replace") and j2 - j1 >= 3 and i2 - i1 < (j2 - j1) // 2]
    print(f"[A] whisperx {len(wx)} palavras | vad {len(vad)} | similaridade {sm.ratio():.1%}")
    for t, txt in perdas: print(f"   REVISAR ~{t:.1f}s: o vad tem e o whisperx não: {txt}")
    us = unidades(wx, ROOT / c["audio"])
    for u, tx in zip(us, iso(ROOT / c["audio"], [(u["a"], u["b"]) for u in us], c["_dir"] / "evals/iso.json")): u["iso"] = tx
    us = decidir(us, pcm(ROOT / c["audio"]), c.get("overrides"))
    print(f"[A] {len(us)} unidades de fala; {sum(u['status']!='manter' for u in us)} marcadas pra cortar")
    return {"ok": not perdas, "unidades": us, "wx": wx}

# ---------------------------------------------------------------- etapa B
def cortar(c):
    a = validar_raw(c); us = a["unidades"]; ed = c["_dir"]
    faixas = (c.get("overrides") or {}).get("remover", [])
    segs = apertar(remover(edl_de(us, ROOT / c["audio"]), faixas), ROOT / c["audio"], a["wx"])
    json.dump([{"clip": c["clip"], "segments": segs}], open(ed / "evals/edl.json", "w"), indent=1)
    linhas = ["| # | tempo | status | texto | nota |", "|---|---|---|---|---|"]
    for i, u in enumerate(us):
        linhas.append(f"| {i} | {u['a']:.1f}-{u['b']:.1f} | {u['status']} | {u['text']} | {u['nota']} |")
    for f0, f1, why in faixas: linhas.append(f"| - | {f0:.1f}-{f1:.1f} | removido | | agente: {why} |")
    (ed / "evals/decisoes.md").write_text("\n".join(linhas))
    out = ed / "evals/preview.mp4"
    (ed / "evals/preview.wx.json").unlink(missing_ok=True); (ed / "evals/preview.iso.json").unlink(missing_ok=True)   # preview novo -> transcrição velha não vale
    parts, lab = [], []
    for n, (s, e) in enumerate(segs):
        parts.append(f"[0:v]trim={s}:{e},setpts=PTS-STARTPTS,fps=30000/1001,scale=960:-2[v{n}]")
        parts.append(f"[0:a]atrim={s}:{e},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.008,afade=t=out:st={e-s-0.008:.3f}:d=0.008[a{n}]")
        lab.append(f"[v{n}][a{n}]")
    parts.append("".join(lab) + f"concat=n={len(segs)}:v=1:a=1[v][a]")
    r = sh(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-i", str(ROOT / c["video"]), "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    if r.returncode: sys.exit(r.stderr[-800:])
    print(f"[B] {len(segs)} segmentos, {sum(e-s for s,e in segs):.1f}s de {dur(ROOT/c['audio']):.1f}s -> {out}")
    return {**a, "segs": segs, "preview": out}


# ---------------------------------------------------------------- etapa C
def pcm(audio):
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    a = array.array("h"); a.frombytes(raw); return a

def db(a, t0, t1, sr=16000):
    x = a[max(0, int(t0 * sr)):int(t1 * sr)]
    return 20 * math.log10(math.sqrt(sum(v * v for v in x) / max(len(x), 1)) / 32768 + 1e-9)

def validar_corte(c, b=None):
    b = b or cortar(c)
    ed, us, segs = c["_dir"], b["unidades"], b["segs"]
    cut = transcrever(b["preview"], ed / "evals/preview.wx.json")
    res = {}
    # (a) nenhuma fala de retake/autocorreção anterior sobrou: n-grama (4 palavras) só dela, ausente do que foi mantido
    ng = lambda ws: {tuple(ws[i:i + 4]) for i in range(len(ws) - 3)}
    mantido = ng([norm(w["text"]) for u in us if u["status"] == "manter" for w in u["words"]])
    cutk = ng([norm(w["text"]) for w in cut])
    sobras = [(u["a"], u["text"]) for u in us if u["status"] != "manter" and len((ng([norm(w["text"]) for w in u["words"]]) - mantido) & cutk) >= 2]
    res["retake_sobrou"] = sobras
    # (a2) frase quase repetida dentro do corte (checagem independente do detector: pega retake que o raw transcreveu diferente)
    fr, atual = [], []
    for i, w in enumerate(cut):
        atual.append(w)
        prox = cut[i + 1]["start"] if i + 1 < len(cut) else None
        if prox is None or prox - w["end"] > 0.7 or w["text"][-1:] in ".?!": fr.append(atual); atual = []
    fk = [[norm(w["text"]) for w in s] for s in fr]; rep = []
    for i in range(len(fk)):
        for j in range(i + 1, min(len(fk), i + 6)):
            if min(len(fk[i]), len(fk[j])) >= 6 and SequenceMatcher(a=fk[i], b=fk[j], autojunk=False).ratio() >= 0.6:
                rep.append((round(fr[i][0]["start"], 1), round(fr[j][0]["start"], 1), " ".join(w["text"] for w in fr[i])))
    # (a3) o mesmo, trecho a trecho (cada trecho transcrito isolado): pega tomada que o whisper fundiu na transcrição do corte inteiro
    sp = partes(b["preview"]); tx = iso(b["preview"], sp, ed / "evals/preview.iso.json"); tk = [[x for x in (norm(w) for w in s.split()) if x] for s in tx]
    for i in range(len(tk)):
        for j in range(i + 1, min(len(tk), i + 5)):
            x, y = (tk[i], tk[j]) if len(tk[i]) <= len(tk[j]) else (tk[j], tk[i])
            pref = len(x) >= 3 and y[:len(x)] == x          # trecho curto = começo do outro (recomeço)
            m = SequenceMatcher(a=tk[i], b=tk[j], autojunk=False).find_longest_match(0, len(tk[i]), 0, len(tk[j])).size
            if pref or m >= 5:
                rep.append((round(sp[i][0], 1), round(sp[j][0], 1), tx[i]))
    res["repeticao_no_corte"] = rep
    # (b) texto esperado (unidades mantidas) == texto do corte
    fora = (c.get("overrides") or {}).get("remover", [])    # faixa removida de propósito não conta como fala sumida
    esp = [norm(w["text"]) for u in us if u["status"] == "manter" for w in u["words"] if not any(a <= w["start"] < b for a, b, _ in fora)]
    got = [norm(w["text"]) for w in cut]
    sm = SequenceMatcher(a=esp, b=got, autojunk=False)
    res["fala_sumiu"] = [" ".join(esp[i1:i2]) for t, i1, i2, j1, j2 in sm.get_opcodes()   # replace do mesmo tamanho = só grafia diferente do whisper
                         if t in ("delete", "replace") and i2 - i1 >= 3 and (j2 - j1) < 0.5 * (i2 - i1)]
    res["similaridade_texto"] = round(sm.ratio(), 4)
    # (c) silêncio longo no corte: a -40dB (a -50dB a respiração conta como fala e a pausa passava); o aperto deixa <= 0.30s
    res["silencio_longo"] = [(round(s, 1), round(e - s, 1)) for s, e in silencios(b["preview"], 0.45, SIL_APERTO)]
    # (d) palavra capada: energia ainda alta no último/primeiro 30ms de cada emenda (no áudio limpo de origem)
    a = pcm(ROOT / c["audio"]); capada = []
    exato = {round(v[2], 3) for v in (c.get("overrides") or {}).get("aparar_inicio", {}).values() if len(v) > 2}   # decidido e conferido pelo agente
    for s, e in segs:
        if db(a, e - 0.03, e) > -42: capada.append(("fim", round(e, 2)))
        if s > 0 and s not in exato and db(a, s, s + 0.03) > -42: capada.append(("inicio", round(s, 2)))
    res["palavra_capada"] = capada
    # gabarito (corte manual do Pedro)
    if c.get("gabarito"):
        gab = transcrever(ROOT / c["gabarito"], ed / "evals/gabarito.wx.json")
        g = [norm(w["text"]) for w in gab]; sm2 = SequenceMatcher(a=g, b=got, autojunk=False)
        res["gabarito_sim"] = round(sm2.ratio(), 4)
        res["gabarito_falta"] = [" ".join(g[i1:i2]) for t, i1, i2, _, _ in sm2.get_opcodes() if t in ("delete", "replace") and i2 - i1 >= 3]
        res["gabarito_sobra"] = [" ".join(got[j1:j2]) for t, _, _, j1, j2 in sm2.get_opcodes() if t in ("insert", "replace") and j2 - j1 >= 3]
    falhas = [k for k in ("retake_sobrou", "repeticao_no_corte", "fala_sumiu", "silencio_longo", "palavra_capada", "gabarito_falta", "gabarito_sobra") if res.get(k)]
    res["aprovado"] = not falhas
    (ed / "evals/resultado.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"[C] {'APROVADO' if res['aprovado'] else 'REPROVADO: ' + ', '.join(falhas)}")
    for k, v in res.items():
        if v and k not in ("aprovado",): print(f"   {k}: {v}")
    return res


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("validar-raw", "cortar", "validar-corte", "run"): sys.exit(__doc__)
    c = caso(sys.argv[2])
    {"validar-raw": validar_raw, "cortar": cortar, "validar-corte": validar_corte, "run": validar_corte}[sys.argv[1]](c)
