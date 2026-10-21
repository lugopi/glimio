import { ProviderStatus } from '../core/api.models';

export interface TranscriptionLanguageOption {
  code: string;
  label: string;
}

// Language codes exposed by whisper.cpp (including Cantonese and Hawaiian).
const WHISPER_LANGUAGES = [
  'en', 'zh', 'de', 'es', 'ru', 'ko', 'fr', 'ja', 'pt', 'tr', 'pl', 'ca', 'nl', 'ar',
  'sv', 'it', 'id', 'hi', 'fi', 'vi', 'he', 'uk', 'el', 'ms', 'cs', 'ro', 'da', 'hu',
  'ta', 'no', 'th', 'ur', 'hr', 'bg', 'lt', 'la', 'mi', 'ml', 'cy', 'sk', 'te', 'fa',
  'lv', 'bn', 'sr', 'az', 'sl', 'kn', 'et', 'mk', 'br', 'eu', 'is', 'hy', 'ne', 'mn',
  'bs', 'kk', 'sq', 'sw', 'gl', 'mr', 'pa', 'si', 'km', 'sn', 'yo', 'so', 'af', 'oc',
  'ka', 'be', 'tg', 'sd', 'gu', 'am', 'yi', 'lo', 'uz', 'fo', 'ht', 'ps', 'tk', 'nn',
  'mt', 'sa', 'lb', 'my', 'bo', 'tl', 'mg', 'as', 'tt', 'haw', 'ln', 'ha', 'ba', 'jw',
  'su', 'yue',
] as const;

export function transcriptionLanguageOptions(locale: 'fr' | 'en'): TranscriptionLanguageOption[] {
  const displayNames = new Intl.DisplayNames([locale], { type: 'language' });
  const collator = new Intl.Collator(locale);
  return WHISPER_LANGUAGES
    .map(code => ({ code, label: displayNames.of(code) ?? code }))
    .sort((left, right) => collator.compare(left.label, right.label));
}

export function providerSupportsTranscriptionLanguage(
  providers: readonly ProviderStatus[] | null,
  providerId: string,
): boolean | undefined {
  if (providers === null) return undefined;
  const provider = providers.find(candidate => candidate.task === 'transcription' && candidate.id === providerId);
  return provider?.capabilities.includes('language-selection') ?? false;
}
