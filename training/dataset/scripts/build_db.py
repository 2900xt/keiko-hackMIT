#!/usr/bin/env python3
"""Build the unified marine animal sound database.

Inputs (under raw/):
  watkins_full/data/*.parquet        Watkins Marine Mammal Sound Database, full cuts (HF mirror)
  reefset/ReefSet_v1.0/              ReefSet v1.0 clips + reefset_annotations.json
  zenodo/<record>/                   small species-specific fish sets
  toadfish/                          ToadFishFinder oyster toadfish clips (optional)

Outputs:
  audio/<dataset>/<taxon>/<file>.wav  extracted clips
  marine_sounds.sqlite                relational DB (species, sound_types, datasets, clips)
  catalog/*.csv                       flat exports
"""
import csv, glob, io, json, os, re, sqlite3, sys, pathlib, collections
import pyarrow.parquet as pq
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, AUDIO, CAT = ROOT / "raw", ROOT / "audio", ROOT / "catalog"
DB = ROOT / "marine_sounds.sqlite"
AUDIO.mkdir(exist_ok=True)

# ----------------------------------------------------------------------------- taxonomy helpers
SYNONYMS = {  # old/variant scientific names in Watkins -> accepted name
    "Physeter catodon": "Physeter macrocephalus",
    "Globicephala melaena": "Globicephala melas",
    "Globicephala scammoni": "Globicephala macrorhynchus",
    "Phoca hispida": "Pusa hispida",
    "Phoca groenlandica": "Pagophilus groenlandicus",
    "Phoca vitulina richardii": "Phoca vitulina",
    "Delphinus bairdii": "Delphinus delphis bairdii",
    "Stenella plagiodon": "Stenella frontalis",
    "Stenella longirostris": "Stenella longirostris",
    "Lagenorhynchus obliquidens": "Lagenorhynchus obliquidens",
    "Sousa chinensis": "Sousa chinensis",
    "Balaenoptera acutorostrata": "Balaenoptera acutorostrata",
    "Eubalaena australis": "Eubalaena australis",
    "Kogia simus": "Kogia sima",
    "Peponocephala electra": "Peponocephala electra",
    "Ziphius cavirostris": "Ziphius cavirostris",
    "Monachus schauinslandi": "Neomonachus schauinslandi",
    "Odobenus rosmarus divergens": "Odobenus rosmarus",
    "Erignathus barbatus": "Erignathus barbatus",
}
GENUS_GROUP = {
    # baleen whales
    "Balaenoptera": "baleen whale", "Megaptera": "baleen whale", "Eubalaena": "baleen whale",
    "Balaena": "baleen whale", "Eschrichtius": "baleen whale",
    # pinnipeds
    "Phoca": "pinniped", "Pusa": "pinniped", "Halichoerus": "pinniped", "Cystophora": "pinniped",
    "Erignathus": "pinniped", "Pagophilus": "pinniped", "Leptonychotes": "pinniped", "Hydrurga": "pinniped",
    "Lobodon": "pinniped", "Ommatophoca": "pinniped", "Odobenus": "pinniped", "Eumetopias": "pinniped",
    "Zalophus": "pinniped", "Mirounga": "pinniped", "Callorhinus": "pinniped", "Monachus": "pinniped",
    "Neomonachus": "pinniped", "Arctocephalus": "pinniped", "Histriophoca": "pinniped", "Phocarctos": "pinniped",
    # sirenians
    "Trichechus": "sirenian", "Dugong": "sirenian",
    # other
    "Enhydra": "sea otter", "Ursus": "polar bear",
}
CETACEAN_GENERA = {"Delphinus", "Tursiops", "Stenella", "Orcinus", "Pseudorca", "Globicephala", "Grampus",
    "Lagenorhynchus", "Delphinapterus", "Monodon", "Physeter", "Kogia", "Phocoena", "Phocoenoides", "Inia",
    "Sotalia", "Sousa", "Steno", "Peponocephala", "Feresa", "Lagenodelphis", "Lissodelphis", "Cephalorhynchus",
    "Ziphius", "Mesoplodon", "Hyperoodon", "Berardius", "Platanista", "Pontoporia", "Lipotes", "Neophocaena",
    "Orcaella", "Tasmacetus", "Indopacetus"}


# Watkins species codes (verified from the WHOI fullCuts.cfm / index.cfm dropdowns, Wayback 2024-08-10)
WATKINS_CODES = {
 "AA1A": ("Balaena mysticetus", "Bowhead whale"), "AA3A": ("Eubalaena glacialis", "North Atlantic right whale"),
 "AA3B": ("Eubalaena australis", "Southern right whale"), "AB1A": ("Eschrichtius robustus", "Gray whale"),
 "AC1A": ("Balaenoptera acutorostrata", "Minke whale"), "AC1E": ("Balaenoptera musculus", "Blue whale"),
 "AC1F": ("Balaenoptera physalus", "Fin whale"), "AC2A": ("Megaptera novaeangliae", "Humpback whale"),
 "BA2A": ("Physeter macrocephalus", "Sperm whale"), "BB1A": ("Delphinapterus leucas", "Beluga"),
 "BB2A": ("Monodon monoceros", "Narwhal"), "BC9A": ("Ziphius cavirostris", "Cuvier's beaked whale"),
 "BD10A": ("Peponocephala electra", "Melon-headed whale"), "BD12A": ("Sotalia borneensis", "Irrawaddy dolphin (as listed by Watkins)"),
 "BD12B": ("Sotalia fluviatilis", "Tucuxi"), "BD15A": ("Stenella attenuata", "Pantropical spotted dolphin"),
 "BD15B": ("Stenella clymene", "Clymene dolphin"), "BD15C": ("Stenella coeruleoalba", "Striped dolphin"),
 "BD15F": ("Stenella frontalis", "Atlantic spotted dolphin"), "BD15L": ("Stenella longirostris", "Spinner dolphin"),
 "BD17A": ("Steno bredanensis", "Rough-toothed dolphin"), "BD19A": ("Tursiops aduncus", "Indo-Pacific bottlenose dolphin"),
 "BD19D": ("Tursiops truncatus", "Common bottlenose dolphin"), "BD1A": ("Cephalorhynchus commersonii", "Commerson's dolphin"),
 "BD1C": ("Cephalorhynchus heavisidii", "Heaviside's dolphin"), "BD3A": ("Delphinus delphis bairdii", "Long-beaked common dolphin"),
 "BD3B": ("Delphinus delphis", "Common dolphin"), "BD4A": ("Grampus griseus", "Risso's dolphin"),
 "BD5A": ("Lagenodelphis hosei", "Fraser's dolphin"), "BD6A": ("Lagenorhynchus acutus", "Atlantic white-sided dolphin"),
 "BD6B": ("Lagenorhynchus albirostris", "White-beaked dolphin"), "BD6C": ("Lagenorhynchus australis", "Peale's dolphin"),
 "BD6G": ("Lagenorhynchus obliquidens", "Pacific white-sided dolphin"), "BD6H": ("Lagenorhynchus obscurus", "Dusky dolphin"),
 "BE3A": ("Globicephala melas", "Long-finned pilot whale"), "BE3C": ("Globicephala melas", "Long-finned pilot whale"),
 "BE3D": ("Globicephala macrorhynchus", "Short-finned pilot whale"), "BE7A": ("Orcinus orca", "Killer whale"),
 "BE9A": ("Pseudorca crassidens", "False killer whale"), "BF2A": ("Phocoena phocoena", "Harbour porpoise"),
 "BF4A": ("Phocoenoides dalli", "Dall's porpoise"), "BF6A": ("Neophocaena phocaenoides", "Finless porpoise"),
 "BG2A": ("Inia geoffrensis", "Amazon river dolphin (boto)"), "CA1F": ("Arctocephalus forsteri", "New Zealand fur seal"),
 "CA1P": ("Arctocephalus philippii", "Juan Fernandez fur seal"), "CA2A": ("Callorhinus ursinus", "Northern fur seal"),
 "CA3B": ("Eumetopias jubatus", "Steller sea lion"), "CA6A": ("Otaria flavescens", "South American sea lion"),
 "CA8A": ("Phocarctos hookeri", "New Zealand sea lion"), "CA9A": ("Zalophus californianus", "California sea lion"),
 "CB1A": ("Odobenus rosmarus", "Walrus"), "CC10A": ("Mirounga angustirostris", "Northern elephant seal"),
 "CC12F": ("Histriophoca fasciata", "Ribbon seal"), "CC12G": ("Pagophilus groenlandicus", "Harp seal"),
 "CC12H": ("Pusa hispida", "Ringed seal"), "CC12L": ("Phoca largha", "Spotted seal"), "CC12V": ("Phoca vitulina", "Harbour seal"),
 "CC14A": ("Ommatophoca rossii", "Ross seal"), "CC1A": ("Cystophora cristata", "Hooded seal"), "CC2A": ("Erignathus barbatus", "Bearded seal"),
 "CC3A": ("Halichoerus grypus", "Grey seal"), "CC4A": ("Hydrurga leptonyx", "Leopard seal"), "CC5A": ("Leptonychotes weddellii", "Weddell seal"),
 "CC6A": ("Lobodon carcinophaga", "Crabeater seal"), "CD1A": ("Enhydra lutris", "Sea otter"), "DB1B": ("Trichechus manatus", "West Indian manatee"),
}
GENUS_GROUP.update({"Otaria": "pinniped", "Phoca": "pinniped"})

