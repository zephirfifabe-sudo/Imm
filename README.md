# Coach EA FC 27 — analyse vidéo passive (PS5 → carte de capture → PC)

Logiciel de coaching qui **lit uniquement la vidéo** (carte de capture HDMI en passthrough ou caméra
virtuelle OBS). Il n'accède jamais à la console, au réseau du jeu ni à la manette, et n'envoie aucune
commande. Les règles de tournoi ou d'EA restent à ta charge.

Source de vérité tactique : `knowledge/paastek.pdf` → `knowledge/rules.yaml` (49 règles, 11 fiches).
Le coach n'affichera **que** des conseils de ce fichier, en citant leur fiche.

## État des phases

| Phase | Contenu | État |
|---|---|---|
| 0 | Capture de frames + export Roboflow | ✅ codée |
| 1 | Capture, benchmark, OCR, curseurs, équipes (overlay debug), dashboard, analyse de clips téléchargés | ✅ codée |
| 2 | Joueurs/balle, suivi à identités stables, homographie auto, terrain 2D, heatmaps | ✅ codée |
| 3 | Événements (passes, pertes, tirs, corners, conduites, pressing, buts, changements de joueur), bilans mi-temps / fin avec extraits vidéo | ✅ codée |
| 4 | Formations (19), postes, lecture de l'adversaire en direct + habitudes, coach `rules.yaml`, démarrage de match | ✅ codée |
| 5 | Historique SQLite, progression par semaine, profils adversaires, conseils personnalisés | ✅ codée |

> **Important — rien n'est encore validé sur de vraies images d'EA FC 27.** Tout est testé sur des
> vidéos et matchs **synthétiques** (102 tests). La porte de validation reste ton contrôle :
> `scripts/eval_phase1.py` doit afficher `PORTE PHASE 1 : PASS` sur ≥ 10 combinaisons de maillots
> avant de faire confiance aux conseils. Tant que les curseurs ou les équipes sont faux, tout ce qui
> est construit dessus l'est aussi.

## Arborescence

```
config/
  config.yaml          configuration principale (source, matériel, détecteur, équipes, UI)
  cursor.yaml          seuils HSV/forme des curseurs (rouge = moi, blanc = adversaire)
  ocr_zones.json       zones OCR (chrono, score, nom sélectionné, pause, mi-temps)
knowledge/
  paastek.pdf          le carnet de coaching (11 fiches)
  rules.yaml           règles extraites : id, fiche, contexte, déclencheur, conseil, bouton, priorité, source
fccoach/
  core/                config typée, logs, matériel (accélérateur + cadence adaptative), état partagé
  capture/             source vidéo, thread de capture, buffer brut 1 s + buffer d'extraits 30 s compressé
  ocr/                 moteurs (Tesseract/PaddleOCR), zones, validation, thread OCR
  vision/              detector.py (YOLO ONNX, tuiles 1080p), cursor.py, teams.py, color.py (CIEDE2000),
                       kits_db.py (kits.sqlite), debug_overlay.py
  tracking/            pitch.py (terrain 105×68), homography.py (calibration + suivi auto par les lignes),
                       tracker.py (joueurs façon ByteTrack, balle)
  analysis/            world.py (terrain 2D normalisé), formation.py (19 formations + postes),
                       opponent_live.py / opponent_profile.py (curseur blanc, habitudes), signals.py
                       (62 signaux des règles), match.py (match complet, bilans, heatmaps), session.py
  events/              passes, pertes, récupérations, tirs, corners, conduites, pressing
  coach/               rules.py (chargement), engine.py (règles -> un conseil à la fois)
  storage/db.py        matches.sqlite : matchs, événements, conseils, situations, progression
  clips/               analyse hors ligne des clips téléchargés (file d'attente, rapport, vidéo annotée)
  ui/                  FastAPI + pages web (dashboard, calibration, clip, bilan, historique)
  app.py               orchestration des threads
scripts/
  phase0_capture_frames.py   capture automatique de frames (par combinaison de maillots / mi-temps)
  phase0_export_roboflow.py  dossier d'upload ou upload API Roboflow (tags combo/mi-temps/clash)
  build_dataset.py           export Roboflow → dataset, découpage PAR COMBINAISON, augmentation teinte/saturation
  train_yolo.py              entraînement Ultralytics (PC ou Colab) + rapport par classe + export ONNX
  export_onnx.py             export d'un .pt en ONNX (ex. YOLO COCO de départ)
  benchmark.py               vitesse détection / curseurs / OCR sur TA machine + cadence recommandée
  eval_phase1.py             porte de validation Phase 1 (curseurs + équipes, rapport par combinaison)
tests/                 tests unitaires (images synthétiques)
```

