==============================================================================
  MALLE TRANSCRIBER - Transcription vidéo 100 % hors-ligne pour Windows 11
==============================================================================

Logiciel de bureau qui transcrit vos vidéos et audios mot pour mot, avec
horodatage, directement sur votre PC. Aucune API, aucune clé, aucun envoi de
données. Internet est nécessaire UNE SEULE FOIS par modèle, pour le
télécharger. Ensuite tout fonctionne sans connexion.

Fichiers du projet :
  src\main.py                    le logiciel (interface + moteur)
  requirements.txt               les dépendances Python
  CREER_EXE.bat                  construit dist\MalleTranscriber.exe en un double-clic
  option_groq\transcrire_groq.py option EN LIGNE facultative (voir section 6)


------------------------------------------------------------------------------
1. CE QU'IL FAUT SAVOIR SUR LA VITESSE (honnêtement)
------------------------------------------------------------------------------

Transcrire 50 min mot pour mot en 5 min, 100 % en local, est IMPOSSIBLE sur
un Ryzen 5 5500 sans carte graphique NVIDIA. Les modèles précis (famille
"large") demandent trop de calcul pour un processeur à 6 cœurs. Avec une
RTX 3060, ça prendrait environ 2 à 3 min. Sur votre CPU, voici le réel.

Temps ESTIMÉS pour une vidéo de 50 min en français, Ryzen 5 5500, int8,
beam_size=1, filtre VAD (silences ignorés) :

  Modèle            Temps 50 min   Précision FR (estimée)  Téléchargement
  ----------------  -------------  ----------------------  --------------
  tiny              2 à 3 min      ~ 70-75 %  (brouillon)       75 Mo
  base              4 à 5 min      ~ 80-85 %                   145 Mo
  small             8 à 11 min     ~ 88-92 %                   485 Mo
  large-v3-turbo    15 à 22 min    ~ 95-97 %  (mot pour mot)   1,6 Go  <- DÉFAUT
  distil-large-v3   14 à 20 min    ANGLAIS seulement            1,5 Go

  * Ces chiffres varient selon la qualité du son, le débit de parole et la
    part de silences. Le logiciel MESURE la vitesse réelle à chaque fin de
    transcription et l'écrit dans le Journal, par exemple :
    "facteur 0.34 -> 50 min de vidéo = 17 min 00 s avec ce modèle".
  * La "précision" correspond à 100 % moins le taux d'erreur de mots
    (WER) typique sur un son propre. Sur un son bruité, comptez moins.

POURQUOI LE MODÈLE PAR DÉFAUT EST large-v3-turbo ET PAS distil-large-v3 :
distil-large-v3 a été entraîné sur des données ANGLAISES uniquement. Sur une
vidéo en français, il traduit en anglais ou invente du texte. large-v3-turbo
va à la même vitesse (4 couches de décodeur contre 2) mais il est
multilingue. C'est le meilleur compromis vitesse/précision pour le français
sur CPU. distil-large-v3 reste disponible pour vos vidéos en anglais.

En résumé :
  - Vous voulez du mot pour mot ?   large-v3-turbo, environ 15-22 min pour 50 min.
  - Vous voulez environ 5 min ?     base, mais attendez-vous à des fautes.
  - Vous voulez 5 min ET du mot pour mot ?  Seule l'option en ligne Groq
    (section 6) le permet, environ 1 min. Elle n'est PAS hors-ligne.

Réglages CPU appliqués (src\main.py) :
  WhisperModel(modèle, device="cpu", compute_type="int8", cpu_threads=12)
  transcribe(beam_size=1, best_of=1, vad_filter=True,
             vad_parameters=dict(min_silence_duration_ms=500),
             condition_on_previous_text=False, language="fr")
  - num_workers est réglé à 1 : il ne sert qu'à transcrire plusieurs
    fichiers EN MÊME TEMPS. Le logiciel les traite un par un (c'est plus
    rapide sur 6 cœurs), donc 6 workers n'apporteraient rien.
  - Astuce : testez le bouton "6 cœurs" dans le panneau de gauche. Sur
    certains Ryzen, 6 threads (cœurs physiques) vont aussi vite, voire plus
    vite, que 12, et le PC reste plus réactif.


------------------------------------------------------------------------------
2. INSTALLATION SUR WINDOWS 11 (une seule fois, pour CONSTRUIRE le .exe)
------------------------------------------------------------------------------

Étape 1 - Installer Python 3.12
  a) Allez sur https://www.python.org/downloads/windows/
     et téléchargez "Windows installer (64-bit)" de Python 3.12.x.
  b) Lancez l'installateur.
     !!! COCHEZ LA CASE "Add python.exe to PATH" en bas de la première fenêtre !!!
  c) Cliquez sur "Install Now".
  (Ou, dans un terminal :  winget install -e --id Python.Python.3.12 )

