# -*- coding: utf-8 -*-
"""
MalleTranscriber — transcription vidéo/audio 100 % hors-ligne pour Windows.

Moteur : faster-whisper (CTranslate2, quantification int8 sur CPU).
Interface : CustomTkinter (mode sombre) + glisser-déposer via tkinterdnd2.

Aucune API, aucune clé, aucun envoi de données : seul le premier lancement
d'un modèle nécessite Internet pour le télécharger dans
%USERPROFILE%\\.cache\\huggingface. Ensuite tout fonctionne hors-ligne.
"""

import os
import sys

# ---------------------------------------------------------------------------
# 0. Corrections indispensables AVANT tout autre import
# ---------------------------------------------------------------------------
# En mode --windowed (PyInstaller), sys.stdout / sys.stderr valent None.
# Plusieurs bibliothèques (tqdm de huggingface_hub, ctranslate2...) écrivent
# dedans et plantent alors silencieusement. On les redirige vers "nul".
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# Pas de télémétrie Hugging Face, pas d'avertissement sur les liens symboliques
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

import queue
import shutil
import subprocess
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except Exception:  # pragma: no cover - message clair si l'UI est absente
    tk.Tk().withdraw()
    messagebox.showerror(
        "MalleTranscriber",
        "La bibliothèque CustomTkinter est introuvable.\n\n"
        "Reconstruisez l'application avec CREER_EXE.bat.",
    )
    sys.exit(1)

# Glisser-déposer : optionnel. Si absent, le bouton « Choisir » reste dispo.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    DND_DISPONIBLE = True
except Exception:
    DND_DISPONIBLE = False
    DND_FILES = None
    TkinterDnD = None


# ---------------------------------------------------------------------------
# 1. Constantes
# ---------------------------------------------------------------------------
APP_NOM = "MalleTranscriber"
APP_VERSION = "1.0.0"

EXTENSIONS = {".mp4", ".mov", ".mkv", ".mp3", ".wav", ".m4a",
              ".avi", ".webm", ".flac", ".ogg", ".aac", ".wma"}

# Infos par modèle. "rtf" = facteur temps réel estimé sur Ryzen 5 5500
# (int8, beam 1, VAD) : durée de traitement / durée du média. Sert uniquement
# à afficher une première estimation avant que la vraie vitesse soit mesurée.
MODELES = {
    "tiny": {
        "taille_mo": 75, "rtf": 0.04,
        "desc": "Ultra rapide, précision faible (brouillon).",
    },
    "base": {
        "taille_mo": 145, "rtf": 0.08,
        "desc": "Très rapide, précision moyenne.",
    },
    "small": {
        "taille_mo": 485, "rtf": 0.18,
        "desc": "Bon compromis, quelques erreurs.",
    },
    "distil-large-v3": {
        "taille_mo": 1510, "rtf": 0.33,
        "desc": "Excellent en ANGLAIS uniquement (mauvais en français).",
    },
    "large-v3-turbo": {
        "taille_mo": 1620, "rtf": 0.38,
        "desc": "Le meilleur en français : quasi mot pour mot.",
    },
}
MODELE_DEFAUT = "large-v3-turbo"

LANGUES = {"Français": "fr", "Anglais": "en", "Détection auto": None}
LANGUE_DEFAUT = "Français"

THREADS = {"12 threads": 12, "6 cœurs": 6}
THREADS_DEFAUT = "12 threads"

# Pas de fenêtre console qui clignote quand on lance ffmpeg/winget sous Windows
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

URL_VCREDIST = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

# Dossier de logs persistant (utile si l'application se ferme brutalement)
if os.name == "nt":
    DOSSIER_APP = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NOM
else:
    DOSSIER_APP = Path.home() / f".{APP_NOM.lower()}"
try:
    DOSSIER_APP.mkdir(parents=True, exist_ok=True)
except Exception:
    DOSSIER_APP = Path.cwd()
FICHIER_LOG = DOSSIER_APP / "malle.log"


