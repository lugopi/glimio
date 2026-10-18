import { provideIcons } from '@ng-icons/core';
import {
  heroArrowPath,
  heroBars3,
  heroBookOpen,
  heroCheckCircle,
  heroClock,
  heroCog6Tooth,
  heroInformationCircle,
  heroMagnifyingGlass,
  heroMicrophone,
  heroPencilSquare,
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
  bars3: heroBars3,
  bookOpen: heroBookOpen,
  checkCircle: heroCheckCircle,
  clock: heroClock,
  cog6Tooth: heroCog6Tooth,
  informationCircle: heroInformationCircle,
  magnifyingGlass: heroMagnifyingGlass,
  microphone: heroMicrophone,
  pencilSquare: heroPencilSquare,
  trash: heroTrash,
  xMark: heroXMark,
};

/** Heroicon kebab-case names used in templates → @ng-icons registry keys. */
const ICON_ALIASES: Record<string, string> = {
  'arrow-path': 'arrowPath',
  'bars-3': 'bars3',
  'book-open': 'bookOpen',
  'check-circle': 'checkCircle',
  clock: 'clock',
  'cog-6-tooth': 'cog6Tooth',
  'information-circle': 'informationCircle',
  'magnifying-glass': 'magnifyingGlass',
  microphone: 'microphone',
  'pencil-square': 'pencilSquare',
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