Étape 2 - Installer Visual C++ Redistributable (si ce n'est pas déjà fait)
  Il est nécessaire au moteur de transcription (CTranslate2).
  Téléchargez et installez :  https://aka.ms/vs/17/release/vc_redist.x64.exe
  (Ou :  winget install -e --id Microsoft.VCRedist.2015+.x64 )
  S'il manque, le logiciel l'indique clairement au démarrage, sans planter.

Étape 3 - Installer ffmpeg (recommandé)
  Ouvrez un "Terminal" (clic droit sur Démarrer > Terminal) et tapez :
      winget install Gyan.FFmpeg
  Si vous sautez cette étape, CREER_EXE.bat télécharge ffmpeg tout seul.
  Dans tous les cas, ffmpeg.exe est EMBARQUÉ dans le .exe final.

Étape 4 - Construire le .exe
  Double-cliquez sur CREER_EXE.bat. Le script :
    - trouve Python ;
    - crée un environnement isolé (.venv) ;
    - installe les dépendances ;
    - récupère ffmpeg.exe ;
    - construit l'exe avec PyInstaller.
  Comptez 5 à 10 minutes la première fois.
  Résultat :  dist\MalleTranscriber.exe  (environ 150 à 200 Mo, modèles non inclus)

  Ce .exe est autonome : vous pouvez le copier sur n'importe quel PC
  Windows 10/11 64 bits, sans installer Python.


------------------------------------------------------------------------------
3. UTILISATION
------------------------------------------------------------------------------

  1. Double-cliquez sur MalleTranscriber.exe.
     Le démarrage prend 5 à 15 s : l'exe se décompresse dans un dossier
     temporaire, c'est normal pour un exe "un seul fichier".
  2. Choisissez le modèle (large-v3-turbo par défaut) et la langue (Français).
  3. Glissez-déposez votre vidéo dans la zone en haut, ou cliquez sur
     "Choisir une vidéo". Vous pouvez en déposer plusieurs : elles passent
     dans une file d'attente.
  4. Au PREMIER usage d'un modèle, il se télécharge (1,6 Go pour
     large-v3-turbo) dans  C:\Users\<vous>\.cache\huggingface\hub
     La progression du téléchargement s'affiche. Ensuite : hors-ligne.
  5. Suivez la barre de progression, le temps restant et la vitesse.
     Le texte s'affiche en direct dans l'onglet "Transcription".
  6. À la fin, ces fichiers sont créés À CÔTÉ de la vidéo :
        ma_video.srt   sous-titres horodatés (VLC, YouTube, Premiere...)
        ma_video.txt   texte brut
        ma_video.vtt   si l'option ".VTT" est activée
     Si le dossier de la vidéo est protégé en écriture, ils sont créés dans
     Documents\MalleTranscriber.

  Formats acceptés : MP4, MOV, MKV, MP3, WAV, M4A (+ AVI, WEBM, FLAC, OGG, AAC, WMA)

  Dossier surveillé :
     Panneau de gauche > "Choisir un dossier...". Tout NOUVEAU fichier
     déposé dans ce dossier est transcrit automatiquement, dès que sa copie
     est terminée. Les fichiers déjà présents sont ignorés. Le bouton
     "Surveillance active" met en pause ou relance la surveillance.

  Bouton "Annuler" : arrête le fichier en cours et vide la file d'attente.


------------------------------------------------------------------------------
4. EN CAS DE PROBLÈME
------------------------------------------------------------------------------

  Tous les messages s'affichent dans l'onglet "Journal" de l'application.
  Ils sont aussi écrits dans :  %LOCALAPPDATA%\MalleTranscriber\malle.log

  "Impossible de charger le moteur (DLL manquante)"
      Installez Visual C++ Redistributable (étape 2), puis relancez.

  "ffmpeg : décodeur intégré" en jaune
      ffmpeg.exe n'a pas été trouvé. Le décodeur intégré (PyAV) fonctionne
      pour la plupart des fichiers. Pour une compatibilité totale, cliquez
      sur "Installer ffmpeg (winget)", ou placez ffmpeg.exe à côté de
      MalleTranscriber.exe.

  "Téléchargement du modèle impossible"
      Il faut Internet au premier usage d'un modèle. Vérifiez votre
      connexion ou votre proxy, et l'espace disque (2 Go libres pour
      large-v3-turbo).

  "Mémoire insuffisante"
      large-v3-turbo utilise environ 2 à 3 Go de RAM. Fermez Chrome et les
      autres gros programmes, ou passez sur "small".

  L'antivirus ou Windows SmartScreen bloque l'exe
      C'est un faux positif fréquent avec les exe PyInstaller "un seul
      fichier". Cliquez sur "Informations complémentaires" puis "Exécuter
      quand même", ou ajoutez une exclusion dans Windows Defender.

  CREER_EXE.bat dit "Python est introuvable"
      Réinstallez Python en cochant "Add python.exe to PATH", puis fermez
      et rouvrez l'explorateur.

  Le texte contient des répétitions ou du texte inventé sur les silences
      C'est rare avec le filtre VAD. Essayez large-v3-turbo plutôt que
      tiny ou base.


------------------------------------------------------------------------------
5. LANCER SANS CONSTRUIRE L'EXE (mode développeur)
------------------------------------------------------------------------------

      py -3.12 -m venv .venv
      .venv\Scripts\pip install -r requirements.txt
      .venv\Scripts\python src\main.py


------------------------------------------------------------------------------
6. OPTION EN LIGNE FACULTATIVE : GROQ (50 min en environ 1 min)
------------------------------------------------------------------------------

  !!! Cette option ENVOIE votre audio sur Internet (serveurs Groq). !!!
  Elle ne fait PAS partie de MalleTranscriber.exe, qui reste 100 % local.
  À n'utiliser que si le contenu n'est pas confidentiel.

  Groq fait tourner whisper-large-v3-turbo sur des puces spécialisées (LPU).
  Une vidéo de 50 min est transcrite en 30 à 90 s, compression et envoi
  compris.

      pip install requests
      set GROQ_API_KEY=gsk_votre_cle      (clé gratuite : https://console.groq.com)
      python option_groq\transcrire_groq.py "C:\Videos\ma_video.mp4"

  Le script compresse l'audio (environ 12 Mo pour 50 min, sous la limite de
  25 Mo du palier gratuit), l'envoie, puis écrit .srt et .txt à côté de la
  vidéo. Il faut ffmpeg dans le PATH (winget install Gyan.FFmpeg).