def log_fichier(texte: str) -> None:
    """Écrit une ligne dans le fichier log (jamais bloquant, jamais d'erreur)."""
    try:
        with open(FICHIER_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {texte}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 2. Utilitaires système
# ---------------------------------------------------------------------------
def dossier_executable() -> Path:
    """Dossier du .exe (ou du script en mode développement)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def trouver_ffmpeg():
    """Cherche ffmpeg : embarqué dans l'exe, à côté de l'exe, puis dans le PATH."""
    nom = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidats = []
    # a) Embarqué par PyInstaller (--add-binary ffmpeg.exe;.)
    if hasattr(sys, "_MEIPASS"):
        candidats.append(Path(sys._MEIPASS) / nom)
    # b) À côté de l'exe / du script, ou dans un sous-dossier ffmpeg\
    base = dossier_executable()
    candidats += [base / nom, base / "ffmpeg" / nom, base.parent / "ffmpeg" / nom]
    # c) Emplacement de winget (le PATH du processus n'est pas rafraîchi
    #    juste après une installation, donc on le teste explicitement)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        candidats.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links" / nom)
    for c in candidats:
        if c.is_file():
            return str(c)
    # d) PATH système
    return shutil.which("ffmpeg")


def verifier_moteur():
    """
    Importe faster-whisper / CTranslate2 et renvoie (ok, message).
    Détecte le cas classique « Visual C++ Redistributable manquant ».
    """
    try:
        import ctranslate2  # noqa: F401
        import faster_whisper  # noqa: F401
        return True, f"Moteur prêt (faster-whisper {faster_whisper.__version__}, CTranslate2 {ctranslate2.__version__})."
    except ModuleNotFoundError as e:
        return False, (
            f"Module manquant : {e.name}\n\n"
            "L'exécutable a été mal construit. Relancez CREER_EXE.bat "
            "(il installe toutes les dépendances)."
        )
    except (ImportError, OSError) as e:
        txt = str(e)
        if "DLL" in txt or "dll" in txt or isinstance(e, OSError):
            return False, (
                "Impossible de charger le moteur de transcription (DLL manquante).\n\n"
                "Cause la plus fréquente : « Microsoft Visual C++ Redistributable » "
                "n'est pas installé.\n\n"
                f"Téléchargez-le et installez-le ici :\n{URL_VCREDIST}\n\n"
                "Puis relancez MalleTranscriber.\n\n"
                f"Détail technique : {txt}"
            )
        return False, f"Erreur au chargement du moteur : {txt}"
    except Exception as e:
        return False, f"Erreur inattendue au chargement du moteur : {e!r}"


def charger_audio(chemin: str, ffmpeg):
    """
    Décode n'importe quel média en audio mono 16 kHz float32 (ce qu'attend Whisper).
    1) ffmpeg.exe s'il est disponible (le plus robuste, tous formats) ;
    2) sinon PyAV, embarqué avec faster-whisper (fonctionne aussi sans ffmpeg.exe).
    """
    import numpy as np

    if ffmpeg:
        cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
               "-i", chemin, "-vn", "-ac", "1", "-ar", "16000",
               "-f", "s16le", "-acodec", "pcm_s16le", "-"]
        proc = subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
        if proc.returncode != 0 or not proc.stdout:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                "ffmpeg n'a pas pu lire ce fichier (corrompu, protégé, ou sans piste audio).\n"
                f"Message ffmpeg : {err[-800:] or 'aucun'}"
            )
        return np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0, "ffmpeg"

    from faster_whisper import decode_audio
    return decode_audio(chemin, sampling_rate=16000), "PyAV (ffmpeg intégré)"


def format_horodatage(secondes: float, sep: str = ",") -> str:
    """12.345 -> '00:00:12,345' (SRT) ou '00:00:12.345' (VTT)."""
    ms = int(round(max(0.0, secondes) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def format_duree(secondes: float) -> str:
    """Durée lisible : 1 h 02 min 05 s / 3 min 12 s / 45 s."""
    secondes = int(max(0, secondes))
    h, r = divmod(secondes, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h} h {m:02d} min {s:02d} s"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


def ecrire_exports(chemin_media: str, segments, avec_vtt: bool):
    """
    Écrit .srt + .txt (+ .vtt) à côté du média.
    Si le dossier est en lecture seule, repli dans Documents\\MalleTranscriber.
    Renvoie la liste des fichiers créés.
    """
    media = Path(chemin_media)
    dossiers = [media.parent, Path.home() / "Documents" / APP_NOM]
    derniere_erreur = None

    for dossier in dossiers:
        try:
            dossier.mkdir(parents=True, exist_ok=True)
            base = dossier / media.stem
            crees = []

            # --- SRT
            srt = base.with_suffix(".srt")
            with open(srt, "w", encoding="utf-8") as f:
                for i, (deb, fin, texte) in enumerate(segments, 1):
                    f.write(f"{i}\n{format_horodatage(deb)} --> {format_horodatage(fin)}\n{texte}\n\n")
            crees.append(srt)

            # --- TXT (texte brut, une phrase/segment par ligne)
            txt = base.with_suffix(".txt")
            with open(txt, "w", encoding="utf-8") as f:
                f.write("\n".join(t for _, _, t in segments) + "\n")
            crees.append(txt)

            # --- VTT (optionnel)
            if avec_vtt:
                vtt = base.with_suffix(".vtt")
                with open(vtt, "w", encoding="utf-8") as f:
                    f.write("WEBVTT\n\n")
                    for deb, fin, texte in segments:
                        f.write(f"{format_horodatage(deb, '.')} --> {format_horodatage(fin, '.')}\n{texte}\n\n")
                crees.append(vtt)
            return crees
        except OSError as e:
            derniere_erreur = e
            continue
    raise RuntimeError(f"Impossible d'écrire les fichiers de sortie : {derniere_erreur}")


def taille_dossier(dossier: Path) -> int:
    """Taille totale (octets) d'un dossier — sert à suivre un téléchargement."""
    total = 0
    try:
        for racine, _, fichiers in os.walk(dossier):
            for nom in fichiers:
                try:
                    total += os.path.getsize(os.path.join(racine, nom))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def ouvrir_dans_explorateur(chemin) -> None:
    """Ouvre un dossier dans l'Explorateur Windows (ou équivalent)."""
    if os.name == "nt":
        os.startfile(str(chemin))  # noqa: S606 - usage local voulu
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(chemin)])
    else:
        subprocess.Popen(["xdg-open", str(chemin)])


# ---------------------------------------------------------------------------
# 3. Moteur de transcription (thread de travail)
# ---------------------------------------------------------------------------
class Annule(Exception):
    """Levée quand l'utilisateur clique sur « Annuler »."""


