import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { GlimioSettings, PreferencesPayload } from '../../core/api.models';
import { PreferencesService } from '../../core/preferences.service';
import { CheckboxFieldComponent } from '../../shared/checkbox-field.component';
import { IconComponent } from '../../shared/icon.component';

@Component({
  standalone: true,
  imports: [FormsModule, DecimalPipe, CheckboxFieldComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './settings.page.html',
  styleUrl: './settings.page.scss',
})
export class SettingsPageComponent {
  readonly preferences = inject(PreferencesService);
  readonly settings = computed(() => this.preferences.preferences()?.settings ?? null);
  patch<K extends keyof GlimioSettings>(key: K, value: GlimioSettings[K]): void {
    const current = this.preferences.preferences();
    if (!current) return;
    const updated: PreferencesPayload = { ...current, settings: { ...current.settings, [key]: value } };
    this.preferences.updatePreferences(updated);
  }

  numberValue(value: string | number): number { return Number(value); }

  audioBitrateValue(value: string | number): GlimioSettings['audio_bitrate_kbps'] {
    const bitrate = Number(value);
    return ([128, 256, 384, 512, 768] as const).includes(bitrate as 128 | 256 | 384 | 512 | 768)
      ? bitrate as GlimioSettings['audio_bitrate_kbps']
      : 256;
  }
  formatLabel(value: string): string { return ({ auto: 'Automatique', summary: 'Synthèse générale', daily: 'Daily — compte rendu de réunion', technical: 'Technique', formal: 'Formel', brainstorm: 'Brainstorming' } as Record<string, string>)[value] ?? value; }
}
