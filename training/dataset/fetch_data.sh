#!/usr/bin/env bash
# Re-download the raw sources (~20 GB) and rebuild audio/ + marine_sounds.sqlite.
# Needs: python3 (pip install huggingface_hub pyarrow soundfile), aria2c, unzip, tar.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p raw/watkins_full/data raw/reefset raw/toadfish raw/orcasound raw/zenodo

# 1. Watkins full cuts (HF mirror, 10.6 GB, 9 parquet shards). Use many connections: HF CDN is slow single-stream.
B=https://huggingface.co/datasets/ivangtorre/watkins-marine-mammal-full-cuts/resolve/main
: > /tmp/watkins_urls.txt
for i in 0 1 2 3 4 5 6 7 8; do printf '%s/data/train-0000%s-of-00009.parquet\n  out=data/train-0000%s-of-00009.parquet\n' "$B" $i $i >> /tmp/watkins_urls.txt; done
aria2c -i /tmp/watkins_urls.txt -d raw/watkins_full -x 16 -s 16 -j 3 -c --file-allocation=none

# 2. ReefSet v1.0 (1.6 GB, CC BY 4.0)
aria2c -d raw/reefset -o ReefSet_v1.0.zip -x 16 -s 16 -c --file-allocation=none "https://zenodo.org/api/records/11071202/files/ReefSet_v1.0.zip/content"
(cd raw/reefset && unzip -qo ReefSet_v1.0.zip)

# 3. ToadFishFinder clips (2 GB, CC0)
aria2c -d raw/toadfish -o wavclips_TFv4.zip -x 16 -s 16 -c --file-allocation=none "https://zenodo.org/api/records/8225808/files/wavclips_TFv4.zip/content"
(cd raw/toadfish && unzip -qo wavclips_TFv4.zip)

# 4. Orcasound Pod.Cast labeled rounds (S3, ~770 MB, CC BY-NC-SA)
O=https://acoustic-sandbox.s3.amazonaws.com/labeled-data/detection
for k in train/OrcasoundLab07052019_PodCastRound2.tar.gz train/OrcasoundLab09272017_PodCastRound3.tar.gz test/OrcasoundLab09272017_Test.tar.gz train/podcast2.tsv train/podcast3.tsv train/test.tsv; do
  aria2c -d raw/orcasound -o "$(basename $k)" -x 8 -s 8 -c --file-allocation=none "$O/$k"
done
(cd raw/orcasound && for t in *.tar.gz; do tar xzf "$t"; done)

# 5. Small Zenodo fish sets
mkdir -p raw/zenodo/southern_ocean_fish_17076825 raw/zenodo/gurnard_4972259 raw/zenodo/french_polynesia_12570714
curl -sL -o raw/zenodo/southern_ocean_fish_17076825/DRUM_CALL.wav "https://zenodo.org/api/records/17076825/files/5756.210426052958_DRUM_CALLx15_AMPLIFIED.wav/content"
curl -sL -o raw/zenodo/southern_ocean_fish_17076825/GRUNT_SERIES.wav "https://zenodo.org/api/records/17076825/files/5756.220103212958_GRUNT_SERIESx20_AMPLIFIED.wav/content"
curl -sL -o raw/zenodo/southern_ocean_fish_17076825/POPS.wav "https://zenodo.org/api/records/17076825/files/5756.211227012958_POPSx15_AMPLIFIED.wav/content"
curl -sL -o raw/zenodo/gurnard_4972259/growl.wav "https://zenodo.org/api/records/4972259/files/craigsgrowl-gurnard.wav/content"
curl -sL -o raw/zenodo/gurnard_4972259/grunt.wav "https://zenodo.org/api/records/4972259/files/craigsgrunt-gurnard.wav/content"
curl -sL -o raw/zenodo/french_polynesia_12570714/sounds.zip "https://zenodo.org/api/records/12570714/files/sounds_below2kHz_French_Polynesia.zip/content"
python3 - <<'PY'
# zip has non-UTF-8 (cp437) filenames; plain unzip chokes on them
import zipfile, os
os.chdir("raw/zenodo/french_polynesia_12570714"); z = zipfile.ZipFile("sounds.zip")
for info in z.infolist():
    name = info.filename
    if not (info.flag_bits & 0x800):
        try: name = name.encode('cp437').decode('utf-8')
        except Exception: name = name.encode('cp437').decode('latin-1', 'replace')
    name = name.replace('�', '_')
    if info.is_dir(): os.makedirs(name, exist_ok=True); continue
    os.makedirs(os.path.dirname(name) or '.', exist_ok=True); open(name, 'wb').write(z.read(info))
os.remove("sounds.zip")
PY

# 6. Cornell/Marinexplore right whale upcall challenge (Kaggle 2013), full 30,000-clip train set via HF monster-monash mirror (480 MB, no login)
python3 - <<'PY'
from huggingface_hub import hf_hub_download
for f in ["CornellWhaleChallenge_X.npy", "CornellWhaleChallenge_y.npy"] + [f"test_indices_fold_{i}.txt" for i in range(5)]:
    hf_hub_download("monster-monash/CornellWhaleChallenge", f, repo_type="dataset", local_dir="raw/cornell_whale_full")
PY

# 7. BEANS "hiceas" minke boing detection set (1.4 GB, NOAA public domain)
mkdir -p raw/beans_hiceas
aria2c -d raw/beans_hiceas -o hiceas_1-20_minke-detection.zip -x 16 -s 16 -c --file-allocation=none "https://storage.googleapis.com/ml-bioacoustics-datasets/hiceas_1-20_minke-detection.zip"
(cd raw/beans_hiceas && unzip -qo hiceas_1-20_minke-detection.zip)

# 8. DCLDE 2027 killer whale ecotype set: annotation table + the size-capped audio subset listed in raw/dclde2027_kw/aria_urls.txt (23 GB of the 1.6 TB set)
mkdir -p raw/dclde2027_kw
curl -s -o raw/dclde2027_kw/Annotations.csv "https://storage.googleapis.com/noaa-passive-bioacoustic/dclde/2027/dclde_2027_killer_whales/Annotations.csv"
cp scripts/dclde2027_selected_urls.txt raw/dclde2027_kw/aria_urls.txt
aria2c -i raw/dclde2027_kw/aria_urls.txt -d raw/dclde2027_kw -x 8 -s 8 -j 6 -c --file-allocation=none

# 9. Antarctic blue/fin whale annotated library (AAD, 13 GB, CC BY 4.0). Needs temporary S3 credentials: request them at
#    https://data.aad.gov.au/eds/5091/download (enter an email; AADC emails an access key / secret key), then:
#    echo '{"endpoint":"https://transfer.data.aad.gov.au","access":"<KEY>","secret":"<SECRET>","bucket":"aadc-datasets","prefix":"AcousticTrends_BlueFinLibrary/"}' > aad_creds.json
#    AAD_CREDS=aad_creds.json python3 scripts/download_aad_bluefin.py

# 10. Build
python3 scripts/build_db.py