class MoteurTranscription(threading.Thread):
    """
    Thread unique qui traite la file d'attente des fichiers, un par un.
    Il ne touche JAMAIS à l'interface directement : il envoie des messages
    dans `self.evenements`, lus par l'UI toutes les 100 ms (thread-safe).
    """

    def __init__(self, evenements: "queue.Queue"):
        super().__init__(daemon=True, name="MoteurTranscription")
        self.evenements = evenements
        self.travaux: "queue.Queue" = queue.Queue()
        self.annuler = threading.Event()
        self.modele = None
        self.cle_modele = None
        self.ffmpeg = trouver_ffmpeg()

    # -- communication avec l'UI -------------------------------------------
    def envoyer(self, type_evt: str, valeur=None) -> None:
        self.evenements.put((type_evt, valeur))

    def log(self, texte: str) -> None:
        log_fichier(texte)
        self.envoyer("log", texte)

    # -- API publique --------------------------------------------------------
    def ajouter(self, chemin: str, reglages: dict) -> None:
        self.travaux.put((chemin, dict(reglages)))

    def tout_annuler(self) -> int:
        """Annule le fichier en cours et vide la file. Renvoie le nb retiré."""
        n = 0
        while True:
            try:
                self.travaux.get_nowait()
                n += 1
            except queue.Empty:
                break
        self.annuler.set()
        return n

    # -- boucle principale ---------------------------------------------------
    def run(self) -> None:
        while True:
            chemin, reglages = self.travaux.get()
            self.annuler.clear()
            self.envoyer("occupe", True)
            try:
                self.traiter(chemin, reglages)
            except Annule:
                self.log("⏹  Transcription annulée par l'utilisateur.")
                self.envoyer("statut", "Annulé")
                self.envoyer("progression", 0.0)
                self.envoyer("eta", "")
            except MemoryError:
                self.log("❌ Mémoire insuffisante. Fermez d'autres programmes ou choisissez un modèle plus petit (small/base).")
                self.envoyer("statut", "Erreur : mémoire insuffisante")
            except Exception as e:
                self.log(f"❌ ERREUR sur « {Path(chemin).name} » : {e}")
                self.log(traceback.format_exc())
                self.envoyer("statut", f"Erreur : {e}"[:120])
            finally:
                self.envoyer("restant", self.travaux.qsize())
                if self.travaux.empty():
                    self.envoyer("occupe", False)

    # -- chargement du modèle (avec téléchargement si besoin) ---------------
    def obtenir_modele(self, nom: str, threads: int):
        cle = (nom, threads)
        if self.modele is not None and self.cle_modele == cle:
            return self.modele

        from faster_whisper import WhisperModel

        # On libère l'ancien modèle avant d'en charger un nouveau (RAM)
        self.modele = None
        self.cle_modele = None

        params = dict(
            device="cpu",
            compute_type="int8",   # int8 = 2 à 4x plus rapide que float32 sur CPU
            cpu_threads=threads,   # Ryzen 5 5500 : 12 threads logiques
            # num_workers ne sert qu'à transcrire plusieurs fichiers EN PARALLÈLE
            # dans des threads différents. Ici on traite un fichier à la fois,
            # donc 1 suffit : aucune perte de vitesse, moins de RAM utilisée.
            num_workers=1,
        )

        # 1) Essai 100 % hors-ligne : modèle déjà présent dans le cache ?
        self.envoyer("statut", f"Chargement du modèle {nom}…")
        self.envoyer("progression", None)  # barre en mode « indéterminé »
        t0 = time.time()
        try:
            modele = WhisperModel(nom, local_files_only=True, **params)
            self.log(f"Modèle « {nom} » chargé depuis le cache en {time.time() - t0:.1f} s (hors-ligne).")
        except Exception:
            # 2) Pas en cache : téléchargement (une seule fois)
            taille = MODELES.get(nom, {}).get("taille_mo", 0)
            self.log(f"⬇  Premier usage du modèle « {nom} » : téléchargement d'environ {taille} Mo "
                     "(une seule fois, ensuite tout fonctionne hors-ligne)…")
            fin_dl = threading.Event()
            threading.Thread(target=self._suivre_telechargement, args=(taille, fin_dl), daemon=True).start()
            try:
                modele = WhisperModel(nom, local_files_only=False, **params)
            except MemoryError:
                raise
            except Exception as e:
                raise RuntimeError(
                    f"Téléchargement du modèle « {nom} » impossible.\n"
                    "Vérifiez la connexion Internet (nécessaire uniquement au premier usage d'un modèle), "
                    "un éventuel proxy/pare-feu, et l'espace disque libre, "
                    "ou choisissez un modèle déjà téléchargé.\n"
                    f"Détail : {type(e).__name__}: {str(e)[:300]}"
                ) from e
            finally:
                fin_dl.set()
            self.log(f"✅ Modèle « {nom} » téléchargé et chargé en {format_duree(time.time() - t0)}.")

        self.modele, self.cle_modele = modele, cle
        return modele

    def _suivre_telechargement(self, taille_mo: int, fin: threading.Event) -> None:
        """Affiche la progression du téléchargement en mesurant le cache HF."""
        try:
            from huggingface_hub.constants import HF_HUB_CACHE
            cache = Path(HF_HUB_CACHE)
        except Exception:
            cache = Path.home() / ".cache" / "huggingface" / "hub"
        depart = taille_dossier(cache)
        while not fin.wait(1.0):
            mo = (taille_dossier(cache) - depart) / 1_048_576
            if taille_mo:
                self.envoyer("progression", min(mo / taille_mo, 0.99))
                self.envoyer("statut", f"Téléchargement du modèle : {mo:.0f} / ~{taille_mo} Mo")
            else:
                self.envoyer("statut", f"Téléchargement du modèle : {mo:.0f} Mo")

    # -- traitement d'un fichier ----------------------------------------------
    def traiter(self, chemin: str, reglages: dict) -> None:
        nom_fichier = Path(chemin).name
        if not Path(chemin).is_file():
            raise FileNotFoundError(f"Fichier introuvable : {chemin}")

        nom_modele = reglages["modele"]
        langue = reglages["langue"]
        threads = reglages["threads"]

        self.envoyer("nouveau_fichier", nom_fichier)
        self.log("─" * 60)
        self.log(f"▶  {nom_fichier}  |  modèle {nom_modele}  |  langue {langue or 'auto'}  |  {threads} threads")
        if nom_modele == "distil-large-v3" and langue != "en":
            self.log("⚠  distil-large-v3 a été entraîné sur l'ANGLAIS uniquement : en français il "
                     "traduit ou invente du texte. Utilisez large-v3-turbo pour le français.")

        modele = self.obtenir_modele(nom_modele, threads)
        if self.annuler.is_set():
            raise Annule()

        # --- Décodage audio
        self.envoyer("statut", "Extraction de l'audio…")
        self.envoyer("progression", None)
        t0 = time.time()
        audio, decodeur = charger_audio(chemin, self.ffmpeg)
        duree_media = len(audio) / 16000.0
        if duree_media < 0.5:
            raise RuntimeError("Aucun son exploitable dans ce fichier (piste audio vide ou absente).")
        self.log(f"Audio extrait via {decodeur} en {time.time() - t0:.1f} s — durée : {format_duree(duree_media)}.")
        if self.annuler.is_set():
            raise Annule()

        estimation = duree_media * MODELES.get(nom_modele, {}).get("rtf", 0.4)
        self.log(f"Estimation initiale sur Ryzen 5 5500 : ~{format_duree(estimation)} (affinée en direct).")
        self.envoyer("statut", "Transcription en cours… (détection des silences)")
        self.envoyer("progression", 0.0)
        self.envoyer("eta", f"Temps restant estimé : ~{format_duree(estimation)}")

        # --- Transcription (paramètres optimisés CPU)
        t_debut = time.time()
        segments_gen, info = modele.transcribe(
            audio,
            language=langue,          # "fr" forcé = pas de détection = plus rapide
            task="transcribe",
            beam_size=1,              # décodage glouton : ~2x plus rapide que beam 5
            best_of=1,
            vad_filter=True,          # saute les silences (gain 10-30 %)
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,  # évite les boucles/répétitions
        )
        if langue is None:
            self.log(f"Langue détectée : {info.language} (confiance {info.language_probability:.0%}).")
        duree = info.duration or duree_media

        resultats = []
        for seg in segments_gen:
            if self.annuler.is_set():
                raise Annule()
            texte = seg.text.strip()
            if not texte:
                continue
            resultats.append((seg.start, seg.end, texte))
            self.envoyer("segment", f"[{format_horodatage(seg.start)[:8]} → {format_horodatage(seg.end)[:8]}]  {texte}\n")

            # Progression réelle = position du segment / durée totale
            p = min(seg.end / duree, 1.0) if duree else 0.0
            ecoule = time.time() - t_debut
            self.envoyer("progression", p)
            if p > 0.02:
                restant = ecoule * (1 - p) / p
                vitesse = (seg.end / ecoule) if ecoule > 0 else 0
                self.envoyer("eta", f"Temps restant : ~{format_duree(restant)}   •   vitesse x{vitesse:.1f}")
            self.envoyer("statut", f"Transcription… {p:.0%}  ({format_duree(ecoule)} écoulées)")

        total = time.time() - t_debut
        if not resultats:
            self.log("⚠  Aucune parole détectée dans ce fichier.")

        # --- Exports
        fichiers = ecrire_exports(chemin, resultats, reglages["vtt"])
        rtf = total / duree_media if duree_media else 0
        self.envoyer("progression", 1.0)
        self.envoyer("eta", f"Terminé en {format_duree(total)}")
        self.envoyer("statut", f"✅ Terminé : {nom_fichier}")
        self.log(f"✅ Terminé en {format_duree(total)} pour {format_duree(duree_media)} de média "
                 f"(facteur {rtf:.2f} → 50 min de vidéo ≈ {format_duree(rtf * 3000)} avec ce modèle).")
        for f in fichiers:
            self.log(f"   💾 {f}")
        self.envoyer("termine", str(fichiers[0].parent))


