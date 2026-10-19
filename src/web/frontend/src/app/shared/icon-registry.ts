import { provideIcons } from '@ng-icons/core';
import {
  heroArrowPath,
  heroArrowDownTray,
  heroArrowTopRightOnSquare,
  heroBars3,
  heroBookOpen,
  heroCheckCircle,
  heroChevronLeft,
  heroChevronRight,
  heroClock,
  heroCog6Tooth,
  heroDocumentText,
  heroEye,
  heroEyeSlash,
  heroInformationCircle,
  heroMagnifyingGlass,
  heroMicrophone,
  heroPencilSquare,
  heroPlus,
  heroSpeakerWave,
  heroStopCircle,
  heroPlay,
  heroSparkles,
  heroTrash,
  heroXMark,
} from '@ng-icons/heroicons/outline';

/**
 * Single source of truth for every icon used in the interface.
 * All icons come from @ng-icons/core + @ng-icons/heroicons (outline set).
 * Add new icons here; components only reference them by name.
 */
export const GLIMIO_ICONS = {
  arrowPath: heroArrowPath,
  arrowDownTray: heroArrowDownTray,
  arrowTopRightOnSquare: heroArrowTopRightOnSquare,
  bars3: heroBars3,
  bookOpen: heroBookOpen,
  checkCircle: heroCheckCircle,
  chevronLeft: heroChevronLeft,
  chevronRight: heroChevronRight,
  clock: heroClock,
  cog6Tooth: heroCog6Tooth,
  documentText: heroDocumentText,
  eye: heroEye,
  eyeSlash: heroEyeSlash,
  informationCircle: heroInformationCircle,
  magnifyingGlass: heroMagnifyingGlass,
  microphone: heroMicrophone,
  pencilSquare: heroPencilSquare,
  plus: heroPlus,
  speakerWave: heroSpeakerWave,
  stopCircle: heroStopCircle,
  play: heroPlay,
  sparkles: heroSparkles,
  trash: heroTrash,
  xMark: heroXMark,
};

/** Heroicon kebab-case names used in templates → @ng-icons registry keys. */
const ICON_ALIASES: Record<string, string> = {
  'arrow-path': 'arrowPath',
  'arrow-down-tray': 'arrowDownTray',
  'arrow-top-right-on-square': 'arrowTopRightOnSquare',
  'bars-3': 'bars3',
  'book-open': 'bookOpen',
  'check-circle': 'checkCircle',
  'chevron-left': 'chevronLeft',
  'chevron-right': 'chevronRight',
  clock: 'clock',
  'cog-6-tooth': 'cog6Tooth',
  'document-text': 'documentText',
  eye: 'eye',
  'eye-slash': 'eyeSlash',
  'information-circle': 'informationCircle',
  'magnifying-glass': 'magnifyingGlass',
  microphone: 'microphone',
  'pencil-square': 'pencilSquare',
  plus: 'plus',
  'speaker-wave': 'speakerWave',
  'stop-circle': 'stopCircle',
  play: 'play',
  sparkles: 'sparkles',
  trash: 'trash',
  'x-mark': 'xMark',
};

export function glimioIconKey(name: string): string {
  return ICON_ALIASES[name] ?? name;
}

/** Provide the whole icon set once for the application. */
export function provideGlimioIcons() {
  return provideIcons(GLIMIO_ICONS);
}
