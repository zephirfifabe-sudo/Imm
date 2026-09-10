import path from "node:path";
import fs from "node:fs";
import multer from "multer";

export const UPLOADS_DIR = path.join(process.cwd(), "uploads");

if (!fs.existsSync(UPLOADS_DIR)) {
  fs.mkdirSync(UPLOADS_DIR, { recursive: true });
}

/**
 * Réception des photos en mémoire (compression + redimensionnement géré
 * ensuite par le service vision avant stockage disque). Limite 8 Mo/photo,
 * 10 photos max par analyse — suffisant pour extérieur + pièces principales.
 *
 * Note MVP : stockage disque local. À remplacer par un bucket objet
 * (S3-compatible) lors du passage en environnement multi-instance.
 */
export const photoUpload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 8 * 1024 * 1024, files: 10 },
  fileFilter: (_req, file, callback) => {
    if (!file.mimetype.startsWith("image/")) {
      callback(new Error("Seuls les fichiers image sont acceptés."));
      return;
    }
    callback(null, true);
  },
});
