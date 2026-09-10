import path from "node:path";
import fs from "node:fs/promises";
import crypto from "node:crypto";
import sharp from "sharp";
import { UPLOADS_DIR } from "../../middleware/upload.middleware";
import type { PhotoForAnalysis } from "../vision/vision.service";

export interface ProcessedPhoto {
  /** URL relative servie par le backend (/uploads/xxx.jpg). */
  url: string;
  forVision: PhotoForAnalysis;
}

/**
 * Compresse et redimensionne chaque photo avant stockage et avant envoi à
 * l'IA vision (économise bande passante et coût API, sans perte visuelle
 * significative pour évaluer l'état général d'une pièce).
 */
export async function processUploadedPhotos(
  files: Express.Multer.File[],
): Promise<ProcessedPhoto[]> {
  return Promise.all(
    files.map(async (file) => {
      const compressed = await sharp(file.buffer)
        .rotate()
        .resize({ width: 1600, height: 1600, fit: "inside", withoutEnlargement: true })
        .jpeg({ quality: 78 })
        .toBuffer();

      const filename = `${crypto.randomUUID()}.jpg`;
      await fs.writeFile(path.join(UPLOADS_DIR, filename), compressed);

      return {
        url: `/uploads/${filename}`,
        forVision: { base64: compressed.toString("base64"), mimeType: "image/jpeg" as const },
      };
    }),
  );
}