# ---------------------------------------------------------------------------
# 4. Surveillance de dossier (simple, robuste, sans dépendance)
# ---------------------------------------------------------------------------
class SurveillantDossier(threading.Thread):
    """
    Scrute un dossier toutes les 3 s. Un nouveau fichier média est envoyé en
    transcription quand sa taille ne bouge plus (copie terminée) et qu'il
    n'est plus verrouillé par Windows.
    """

    INTERVALLE = 3.0

    def __init__(self, dossier: str, rappel, log):
        super().__init__(daemon=True, name="SurveillantDossier")
        self.dossier = Path(dossier)
        self.rappel = rappel   # fonction(chemin) appelée pour chaque nouveau fichier
        self.log = log
        self.stop = threading.Event()
        self.connus = set()    # fichiers déjà présents ou déjà envoyés
        self.en_attente = {}   # chemin -> (taille, nb de mesures stables)

    def _medias(self):
        try:
            return {str(p) for p in self.dossier.iterdir()
                    if p.is_file() and p.suffix.lower() in EXTENSIONS}
        except OSError as e:
            self.log(f"⚠  Dossier surveillé inaccessible : {e}")
            return set()

    @staticmethod
    def _deverrouille(chemin: str) -> bool:
        try:
            with open(chemin, "rb"):
                return True
        except OSError:
            return False

    def run(self) -> None:
        # Les fichiers déjà présents au démarrage sont ignorés (seuls les
        # nouveaux dépôts sont transcrits).
        self.connus = self._medias()
        self.log(f"👁  Surveillance active : {self.dossier}  ({len(self.connus)} fichier(s) existant(s) ignoré(s))")
        while not self.stop.wait(self.INTERVALLE):
            actuels = self._medias()
            self.connus &= actuels  # un fichier supprimé puis redéposé sera retraité
            for chemin in actuels - self.connus:
                try:
                    taille = os.path.getsize(chemin)
                except OSError:
                    continue
                ancienne, stable = self.en_attente.get(chemin, (-1, 0))
                stable = stable + 1 if (taille == ancienne and taille > 0) else 0
                self.en_attente[chemin] = (taille, stable)
                if stable >= 1 and self._deverrouille(chemin):
                    self.connus.add(chemin)
                    self.en_attente.pop(chemin, None)
                    self.log(f"📥 Nouveau fichier détecté : {Path(chemin).name}")
                    self.rappel(chemin)
        self.log("Surveillance arrêtée.")