## Installation (Windows)

1. Python 3.11+ : https://www.python.org (cocher « Add to PATH »).
2. Dans le dossier du projet :
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Accélérateur** (un seul paquet ONNX Runtime à la fois) :
   - Nvidia : `pip uninstall -y onnxruntime && pip install onnxruntime-gpu` (+ CUDA 12 / cuDNN 9 installés)
   - AMD ou Intel sous Windows : `pip uninstall -y onnxruntime && pip install onnxruntime-directml`
   - Intel (OpenVINO) : `pip uninstall -y onnxruntime && pip install onnxruntime-openvino`
   - Sinon CPU : rien à faire.
   Au démarrage, les logs affichent : `Accélérateur détecté : CUDA (…)`.
4. **OCR** : installer Tesseract (https://github.com/UB-Mannheim/tesseract/wiki), puis si besoin
   renseigner `ocr.tesseract_cmd: C:\Program Files\Tesseract-OCR\tesseract.exe` dans `config.yaml`.
   PaddleOCR est optionnel (`pip install paddleocr paddlepaddle-gpu`), choisi en priorité sur GPU.
5. **Modèle de départ** (en attendant ton modèle entraîné) :
   ```bat
   pip install ultralytics onnx
   python scripts/export_onnx.py --weights yolo11n.pt --out models/fc_yolo_n.onnx
   ```
   Le logiciel reconnaît un modèle COCO : « person » → player, « sports ball » → ball (gardiens et
   arbitre non distingués, rejetés par couleur dans `teams.py`).

## Phase 0 — capture et export Roboflow

**Ce que tu dois faire :** jouer/rejouer des matchs et capturer **au moins 10 combinaisons de
maillots**, **les deux mi-temps** à chaque fois, **dont des clashs** (maillots proches).

1. Trouver l'index de ta source : carte de capture ou « OBS Virtual Camera » (souvent 0, 1 ou 2).
   Dans OBS : *Démarrer la caméra virtuelle*, sortie 1920×1080.
2. Capturer (une commande par combinaison et par mi-temps) :
   ```bat
   python scripts\phase0_capture_frames.py --source 1 --combo psg-dom_vs_om-ext --half 1
   python scripts\phase0_capture_frames.py --source 1 --combo psg-dom_vs_om-ext --half 2
   python scripts\phase0_capture_frames.py --source match.mp4 --combo liv-dom_vs_mu-dom --half 1 --clash
   ```
   Images 1080p natives, doublons et menus filtrés, dans `data/raw/<combo>/h<1|2>/`.
3. Préparer Roboflow :
   ```bat
   python scripts\phase0_export_roboflow.py --preannotate models\fc_yolo_n.onnx
   ```
   → `data/roboflow_upload/` (images + pré-annotations YOLO + `classes.txt`) à glisser-déposer dans un
   projet Roboflow « Object Detection ». Ou upload direct : `set ROBOFLOW_API_KEY=…` puis
   `--upload --workspace <toi> --project fc-coach`.
4. **Annotation (toi, dans Roboflow)** : 4 classes exactement `player, goalkeeper, referee, ball`.
   Pas de classe d'équipe. Corrige les pré-annotations, annote la balle même petite.
5. Export Roboflow au format **YOLOv11** (sans redimensionnement !), puis :
   ```bat
   python scripts\build_dataset.py --export data\roboflow_export --out data\dataset --val-combos 2
   python scripts\train_yolo.py --data data\dataset\data.yaml --size n
   ```
   Le découpage train/val se fait **par combinaison de maillots** (le nom de fichier porte la
   combinaison). `train_yolo.py` produit `reports/detector_fc_yolo_n.json` (précision/rappel/mAP par
   classe) et `models/fc_yolo_n.onnx`. PC trop faible : même commande sur Google Colab (GPU T4).

## Phase 1 — lancer, mesurer, valider

```bat
python scripts\benchmark.py                 :: vitesse sur TA machine + cadence recommandée
python -m fccoach                           :: source de config.yaml, dashboard http://127.0.0.1:8000
python -m fccoach --source match.mp4        :: rejouer une vidéo enregistrée
```

Ouvre `http://127.0.0.1:8000` sur le second écran : score/chrono (OCR), bandeau **Adversaire**
(curseur blanc, joueur sélectionné, changements), **Moi** (curseur rouge), **Équipes** (couleurs
des prototypes maillot/short/chaussettes, confiance, clash, mi-temps, sens d'attaque), événements,
et l'**overlay debug** (chaque joueur : équipe, confiance, n° de track ; curseurs et leur état).

Ce que fait la Phase 1 :
- **Capture** : thread dédié à pleine vitesse, buffer circulaire de 30 s horodaté ; elle n'attend jamais.
- **Matériel** : CUDA > DirectML/ROCm > OpenVINO > CPU ; mesure au démarrage puis cadence de détection
  adaptative 60 → 30 → 15 → 10 i/s. Curseurs (30 Hz) et OCR gardent leurs cadences propres.
- **Détection** : YOLO ONNX en 1080p natif par tuiles 640 px avec recouvrement (jamais d'image réduite).
- **Curseurs** : masque HSV rouge/blanc + triangle pointant vers le bas + isolement + joueur juste
  dessous ; lissage, interpolation 2 s, puis repli ; événement à chaque changement de joueur.
- **Équipes** : torse/short/chaussettes, pelouse et peau masquées, K-means Lab, CIEDE2000, vote sur
  15 images par track ; ancrage continu par les curseurs ; calibration au coup d'envoi (00:00 / 45:00) ;
  mode clash ; mi-temps (le chrono repart de 45:00 après le temps additionnel) ; `data/kits.sqlite`.
  Sous 70 % de confiance : alerte « Équipes incertaines », rien qui dépend de l'équipe.
- **OCR** : thread séparé ; chrono 2/s, score 1/s (+ à chaque but), nom sélectionné 3/s près du
  curseur, pseudo adverse sur l'overlay « Pause demandée par … », écrans de mi-temps/fin à la demande.
  Le chrono ne recule jamais (sauf reprise de période à 45:00), le score ne monte que de 1.

### Analyser un clip téléchargé

Un clip récupéré ailleurs (partage PS5, OBS, réseau social, YouTube…) passe par la même analyse que
le direct : détection, équipes, curseurs, OCR. Il est lu **au rythme de la vidéo** (temps du clip),
aussi vite que la machine le permet, dans un thread à part : la capture en direct n'est jamais bloquée.

- **Depuis le dashboard** : section « Analyser un clip téléchargé ». Glisse un ou plusieurs fichiers
  (MP4, MKV, MOV, AVI, WebM, M4V, TS). Ils passent en file d'attente, un à la fois, avec une barre de
  progression, puis « voir le résultat » ouvre la page du clip.
- **Sans carte de capture** : `python -m fccoach --clips-only` ouvre seulement le dashboard des clips.
- **En ligne de commande** : `python -m fccoach.clips mon_clip.mp4 [autre.mp4 …] [--no-video]`.

Résultat (dossier `data/clips/<id>/`, aussi affiché sur la page du clip) :
- `report.json` : durée, vitesse d'analyse, équipes (couleurs, confiance, clash), chrono et score lus,
  pseudo adverse, changements de joueur (moi / adversaire, par minute pour un clip d'au moins 1 min,
  zones des switchs adverses), événements horodatés **en temps du clip**, une ligne par seconde ;
- `annotated.webm` : la vidéo avec l'overlay debug, lisible dans le navigateur. Un clic sur un
  événement saute au bon moment ;
- `events/*.jpg` : une image clé par événement.

Réglages dans `config.yaml > clips` : `analysis_fps` (15 détections par seconde de vidéo),
`annotated_video`, taille maximale du fichier. Un clip en 720p ou d'un autre format que le 16:9 est
ramené en 1920×1080 (bandes noires si besoin), avec un avertissement : sous 1080p, la balle, les
curseurs et l'OCR sont moins fiables. Un clip qui ne commence pas au coup d'envoi est calibré par les
curseurs. Les ralentis (caméra différente) faussent l'analyse. Les conseils sur un clip
(« ce que j'aurais dû faire ») arrivent avec le coach en Phase 4.

### Porte de validation Phase 1

1. Capture des séquences serrées (`--interval 0.2`) sur ≥ 10 combinaisons, deux mi-temps, ≥ 1 clash.
2. Projet Roboflow **séparé** « fc-eval » avec les classes d'évaluation :
   `player_me, player_opp, goalkeeper, referee, ball, cursor_me, cursor_opp`.
3. Export YOLO puis :
   ```bat
   python scripts\eval_phase1.py --export data\eval_export
   ```
   Rapport `reports/phase1_eval.json` : rappel/précision des curseurs, confusion rouge/blanc, taux
   d'erreur d'équipe et couverture par combinaison, verdict PASS/FAIL.

## Tests

```bat
python -m pytest
```
102 tests sur données synthétiques, dont une intégration complète (clip « vue télé » avec caméra qui
panote : calibration, homographie, équipes, formation, passes, coach, bilan, heatmaps). Règles (format, 15 mots max, 11 fiches, règles
prioritaires), CIEDE2000 (valeurs de référence Sharma), validation OCR, curseurs (rouge vs maillot
rouge, blanc vs ligne, triangle à l'envers, interpolation/repli, changement de joueur), équipes
(coup d'envoi, repli curseurs, kits.sqlite, clash, mi-temps), tuiles 1080p, décodage ONNX, dashboard,
clips (mise au 1080p, analyse complète, fichier refusé, dépôt par l'API).

## Phases 2 à 5 — terrain, événements, coach, historique

### 1. Calibrer le terrain (une fois)
Dashboard → **Calibration** : fige une image de jeu (direct ou clip), choisis un point du terrain
(il s'allume sur le schéma) et clique-le dans l'image ; 4 points minimum, 6 à 8 bien répartis c'est
mieux (milieu haut / bas, centre, coins de surface…). Les lignes reprojetées en jaune doivent tomber
sur les lignes blanches. Ensuite l'homographie **suit seule** la caméra (panoramique, zoom) en
alignant les lignes du terrain, et se retrouve après un ralenti. Recalibre seulement si tu changes
le réglage de caméra du jeu. Sans calibration : pas de terrain 2D, d'événements ni de conseils.

### 2. Pendant le match (`python -m fccoach`)
- **Terrain 2D** : joueurs en rouge (moi) / blanc (adversaire) avec leur poste, ballon, joueurs sélectionnés.
- **Conseil** : un seul à la fois, uniquement depuis `rules.yaml`, avec sa fiche et le bouton *suggéré*.
  Rien pendant l'engagement ni en pause ; ensuite au plus un toutes les 20 s, le même pas avant 90 s.
  Équipes ou formation sous 70 % → règles dépendantes bloquées. Signal non mesurable → règle ignorée.
- **Adversaire** : poste du joueur sous son curseur, formation, hauteur de ligne, habitudes
  (2 fois = « à confirmer », 3 fois = installée). Profil gardé par pseudo (lu sur l'overlay de pause).
- **Formations reconnues (19)** : 4312, 41212, 4213, 433, 4231, 442, 4321, 4141, 4411, 4222, 352, 343,
  3412, 3421, 3142, 532, 5212, 523, 541. Les variantes très proches (ex. 433 (1) / 433 (4)) ne sont pas
  distinguées ; quand les joueurs bougent beaucoup, 433 / 4231 / 4213 peuvent se confondre et la
  confiance reste sous 70 % → aucun conseil de formation.

### 3. Bilans et historique
- À la mi-temps et à la fin : `data/matches/match_NNNNN/bilan_*.json`, page **Bilan** : « Ce que
  j'aurais dû faire » (règles déclenchées, fiche, moments, **extraits vidéo** de 6 s avant à 3 s après),
  stats (possession, passes, pertes, tirs, corners…), formations, habitudes adverses, heatmaps.
- Page **Historique** : matchs, score, et progression **semaine après semaine** (situations ratées par
  match, règles à travailler). Les règles que tu rates le plus passent en priorité (conseils personnalisés).
- Les clips téléchargés passent par la même analyse (bilan sur la page du clip), sans entrer dans l'historique.

### Mémoire (correctif)
Le buffer de 30 s de la Phase 1 gardait des images 1080p brutes : ~11 Go de RAM à 60 i/s. Désormais
1 s d'images brutes pour l'analyse + 30 s compressées (≈ 50 Mo) pour les extraits.

## Ce qui dépend de ton matériel ou de réglages — à vérifier chez toi

- **Index de la source** (`capture.source`) et backend (`dshow` conseillé pour OBS sous Windows).
  La carte doit sortir du **1920×1080** (les zones OCR et seuils curseurs sont calés dessus).
- **Zones OCR** (`config/ocr_zones.json`) : positions estimées du HUD EA FC ; ajuste `box` si ton
  HUD diffère (thème, taille d'interface, mode de jeu). Le nom du joueur sélectionné est cherché
  relativement au curseur (`offset_px`).
- **Seuils curseurs** (`config/cursor.yaml`) : valeurs par défaut non vérifiées sur de vraies images
  EA FC 27 (taille du triangle, teinte exacte). Si un curseur est raté ou confondu, corrige les
  plages HSV, `min_area`/`max_area` ou `exclude_regions` (pas d'assistant de calibration).
- **Seuil de clash** (`teams.clash_delta_e`, 12 par défaut) et **min_confidence** (0,70).
- **Paquet ONNX Runtime** selon ta carte (voir Installation) ; l'option `precision_mode` n'est
  utilisée que si un GPU Nvidia ≥ 8 Go est détecté.
- **Cadence** : `scripts/benchmark.py` donne la cadence réelle ; sur CPU seul, attends 10-15 i/s.
- **Caméra du jeu** : prévue fixe. Le recalcul automatique de l'homographie (lignes du terrain) arrive
  en Phase 2.

## Limites connues (honnêtement)

- Tout a été testé sur des **images synthétiques** (vue « télé » générée, joueurs rectangulaires) :
  aucune vidéo réelle d'EA FC 27 n'était disponible. Les seuils (distances, vitesses, hauteur de
  ligne en « prof », zones OCR, couleurs des curseurs) sont des estimations à affiner sur tes matchs.
- Le terrain n'est jamais vu en entier : formation et habitudes adverses s'accumulent sur la durée ;
  un côté hors champ n'est jamais considéré comme « vide ».
- Les buts sont lus par l'OCR ; qui a marqué est déduit du dernier tir / de la possession.
- LLM optionnel : non intégré. Le coach n'utilise que `rules.yaml` (c'est le repli prévu).
- `live_coaching: false` coupe l'affichage des conseils mais garde les bilans et l'historique.
