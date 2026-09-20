# Non-mammal marine bioacoustics ML literature sweep (fish, invertebrates, sea turtles, reef/soundscape datasets)

Compiled 2026-09-19 from ~48 web searches and ~40 page reads (Zenodo, Borealis, NCEI, AODN, Dryad, HF, Frontiers/PLOS/JASA/PMC). Numbers omitted where a source did not state them. "unverified" = could not be confirmed on the primary page.

## 1. DATASETS

| # | Dataset | Host / institution | URL | Taxa covered | Sound types labeled | Size | Sample rate | Label format | License / access | Papers using it |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | FishSounds.net (Website Data Repository) | Univ. of Victoria / MERIDIAN (Dal) / Borealis | https://fishsounds.net/ ; data: https://borealisdata.ca/dataset.xhtml?persistentId=doi%3A10.5683%2FSP2%2FTACOUX | 1,252 fish species (2,916 examinations, 1,013 refs, 1874–2023) | Per-species sound-production descriptors (grunt, drum, hum, boatwhistle, etc.), frequency measurements for 52 recordings | 1,304 recordings; Borealis v10: 342 files, 650 MB (154 audio, 138 images, 35 tabular) | varies | CSV/tabular + audio + images | CC BY-NC 4.0 | Looby et al. 2022 Ecol. Informatics https://www.sciencedirect.com/science/article/abs/pii/S1574954122004034 ; Looby et al. 2025 GEB https://onlinelibrary.wiley.com/doi/10.1111/geb.70149 |
| 2 | ReefSet v1.0 (+ SurfPerch model) | UCL / Google DeepMind / Google Research; Zenodo | https://zenodo.org/records/11071202 ; model: https://www.kaggle.com/models/google/surfperch ; code: https://github.com/google-research/perch | Tropical reef biophony from 16 datasets, 12 countries; fish (damselfish, grouper), dolphins, croaks/crackles/growls, snapping shrimp crackle, anthropogenic noise, waves | 37 classes | 57,084 WAV clips × 1.88 s (1.6 GB) | 16 kHz | reefset_annotations.json | CC BY 4.0 | Williams et al. 2024/2025 https://arxiv.org/abs/2404.16436 ; Burns et al. 2025 Perch 2.0 https://arxiv.org/abs/2512.03219 |
| 3 | Coral Reef Soundscapes – French Polynesia | Ben Williams (UCL); Zenodo | https://zenodo.org/records/10539938 | Whole reef soundscapes | Raw 1-min recordings; site-level classes | 22 GB, 50 zip parts | not stated | Raw WAV | CC BY 4.0 | Williams et al. 2025 PLOS Comput. Biol. https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1013029 |
| 4 | Polynesian altiphotic/mesophotic/rariphotic soundscapes (Sci. Data 2026) | CRIOBE / Univ. Brest; Zenodo (~30 records) | https://www.nature.com/articles/s41597-026-06964-3 ; sounds <2 kHz 10.5281/zenodo.12570714 ; ID key https://zenodo.org/records/10592329 | Fish, benthic invertebrates, dolphins, baleen whales; French Polynesia 20–300 m | Broadband transient sounds (invertebrates), fish sounds <2 kHz, odontocete whistles, humpback/minke | 2016–2022 campaigns | 44.1–96 kHz | Raw WAV + metadata; ID key | CC BY-NC-ND 4.0 (some records CC BY) | Sci. Data 2026 descriptor |
| 5 | ToadFishFinder classifier v4 call catalog | NC State (Bohnenstiehl); Dryad/Zenodo | https://zenodo.org/records/8225808 ; code https://github.com/drbohnen/ToadFishFinder | Opsanus tau | Boatwhistle vs other | >10,000 + >10,000 labeled clips; WAV clips 2.0 GB | 24 kHz; 1,350 ms segments | Spectrogram PNGs + .mat + WAV | CC0 | Bohnenstiehl 2023 https://doi.org/10.1016/j.ecoinf.2023.102268 ; Ricci et al. 2017 https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0182757 |
| 6 | NOAA/Navy SanctSound detection products | NOAA ONMS + US Navy; NCEI; Google Cloud | gs://noaa-passive-bioacoustic/sanctsound/products/detections/ ; https://sanctsound.ioos.us/ | Atlantic cod, haddock, red/black grouper, plainfin midshipman, bocaccio, toadfish, damselfish, fish chorus, snapping shrimp, mammals | Cod grunts, grouper calls, midshipman hums, knocks, chorus presence | 300 TB raw, 2018–2021 | SoundTrap | CSV + netCDF detection tables | Public domain | Urazghildiiev & Van Parijs 2016; https://www.ncei.noaa.gov/news/sanctsound-studying-underwater-world-sound |
| 7 | Australian Fish Chorus Catalogue (2005–2023) | Curtin CMST / IMOS; AODN | https://doi.org/10.26198/qfj2-jj93 | 301 fish choruses, 83 sites; some attributed to Protonibea diacanthus, Argyrosomus japonicus, Terapontidae, Platax orbicularis | Chorus min/max/peak freq, timing | 301 records | 3–96 kHz | Tabular | CC BY 4.0 | Parsons et al. 2024 https://www.frontiersin.org/journals/remote-sensing/articles/10.3389/frsen.2024.1473168/full |
| 8 | FADAR Caribbean grouper call dataset | FAU / CFMC / NOAA | https://github.com/Aliklawat/-Fish-Acoustic-Detection-Algorithm-Research (code only) | Epinephelus guttatus, E. striatus, Mycteroperca venenosa, M. bonaci | RH1–4, N1–4, YF1–2, black grouper tonal | 73,466 spectrograms | 10 kHz | per-clip class | Not public | Ali et al. 2024 https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2024.1378159/full ; Ibrahim et al. 2018/2020 JASA-EL |
| 9 | May River (SC) sciaenid acoustic library | USC Beaufort | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0209914 (SI) | Pogonias cromis, Bairdiella chrysoura, Cynoscion nebulosus, Sciaenops ocellatus | Drum, pulse, grunt, staccato | 51/144/145/171 library calls | 80 kHz | Feature tables | CC BY | Monczak et al. 2019 |
| 10 | FishSound Finder training sets (BC & Miami) | DFO / UVic / NOAA NEFSC (Mouy) | https://github.com/xaviermouy/FishSound_Finder | Unidentified fish (rockfish habitats, Miami) | Grunts, pulses, pulse trains vs noise | 21,032 + 5,431 + 19,858 annotations | ≥32 kHz / 144 kHz | Raven boxes | Data on request; code BSD-3 | Mouy et al. 2024 https://www.frontiersin.org/journals/remote-sensing/articles/10.3389/frsen.2024.1439995/full ; Mouy et al. 2023 MEE |
| 11 | Arraial do Cabo reef fish pulsed-sound set | UFF / IEAPM Brazil | https://github.com/vivianeocn/fish_sounds_shap ; https://doi.org/10.6084/m9.figshare.c.7837885 | Unidentified reef fish | 4 pulsed classes | 120 clips (+aug to 360) | 52,734 Hz | per-clip class | Open | Barroso et al. 2025 https://pmc.ncbi.nlm.nih.gov/articles/PMC12159670/ |
| 12 | Hawai'i Island reef year-long PAM (Duane et al.) | NUWC / Cornell; Kaggle | https://doi.org/10.34740/kaggle/m/442941 | Damselfish, parrotfish, holocentrids, humpback units, ship noise | 9 unsupervised classes, 150–750 Hz | 7.77 M detections, 2020–21 | 96 kHz | Cluster labels | Processed open; raw restricted | Duane et al. 2026 https://pmc.ncbi.nlm.nih.gov/articles/PMC13411937/ |
| 13 | Koh Man Marine Soundscape | Thailand DMCR; HF | https://huggingface.co/datasets/WasuratS/ocean_soundscape | Pristine vs degraded reef | Unannotated | 197 GB | SoundTrap ST600 | none | CC BY-NC 4.0 | — |
| 14 | OCEANS (NeurIPS 2025 D&B) | MIT (Kurinchi-Vendhan & Beery) | https://neurips.cc/virtual/2025/125868 | Cetaceans to crustaceans | Long-form + unknown-event markers | not stated | — | metadata + markers | Open (unverified) | NeurIPS 2025 D&B |
| 15 | Fish & Mowbray "Sounds of Western North Atlantic Fishes" | URI GSO | https://web.uri.edu/gso/research/fish-sounds/ | 153 soniferous species, 1950–70 | Boatwhistles, rasps, ratchets, etc. | analog era | n/a | Book + index; MP3 on request | Request via fishsounds@uri.edu | Fish & Mowbray 1970 |
| 16 | Macaulay Library marine collection | Cornell | https://search.macaulaylibrary.org/catalog?mediaType=audio | Fishes, marine mammals | Species-tagged | ~5,700 clips (1,200 h) | varies | metadata | Playback free; download by request | — |
| 17 | DOSITS Audio Gallery | URI / DOSITS | https://dosits.org/galleries/audio-gallery/ | Fishes + invertebrates (mantis shrimp, snapping shrimp, kina, spiny lobster, scallop, polychaete, ghost crab) | Named per species | dozens of clips | varies | web | Educational; blocks scraping | Malfante et al. 2018 JASA |
| 18 | NOAA Fisheries "Sounds in the Ocean: Fish and Invertebrates" | NOAA | https://www.fisheries.noaa.gov/national/science-data/sounds-ocean-fish-and-invertebrates | Cod, black drum, groupers, haddock, silver perch, toadfish, snapping shrimp | Grunts, drumming, pulses, knocks, snaps | 8 clips | — | web | Public domain | — |
| 19 | Coquereau et al. 2016 maerl-bed invertebrate sound library | IUEM/LEMAR Brest | https://link.springer.com/article/10.1007/s00227-016-2902-2 ; https://www.liabebest.org/production-media/publications/coquereauetal2016.pdf | 8 soniferous invertebrates (urchins, limpet, scallops, shrimp, spider crab) | 15 sound types | ~1,300 signals | 192/156 kHz | Table 2 + ESM audio | Journal supplement | Coquereau 2016/2017; Solé et al. 2023 review |
| 20 | European lobster buzz dataset (Johnshaven) | arXiv authors | https://arxiv.org/abs/2511.16848 | Homarus gammarus | Buzz | 7,307 s, 24 individuals | — | sex/age class | unverified | Ecol. Informatics 2026 |
| 21 | Palinurus elephas antennal rasps | IUEM/LEMAR | https://pmc.ncbi.nlm.nih.gov/articles/PMC7242360/ | Palinurus elephas | Antennal rasps | 1,560 rasps | 156 kHz | — | on request | Jézéquel et al. 2020 Sci. Rep. |
| 22 | Green turtle sound repertoire (Martinique) | CNRS / MNHN | https://www.int-res.com/articles/esr2022/48/n048p031.pdf | Chelonia mydas juveniles | 10 sound types + grunt | 950 sounds | tag audio | manual | audio not deposited | Charrier et al. 2022/2025 |
| 23 | Snapping shrimp template kernels | Figshare (NC State) | https://figshare.com/articles/dataset/Building_Template_Kernels_for_Snapping_Shrimp_Detection_Algorithm/4781833 | Alpheidae | Snap templates | small | — | MATLAB | Figshare | Bohnenstiehl |
| 24 | Alpheus richardsoni audiograms (Dryad) | Univ. Auckland | https://datadryad.org/dataset/doi:10.5061/dryad.nk98sf7t7 | Alpheus richardsoni | hearing only, no audio | 27 KB | — | CSV | CC0 | Dinh & Radford 2021 |
| 25 | BOEM AT-20-06 Atlantic fish sound catalog | Cornell (Rice) for BOEM | https://boem.gov/environment/environmental-studies/database-and-acoustic-reference-catalog-marine-fish-sounds | US Atlantic soniferous fishes | Species catalog + detectors | FY2021–23 | — | relational DB | public (portal pending) | Parsons et al. 2022 https://www.frontiersin.org/journals/ecology-and-evolution/articles/10.3389/fevo.2022.810156/full |
| 26 | Freesound hydrophone packs | Freesound | https://freesound.org/people/digifishmusic/packs/2885/ ; https://freesound.org/people/klankbeeld/packs/26803/ | Snapping shrimp, ambience | unlabeled | tens of clips | varies | tags | CC per clip | — |
| 27 | HF model axds/classify-fish-sounds | Mote / SECOORA / Axiom | https://huggingface.co/axds/classify-fish-sounds | Florida fish | see card | — | — | — | HF | https://secoora.org/from-a-whales-song-to-an-oceans-symphony-how-ai-decodes-underwater-sound/ |
| 28 | Orcasound open data (AWS) | Orcasound | https://registry.opendata.aws/orcasound/ | Salish Sea hydrophones | Orca annotations | multi-year | varies | — | Open | — |

