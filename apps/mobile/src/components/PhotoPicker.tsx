import { useCallback } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { colors, radii, spacing, typography } from "../theme";
import type { PickedPhoto } from "../services/api/analyses.api";

interface Props {
  photos: PickedPhoto[];
  onChange: (photos: PickedPhoto[]) => void;
  maxPhotos?: number;
}

function toPickedPhoto(asset: ImagePicker.ImagePickerAsset): PickedPhoto {
  return {
    uri: asset.uri,
    fileName: asset.fileName ?? `photo-${Date.now()}.jpg`,
    mimeType: asset.mimeType ?? "image/jpeg",
  };
}

/** Sélection de photos (galerie ou appareil photo), avec compression légère avant envoi. */
export function PhotoPicker({ photos, onChange, maxPhotos = 10 }: Props) {
  const remainingSlots = maxPhotos - photos.length;

  const pickFromLibrary = useCallback(async () => {
    if (remainingSlots <= 0) return;

    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert(
        "Accès à la galerie refusé",
        "Autorise l'accès aux photos dans les réglages pour ajouter des images du bien.",
      );
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsMultipleSelection: true,
      selectionLimit: remainingSlots,
      quality: 0.7,
    });

    if (!result.canceled) {
      onChange([...photos, ...result.assets.map(toPickedPhoto)]);
    }
  }, [photos, onChange, remainingSlots]);

  const takePhoto = useCallback(async () => {
    if (remainingSlots <= 0) return;

    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      Alert.alert(
        "Accès à l'appareil photo refusé",
        "Autorise l'accès à l'appareil photo dans les réglages pour prendre une photo du bien.",
      );
      return;
    }

    const result = await ImagePicker.launchCameraAsync({ quality: 0.7 });
    if (!result.canceled) {
      onChange([...photos, ...result.assets.map(toPickedPhoto)]);
    }
  }, [photos, onChange, remainingSlots]);

  const removePhoto = useCallback(
    (uri: string) => onChange(photos.filter((photo) => photo.uri !== uri)),
    [photos, onChange],
  );

  return (
    <View style={styles.container}>
      <View style={styles.grid}>
        {photos.map((photo) => (
          <View key={photo.uri} style={styles.thumbnailWrapper}>
            <Image source={{ uri: photo.uri }} style={styles.thumbnail} contentFit="cover" />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Retirer cette photo"
              onPress={() => removePhoto(photo.uri)}
              style={styles.removeBadge}
            >
              <Text style={styles.removeBadgeText}>✕</Text>
            </Pressable>
          </View>
        ))}
      </View>

      {remainingSlots > 0 ? (
        <View style={styles.actionsRow}>
          <Pressable style={styles.actionButton} onPress={pickFromLibrary} accessibilityRole="button">
            <Text style={styles.actionText}>Choisir dans la galerie</Text>
          </Pressable>
          <Pressable style={styles.actionButton} onPress={takePhoto} accessibilityRole="button">
            <Text style={styles.actionText}>Prendre une photo</Text>
          </Pressable>
        </View>
      ) : (
        <Text style={styles.limitText}>Nombre maximal de photos atteint ({maxPhotos}).</Text>
      )}
    </View>
  );
}

const THUMBNAIL_SIZE = 84;

const styles = StyleSheet.create({
  container: { gap: spacing.sm },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  thumbnailWrapper: { position: "relative" },
  thumbnail: {
    width: THUMBNAIL_SIZE,
    height: THUMBNAIL_SIZE,
    borderRadius: radii.sm,
    backgroundColor: colors.surfaceMuted,
  },
  removeBadge: {
    position: "absolute",
    top: -6,
    right: -6,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  removeBadgeText: { color: colors.textOnPrimary, fontSize: 12, fontWeight: "700" },
  actionsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  actionButton: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  actionText: { ...typography.body, color: colors.primary },
  limitText: { ...typography.caption, color: colors.textSecondary },
});
