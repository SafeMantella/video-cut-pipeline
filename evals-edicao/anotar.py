#!/usr/bin/env python3
"""Consolida as decisões do Pedro (db/reviews) + chunks + sugestões em anotacoes.json/.md na pasta do vídeo.
Uso: anotar.py <pasta-do-video> --titulo "Nome"   (a pasta tem evals-edicao/{chunks.json,sugestoes.json,db/reviews})"""
import argparse, glob, json, pathlib

p = argparse.ArgumentParser(); p.add_argument("pasta"); p.add_argument("--titulo", default="")
x = p.parse_args(); v = pathlib.Path(x.pasta); e = v / "evals-edicao"
ch = json.load(open(e / "chunks.json")); sg = json.load(open(e / "sugestoes.json"))
rv = {r["i"]: r for r in (json.load(open(f)) for f in glob.glob(str(e / "db/reviews/*.json")))}
rows, kept = [], 0.0
for c in ch["chunks"]:
    i, r, s = c["i"], rv[c["i"]], sg[str(c["i"])]
    rows.append({"i": i, "start": c["start"], "end": c["end"], "texto": c["text"], "sugestao": s["action"], "sugestao_motivo": s["why"],
                 "sugestao_detalhe": s.get("detail", ""), "decisao": r["action"], "trimIn": r["trimIn"], "trimOut": r["trimOut"],
                 "cortes_internos": r["cuts"], "tags": r["tags"], "detalhe": r["detail"], "motion_escolhido": r.get("motionLabel", ""), "motion_desc": r.get("motionDesc", ""), "nota": r["note"], "igual_a_sugestao": r["action"] == s["action"]})
    if r["action"] != "remover": kept += r["trimOut"] - r["trimIn"] - sum(b - a for a, b in r["cuts"])
ag = sum(r["igual_a_sugestao"] for r in rows)
out = {"video": v.name, "titulo": x.titulo, "duracao_raw": ch["duration"], "duracao_mantida": round(kept, 2), "concordancia_acao": f"{ag}/{len(rows)}",
       "mantidos": [r["i"] for r in rows if r["decisao"] != "remover"], "chunks": rows}
json.dump(out, open(v / "anotacoes.json", "w"), ensure_ascii=False, indent=1)
md = [f"# Anotações de edição: {v.name} ({x.titulo})", "", f"Raw {ch['duration']:.1f} s, mantido {kept:.1f} s. Ação igual à sugestão: {ag}/{len(rows)}. Tempos em segundos do vídeo original. Completo: `anotacoes.json`.", "",
      "## Fica no vídeo (ordem final)", "", "| # | início | fim | decisão | texto | detalhe/nota/cortes |", "|---|---|---|---|---|---|"]
for r in rows:
    if r["decisao"] != "remover":
        ex = "; ".join(filter(None, [("motion: " + r["motion_escolhido"] + " (" + r["motion_desc"] + ")") if r["motion_escolhido"] else "", r["detalhe"], r["nota"], f"cortes {r['cortes_internos']}" if r["cortes_internos"] else "", ",".join(r["tags"])]))
        md.append(f"| {r['i']} | {r['trimIn']:.2f} | {r['trimOut']:.2f} | {r['decisao']} | {r['texto']} | {ex} |")
md += ["", "## Sai do vídeo", "", ", ".join(f"#{r['i']}" for r in rows if r["decisao"] == "remover"), "", "## Onde discordou de mim", ""]
md += [f"- #{r['i']}: sugeri **{r['sugestao']}**, ele marcou **{r['decisao']}**." for r in rows if not r["igual_a_sugestao"]] or ["- Nenhuma."]
(v / "anotacoes.md").write_text("\n".join(md) + "\n")
print(out["duracao_mantida"], out["concordancia_acao"], out["mantidos"])