Negative findings: xeno-canto has no marine fish; Kaggle has no dedicated fish-sound audio set; HF ReefEcho-Hydrophone-Clips is empty; SAVEX-15 snapping-shrimp recordings are Navy-only.

## 2. SPECIES_SOUNDS

| scientific_name | common_name | group | sound_type | freq_range_hz | duration | datasets_containing_it | source URL |
|---|---|---|---|---|---|---|---|
| Opsanus tau | Oyster toadfish | fish | Boatwhistle | fundamental 140–260 Hz | 200–650 ms | ToadFishFinder; NOAA; SanctSound; Fish & Mowbray; FishSounds | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0182757 |
| Opsanus tau | Oyster toadfish | fish | Grunt (agonistic) | — | — | FishSounds | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4662586/ |
| Halobatrachus didactylus | Lusitanian toadfish | fish | Boatwhistle | fundamental ~60 Hz | ~0.8 s | DOSITS; FishSounds | https://dosits.org/galleries/audio-gallery/fishes/lusitanian-toadfish/ |
| Porichthys notatus | Plainfin midshipman | fish | Hum | fundamental 98–108 Hz | minutes to >1 h | SanctSound; DOSITS | https://dosits.org/galleries/audio-gallery/fishes/plainfin-midshipman/ |
| Gadus morhua | Atlantic cod | fish | Grunt | 50–500 Hz; fundamental 45–60 Hz | ~200–300 ms | SanctSound; NOAA | https://pubs.aip.org/asa/jasa/article-abstract/139/5/2532/838475 |
| Pollachius pollachius | Pollack | fish | Grunt | low | — | — | https://onlinelibrary.wiley.com/doi/10.1111/jfb.12342 |
| Melanogrammus aeglefinus | Haddock | fish | Knock | <1 kHz | pulses 10–20 ms apart | SanctSound; NOAA | https://ncbi.nlm.nih.gov/pmc/articles/PMC7588448 |
| Pogonias cromis | Black drum | fish | Harmonic drumming | 80–400 Hz | long | May River; NOAA | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0209914 |
| Bairdiella chrysoura | Silver perch | fish | Pulsed call / knocks | 80–5000 Hz | 5–13+ pulses | May River; NOAA | same |
| Cynoscion nebulosus | Spotted seatrout | fish | Grunt, drum, staccato | — | staccato ≤21+ pulses | May River | same |
| Sciaenops ocellatus | Red drum | fish | Pulse sequence | — | 3–5+ pulses | May River | same |
| Cynoscion regalis | Weakfish | fish | Purr | 300–600 Hz, peak ~540 Hz | 0.5–1.0 s | CMAST gallery | https://pubmed.ncbi.nlm.nih.gov/10751166/ |
| Protonibea diacanthus | Black jewfish | fish | Chorus | — | — | Australian Fish Chorus Catalogue | https://academic.oup.com/icesjms/article/73/8/2058/2198353 |
| Argyrosomus japonicus | Mulloway | fish | Chorus | — | — | Australian Fish Chorus Catalogue | https://www.frontiersin.org/journals/remote-sensing/articles/10.3389/frsen.2024.1473168/full |
| Terapontidae spp. | Grunters | fish | Trumpet/buzz chorus | — | — | Australian Fish Chorus Catalogue | https://www.curtin.edu.au/news/singing-fish-no-tall-tale/ |
| Platax orbicularis | Orbicular batfish | fish | Staccato beat | — | — | Australian Fish Chorus Catalogue | same |
| Epinephelus guttatus | Red hind | fish | RH1–RH4 | 20–360 Hz | — | FADAR | https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2024.1378159/full |
| Epinephelus striatus | Nassau grouper | fish | N1 alarm pulses; N2 courtship tonal; N3 agonistic double pulses; N4 grunt pairs | 30–300 Hz | CAS 1.6 s; pulses 0.09 s | FADAR; DOSITS | https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2019.00779/pdf |
| Mycteroperca venenosa | Yellowfin grouper | fish | YF1, YF2 | peak 89–142 Hz | YF1 ~3 s | FADAR | FADAR paper |
| Mycteroperca bonaci | Black grouper | fish | Modulated tonal | 60–120 Hz | — | FADAR; SanctSound; NOAA | FADAR paper |
| Epinephelus morio | Red grouper | fish | Pulses + growl; pulse train | peak ~180 Hz | growl 0.5–2 s | SanctSound; NOAA; DOSITS | https://www.researchgate.net/publication/278176913 |
| Epinephelus itajara | Goliath grouper | fish | Boom | — | — | — | https://www.researchgate.net/publication/240809988 |
| Sebastes maliger | Quillback rockfish | fish | Low-frequency pulses | — | — | Mouy 2023 | https://besjournals.onlinelibrary.wiley.com/doi/full/10.1111/2041-210X.14095 |
| Sebastes caurinus | Copper rockfish | fish | Low-frequency sounds | — | — | Mouy 2023 | same |
| Ophiodon elongatus | Lingcod | fish | Low-frequency sounds | — | — | Mouy 2023 | same |
| Sebastes paucispinis | Bocaccio | fish | Low-frequency calls | — | — | SanctSound | https://sanctsound.ioos.us/sounds.html |
| Pomacentridae | Damselfishes | fish | Pulses / pulse trains | 100–1000 Hz, peaks 100–300 Hz | pulses <100 ms | ReefSet; Duane; SanctSound | https://link.springer.com/article/10.1007/BF00606305 |
| Chromis viridis | Blue-green damselfish | fish | Agonistic pulse trains | — | 1–22 pulses | — | https://www.researchgate.net/publication/241681939 |
| Dascyllus aruanus | Humbug dascyllus | fish | Pop; Chirp | pops peak 680–1300 Hz; chirps 3400–4100 Hz | pops 6.7 ms | — | https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1095-8649.2006.01117.x |
| Plectroglyphidodon lacrymatus | Whitespotted devil | fish | Pulsed / chirps | — | — | — | same |
| Pomacentrus amboinensis | Ambon damselfish | fish | Reproductive pulsed + tonal | ~414 Hz | — | — | https://www.researchgate.net/publication/306343726 |
| Holocentridae spp. | Squirrelfish | fish | Grunts/staccato | 150–750 Hz | — | Duane (Kaggle) | https://pmc.ncbi.nlm.nih.gov/articles/PMC13411937/ |
| Scaridae spp. | Parrotfishes | fish | Feeding scrapes; rasps | — | — | Duane; Fish & Mowbray | https://web.uri.edu/gso/research/fish-sounds/ |
| Ariopsis felis | Hardhead sea catfish | fish | Vocalizations | — | — | Fish & Mowbray | https://web.uri.edu/wp-content/uploads/sites/916/sea-catfish_047.002_mono.mp3 |
| Alpheus heterochaelis | Bigclaw snapping shrimp | crustacean | Snap | 2–>200 kHz, main 2–5 kHz | 0.5–1 ms | NOAA | https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2023.1029003/full |
| Synalpheus parneomeris | Snapping shrimp | crustacean | Snap | 2–200 kHz | — | — | https://www.researchgate.net/publication/252682379 |
| Alpheidae | Snapping shrimp | crustacean | Snap / crackle | ~3–13 kHz | — | SanctSound; ReefSet; Koh Man; Polynesia | https://sanctsound.ioos.us/sounds.html |
| Athanas nitescens | Hooded shrimp | crustacean | Snap | peak 9 kHz and 33 kHz | — | Coquereau 2016 | https://www.liabebest.org/production-media/publications/coquereauetal2016.pdf |
| Maja brachydactyla | Atlantic spider crab | crustacean | Types 1–3 (feeding) | 3–45 kHz | — | Coquereau 2016 | same |
| Echinus esculentus | Edible sea urchin | echinoderm | Feeding; Moving | feeding peak 46 kHz | — | Coquereau 2016 | same |
| Paracentrotus lividus | Purple sea urchin | echinoderm | Feeding; Moving | 45 kHz | — | Coquereau 2016 | same |
| Psammechinus miliaris | Green sea urchin | echinoderm | Feeding; Moving | 49 kHz | — | Coquereau 2016 | same |
| Evechinus chloroticus | Kina | echinoderm | Grazing chorus | 700–2800 Hz | dusk | DOSITS | https://dosits.org/galleries/audio-gallery/marine-invertebrates/sea-urchin-kina/ |
| Diadema antillarum et al. | Tropical sea urchins | echinoderm | Feeding scrapes | 2.3–9.2 kHz | — | — | https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2023.1129057/full |
| Pecten maximus | Great scallop | mollusc | Swimming; coughing | 35 kHz; 20 Hz–27 kHz | — | Coquereau; DOSITS | https://dosits.org/galleries/audio-gallery/marine-invertebrates/great-scallop-pecten-maximus/ |
| Mimachlamys varia | Variegated scallop | mollusc | Jumping; swimming | 35–37 kHz | — | Coquereau 2016 | Coquereau Table 2 |
| Crepidula fornicata | Slipper limpet | mollusc | Moving | 45 kHz | — | Coquereau 2016 | same |
| Perna perna | Brown mussel | mollusc | Valve movements | 4–6 kHz | — | — | Solé et al. 2023 |
| Homarus americanus | American lobster | crustacean | Buzz | 87–261 Hz | ~200 ms | — | https://journals.biologists.com/jeb/article/224/6/jeb240747/237913 |
| Homarus gammarus | European lobster | crustacean | Buzz | ~100 Hz | ~200 ms | Johnshaven | https://arxiv.org/abs/2511.16848 |
| Palinurus elephas | European spiny lobster | crustacean | Antennal rasp | 2–75 kHz | — | Jézéquel 2020; DOSITS | https://pmc.ncbi.nlm.nih.gov/articles/PMC7242360/ |
| Panulirus interruptus | California spiny lobster | crustacean | Antennal rasp | — | — | — | https://pubmed.ncbi.nlm.nih.gov/19425682/ |
| Panulirus spp. (Brazil) | Spiny lobsters | crustacean | Rasp | — | 125–265 pulses/s | — | https://link.springer.com/article/10.1007/s00435-019-00461-5 |
| Hemisquilla californiensis | California mantis shrimp | crustacean | Rumble | 20–60 Hz | — | DOSITS | https://dosits.org/galleries/audio-gallery/marine-invertebrates/mantis-shrimp/ |
| Chionoecetes opilio | Snow crab | crustacean | Rasp | — | — | — | https://pubs.aip.org/asa/jasa/article/159/5/4079/3391266 |
| Ocypode spp. | Ghost crab | crustacean | Stridulation | — | — | DOSITS | https://dosits.org/galleries/audio-gallery/marine-invertebrates/ |
| Leocratides kimuraorum | Polychaete worm | annelid | Pops | — | — | DOSITS | same |
| Chelonia mydas (juvenile) | Green sea turtle | reptile | Pulses, croak, rumble, FM sound, squeaks, grunt | peak 200–400 Hz | — | Charrier 2022/2025 | https://www.int-res.com/articles/esr2022/48/n048p031.pdf |
| Chelonia mydas (hatchling) | Green sea turtle | reptile | 4 categories | — | — | — | https://bioone.org/journals/copeia/volume-2014/issue-2/CE-13-087/ |
| Dermochelys coriacea | Leatherback | reptile | 4 nest sound types | — | — | — | https://bioone.org/journals/chelonian-conservation-and-biology/volume-13/issue-1/CCB-1045.1/ |

## Key takeaways
- Best ready-to-train, openly licensed: ReefSet v1.0 (57k clips, CC BY), ToadFishFinder (20k+ clips, CC0), SanctSound detection CSVs (public), Australian Fish Chorus Catalogue (CC BY, tabular), FishSounds.net Borealis repo (CC BY-NC).
- Invertebrate audio is scarce as ML datasets; Coquereau 2016 is the only structured invertebrate library.
- Sea turtle audio exists only inside papers; no public repository found.