def canonical(name):
    if not name: return None
    name = re.sub(r"\s+", " ", name.strip())
    return SYNONYMS.get(name, name)

def taxon_group(sci):
    if not sci: return None
    g = sci.split()[0]
    if g in GENUS_GROUP: return GENUS_GROUP[g]
    if g in CETACEAN_GENERA: return "toothed whale"
    return None

def prettify(disp):
    """Watkins display names like 'Fin_FinbackWhale' -> 'Fin / Finback Whale'."""
    t = disp.replace("_", " / ").replace("(", " (")
    t = re.sub(r"(?<=[a-z'])(?=[A-Z])", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "unknown").strip("_")

# coarse sound tags mined from Watkins free-text notes
TAG_PATTERNS = [
    ("click", r"\bclick"), ("whistle", r"\bwhistl"), ("squeal", r"\bsqueal"), ("squeak", r"\bsqueak"),
    ("moan", r"\bmoan"), ("song", r"\bsong"), ("pulse", r"\bpuls"), ("buzz", r"\bbuzz"), ("creak", r"\bcreak"),
    ("bark", r"\bbark"), ("grunt", r"\bgrunt"), ("groan", r"\bgroan"), ("growl", r"\bgrowl"), ("roar", r"\broar"),
    ("trill", r"\btrill"), ("knock", r"\bknock"), ("scream", r"\bscream"), ("chirp", r"\bchirp"),
    ("upcall", r"\bupcall|\bup-call|\bupsweep"), ("downsweep", r"\bdownsweep|\bdown-sweep"), ("gunshot", r"\bgunshot"),
    ("coda", r"\bcoda"), ("call", r"\bcall"), ("cry", r"\bcry|\bcries"), ("bell", r"\bbell"), ("blow", r"\bblow"),
    ("echolocation", r"\becholoc"), ("sonar", r"\bsonar"), ("tonal", r"\btonal"), ("chorus", r"\bchorus"),
    ("boing", r"\bboing"), ("rasp", r"\brasp"), ("snap", r"\bsnap"), ("drum", r"\bdrum"), ("hum", r"\bhum\b|\bhums\b"),
    ("pop", r"\bpop"), ("yelp", r"\byelp"), ("bleat", r"\bbleat"), ("wail", r"\bwail"), ("burst", r"\bburst"),
]
def tags_from_note(note):
    if not note: return ""
    low = note.lower()
    return ";".join(t for t, p in TAG_PATTERNS if re.search(p, low))

# ----------------------------------------------------------------------------- schema
SCHEMA = """
PRAGMA journal_mode=WAL;
DROP TABLE IF EXISTS clips; DROP TABLE IF EXISTS sound_types; DROP TABLE IF EXISTS datasets; DROP TABLE IF EXISTS species;
DROP VIEW IF EXISTS v_species_summary; DROP VIEW IF EXISTS v_clips;
CREATE TABLE species (
  species_id INTEGER PRIMARY KEY,
  scientific_name TEXT UNIQUE,
  common_name TEXT,
  taxon_group TEXT,          -- baleen whale / toothed whale / pinniped / sirenian / fish / crustacean / echinoderm / mollusc / reptile / annelid / other
  synonyms TEXT,             -- ; separated alternative names seen in sources
  watkins_species_code TEXT
);
CREATE TABLE datasets (
  dataset_id INTEGER PRIMARY KEY,
  name TEXT UNIQUE, host TEXT, url TEXT, taxa TEXT, sound_types TEXT, size TEXT, sample_rate TEXT,
  label_format TEXT, license_access TEXT, papers TEXT, survey TEXT,
  downloaded INTEGER DEFAULT 0, local_path TEXT
);
CREATE TABLE sound_types (
  sound_type_id INTEGER PRIMARY KEY,
  species_id INTEGER REFERENCES species(species_id),
  taxon_label TEXT,          -- verbatim label when species is a family/unknown
  sound_type TEXT, freq_range_hz TEXT, freq_low_hz REAL, freq_high_hz REAL, duration TEXT,
  datasets_containing_it TEXT, source_url TEXT, survey TEXT
);
CREATE TABLE clips (
  clip_id INTEGER PRIMARY KEY,
  dataset_id INTEGER REFERENCES datasets(dataset_id),
  species_id INTEGER REFERENCES species(species_id),
  taxon_label TEXT,          -- label as given by the source (family, "unidentified fish", ReefSet class, ...)
  sound_type TEXT,           -- call type if the source gives one, else keyword tags mined from notes
  file_path TEXT UNIQUE,     -- relative to project root
  sample_rate INTEGER, duration_s REAL, channels INTEGER,
  source_record_id TEXT, observation_date TEXT, location TEXT, lat REAL, lon REAL,
  quality INTEGER, note TEXT, license TEXT, source_url TEXT
);
CREATE INDEX idx_clips_species ON clips(species_id);
CREATE INDEX idx_clips_dataset ON clips(dataset_id);
CREATE INDEX idx_clips_sound ON clips(sound_type);
CREATE VIEW v_clips AS
  SELECT c.clip_id, d.name AS dataset, s.scientific_name, s.common_name, s.taxon_group, c.taxon_label,
         c.sound_type, c.file_path, c.sample_rate, c.duration_s, c.observation_date, c.location, c.quality, c.note, c.license
  FROM clips c LEFT JOIN species s USING(species_id) LEFT JOIN datasets d USING(dataset_id);
CREATE VIEW v_species_summary AS
  SELECT s.species_id, s.scientific_name, s.common_name, s.taxon_group,
         COUNT(c.clip_id) AS n_clips, ROUND(COALESCE(SUM(c.duration_s),0)/60.0,1) AS minutes,
         COUNT(DISTINCT c.dataset_id) AS n_datasets,
         (SELECT COUNT(*) FROM sound_types t WHERE t.species_id=s.species_id) AS n_sound_types
  FROM species s LEFT JOIN clips c USING(species_id) GROUP BY s.species_id ORDER BY n_clips DESC;
"""

