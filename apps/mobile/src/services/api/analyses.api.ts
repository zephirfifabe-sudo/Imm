import type { AnalysisRecord, EnergyClass, EnergyStandard, PropertyType } from "@previsite/shared";
import { apiClient } from "./client";

export interface PickedPhoto {
  uri: string;
  fileName: string;
  mimeType: string;
}

export interface AnalysisFormValues {
  propertyType: PropertyType;
  askingPrice: string;
  livingAreaM2: string;
  commune: string;
  postalCode: string;
  countryCode: "BE" | "FR";
  energyStandard?: EnergyStandard;
  energyClass?: EnergyClass;
  photos: PickedPhoto[];
}

export function submitAnalysis(values: AnalysisFormValues) {
  const formData = new FormData();
  formData.append("propertyType", values.propertyType);
  formData.append("askingPrice", values.askingPrice);
  if (values.livingAreaM2) formData.append("livingAreaM2", values.livingAreaM2);
  formData.append("commune", values.commune);
  formData.append("postalCode", values.postalCode);
  formData.append("countryCode", values.countryCode);
  if (values.energyStandard) formData.append("energyStandard", values.energyStandard);
  if (values.energyClass) formData.append("energyClass", values.energyClass);

  values.photos.forEach((photo, index) => {
    // FormData accepte cet objet "fichier" en React Native (uri + name + type).
    formData.append("photos", {
      uri: photo.uri,
      name: photo.fileName || `photo-${index}.jpg`,
      type: photo.mimeType || "image/jpeg",
    } as unknown as Blob);
  });

  return apiClient.postForm<{ analysis: AnalysisRecord }>("/api/analyses", formData);
}

export function fetchAnalysisHistory() {
  return apiClient.get<{ analyses: AnalysisRecord[] }>("/api/analyses");
}

export function fetchAnalysis(id: string) {
  return apiClient.get<{ analysis: AnalysisRecord }>(`/api/analyses/${id}`);
}
