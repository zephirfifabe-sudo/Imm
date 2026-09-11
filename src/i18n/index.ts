import fr from "@/i18n/messages/fr.json";
import nl from "@/i18n/messages/nl.json";
import en from "@/i18n/messages/en.json";

export const SUPPORTED_LOCALES = ["fr", "nl", "en"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

/** Le français est la seule langue livrée pour le MVP; nl/en sont préparées. */
export const DEFAULT_LOCALE: Locale = "fr";

const dictionaries: Record<Locale, Record<string, unknown>> = { fr, nl, en };

function resolve(dictionary: Record<string, unknown>, path: string): string {
  const value = path
    .split(".")
    .reduce<unknown>(
      (acc, key) =>
        typeof acc === "object" && acc !== null
          ? (acc as Record<string, unknown>)[key]
          : undefined,
      dictionary,
    );
  return typeof value === "string" ? value : path;
}

/**
 * Traduction simple par clé pointée ("auth.loginTitle"), avec interpolation
 * `{variable}`. Volontairement minimal pour le MVP; à remplacer par
 * next-intl si l'app devient multilingue en production.
 */
export function getTranslator(locale: Locale = DEFAULT_LOCALE) {
  const dictionary = dictionaries[locale] ?? dictionaries[DEFAULT_LOCALE];

  return function t(key: string, params?: Record<string, string | number>) {
    const template = resolve(dictionary, key);
    if (!params) return template;
    return Object.entries(params).reduce(
      (result, [name, value]) =>
        result.replace(`{${name}}`, String(value)),
      template,
    );
  };
}
