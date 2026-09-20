# whale-clips build

sr=8000 Hz, win=2.0 s, max_watkins=3

| source | step | n |
|---|---|---:|
| kaggle | labelled clips in train.csv | 30,000 |
| kaggle | clips present on disk | 30,000 |
| dclde | call boxes in catalogue | 97,880 |
| dclde | dropped: undetermined biological | 837 |
| dclde | dropped: annotator flagged killer whale as uncertain | 341 |
| dclde | per-call UTC matched from Annotations.csv | 96,702 |
| dclde | boxes whose original recording is on disk | 96,702 |
| dclde | boxes at sites with a published position | 9,400 |
| dclde | negative windows sampled between annotations (<= 3 per file) | 5,463 |
| aad | call clips with audio on disk | 107,948 |
| aad | dropped: unidentified call (no species) | 31,047 |
| aad | per-call UTC matched from Raven tables | 76,901 |
| all | source clips to window | 220,291 |
| all | original recordings to cut windows from | 1,964 |
| all | source clips unreadable (skipped) | 12 |
| all | clips written (2 s, 8000 Hz, mono 16-bit) | 222,999 |

## clips per source x label

| source   |   label | common_name                  |   clips |
|:---------|--------:|:-----------------------------|--------:|
| aad      |       1 | Antarctic blue whale         |   48006 |
| aad      |       1 | Antarctic minke whale        |    1424 |
| aad      |       1 | Fin whale                    |   27263 |
| aad      |       1 | Humpback whale               |     208 |
| dclde    |       0 | noise                        |    5775 |
| dclde    |       1 | Humpback whale               |   69265 |
| dclde    |       1 | Killer whale                 |   27113 |
| kaggle   |       0 | noise                        |   22973 |
| kaggle   |       1 | North Atlantic right whale   |    7027 |
| watkins  |       1 | Atlantic spotted dolphin     |     248 |
| watkins  |       1 | Atlantic white-sided dolphin |     633 |
| watkins  |       1 | Beluga                       |     123 |
| watkins  |       1 | Blue whale                   |       9 |
| watkins  |       1 | Bowhead whale                |     127 |
| watkins  |       1 | Clymene dolphin              |     343 |
| watkins  |       1 | Commerson's dolphin          |       1 |
| watkins  |       1 | Common bottlenose dolphin    |     125 |
| watkins  |       1 | Common dolphin               |     980 |
| watkins  |       1 | Common/dwarf minke whale     |      36 |
| watkins  |       1 | Dall's porpoise              |      55 |
| watkins  |       1 | Dusky dolphin                |      68 |
| watkins  |       1 | False killer whale           |     551 |
| watkins  |       1 | Fin whale                    |    1036 |
| watkins  |       1 | Fraser's dolphin             |     158 |
| watkins  |       1 | Gray whale                   |      52 |
| watkins  |       1 | Harbour porpoise             |      42 |
| watkins  |       1 | Humpback whale               |     905 |
| watkins  |       1 | Killer whale                 |    1290 |
| watkins  |       1 | Long-beaked common dolphin   |      75 |
| watkins  |       1 | Long-finned pilot whale      |    1265 |
| watkins  |       1 | Melon-headed whale           |     183 |
| watkins  |       1 | Narwhal                      |      72 |
| watkins  |       1 | North Atlantic right whale   |     440 |
| watkins  |       1 | Pantropical spotted dolphin  |     778 |
| watkins  |       1 | Risso's dolphin              |     377 |
| watkins  |       1 | Rough-toothed dolphin        |     100 |
| watkins  |       1 | Short-finned pilot whale     |     644 |
| watkins  |       1 | Sperm whale                  |    1789 |
| watkins  |       1 | Spinner dolphin              |     522 |
| watkins  |       1 | Striped dolphin              |     707 |
| watkins  |       1 | White-beaked dolphin         |     211 |

## split

| source   | split   |   clips |
|:---------|:--------|--------:|
| aad      | test    |   10863 |
| aad      | train   |   66038 |
| dclde    | test    |   15819 |
| dclde    | train   |   86334 |
| kaggle   | test    |    4585 |
| kaggle   | train   |   25415 |
| watkins  | test    |    1909 |
| watkins  | train   |   12036 |

## unreadable

- dclde_neg114: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20190528_1931.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg115: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20190528_1931.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg116: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20190528_1931.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg117: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20190602_1143.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg118: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20190602_1143.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg119: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20190602_1143.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg120: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20200621_0380.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg121: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20200621_0380.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg122: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20200621_0380.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg123: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20200630_0390.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg124: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20200630_0390.wav': Error in WAV file. No 'RIFF' chunk marker.
- dclde_neg125: read error: Error opening '/Users/mallhw/Projects/marine-sounds-db/raw/dclde2027_kw/uaf/audio/field/20200630_0390.wav': Error in WAV file. No 'RIFF' chunk marker.