def wav_info(path):
    try:
        i = sf.info(str(path)); return i.samplerate, round(i.frames / i.samplerate, 3), i.channels
    except Exception:
        return None, None, None

def parse_freq(text):
    """Best-effort numeric low/high Hz from strings like '50–250 Hz', '~130 kHz', '2–>200 kHz'."""
    if not text or text.strip() in ("—", "-", ""): return None, None
    t = text.replace("–", "-").replace("—", "-").replace("→", "-").replace(">", "").replace("<", "").replace("~", "")
    nums = re.findall(r"(\d+(?:[.,]\d+)?)\s*(kHz|Hz)?", t, flags=re.I)
    vals = []
    for n, unit in nums:
        v = float(n.replace(",", ""))
        if unit and unit.lower() == "khz": v *= 1000
        elif not unit and "khz" in t.lower() and v < 1000: v *= 1000
        vals.append(v)
    if not vals: return None, None
    return min(vals), max(vals)

class Builder:
    def __init__(self):
        if DB.exists(): DB.unlink()
        self.con = sqlite3.connect(DB); self.con.executescript(SCHEMA)
        self.species_ids = {}
        self.stats = collections.Counter()

    def species(self, sci, common=None, group=None, synonym=None, code=None):
        sci = canonical(sci)
        if not sci: return None
        cur = self.con.execute("SELECT species_id, common_name, taxon_group, synonyms, watkins_species_code FROM species WHERE scientific_name=?", (sci,)).fetchone()
        if cur:
            sid, c0, g0, syn0, code0 = cur
            syns = set(filter(None, (syn0 or "").split(";")))
            if synonym and synonym != sci: syns.add(synonym)
            self.con.execute("UPDATE species SET common_name=?, taxon_group=?, synonyms=?, watkins_species_code=? WHERE species_id=?",
                             (c0 or common, g0 or group, ";".join(sorted(syns)), code0 or code, sid))
            return sid
        group = group or taxon_group(sci)
        syns = synonym if (synonym and synonym != sci) else None
        cur = self.con.execute("INSERT INTO species(scientific_name, common_name, taxon_group, synonyms, watkins_species_code) VALUES (?,?,?,?,?)", (sci, common, group, syns, code))
        return cur.lastrowid

    def dataset(self, name, **kw):
        row = self.con.execute("SELECT dataset_id FROM datasets WHERE name=?", (name,)).fetchone()
        if row:
            sets = ", ".join(f"{k}=?" for k in kw); self.con.execute(f"UPDATE datasets SET {sets} WHERE dataset_id=?", (*kw.values(), row[0])); return row[0]
        cols = ["name"] + list(kw); cur = self.con.execute(f"INSERT INTO datasets({','.join(cols)}) VALUES ({','.join('?'*len(cols))})", (name, *kw.values()))
        return cur.lastrowid

    def clip(self, **kw):
        cols = list(kw)
        try:
            self.con.execute(f"INSERT INTO clips({','.join(cols)}) VALUES ({','.join('?'*len(cols))})", tuple(kw.values()))
            self.stats[kw.get("dataset_id")] += 1
        except sqlite3.IntegrityError:
            pass

    # ------------------------------------------------------------------ catalog CSVs (from literature survey)
    def load_catalog(self):
        for f in sorted(CAT.glob("datasets_*.csv")):
            for r in csv.DictReader(open(f)):
                name = r.get("dataset", "").strip()
                if not name: continue
                self.dataset(name, host=r.get("host_institution"), url=r.get("url"), taxa=r.get("species") or r.get("taxa_covered"),
                             sound_types=r.get("labeled_sound_types") or r.get("sound_types_labeled"), size=r.get("size"),
                             sample_rate=r.get("sample_rate"), label_format=r.get("label_format"), license_access=r.get("license_access"),
                             papers=r.get("papers_that_used_it") or r.get("papers_using_it"), survey=r.get("survey"))
        for f in sorted(CAT.glob("species_sounds_*.csv")):
            for r in csv.DictReader(open(f)):
                sci = r["scientific_name"].strip()
                group = r.get("group", "").strip() or None
                # family-level or unidentified rows: keep as taxon_label without a species row
                is_species = bool(re.match(r"^[A-Z][a-z]+ [a-z]+", sci)) and "spp" not in sci and "Unidentified" not in sci
                base = re.sub(r"\s*\(.*?\)", "", sci).strip()
                sid = self.species(base, common=r.get("common_name") or None, group=group) if is_species else None
                lo, hi = parse_freq(r.get("freq_range_hz", ""))
                self.con.execute("INSERT INTO sound_types(species_id, taxon_label, sound_type, freq_range_hz, freq_low_hz, freq_high_hz, duration, datasets_containing_it, source_url, survey) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 (sid, sci if not sid else (sci if sci != base else None), r.get("sound_type"), r.get("freq_range_hz"), lo, hi, r.get("duration"),
                                  r.get("datasets_containing_it"), r.get("source_paper_or_page_url") or r.get("source_url"), r.get("survey")))
        self.con.commit()

    # ------------------------------------------------------------------ Watkins
    def load_watkins(self):
        files = sorted(glob.glob(str(RAW / "watkins_full/data/*.parquet")))
        files = [f for f in files if not os.path.exists(f + ".aria2")]
        if not files: print("Watkins: no complete shards"); return
        did = self.dataset("Watkins Marine Mammal Sound Database (WMMD, \"All Cuts\")", downloaded=1, local_path="audio/watkins",
                           url="https://cis.whoi.edu/science/B/whalesounds/index.cfm (mirror: huggingface.co/datasets/ivangtorre/watkins-marine-mammal-full-cuts)")
        out = AUDIO / "watkins"
        n = 0
        for f in files:
            pf = pq.ParquetFile(f)
            for rg in range(pf.num_row_groups):
                tb = pf.read_row_group(rg)
                for r in tb.to_pylist():
                    sci = r.get("scientific_name"); disp = r.get("display_name") or ""
                    if not sci and r.get("animal") and r["animal"].get("genus"):
                        sci = r["animal"]["genus"][0].get("name")
                    common = prettify(disp) if disp else None
                    code = r.get("species_code")
                    if code in WATKINS_CODES:  # code is authoritative; fixes rows whose name/display disagree
                        sci_code, common_code = WATKINS_CODES[code]
                        if canonical(sci) != sci_code: self.stats["watkins_code_override"] += 1
                        sci, common = sci_code, common_code
                    sid = self.species(sci, common=common, synonym=r.get("scientific_name"), code=code) if sci else None
                    folder = out / slug(canonical(sci) or disp or "unknown")
                    folder.mkdir(parents=True, exist_ok=True)
                    a = r["audio"]; fname = a.get("path") or f"{r['record_number']}.wav"
                    fpath = folder / fname
                    if not fpath.exists(): fpath.write_bytes(a["bytes"])
                    sr, dur, ch = wav_info(fpath)
                    loc = r.get("location") or {}
                    locname = "; ".join(loc.get("name") or []) or None
                    coords = (loc.get("coordinates") or [{}])[0]
                    sig = r.get("signal") or {}
                    note = r.get("note")
                    self.clip(dataset_id=did, species_id=sid, taxon_label=disp or sci, sound_type=tags_from_note(note),
                              file_path=str(fpath.relative_to(ROOT)), sample_rate=sr or (r.get("sound") or {}).get("sample_rate"),
                              duration_s=dur if dur is not None else sig.get("cut_size"), channels=ch,
                              source_record_id=r.get("record_number"), observation_date=r.get("observation_date"), location=locname,
                              lat=coords.get("lat"), lon=coords.get("lon"), quality=sig.get("quality"), note=note,
                              license="Free for personal/academic use (WHOI terms)", source_url="https://cis.whoi.edu/science/B/whalesounds/")
                    n += 1
            self.con.commit(); print(f"Watkins: {os.path.basename(f)} done, total {n}")

    # ------------------------------------------------------------------ ReefSet
    # ReefSet label -> (taxon_label, scientific name or None, taxon group, sound type). Species-level labels resolved
    # from the SurfPerch paper's supplementary label table (megnov = Megaptera novaeangliae, mycbon = Mycteroperca bonaci, ...).
    REEF_MAP = {
        "bioph_megnov": ("Humpback whale", "Megaptera novaeangliae", "baleen whale", "song/call unit"),
        "bioph_midshipman": ("Plainfin midshipman", "Porichthys notatus", "fish", "hum"),
        "bioph_mycbon": ("Black grouper", "Mycteroperca bonaci", "fish", "grouper call (tonal/pulse)"),
        "bioph_epigut": ("Red hind", "Epinephelus guttatus", "fish", "grouper call"),
        "bioph_pomamb": ("Ambon damselfish", "Pomacentrus amboinensis", "fish", "pulsed call"),
        "bioph_holocentrus": ("Squirrelfish (Holocentrus spp.)", None, "fish", "grunt/staccato"),
        "bioph_damselfish": ("Damselfish (Pomacentridae)", None, "fish", "pulsed call"),
        "bioph_grouper_a": ("Grouper (Epinephelidae)", None, "fish", "grouper call type A"),
        "bioph_grouper_groan": ("Grouper (Epinephelidae)", None, "fish", "groan"),
        "bioph_dolphin": ("Dolphin (Delphinidae)", None, "toothed whale", "whistle/click"),
        "bioph_echinidae": ("Sea urchin (Echinidae)", None, "echinoderm", "grazing scrape"),
        "bioph_crackle": ("Snapping shrimp (Alpheidae)", None, "crustacean", "crackle"),
        "bioph_grazing": ("Unidentified grazer (parrotfish/urchin)", None, "fish/echinoderm", "grazing"),
        "bioph_cascading_saw": ("Unidentified reef fish", None, "fish", "cascading saw"),
        "bioph_croak": ("Unidentified reef fish", None, "fish", "croak"),
        "bioph_knock_croak_a": ("Unidentified reef fish", None, "fish", "knock-croak A"),
        "bioph_knock_croak_b": ("Unidentified reef fish", None, "fish", "knock-croak B"),
        "bioph_knock_croak_c": ("Unidentified reef fish", None, "fish", "knock-croak C"),
        "bioph_knock": ("Unidentified reef fish", None, "fish", "knock"),
        "bioph_rattle": ("Unidentified reef fish", None, "fish", "rattle"),
        "bioph_rattle_response": ("Unidentified reef fish", None, "fish", "rattle response"),
        "bioph_growl": ("Unidentified reef fish", None, "fish", "growl"),
        "bioph_low_growl": ("Unidentified reef fish", None, "fish", "low growl"),
        "bioph_pulse": ("Unidentified reef fish", None, "fish", "pulse"),
        "bioph_double_pulse": ("Unidentified reef fish", None, "fish", "double pulse"),
        "bioph_series_a": ("Unidentified reef fish", None, "fish", "pulse series A"),
        "bioph_series_b": ("Unidentified reef fish", None, "fish", "pulse series B"),
        "bioph_chatter": ("Unidentified reef fish", None, "fish", "chatter"),
        "bioph_chorus": ("Unidentified fish chorus", None, "fish", "chorus"),
        "bioph_whup": ("Unidentified reef biophony", None, None, "whup"),
        "bioph_stridulation": ("Unidentified reef invertebrate/fish", None, None, "stridulation"),
        "bioph": ("Unidentified reef biophony", None, None, "biophony (unspecified)"),
        "ambient": ("Non-biological: ambient", None, "non-biological", "ambient"),
        "anthrop_boat_engine": ("Non-biological: boat engine", None, "non-biological", "boat engine"),
        "anthrop_mechanical": ("Non-biological: mechanical", None, "non-biological", "mechanical noise"),
        "anthrop_bomb": ("Non-biological: blast fishing", None, "non-biological", "explosion"),
        "geoph_waves": ("Non-biological: waves", None, "non-biological", "waves"),
    }
    def load_reefset(self):
        base = RAW / "reefset"
        ann = list(base.rglob("reefset_annotations.json"))
        if not ann: print("ReefSet: annotations not found (zip not extracted?)"); return
        ann = ann[0]; data = json.load(open(ann))
        did = self.dataset("ReefSet v1.0 (+ SurfPerch model)", downloaded=1, local_path="audio/reefset")
        wavdir = ann.parent
        idx = {p.name: p for p in wavdir.rglob("*.wav")}
        recs = data if isinstance(data, list) else (data.get("data") or data.get("annotations") or list(data.values()))
        out = AUDIO / "reefset"; n = 0
        for r in recs:
            if not isinstance(r, dict): continue
            label = r.get("label") or r.get("Label") or ""
            fname = r.get("filename") or r.get("file_name") or r.get("Filename") or ""
            src = idx.get(fname) or idx.get(os.path.basename(fname))
            if not src: continue
            taxon, sci, group, stype = self.REEF_MAP.get(label, (label, None, None, label.replace("bioph_", "").replace("anth_", "anthropogenic:").replace("geoph_", "geophony:")))
            sid = self.species(sci, group=group) if sci else None
            folder = out / slug(label); folder.mkdir(parents=True, exist_ok=True)
            dst = folder / src.name
            if not dst.exists(): os.link(src, dst) if os.stat(src).st_dev == os.stat(folder).st_dev else dst.write_bytes(src.read_bytes())
            sr, dur, ch = wav_info(dst)
            self.clip(dataset_id=did, species_id=sid, taxon_label=taxon, sound_type=stype, file_path=str(dst.relative_to(ROOT)),
                      sample_rate=sr, duration_s=dur, channels=ch, source_record_id=str(r.get("id") or r.get("file_id") or fname),
                      location=r.get("dataset") or r.get("Dataset"), note=json.dumps({k: v for k, v in r.items() if k not in ("filename",)})[:400],
                      license="CC BY 4.0", source_url="https://zenodo.org/records/11071202")
            n += 1
        self.con.commit(); print(f"ReefSet: {n} clips")

    # ------------------------------------------------------------------ small Zenodo sets
    def load_zenodo(self):
        sets = [
            dict(dir="zenodo/southern_ocean_fish_17076825", name="Southern Ocean soniferous fishes (Prince Edward Islands) - Zenodo 17076825",
                 url="https://zenodo.org/records/17076825", license="CC BY 4.0", taxon="Unidentified benthic fish (Southern Ocean)", sci=None, group="fish",
                 stype_from_name=lambda f: f.replace(".wav", "").replace("_", " ").lower(), location="Prince Edward Islands, sub-Antarctic"),
            dict(dir="zenodo/gurnard_4972259", name="Bluefin gurnard vocalisation repertoire (Zenodo 4972259)",
                 url="https://zenodo.org/records/4972259", license="CC0", taxon="Bluefin gurnard", sci="Chelidonichthys kumu", common="Bluefin gurnard", group="fish",
                 stype_from_name=lambda f: f.replace(".wav", ""), location="Captivity, New Zealand"),
            dict(dir="zenodo/french_polynesia_12570714", name="Marine sounds below 2 kHz from French Polynesia (Zenodo 12570714)",
                 url="https://zenodo.org/records/12570714", license="CC BY 4.0", taxon="Unidentified fish (French Polynesia reef, <2 kHz)", sci=None, group="fish",
                 stype_from_name=None, location="French Polynesia"),
        ]
        for s in sets:
            src = RAW / s["dir"]
            if not src.exists(): continue
            did = self.dataset(s["name"], url=s["url"], license_access=s["license"], downloaded=1, local_path=f"audio/{pathlib.Path(s['dir']).name}", taxa=s["taxon"], survey="direct_download")
            sid = self.species(s["sci"], common=s.get("common"), group=s["group"]) if s.get("sci") else None
            out = AUDIO / pathlib.Path(s["dir"]).name; n = 0
            for f in sorted(src.rglob("*")):
                if f.suffix.lower() != ".wav": continue
                rel = f.relative_to(src)
                stype = s["stype_from_name"](f.name) if s["stype_from_name"] else str(rel.parent).split("/")[-1] if str(rel.parent) != "." else "unspecified"
                if s["stype_from_name"] is None:  # French Polynesia: folder = sound-type code from the identification key
                    parts = [p for p in rel.parts[:-1] if p != "sounds_below2kHz_French_Polynesia"]
                    stype = " / ".join(parts) if parts else "unspecified"
                dst = out / slug(stype) / f.name; dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists(): dst.write_bytes(f.read_bytes())
                sr, dur, ch = wav_info(dst)
                self.clip(dataset_id=did, species_id=sid, taxon_label=s["taxon"], sound_type=stype, file_path=str(dst.relative_to(ROOT)),
                          sample_rate=sr, duration_s=dur, channels=ch, source_record_id=str(rel), location=s["location"],
                          license=s["license"], source_url=s["url"])
                n += 1
            self.con.commit(); print(f"{s['name']}: {n} clips")

    # ------------------------------------------------------------------ ToadFishFinder (optional)
    def load_toadfish(self):
        src = RAW / "toadfish"
        wavs = list(src.rglob("*.wav")) if src.exists() else []
        if not wavs: return
        did = self.dataset("ToadFishFinder classifier v4 call catalog", downloaded=1, local_path="audio/toadfish")
        sid = self.species("Opsanus tau", common="Oyster toadfish", group="fish")
        out = AUDIO / "toadfish"; n = 0
        for f in wavs:
            rel = str(f.relative_to(src)).lower()
            is_toad = "bwhistle" in rel
            stype = "boatwhistle" if is_toad else "other/noise"
            dst = out / ("boatwhistle" if is_toad else "other") / f.name; dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists(): os.link(f, dst)
            sr, dur, ch = wav_info(dst)
            self.clip(dataset_id=did, species_id=sid if is_toad else None, taxon_label="Oyster toadfish" if is_toad else "non-toadfish (noise/other)",
                      sound_type=stype, file_path=str(dst.relative_to(ROOT)), sample_rate=sr, duration_s=dur, channels=ch,
                      source_record_id=str(f.relative_to(src)), location="Pamlico Sound, North Carolina", license="CC0", source_url="https://zenodo.org/records/8225808")
            n += 1
        self.con.commit(); print(f"ToadFish: {n} clips")


    # ------------------------------------------------------------------ Orcasound Pod.Cast labeled SRKW calls
    def load_orcasound(self):
        base = RAW / "orcasound"
        tsvs = ["podcast2.tsv", "podcast3.tsv", "test.tsv"]
        if not base.exists(): return
        did = self.dataset("Orcasound open data (streaming-orcasound-net, archive-orcasound-net, acoustic-sandbox / Pod.Cast)", downloaded=1, local_path="audio/orcasound",
                           url="https://github.com/orcasound/orcadata/wiki/Pod.Cast-data-archive (s3://acoustic-sandbox/labeled-data/detection/)")
        sid = self.species("Orcinus orca", common="Killer whale", group="toothed whale")
        out = AUDIO / "orcasound" / "SRKW_call"; out.mkdir(parents=True, exist_ok=True)
        wavidx = {p.name: p for p in base.rglob("*.wav")}   # tarballs use different internal layouts; index by basename
        n = 0
        for tsv in tsvs:
            tp = base / tsv
            if not tp.exists(): continue
            for r in csv.DictReader(open(tp), delimiter="\t"):
                fname = r.get("filename") or r.get("wav_filename")
                src = wavidx.get(fname)
                if not src: continue
                start, dur = float(r["start"]), float(r["duration_s"])
                if dur < 0.05: continue  # placeholder row for negative-only files
                dst = out / f"{pathlib.Path(fname).stem}_{start:08.3f}.wav"
                if not dst.exists():
                    try:
                        info = sf.info(str(src)); sr = info.samplerate
                        a, _ = sf.read(str(src), start=int(start * sr), frames=int(dur * sr), dtype="int16")
                        if len(a) == 0: continue
                        sf.write(str(dst), a, sr, subtype="PCM_16")
                    except Exception as e:
                        print("orcasound cut failed", fname, e); continue
                sr, d, ch = wav_info(dst)
                self.clip(dataset_id=did, species_id=sid, taxon_label="Southern Resident killer whale (SRKW)", sound_type="call (pulsed call/whistle, unspecified)",
                          file_path=str(dst.relative_to(ROOT)), sample_rate=sr, duration_s=d, channels=ch,
                          source_record_id=f"{fname}@{start}", observation_date=r.get("date"), location=r.get("location", "").replace("_", " ") + ", Salish Sea (Orcasound Lab hydrophone)",
                          lat=48.5583, lon=-123.1735, note=f"{r.get('data_source')} label={r.get('label')}; segment cut from {fname}",
                          license="CC BY-NC-SA 4.0 (Orcasound)", source_url="https://registry.opendata.aws/orcasound/")
                n += 1
        self.con.commit(); print(f"Orcasound: {n} labeled call clips")


    # ------------------------------------------------------------------ Cornell/Marinexplore Whale Detection Challenge (Kaggle 2013) via the
    # timeseriesclassification.com "RightWhaleCalls" mirror: 2-s clips @ 2 kHz, label 1 = North Atlantic right whale upcall, 0 = noise
    def load_right_whale(self):
        base = RAW / "right_whale_calls"
        files = [(base / "RightWhaleCalls_TRAIN.ts", "train"), (base / "RightWhaleCalls_TEST.ts", "test")]
        if not any(f.exists() for f, _ in files): return
        import numpy as np
        did = self.dataset("Marinexplore/Cornell Whale Detection Challenge (Kaggle 2013)", downloaded=1, local_path="audio/right_whale_calls",
                           url="https://www.kaggle.com/competitions/whale-detection-challenge/data (mirror: https://www.timeseriesclassification.com/description.php?Dataset=RightWhaleCalls)")
        sid = self.species("Eubalaena glacialis", common="North Atlantic right whale", group="baleen whale")
        out = AUDIO / "right_whale_calls"; n = 0
        for f, split in files:
            if not f.exists(): continue
            i = 0
            for line in open(f):
                if line.startswith(("#", "@")) or not line.strip(): continue
                vals, lab = line.rsplit(":", 1); lab = lab.strip(); i += 1
                is_call = lab == "1"
                folder = out / ("upcall" if is_call else "noise"); folder.mkdir(parents=True, exist_ok=True)
                dst = folder / f"rwc_{split}_{i:05d}.wav"
                if not dst.exists():
                    a = np.array(vals.split(","), dtype=np.float64)
                    if np.abs(a).max() <= 1.0:           # mirror stores float samples in [-1, 1]; fixed global scale keeps relative loudness
                        a = np.clip(a * 32768.0, -32768, 32767)
                    sf.write(str(dst), a.astype(np.int16), 2000, subtype="PCM_16")
                sr, dur, ch = wav_info(dst)
                self.clip(dataset_id=did, species_id=sid if is_call else None,
                          taxon_label="North Atlantic right whale" if is_call else "noise (no right whale; ambient/ship/anthropogenic)",
                          sound_type="upcall" if is_call else "noise", file_path=str(dst.relative_to(ROOT)), sample_rate=sr, duration_s=dur, channels=ch,
                          source_record_id=f"{split}:{i}", location="Massachusetts Bay / Cape Cod (Cornell MARU buoys)",
                          note=f"Kaggle whale-detection-challenge {split} split via timeseriesclassification.com mirror; label={lab}",
                          license="Kaggle competition rules (research use)", source_url="https://www.kaggle.com/competitions/whale-detection-challenge")
                n += 1
        self.con.commit(); print(f"RightWhaleCalls: {n} clips")


    # ------------------------------------------------------------------ BEANS "hiceas" minke boing detection set (HICEAS 2017 towed array, NOAA PIFSC)
    def load_hiceas(self):
        base = RAW / "beans_hiceas"
        if not (base / "wav").exists(): return
        did = self.dataset("BEANS benchmark (earthspecies)", downloaded=1, local_path="audio/hiceas_minke",
                           url="https://github.com/earthspecies/beans (https://storage.googleapis.com/ml-bioacoustics-datasets/hiceas_1-20_minke-detection.zip)")
        sid = self.species("Balaenoptera acutorostrata", common="Minke whale", group="baleen whale")
        out = AUDIO / "hiceas_minke"; n = 0
        for split in ("train", "valid", "test"):
            f = base / f"{split}.jsonl"
            if not f.exists(): continue
            for line in open(f):
                r = json.loads(line); src = base / "wav" / os.path.basename(r["path"])
                if not src.exists(): continue
                anns = r.get("annotations") or []
                if anns:
                    info = sf.info(str(src)); sr = info.samplerate
                    for k, a in enumerate(anns):
                        st, ed = float(a["st"]), float(a["ed"])
                        dst = out / "boing" / f"{src.stem}_{st:06.2f}.wav"; dst.parent.mkdir(parents=True, exist_ok=True)
                        if not dst.exists():
                            x, _ = sf.read(str(src), start=int(st * sr), frames=int((ed - st) * sr), dtype="int16")
                            if len(x) == 0: continue
                            sf.write(str(dst), x, sr, subtype="PCM_16")
                        sr2, dur, ch = wav_info(dst)
                        self.clip(dataset_id=did, species_id=sid, taxon_label="Minke whale", sound_type="boing", file_path=str(dst.relative_to(ROOT)),
                                  sample_rate=sr2, duration_s=dur, channels=ch, source_record_id=f"{split}:{src.name}@{st}", observation_date=src.stem.split("_")[1] if "_" in src.stem else None,
                                  location="Hawaiian EEZ (HICEAS 2017 towed array)", note=f"BEANS hiceas {split}; label={a.get('label')}",
                                  license="NOAA public domain (via BEANS)", source_url="https://github.com/earthspecies/beans"); n += 1
                else:
                    dst = out / "noise" / src.name; dst.parent.mkdir(parents=True, exist_ok=True)
                    if not dst.exists(): os.link(src, dst)
                    sr2, dur, ch = wav_info(dst)
                    self.clip(dataset_id=did, species_id=None, taxon_label="noise (no minke boing; towed-array ambient)", sound_type="noise", file_path=str(dst.relative_to(ROOT)),
                              sample_rate=sr2, duration_s=dur, channels=ch, source_record_id=f"{split}:{src.name}", observation_date=src.stem.split("_")[1] if "_" in src.stem else None,
                              location="Hawaiian EEZ (HICEAS 2017 towed array)", note=f"BEANS hiceas {split}; no annotations",
                              license="NOAA public domain (via BEANS)", source_url="https://github.com/earthspecies/beans"); n += 1
        self.con.commit(); print(f"HICEAS minke: {n} clips")


    # ------------------------------------------------------------------ DCLDE 2027 killer whale ecotype dataset (NOAA NCEI GCS bucket), size-capped subset
    # Annotations.csv gives per-file bounding boxes (FileBeginSec/FileEndSec, Low/HighFreqHz) with ClassSpecies (KW/HW/AB/UndBio) and Ecotype.
    # raw/dclde2027_kw/selected_files.csv lists which sound files were downloaded (see catalog/survey_registries_endpoints.md for the full 1.6 TB set).
    DCLDE_ECO = {"SRKW": "Southern Resident killer whale (SRKW)", "NRKW": "Northern Resident killer whale (NRKW)", "TKW": "Bigg's / transient killer whale (TKW)",
                 "OKW": "Offshore killer whale (OKW)", "SAR": "Southern Alaska Resident killer whale (SAR)"}
    def load_dclde_kw(self):
        base = RAW / "dclde2027_kw"
        ann_path = base / "Annotations.csv"
        if not ann_path.exists(): return
        did = self.dataset("DCLDE 2027 (ex-2026) killer whale dataset", downloaded=1, local_path="audio/dclde2027_kw",
                           url="https://doi.org/10.25921/15ey-mh50 (gs://noaa-passive-bioacoustic/dclde/2027/dclde_2027_killer_whales/)")
        sid_kw = self.species("Orcinus orca", common="Killer whale", group="toothed whale")
        sid_hw = self.species("Megaptera novaeangliae", common="Humpback whale", group="baleen whale")
        wavidx = {p.name: p for p in base.rglob("*") if p.suffix.lower() in (".flac", ".wav") and not (p.with_name(p.name + ".aria2")).exists()}
        out = AUDIO / "dclde2027_kw"; n = 0; skipped = 0
        by_file = collections.defaultdict(list)
        with open(ann_path, newline="") as f:
            for r in csv.DictReader(f):
                if r["Soundfile"] in wavidx: by_file[r["Soundfile"]].append(r)
        PAD = 0.1
        for fname, rows in by_file.items():
            src = wavidx[fname]
            try: info = sf.info(str(src)); sr = info.samplerate; nfr = info.frames
            except Exception as e: print("dclde unreadable", fname, e); continue
            for r in rows:
                cls, eco = r["ClassSpecies"], (r.get("Ecotype") or "NA")
                if cls == "KW":
                    sid, taxon = sid_kw, self.DCLDE_ECO.get(eco, "Killer whale (ecotype unknown)")
                    folder = "KW_" + (eco if eco in self.DCLDE_ECO else "unknown")
                elif cls == "HW": sid, taxon, folder = sid_hw, "Humpback whale", "HW"
                elif cls == "AB": sid, taxon, folder = None, "abiotic (non-biological)", "abiotic"
                else: sid, taxon, folder = None, "undetermined biological", "undetermined_bio"
                try: b, e = float(r["FileBeginSec"]), float(r["FileEndSec"])
                except ValueError: continue
                b0, e0 = max(0.0, b - PAD), e + PAD
                start, frames = int(b0 * sr), int((e0 - b0) * sr)
                if frames <= 0 or start >= nfr: skipped += 1; continue
                dst = out / folder / f"{pathlib.Path(fname).stem}_{b:09.3f}.wav"; dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    try:
                        x, _ = sf.read(str(src), start=start, frames=min(frames, nfr - start), dtype="int16")
                        if x.ndim > 1: x = x[:, 0]           # multichannel arrays: keep channel 1
                        if len(x) == 0: skipped += 1; continue
                        sf.write(str(dst), x, sr, subtype="PCM_16")
                    except Exception as ex: print("dclde cut failed", fname, ex); skipped += 1; continue
                sr2, dur, ch = wav_info(dst)
                stype = {"KW": "killer whale call/click/whistle (box)", "HW": "humpback call (box)", "AB": "abiotic", "UndBio": "undetermined biological"}.get(cls, cls)
                self.clip(dataset_id=did, species_id=sid, taxon_label=taxon, sound_type=stype, file_path=str(dst.relative_to(ROOT)),
                          sample_rate=sr2, duration_s=dur, channels=ch, source_record_id=f"{fname}@{b}-{e}", observation_date=(r.get("UTC") or "")[:10] or None,
                          location=f"{r.get('Provider')} / {r.get('Dataset')} (NE Pacific)",
                          note=f"DCLDE2027 {r.get('AnnotationLevel')} box {r.get('LowFreqHz')}-{r.get('HighFreqHz')} Hz; KW_certain={r.get('KW_certain')}; pad={PAD}s",
                          license="CC BY 4.0 per bucket license file (Sci Data paper states CC BY-NC-ND 4.0)", source_url="https://doi.org/10.25921/15ey-mh50")
                n += 1
            if n % 5000 == 0: self.con.commit()
        self.con.commit(); print(f"DCLDE 2027 KW: {n} clips from {len(by_file)} files (skipped {skipped})")


    # ------------------------------------------------------------------ AAD AcousticTrends_BlueFinLibrary (IWC-SORP Antarctic blue & fin whale annotated library)
    # Site folders each hold wav/ (250-2000 Hz, ~1 h files) plus Raven selection tables, one per call type; the call type is encoded in the table filename.
    AAD_TYPES = [  # (regex on table filename, scientific name, common name, sound_type)
        (r"ant[-_. ]?a", "Balaenoptera musculus intermedia", "Antarctic blue whale", "Bm-Ant-A (Z-call unit A)"),
        (r"ant[-_. ]?b", "Balaenoptera musculus intermedia", "Antarctic blue whale", "Bm-Ant-B (Z-call unit B)"),
        (r"ant[-_. ]?z", "Balaenoptera musculus intermedia", "Antarctic blue whale", "Bm-Ant-Z (Z-call)"),
        (r"bm[-_. ]?d\b|bm[-_. ]?dcalls|bm\.d\.|_d\.txt|bmd\.", "Balaenoptera musculus intermedia", "Antarctic blue whale", "Bm-D (D-call)"),
        (r"20 ?plus", "Balaenoptera physalus", "Fin whale", "Bp-20Plus (20 Hz pulse with high-frequency component)"),
        (r"20 ?hz|bp20(?!plus)", "Balaenoptera physalus", "Fin whale", "Bp-20Hz (20 Hz pulse)"),
        (r"downsweep|dwnswp|dswp|fin\.ds|bp\.ds|bp-ds|bp_ds", "Balaenoptera physalus", "Fin whale", "Bp-Downsweep (40 Hz downsweep)"),
        (r"highercall", "Balaenoptera physalus", "Fin whale", "Bp higher-frequency call"),
        (r"minke|bioduck", "Balaenoptera bonaerensis", "Antarctic minke whale", "bio-duck / downsweep"),
        (r"hump", "Megaptera novaeangliae", "Humpback whale", "call"),
        (r"unid|unknown|swi|tonal30|backbeat|recurrent", None, None, "unidentified call"),
    ]
    def load_aad_bluefin(self):
        base = RAW / "aad_bluefin"
        if not base.exists(): return
        did = self.dataset("AcousticTrends_BlueFinLibrary (IWC-SORP/SOOS Acoustic Trends annotated library)", downloaded=1, local_path="audio/aad_bluefin",
                           url="https://data.aad.gov.au/metadata/AcousticTrends_BlueFinLibrary (DOI 10.26179/5e6056035c01b)")
        out = AUDIO / "aad_bluefin"; n = 0; skipped = 0; PAD = 0.25
        sid_cache = {}
        for table in sorted(base.rglob("*.txt")):
            if "/wav/" in str(table) or table.name.lower() in ("readme.txt", "license.txt", "readme"): continue
            site = table.relative_to(base).parts[0]
            wavdir = base / site / "wav"
            if not wavdir.exists(): continue
            name = table.name.lower()
            match = next(((sci, common, st) for rx, sci, common, st in self.AAD_TYPES if re.search(rx, name)), None)
            if not match: continue
            sci, common, stype = match
            sid = None
            if sci:
                sid = sid_cache.get(sci) or self.species(sci, common=common, group="baleen whale"); sid_cache[sci] = sid
            try: lines = table.read_text(errors="replace").splitlines()
            except Exception: continue
            if not lines or "\t" not in lines[0]: continue
            hdr = lines[0].split("\t"); H = {h.strip().lower(): i for i, h in enumerate(hdr)}
            col = lambda *names: next((H[k] for k in names if k in H), None)
            c_file, c_bs, c_es = col("begin file"), col("beg file samp (samples)", "begin file samp (samples)"), col("end file samp (samples)")
            c_bt, c_et, c_off = col("begin time (s)"), col("end time (s)"), col("file offset (s)")
            c_lo, c_hi = col("low freq (hz)"), col("high freq (hz)")
            if c_file is None or (c_bs is None and c_off is None): skipped += 1; continue
            info_cache = {}
            for ln in lines[1:]:
                f = ln.split("\t")
                if len(f) <= max(c_file, c_bs or 0, c_es or 0): continue
                wav = wavdir / f[c_file].strip()
                if not wav.exists(): skipped += 1; continue
                try:
                    if wav not in info_cache: info_cache[wav] = sf.info(str(wav))
                    info = info_cache[wav]; sr = info.samplerate
                    if c_bs is not None and f[c_bs].strip():
                        b_s, e_s = int(float(f[c_bs])), int(float(f[c_es]))
                    else:
                        off = float(f[c_off]); dur = float(f[c_et]) - float(f[c_bt]); b_s, e_s = int(off * sr), int((off + dur) * sr)
                    b_s = max(0, b_s - int(PAD * sr)); e_s = min(info.frames, e_s + int(PAD * sr))
                    if e_s <= b_s: skipped += 1; continue
                    dst = out / slug(site) / slug(stype.split(" (")[0]) / f"{wav.stem}_{b_s:09d}.wav"; dst.parent.mkdir(parents=True, exist_ok=True)
                    if not dst.exists():
                        x, _ = sf.read(str(wav), start=b_s, frames=e_s - b_s, dtype="int16")
                        if x.ndim > 1: x = x[:, 0]
                        sf.write(str(dst), x, sr, subtype="PCM_16")
                    sr2, dur2, ch = wav_info(dst)
                    lo = f[c_lo] if c_lo is not None and len(f) > c_lo else ""; hi = f[c_hi] if c_hi is not None and len(f) > c_hi else ""
                    self.clip(dataset_id=did, species_id=sid, taxon_label=common or "unidentified (Antarctic low-frequency)", sound_type=stype,
                              file_path=str(dst.relative_to(ROOT)), sample_rate=sr2, duration_s=dur2, channels=ch,
                              source_record_id=f"{site}/{table.name}#{f[0]}", observation_date=wav.stem[:8] if wav.stem[:8].isdigit() else None,
                              location=f"{site} (Southern Ocean)", note=f"Raven selection {lo}-{hi} Hz; pad={PAD}s",
                              license="CC BY 4.0", source_url="https://data.aad.gov.au/metadata/AcousticTrends_BlueFinLibrary")
                    n += 1
                except Exception as ex:
                    skipped += 1
            self.con.commit()
        print(f"AAD BlueFin: {n} clips (skipped {skipped})")


    # ------------------------------------------------------------------ Cornell/Marinexplore Whale Detection Challenge, FULL 30,000-clip training set
    # via HF monster-monash/CornellWhaleChallenge (X: 30000x1x4000 int16-valued float32 @ 2 kHz; y: 1 = NARW upcall). Supersedes the 12,896 mirror subset.
    def load_cornell_full(self):
        base = RAW / "cornell_whale_full"
        xp, yp = base / "CornellWhaleChallenge_X.npy", base / "CornellWhaleChallenge_y.npy"
        if not (xp.exists() and yp.exists()): return
        import numpy as np
        X = np.load(xp, mmap_mode="r"); y = np.load(yp)
        folds = {}
        for k in range(5):
            fp = base / f"test_indices_fold_{k}.txt"
            if fp.exists():
                for i in fp.read_text().split(): folds[int(i)] = k
        did = self.dataset("Marinexplore/Cornell Whale Detection Challenge (Kaggle 2013)", downloaded=1, local_path="audio/cornell_whale",
                           url="https://www.kaggle.com/competitions/whale-detection-challenge/data (full train set via https://huggingface.co/datasets/monster-monash/CornellWhaleChallenge)")
        sid = self.species("Eubalaena glacialis", common="North Atlantic right whale", group="baleen whale")
        out = AUDIO / "cornell_whale"; (out / "upcall").mkdir(parents=True, exist_ok=True); (out / "noise").mkdir(parents=True, exist_ok=True)
        n = 0
        for i in range(X.shape[0]):
            is_call = int(y[i]) == 1
            dst = out / ("upcall" if is_call else "noise") / f"cwc_{i:05d}.wav"
            if not dst.exists():
                a = np.asarray(X[i]).reshape(-1)
                sf.write(str(dst), np.clip(a, -32768, 32767).astype(np.int16), 2000, subtype="PCM_16")
            self.clip(dataset_id=did, species_id=sid if is_call else None,
                      taxon_label="North Atlantic right whale" if is_call else "noise (no right whale; ambient/ship/anthropogenic)",
                      sound_type="upcall" if is_call else "noise", file_path=str(dst.relative_to(ROOT)), sample_rate=2000, duration_s=2.0, channels=1,
                      source_record_id=f"train:{i}", location="Massachusetts Bay / Cape Cod (Cornell MARU buoys)",
                      note=f"Kaggle whale-detection-challenge train clip {i}; MONSTER cv fold={folds.get(i)}; label={int(y[i])}",
                      license="Copyright 2011 Cornell University (Kaggle competition rules, research use)", source_url="https://www.kaggle.com/competitions/whale-detection-challenge")
            n += 1
            if n % 5000 == 0: self.con.commit(); print(f"  cornell {n}")
        self.con.commit(); print(f"Cornell full: {n} clips")

    # ------------------------------------------------------------------ exports
    def export(self):
        for name, q in [("species", "SELECT * FROM v_species_summary"), ("clips", "SELECT * FROM v_clips"),
                        ("sound_types", "SELECT t.*, s.scientific_name, s.common_name FROM sound_types t LEFT JOIN species s USING(species_id)"),
                        ("datasets", "SELECT * FROM datasets")]:
            cur = self.con.execute(q); cols = [d[0] for d in cur.description]
            with open(CAT / f"{name}.csv", "w", newline="") as f:
                w = csv.writer(f); w.writerow(cols); w.writerows(cur.fetchall())
        print("exported CSVs to", CAT)

