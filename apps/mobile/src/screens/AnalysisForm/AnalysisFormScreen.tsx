import { useState } from "react";
import { Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { z } from "zod";
import type { EnergyClass, EnergyStandard, PropertyType } from "@previsite/shared";
import { ScreenContainer } from "../../components/ScreenContainer";
import { FormField, TextField } from "../../components/FormField";
import { SegmentedChoice } from "../../components/SegmentedChoice";
import { PhotoPicker } from "../../components/PhotoPicker";
import { PrimaryButton } from "../../components/PrimaryButton";
import { submitAnalysis, type PickedPhoto } from "../../services/api/analyses.api";
import { ApiRequestError } from "../../services/api/client";
import { colors, spacing, typography } from "../../theme";
import type { RootStackParamList } from "../../navigation/types";

type Props = NativeStackScreenProps<RootStackParamList, "AnalysisForm">;

const PROPERTY_TYPE_OPTIONS: { label: string; value: PropertyType }[] = [
  { label: "Maison", value: "maison" },
  { label: "Appartement", value: "appartement" },
  { label: "Studio", value: "studio" },
  { label: "Terrain", value: "terrain" },
];

const ENERGY_STANDARD_OPTIONS: { label: string; value: EnergyStandard }[] = [
  { label: "PEB (Belgique)", value: "PEB" },
  { label: "DPE (France)", value: "DPE" },
];

const ENERGY_CLASS_OPTIONS: { label: string; value: EnergyClass }[] = (
  ["A", "B", "C", "D", "E", "F", "G"] as const
).map((value) => ({ label: value, value }));

const formSchema = z.object({
  propertyType: z.enum(["maison", "appartement", "studio", "terrain"]),
  askingPrice: z.coerce.number({ invalid_type_error: "Indique un prix valide." }).positive("Le prix doit être supérieur à 0."),
  livingAreaM2: z
    .union([z.coerce.number().positive("La surface doit être supérieure à 0."), z.literal("")])
    .optional(),
  commune: z.string().min(2, "Indique la commune du bien."),
  postalCode: z.string().regex(/^\d{4,5}$/, "Code postal invalide."),
  countryCode: z.enum(["BE", "FR"]),
});

export function AnalysisFormScreen({ navigation }: Props) {
  const [propertyType, setPropertyType] = useState<PropertyType>("maison");
  const [askingPrice, setAskingPrice] = useState("");
  const [livingAreaM2, setLivingAreaM2] = useState("");
  const [commune, setCommune] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [countryCode, setCountryCode] = useState<"BE" | "FR">("BE");
  const [energyStandard, setEnergyStandard] = useState<EnergyStandard | undefined>("PEB");
  const [energyClass, setEnergyClass] = useState<EnergyClass | undefined>(undefined);
  const [photos, setPhotos] = useState<PickedPhoto[]>([]);

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setFormError(null);

    if (photos.length === 0) {
      setFormError("Ajoute au moins une photo du bien pour lancer l'analyse.");
      return;
    }

    const parsed = formSchema.safeParse({
      propertyType,
      askingPrice,
      livingAreaM2: livingAreaM2 || "",
      commune,
      postalCode,
      countryCode,
    });

    if (!parsed.success) {
      const errors: Record<string, string> = {};
      parsed.error.issues.forEach((issue) => {
        errors[String(issue.path[0])] = issue.message;
      });
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});
    setSubmitting(true);

    try {
      const { analysis } = await submitAnalysis({
        propertyType: parsed.data.propertyType,
        askingPrice: String(parsed.data.askingPrice),
        livingAreaM2: parsed.data.livingAreaM2 ? String(parsed.data.livingAreaM2) : "",
        commune: parsed.data.commune,
        postalCode: parsed.data.postalCode,
        countryCode: parsed.data.countryCode,
        energyStandard,
        energyClass,
        photos,
      });
      navigation.replace("AnalysisResult", { analysis });
    } catch (error) {
      setFormError(
        error instanceof ApiRequestError ? error.message : "L'analyse n'a pas pu être lancée.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ScreenContainer>
      <View style={{ gap: spacing.xs }}>
        <Text style={typography.h2}>Analyser un bien</Text>
        <Text style={[typography.body, { color: colors.textSecondary }]}>
          Plus tu donnes d'informations, plus l'analyse sera précise.
        </Text>
      </View>

      <FormField label="Type de bien" required>
        <SegmentedChoice
          accessibilityLabel="Type de bien"
          options={PROPERTY_TYPE_OPTIONS}
          value={propertyType}
          onChange={setPropertyType}
        />
      </FormField>

      <FormField label="Prix demandé (€)" error={fieldErrors.askingPrice} required>
        <TextField
          value={askingPrice}
          onChangeText={setAskingPrice}
          keyboardType="numeric"
          placeholder="Ex: 245000"
        />
      </FormField>

      <FormField label="Surface habitable (m²)" error={fieldErrors.livingAreaM2}>
        <TextField
          value={livingAreaM2}
          onChangeText={setLivingAreaM2}
          keyboardType="numeric"
          placeholder="Ex: 120 (si connue)"
        />
      </FormField>

      <FormField label="Commune" error={fieldErrors.commune} required>
        <TextField value={commune} onChangeText={setCommune} placeholder="Ex: Namur" />
      </FormField>

      <FormField label="Code postal" error={fieldErrors.postalCode} required>
        <TextField
          value={postalCode}
          onChangeText={setPostalCode}
          keyboardType="numeric"
          placeholder="Ex: 5000"
        />
      </FormField>

      <FormField label="Pays" required>
        <SegmentedChoice
          accessibilityLabel="Pays"
          options={[
            { label: "Belgique", value: "BE" as const },
            { label: "France", value: "FR" as const },
          ]}
          value={countryCode}
          onChange={setCountryCode}
        />
      </FormField>

      <FormField label="Norme énergétique">
        <SegmentedChoice
          accessibilityLabel="Norme énergétique"
          options={ENERGY_STANDARD_OPTIONS}
          value={energyStandard}
          onChange={setEnergyStandard}
        />
      </FormField>

      <FormField label="Classe énergétique (PEB/DPE)">
        <SegmentedChoice
          accessibilityLabel="Classe énergétique"
          options={ENERGY_CLASS_OPTIONS}
          value={energyClass}
          onChange={setEnergyClass}
        />
      </FormField>

      <FormField label="Photos du bien" required>
        <Text style={[typography.caption, { color: colors.textSecondary }]}>
          Extérieur, cuisine, salle de bain, pièces principales, toiture si visible.
        </Text>
        <PhotoPicker photos={photos} onChange={setPhotos} />
      </FormField>

      {formError ? (
        <Text style={{ color: colors.danger }} accessibilityRole="alert">
          {formError}
        </Text>
      ) : null}

      <PrimaryButton
        label="Lancer l'analyse"
        onPress={handleSubmit}
        loading={isSubmitting}
      />
    </ScreenContainer>
  );
}
