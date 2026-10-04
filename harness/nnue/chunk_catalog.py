"""The chunk catalog: every training chunk, the networks trained on it, and what each chunk measured.

    python harness/nnue/chunk_catalog.py [--meta catalog/chunks_meta.json] [--queue E:/machete/queue-gpu]
        [--roots E:/machete/corpora E:/machete/claude/data] [--out catalog]

A network is a list of chunks (corpus files) plus a width, an epoch count and
a seed. This reads which chunks every network was trained on from the GPU
queue's job records (the argv of each train.py run), the chunks' sizes from
disk, and the hand-kept half - what each chunk is, and what each experiment
that isolated a chunk measured - from catalog/chunks_meta.json. It writes:

  catalog/catalog.json       everything, for other tools
  catalog/chunk_ledger.tsv   one row per isolating experiment: the record of
                             Elo shifts by chunk, appended to as chunks are tried
  catalog/chunk-catalog.html one self-contained page to explore it

To record a new result: add the chunk (if new) and one experiment to
chunks_meta.json, and run this again.
"""
import argparse
import glob
import json
import os
import sys

RECORD = 70


def networks(queue):
    out = []
    for folder in ("done", "failed"):
        for f in sorted(glob.glob(os.path.join(queue, folder, "*.json"))):
            job = json.load(open(f, encoding="utf-8"))
            argv = job.get("argv", [])
            if not any("train.py" in a for a in argv):
                continue
            flags = {argv[i]: argv[i + 1] for i in range(len(argv) - 1) if argv[i].startswith("--")}
            chunks = []
            for a in argv:
                base = os.path.basename(a)
                if base.endswith(".bin") or ".bin@" in base:
                    name, _, take = base.partition("@")
                    chunks.append(dict(chunk=name, take=int(take) if take else None))
            merged = {}
            for c in chunks:  # a chunk listed twice is weighted twice
                key = (c["chunk"], c["take"])
                merged.setdefault(key, dict(chunk=c["chunk"], take=c["take"], copies=0))["copies"] += 1
            out.append(dict(
                id=job["id"].replace("TRAIN-", ""), job=job["id"], date="%s-%s-%s" % (os.path.basename(f)[:4], os.path.basename(f)[4:6], os.path.basename(f)[6:8]),
                finished=folder == "done", hidden=int(flags.get("--hidden", 256)), epochs=int(flags.get("--epochs", 12)),
                seed=int(flags.get("--seed", 1)), change=job.get("change", ""), chunks=list(merged.values()),
                trainer=next((os.path.basename(os.path.dirname(a)) for a in argv if "train.py" in a), "")))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meta", default="catalog/chunks_meta.json")
    parser.add_argument("--queue", default="E:/machete/queue-gpu")
    parser.add_argument("--roots", nargs="*", default=["E:/machete/corpora", "E:/machete/claude/data"])
    parser.add_argument("--out", default="catalog")
    args = parser.parse_args()
    meta = json.load(open(args.meta, encoding="utf-8"))
    nets = networks(args.queue)

    names = list(meta["chunks"])
    for n in nets:
        for c in n["chunks"]:
            if c["chunk"] not in names:
                names.append(c["chunk"])
    chunks = []
    for name in names:
        m = meta["chunks"].get(name, {})
        path = next((os.path.join(r, name) for r in args.roots if os.path.exists(os.path.join(r, name))), None)
        parts = [p for r in args.roots for p in glob.glob(os.path.join(r, name + ".*.part"))]
        size = os.path.getsize(path) // RECORD if path else (sum(os.path.getsize(p) for p in parts) // RECORD if parts else None)
        used = [n["id"] for n in nets if n["finished"] and any(c["chunk"] == name for c in n["chunks"])]
        chunks.append(dict(name=name, positions=size, on_disk=bool(path or parts), in_progress=bool(parts and not path),
                           family=m.get("family", "undescribed"), teacher=m.get("teacher", ""), source=m.get("source", ""),
                           addresses=m.get("addresses", ""), note=m.get("note", ""), status=m.get("status", ""),
                           used_by=used, first=used[0] if used else None,
                           experiments=[i for i, e in enumerate(meta["experiments"]) if name in e.get("chunks", [])]))
    sizes = {c["name"]: c["positions"] for c in chunks}
    for n in nets:
        total = 0
        for c in n["chunks"]:
            c["positions"] = c["take"] or sizes.get(c["chunk"])
            total += (c["positions"] or 0) * c["copies"]
        n["positions"] = total
    catalog = dict(chunks=chunks, networks=nets, experiments=meta["experiments"], seed_noise=meta.get("seed_noise", []))

    os.makedirs(args.out, exist_ok=True)
    json.dump(catalog, open(os.path.join(args.out, "catalog.json"), "w", encoding="utf-8"), indent=1)
    with open(os.path.join(args.out, "chunk_ledger.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("date\tnetwork\tbase\tchange\tchunks\tgames\telo\tmargin95\tverdict\tsource\n")
        for e in meta["experiments"]:
            f.write("\t".join(str(x if x is not None else "-") for x in (
                e["date"], e["net"], e["base"], e["delta"], ",".join(e.get("chunks", [])) or "-", e.get("games"),
                e.get("elo"), e.get("margin"), e["verdict"], e["source"])) + "\n")
    template = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "chunk_catalog.html"), encoding="utf-8").read()
    page = template.replace("/*DATA*/null", json.dumps(catalog, separators=(",", ":")))
    open(os.path.join(args.out, "chunk-catalog.html"), "w", encoding="utf-8", newline="\n").write(page)
    print("%d chunks (%d on disk), %d networks, %d experiments -> %s" % (
        len(chunks), sum(c["on_disk"] for c in chunks), len(nets), len(meta["experiments"]), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