# ---------------------------------------------------------------------------
# 5. Interface graphique
# ---------------------------------------------------------------------------
BaseFenetre = ctk.CTk
if DND_DISPONIBLE:
    class BaseFenetre(ctk.CTk, TkinterDnD.DnDWrapper):  # type: ignore[no-redef]
        """Fenêtre CustomTkinter + support natif du glisser-déposer."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_ok = True
            except Exception as e:  # tkdnd introuvable : on continue sans
                self.dnd_ok = False
                self.dnd_erreur = str(e)

# Palette inspirée de macOS (mode sombre)
COUL_FOND = "#1c1c1e"
COUL_PANNEAU = "#2c2c2e"
COUL_CARTE = "#242426"
COUL_BORD = "#3a3a3c"
COUL_ACCENT = "#0a84ff"
COUL_TEXTE2 = "#98989d"
COUL_VERT = "#30d158"
COUL_ROUGE = "#ff453a"


class Application(BaseFenetre):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()
        if not hasattr(self, "dnd_ok"):
            self.dnd_ok = False

        self.title(f"{APP_NOM} — transcription 100 % hors-ligne")
        self.geometry("1180x780")
        self.minsize(980, 660)
        self.configure(fg_color=COUL_FOND)

        self.evenements: "queue.Queue" = queue.Queue()
        self.moteur = MoteurTranscription(self.evenements)
        self.moteur.start()
        self.surveillant = None
        self.dossier_surveille = None
        self.dernier_dossier_sortie = None
        self.moteur_ok = None  # None = vérification en cours

        self._construire_sidebar()
        self._construire_zone_principale()

        self.protocol("WM_DELETE_WINDOW", self.quitter)
        self.after(100, self._lire_evenements)
        self.after(300, self._verifications_demarrage)

    # ======================================================================
    # Construction de l'interface
    # ======================================================================
    def _construire_sidebar(self):
        sb = ctk.CTkFrame(self, width=290, corner_radius=0, fg_color=COUL_PANNEAU)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        ctk.CTkLabel(sb, text="🎙  Malle", font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w", padx=22, pady=(26, 0))
        ctk.CTkLabel(sb, text="Transcriber  •  100 % hors-ligne", text_color=COUL_TEXTE2,
                     font=ctk.CTkFont(size=13)).pack(anchor="w", padx=22, pady=(0, 20))

        def titre(t):
            ctk.CTkLabel(sb, text=t.upper(), text_color=COUL_TEXTE2,
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=22, pady=(14, 4))

        # --- Modèle
        titre("Modèle Whisper")
        self.var_modele = ctk.StringVar(value=MODELE_DEFAUT)
        ctk.CTkOptionMenu(sb, values=list(MODELES), variable=self.var_modele, width=246,
                          command=self._maj_desc_modele).pack(padx=22)
        self.lbl_desc_modele = ctk.CTkLabel(sb, text="", text_color=COUL_TEXTE2, wraplength=240,
                                            justify="left", font=ctk.CTkFont(size=12))
        self.lbl_desc_modele.pack(anchor="w", padx=22, pady=(4, 0))
        self._maj_desc_modele(MODELE_DEFAUT)

        # --- Langue
        titre("Langue de la vidéo")
        self.var_langue = ctk.StringVar(value=LANGUE_DEFAUT)
        ctk.CTkOptionMenu(sb, values=list(LANGUES), variable=self.var_langue, width=246).pack(padx=22)

        # --- Threads
        titre("Processeur")
        self.var_threads = ctk.StringVar(value=THREADS_DEFAUT)
        ctk.CTkSegmentedButton(sb, values=list(THREADS), variable=self.var_threads, width=246).pack(padx=22)

        # --- Exports
        titre("Exports")
        ctk.CTkLabel(sb, text="✓ .SRT et .TXT créés à côté de la vidéo", text_color=COUL_TEXTE2,
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=22)
        self.var_vtt = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(sb, text="Créer aussi un .VTT", variable=self.var_vtt).pack(anchor="w", padx=22, pady=(6, 0))

        # --- Dossier surveillé
        titre("Dossier surveillé")
        ctk.CTkButton(sb, text="📁  Choisir un dossier…", width=246, fg_color=COUL_BORD,
                      hover_color="#48484a", command=self.choisir_dossier_surveille).pack(padx=22)
        self.lbl_dossier = ctk.CTkLabel(sb, text="Aucun dossier", text_color=COUL_TEXTE2, wraplength=240,
                                        justify="left", font=ctk.CTkFont(size=12))
        self.lbl_dossier.pack(anchor="w", padx=22, pady=(4, 0))
        self.var_surveillance = ctk.BooleanVar(value=False)
        self.sw_surveillance = ctk.CTkSwitch(sb, text="Surveillance active", variable=self.var_surveillance,
                                             command=self.basculer_surveillance, progress_color=COUL_VERT)
        self.sw_surveillance.pack(anchor="w", padx=22, pady=(6, 0))

        # --- Bas de la sidebar : état du système
        bas = ctk.CTkFrame(sb, fg_color="transparent")
        bas.pack(side="bottom", fill="x", padx=22, pady=18)
        self.lbl_moteur = ctk.CTkLabel(bas, text="● Moteur : vérification…", text_color=COUL_TEXTE2,
                                       font=ctk.CTkFont(size=12), anchor="w")
        self.lbl_moteur.pack(fill="x")
        self.lbl_ffmpeg = ctk.CTkLabel(bas, text="● ffmpeg : …", text_color=COUL_TEXTE2,
                                       font=ctk.CTkFont(size=12), anchor="w")
        self.lbl_ffmpeg.pack(fill="x")
        self.btn_install_ffmpeg = ctk.CTkButton(bas, text="Installer ffmpeg (winget)", height=26,
                                                fg_color=COUL_BORD, hover_color="#48484a",
                                                command=self.installer_ffmpeg)
        ctk.CTkLabel(bas, text=f"v{APP_VERSION}", text_color="#636366",
                     font=ctk.CTkFont(size=11), anchor="w").pack(fill="x", pady=(6, 0))

    def _construire_zone_principale(self):
        zone = ctk.CTkFrame(self, fg_color="transparent")
        zone.pack(side="left", fill="both", expand=True, padx=22, pady=22)

        # --- Zone de dépôt
        self.zone_depot = ctk.CTkFrame(zone, height=150, corner_radius=18, fg_color=COUL_CARTE,
                                       border_width=2, border_color=COUL_BORD)
        self.zone_depot.pack(fill="x")
        self.zone_depot.pack_propagate(False)
        self.lbl_depot = ctk.CTkLabel(
            self.zone_depot,
            text="⬇  Glissez-déposez vos vidéos ici" if self.dnd_ok else "Glisser-déposer indisponible",
            font=ctk.CTkFont(size=19, weight="bold"))
        self.lbl_depot.pack(pady=(30, 4))
        ctk.CTkLabel(self.zone_depot, text="MP4 · MOV · MKV · MP3 · WAV · M4A", text_color=COUL_TEXTE2).pack()
        ctk.CTkButton(self.zone_depot, text="Choisir une vidéo", width=200, height=34, corner_radius=17,
                      fg_color=COUL_ACCENT, command=self.choisir_fichiers).pack(pady=(10, 0))

        if self.dnd_ok:
            for w in (self, self.zone_depot, self.lbl_depot):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self.sur_depot)
                    w.dnd_bind("<<DropEnter>>", lambda e: (self.zone_depot.configure(border_color=COUL_ACCENT), e.action)[1])
                    w.dnd_bind("<<DropLeave>>", lambda e: (self.zone_depot.configure(border_color=COUL_BORD), e.action)[1])
                except Exception:
                    pass

        # --- Carte de progression
        carte = ctk.CTkFrame(zone, corner_radius=18, fg_color=COUL_CARTE)
        carte.pack(fill="x", pady=(16, 0))
        haut = ctk.CTkFrame(carte, fg_color="transparent")
        haut.pack(fill="x", padx=20, pady=(16, 6))
        self.lbl_fichier = ctk.CTkLabel(haut, text="Aucun fichier en cours", font=ctk.CTkFont(size=15, weight="bold"),
                                        anchor="w")
        self.lbl_fichier.pack(side="left", fill="x", expand=True)
        self.btn_ouvrir = ctk.CTkButton(haut, text="Ouvrir le dossier", width=140, fg_color=COUL_BORD,
                                        hover_color="#48484a", state="disabled", command=self.ouvrir_sortie)
        self.btn_ouvrir.pack(side="right", padx=(8, 0))
        self.btn_annuler = ctk.CTkButton(haut, text="Annuler", width=100, fg_color=COUL_ROUGE,
                                         hover_color="#d63a31", state="disabled", command=self.annuler)
        self.btn_annuler.pack(side="right")

        self.barre = ctk.CTkProgressBar(carte, height=10, corner_radius=5, progress_color=COUL_ACCENT)
        self.barre.pack(fill="x", padx=20)
        self.barre.set(0)
        self.barre_indeterminee = False

        bas = ctk.CTkFrame(carte, fg_color="transparent")
        bas.pack(fill="x", padx=20, pady=(6, 14))
        self.lbl_statut = ctk.CTkLabel(bas, text="Prêt.", text_color=COUL_TEXTE2, anchor="w")
        self.lbl_statut.pack(side="left")
        self.lbl_eta = ctk.CTkLabel(bas, text="", text_color=COUL_TEXTE2, anchor="e")
        self.lbl_eta.pack(side="right")

        # --- Onglets : transcription + journal
        onglets = ctk.CTkTabview(zone, corner_radius=18, fg_color=COUL_CARTE,
                                 segmented_button_selected_color=COUL_ACCENT)
        onglets.pack(fill="both", expand=True, pady=(16, 0))
        onglets.add("Transcription")
        onglets.add("Journal")
        self.onglets = onglets

        self.txt_transcription = ctk.CTkTextbox(onglets.tab("Transcription"), wrap="word",
                                                font=ctk.CTkFont(size=14), fg_color=COUL_FOND)
        self.txt_transcription.pack(fill="both", expand=True)
        outils = ctk.CTkFrame(onglets.tab("Transcription"), fg_color="transparent")
        outils.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(outils, text="Copier tout", width=110, fg_color=COUL_BORD, hover_color="#48484a",
                      command=self.copier_transcription).pack(side="right")
        ctk.CTkButton(outils, text="Effacer", width=90, fg_color=COUL_BORD, hover_color="#48484a",
                      command=lambda: self.txt_transcription.delete("1.0", "end")).pack(side="right", padx=8)

        self.txt_journal = ctk.CTkTextbox(onglets.tab("Journal"), wrap="word",
                                          font=ctk.CTkFont(family="Consolas", size=12), fg_color=COUL_FOND)
        self.txt_journal.pack(fill="both", expand=True)

    # ======================================================================
    # Démarrage : vérifications du système
    # ======================================================================
    def _verifications_demarrage(self):
        self.log(f"{APP_NOM} v{APP_VERSION} — journal : {FICHIER_LOG}")
        if not self.dnd_ok:
            self.log("⚠  Glisser-déposer indisponible (tkdnd non chargé). Utilisez le bouton « Choisir une vidéo ».")

        ff = self.moteur.ffmpeg
        if ff:
            self.lbl_ffmpeg.configure(text="● ffmpeg : OK", text_color=COUL_VERT)
            self.log(f"ffmpeg trouvé : {ff}")
        else:
            self.lbl_ffmpeg.configure(text="● ffmpeg : décodeur intégré", text_color="#ffd60a")
            self.log("ℹ  ffmpeg.exe introuvable : utilisation du décodeur intégré (PyAV). "
                     "La plupart des fichiers fonctionnent quand même. Pour une compatibilité "
                     "maximale, cliquez sur « Installer ffmpeg (winget) ».")
            self.btn_install_ffmpeg.pack(fill="x", pady=(4, 0))

        # L'import de CTranslate2 prend 1-2 s : on le fait hors du thread UI
        def verif():
            ok, msg = verifier_moteur()
            self.evenements.put(("moteur", (ok, msg)))
        threading.Thread(target=verif, daemon=True).start()

    def installer_ffmpeg(self):
        if os.name != "nt":
            messagebox.showinfo(APP_NOM, "Installation automatique disponible uniquement sous Windows.")
            return
        if not shutil.which("winget"):
            messagebox.showerror(APP_NOM, "winget est introuvable sur ce PC.\n\n"
                                 "Téléchargez ffmpeg sur https://www.gyan.dev/ffmpeg/builds/ "
                                 "et placez ffmpeg.exe à côté de MalleTranscriber.exe.")
            return
        if not messagebox.askyesno(APP_NOM, "Installer ffmpeg via winget (Internet requis, ~1 min) ?"):
            return
        self.btn_install_ffmpeg.configure(state="disabled", text="Installation en cours…")
        self.log("Installation de ffmpeg via winget…")

        def tache():
            try:
                p = subprocess.run(
                    ["winget", "install", "-e", "--id", "Gyan.FFmpeg",
                     "--accept-source-agreements", "--accept-package-agreements", "--silent"],
                    capture_output=True, text=True, errors="replace", creationflags=CREATE_NO_WINDOW)
                sortie = (p.stdout or "")[-500:] + (p.stderr or "")[-300:]
            except Exception as e:
                sortie = str(e)
            self.evenements.put(("ffmpeg_installe", sortie))
        threading.Thread(target=tache, daemon=True).start()

    # ======================================================================
    # Actions utilisateur
    # ======================================================================
    def _maj_desc_modele(self, nom):
        m = MODELES[nom]
        self.lbl_desc_modele.configure(
            text=f"{m['desc']}\n~{format_duree(m['rtf'] * 3000)} pour 50 min • {m['taille_mo']} Mo")

    def reglages(self) -> dict:
        return {
            "modele": self.var_modele.get(),
            "langue": LANGUES[self.var_langue.get()],
            "threads": THREADS[self.var_threads.get()],
            "vtt": bool(self.var_vtt.get()),
        }

    def ajouter_fichiers(self, chemins):
        if self.moteur_ok is False:
            messagebox.showerror(APP_NOM, "Le moteur de transcription n'a pas pu démarrer.\n"
                                 "Consultez l'onglet Journal pour la solution.")
            return
        ajoutes = 0
        for c in chemins:
            p = Path(c)
            if p.is_dir():
                self.log(f"⚠  « {p.name} » est un dossier : utilisez « Dossier surveillé » pour les dossiers.")
                continue
            if p.suffix.lower() not in EXTENSIONS:
                self.log(f"⚠  Format non pris en charge ignoré : {p.name}")
                continue
            self.moteur.ajouter(str(p), self.reglages())
            ajoutes += 1
            self.log(f"➕ Ajouté à la file : {p.name}")
        if ajoutes:
            self.btn_annuler.configure(state="normal")
            restant = self.moteur.travaux.qsize()
            if restant > 1:
                self.lbl_statut.configure(text=f"{restant} fichier(s) en attente")

    def choisir_fichiers(self):
        chemins = filedialog.askopenfilenames(
            title="Choisir une ou plusieurs vidéos",
            filetypes=[("Vidéos et audios", " ".join(f"*{e}" for e in sorted(EXTENSIONS))),
                       ("Tous les fichiers", "*.*")])
        if chemins:
            self.ajouter_fichiers(chemins)

    def sur_depot(self, event):
        self.zone_depot.configure(border_color=COUL_BORD)
        try:
            chemins = self.tk.splitlist(event.data)
        except Exception:
            chemins = [event.data]
        self.ajouter_fichiers(chemins)
        return event.action

    def annuler(self):
        n = self.moteur.tout_annuler()
        self.log(f"Annulation demandée{f' ({n} fichier(s) retiré(s) de la file)' if n else ''}…")
        self.lbl_statut.configure(text="Annulation…")

    def ouvrir_sortie(self):
        if self.dernier_dossier_sortie:
            try:
                ouvrir_dans_explorateur(self.dernier_dossier_sortie)
            except Exception as e:
                self.log(f"Impossible d'ouvrir le dossier : {e}")

    def copier_transcription(self):
        self.clipboard_clear()
        self.clipboard_append(self.txt_transcription.get("1.0", "end"))
        self.lbl_statut.configure(text="Transcription copiée dans le presse-papiers.")

    def choisir_dossier_surveille(self):
        d = filedialog.askdirectory(title="Dossier à surveiller")
        if not d:
            return
        self.dossier_surveille = d
        self.lbl_dossier.configure(text=d)
        self.var_surveillance.set(True)
        self.basculer_surveillance()

    def basculer_surveillance(self):
        # Arrêt de l'éventuel surveillant en cours
        if self.surveillant:
            self.surveillant.stop.set()
            self.surveillant = None
        if not self.var_surveillance.get():
            return
        if not self.dossier_surveille:
            self.var_surveillance.set(False)
            messagebox.showinfo(APP_NOM, "Choisissez d'abord un dossier à surveiller.")
            return
        self.surveillant = SurveillantDossier(
            self.dossier_surveille,
            rappel=lambda c: self.evenements.put(("auto_fichier", c)),
            log=lambda t: self.evenements.put(("log", t)))
        self.surveillant.start()

    def quitter(self):
        if self.moteur.travaux.qsize() or self.btn_annuler.cget("state") == "normal":
            if not messagebox.askyesno(APP_NOM, "Une transcription est en cours. Quitter quand même ?"):
                return
        self.moteur.tout_annuler()
        if self.surveillant:
            self.surveillant.stop.set()
        self.destroy()

    # ======================================================================
    # Journal & boucle d'événements
    # ======================================================================
    def log(self, texte: str):
        log_fichier(texte)
        self._ecrire_journal(texte)

    def _ecrire_journal(self, texte: str):
        self.txt_journal.insert("end", f"{datetime.now():%H:%M:%S}  {texte}\n")
        self.txt_journal.see("end")

    def _barre(self, valeur):
        """valeur None = animation indéterminée, sinon 0..1."""
        if valeur is None:
            if not self.barre_indeterminee:
                self.barre.configure(mode="indeterminate")
                self.barre.start()
                self.barre_indeterminee = True
        else:
            if self.barre_indeterminee:
                self.barre.stop()
                self.barre.configure(mode="determinate")
                self.barre_indeterminee = False
            self.barre.set(valeur)

    def _lire_evenements(self):
        try:
            for _ in range(200):  # on vide par paquets pour garder l'UI fluide
                type_evt, val = self.evenements.get_nowait()
                if type_evt == "log":
                    self._ecrire_journal(val)
                elif type_evt == "statut":
                    self.lbl_statut.configure(text=val)
                elif type_evt == "eta":
                    self.lbl_eta.configure(text=val)
                elif type_evt == "progression":
                    self._barre(val)
                elif type_evt == "segment":
                    self.txt_transcription.insert("end", val)
                    self.txt_transcription.see("end")
                elif type_evt == "nouveau_fichier":
                    self.lbl_fichier.configure(text=f"🎬  {val}")
                    self.txt_transcription.insert("end", f"\n━━━━━━━━  {val}  ━━━━━━━━\n")
                    self.onglets.set("Transcription")
                elif type_evt == "occupe":
                    self.btn_annuler.configure(state="normal" if val else "disabled")
                    if not val:
                        self._barre(self.barre.get())
                elif type_evt == "restant":
                    if val:
                        self.log(f"{val} fichier(s) encore en attente.")
                elif type_evt == "termine":
                    self.dernier_dossier_sortie = val
                    self.btn_ouvrir.configure(state="normal")
                elif type_evt == "auto_fichier":
                    self.ajouter_fichiers([val])
                elif type_evt == "moteur":
                    ok, msg = val
                    self.moteur_ok = ok
                    self.log(("✅ " if ok else "❌ ") + msg)
                    if ok:
                        self.lbl_moteur.configure(text="● Moteur : prêt", text_color=COUL_VERT)
                    else:
                        self.lbl_moteur.configure(text="● Moteur : ERREUR", text_color=COUL_ROUGE)
                        self.onglets.set("Journal")
                        messagebox.showerror(APP_NOM, msg)
                elif type_evt == "ffmpeg_installe":
                    self.log(f"Résultat winget : {val.strip()}")
                    self.moteur.ffmpeg = trouver_ffmpeg()
                    if self.moteur.ffmpeg:
                        self.lbl_ffmpeg.configure(text="● ffmpeg : OK", text_color=COUL_VERT)
                        self.btn_install_ffmpeg.pack_forget()
                        self.log(f"✅ ffmpeg installé : {self.moteur.ffmpeg}")
                    else:
                        self.btn_install_ffmpeg.configure(state="normal", text="Installer ffmpeg (winget)")
                        self.log("⚠  ffmpeg toujours introuvable. Redémarrez l'application, "
                                 "ou placez ffmpeg.exe à côté de MalleTranscriber.exe.")
        except queue.Empty:
            pass
        except Exception as e:
            self.log(f"Erreur interface : {e!r}")
            log_fichier(traceback.format_exc())
        self.after(100, self._lire_evenements)

    # Toute exception dans un callback Tk finit dans le journal, pas dans le vide
    def report_callback_exception(self, exc, val, tb):
        texte = "".join(traceback.format_exception(exc, val, tb))
        log_fichier(texte)
        try:
            self._ecrire_journal(f"❌ Erreur inattendue : {val}\n{texte}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 6. Point d'entrée
# ---------------------------------------------------------------------------
def main():
    def crash(exc, val, tb):
        texte = "".join(traceback.format_exception(exc, val, tb))
        log_fichier("CRASH:\n" + texte)
        try:
            messagebox.showerror(APP_NOM, f"Erreur fatale :\n{val}\n\nDétails dans :\n{FICHIER_LOG}")
        except Exception:
            pass

    sys.excepthook = crash
    try:
        app = Application()
        app.mainloop()
    except Exception:
        crash(*sys.exc_info())
        sys.exit(1)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
