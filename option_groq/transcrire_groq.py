# -*- coding: utf-8 -*-
"""
OPTION EN LIGNE (facultative) — transcription ultra-rapide via l'API Groq.

⚠  Ce script N'EST PAS hors-ligne : l'audio est envoyé aux serveurs de Groq.
   Il ne fait pas partie de MalleTranscriber.exe (qui reste 100 % local).
   À utiliser seulement si 5 minutes max est impératif et que le contenu
   n'est pas confidentiel.

Vitesse : whisper-large-v3-turbo sur LPU Groq ≈ 30 à 90 s pour 50 min de vidéo
(compression audio + envoi + transcription).

Utilisation (dans une invite de commandes) :
    pip install requests
    set GROQ_API_KEY=gsk_votre_cle        (clé gratuite sur https://console.groq.com)
    python transcrire_groq.py "C:\\chemin\\ma_video.mp4"
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELE = "whisper-large-v3-turbo"
LIMITE_MO = 25  # limite d'envoi du palier gratuit Groq


def horodatage(s: float) -> str:
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def main() -> int:
    try:
        import requests
    except ImportError:
        print("Installez d'abord requests :  pip install requests")
        return 1

    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    media = Path(sys.argv[1])
    cle = os.environ.get("GROQ_API_KEY")
    if not cle:
        print("Variable GROQ_API_KEY absente. Exemple :  set GROQ_API_KEY=gsk_...")
        return 1
    if not media.is_file():
        print(f"Fichier introuvable : {media}")
        return 1
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg introuvable. Installez-le :  winget install Gyan.FFmpeg")
        return 1

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        # Compression : mono 16 kHz 32 kb/s -> ~12 Mo pour 50 min (sous la limite de 25 Mo)
        mp3 = Path(tmp) / "audio.mp3"
        print("Compression de l'audio…")
        subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(media),
                        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(mp3)], check=True)
        taille = mp3.stat().st_size / 1_048_576
        if taille > LIMITE_MO:
            print(f"Audio trop gros pour Groq ({taille:.0f} Mo > {LIMITE_MO} Mo). Découpez la vidéo.")
            return 1

        print(f"Envoi à Groq ({taille:.1f} Mo)…")
        with open(mp3, "rb") as f:
            r = requests.post(
                URL,
                headers={"Authorization": f"Bearer {cle}"},
                files={"file": ("audio.mp3", f, "audio/mpeg")},
                data={"model": MODELE, "language": "fr", "response_format": "verbose_json",
                      "temperature": "0"},
                timeout=600,
            )
    if r.status_code != 200:
        print(f"Erreur Groq {r.status_code} : {r.text[:500]}")
        return 1

    segments = r.json().get("segments", [])
    srt = media.with_suffix(".srt")
    txt = media.with_suffix(".txt")
    with open(srt, "w", encoding="utf-8") as f:
        for i, s in enumerate(segments, 1):
            f.write(f"{i}\n{horodatage(s['start'])} --> {horodatage(s['end'])}\n{s['text'].strip()}\n\n")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("\n".join(s["text"].strip() for s in segments) + "\n")

    print(f"Terminé en {time.time() - t0:.0f} s.\n  {srt}\n  {txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
