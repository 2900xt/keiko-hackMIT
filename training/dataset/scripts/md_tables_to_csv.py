"""Parse the markdown tables in catalog/survey_*.md into CSV files."""
import csv, re, sys, pathlib
def parse_tables(text):
    tables, cur = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cur.append(line)
        else:
            if len(cur) >= 2: tables.append(cur)
            cur = []
    if len(cur) >= 2: tables.append(cur)
    out = []
    for t in tables:
        rows = []
        for line in t:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells): continue
            rows.append(cells)
        hdr = [h.lower().strip("*# ").replace(" / ", "_").replace(" ", "_") for h in rows[0]]
        body = [dict(zip(hdr, r + [""]*(len(hdr)-len(r)))) for r in rows[1:]]
        out.append((hdr, body))
    return out
def clean(s): return re.sub(r"\*+", "", s).strip()
for name, group_default in [("survey_marine_mammals", "mammal"), ("survey_fish_invertebrates", "non-mammal")]:
    text = pathlib.Path(f"catalog/{name}.md").read_text()
    tabs = parse_tables(text)
    for hdr, body in tabs:
        if "scientific_name" in hdr: kind = "species_sounds"
        elif any("dataset" in h for h in hdr[:2]): kind = "datasets"
        else: continue
        path = pathlib.Path(f"catalog/{kind}_{name.replace('survey_','')}.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=hdr + ["survey"]); w.writeheader()
            for r in body:
                r = {k: clean(v) for k, v in r.items()}; r["survey"] = name; w.writerow(r)
        print(path, len(body), "rows; cols:", hdr)
