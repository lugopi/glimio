/** Shared output-language choices for summary generation and post-hoc translations. */
export type SummaryLanguageCode = 'auto' | 'fr' | 'en' | 'de' | 'it' | 'es' | 'pt' | 'nl';
export type SummaryTranslationLanguageCode = Exclude<SummaryLanguageCode, 'auto'>;

export interface SummaryLanguageOption {
  code: SummaryLanguageCode;
  label: string;
}

export type SummaryTranslationLanguageOption = SummaryLanguageOption & {
  code: SummaryTranslationLanguageCode;
};

export const summaryLanguageOptions: readonly SummaryLanguageOption[] = [
  { code: 'auto', label: 'Suivre la langue de la transcription' },
  { code: 'fr', label: 'Français' },
  { code: 'en', label: 'Anglais' },
  { code: 'de', label: 'Allemand' },
  { code: 'it', label: 'Italien' },
  { code: 'es', label: 'Espagnol' },
  { code: 'pt', label: 'Portugais' },
  { code: 'nl', label: 'Néerlandais' },
];

export const summaryTranslationOptions: readonly SummaryTranslationLanguageOption[] = summaryLanguageOptions.filter(
  (option): option is SummaryTranslationLanguageOption => option.code !== 'auto',
);

export function summaryLanguageLabel(code: string): string {
  return summaryLanguageOptions.find(option => option.code === code)?.label ?? code;
}