if __name__ == "__main__":
    b = Builder()
    b.load_catalog()
    b.load_watkins()
    b.load_reefset()
    b.load_zenodo()
    b.load_toadfish()
    b.load_orcasound()
    b.load_cornell_full()   # full 30k set; load_right_whale() (12,896 mirror subset) is superseded
    b.load_hiceas()
    skip = set(os.environ.get("SKIP_LOADERS", "").split(","))   # e.g. SKIP_LOADERS=dclde_kw,aad_bluefin while those downloads are incomplete
    if "dclde_kw" not in skip: b.load_dclde_kw()
    if "aad_bluefin" not in skip: b.load_aad_bluefin()
    b.export()
    for row in b.con.execute("SELECT s.taxon_group, COUNT(DISTINCT c.species_id), COUNT(*) FROM clips c LEFT JOIN species s USING(species_id) GROUP BY s.taxon_group"):
        print(row)
    print("total clips", b.con.execute("SELECT COUNT(*) FROM clips").fetchone()[0],
          "species", b.con.execute("SELECT COUNT(*) FROM species").fetchone()[0],
          "sound types", b.con.execute("SELECT COUNT(*) FROM sound_types").fetchone()[0],
          "datasets", b.con.execute("SELECT COUNT(*) FROM datasets").fetchone()[0])
