#!/usr/bin/env python3
"""Gera os documentos do banco do artifact (videos/ e chunks/) a partir de chunks.json + sugestoes.json.
Uso: semear.py <pasta evals-edicao> --vid slug --titulo "Nome" --asset <id do proxy.mp4> [--sugestoes sugestoes.json]
sugestoes.json: {"1": {"action": "manter|remover|motion|imagem|imagem+motion", "why": "...", "detail": "...", "images": [{"assetId": "...", "label": "..."}], "motions": [{"label": "...", "desc": "...", "timing": "..."}]}}   # motions: 4 opções por chunk motion / imagem+motion
Saída: <pasta>/seed/video.json, <vid>_NNN.json e writes.json (lista pro ArtifactData batch, no máx. 50 por chamada)."""
import argparse, json, pathlib, time

ACOES = {"manter", "remover", "motion", "imagem", "imagem+motion"}


def main():
    p = argparse.ArgumentParser(); p.add_argument("pasta"); p.add_argument("--vid", required=True); p.add_argument("--titulo", required=True)
    p.add_argument("--asset", required=True); p.add_argument("--sugestoes"); x = p.parse_args()
    pasta = pathlib.Path(x.pasta); d = json.load(open(pasta / "chunks.json"))
    sug = json.load(open(x.sugestoes or pasta / "sugestoes.json")); out = pasta / "seed"; out.mkdir(exist_ok=True)
    falta = [str(c["i"]) for c in d["chunks"] if str(c["i"]) not in sug]
    ruim = [k for k, v in sug.items() if v.get("action") not in ACOES]
    sem4 = [k for k, v in sug.items() if v.get("action") in ("motion", "imagem+motion") and len(v.get("motions") or []) != 4]
    if sem4: print(f"AVISO: motion/imagem+motion sem 4 opções em motions: {sem4}")
    assert not falta and not ruim, f"sem sugestão: {falta}; ação inválida: {ruim}"
    json.dump({"title": x.titulo, "assetId": x.asset, "duration": d["duration"], "minSil": d["min_sil"], "peaks": d["peaks"],
               "createdAt": int(time.time() * 1000), "n": len(d["chunks"])}, open(out / "video.json", "w"))
    writes = [{"op": "set", "collection": "videos", "doc_id": x.vid, "file_path": str((out / "video.json").resolve())}]
    for c in d["chunks"]:
        did = f"{x.vid}_{c['i']:03d}"
        json.dump({"vid": x.vid, "i": c["i"], "start": c["start"], "end": c["end"], "text": c.get("text", ""), "sug": sug[str(c["i"])]},
                  open(out / f"{did}.json", "w"), ensure_ascii=False)
        writes.append({"op": "set", "collection": "chunks", "doc_id": did, "file_path": str((out / f"{did}.json").resolve())})
    json.dump(writes, open(out / "writes.json", "w"), indent=1)
    print(f"{len(writes)} escritas em {out / 'writes.json'} ({(len(writes) + 49) // 50} chamada(s) de batch)")


if __name__ == "__main__": main()
