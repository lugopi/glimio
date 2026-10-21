import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { GlimioSettings, PreferencesPayload, ProviderOption, ProviderStatus } from '../../core/api.models';
import { PreferencesService } from '../../core/preferences.service';
import { ApiService } from '../../core/api.service';
import { CheckboxFieldComponent } from '../../shared/checkbox-field.component';
import { IconComponent } from '../../shared/icon.component';
import { ProviderOptionsComponent } from '../../shared/provider-options.component';

@Component({
  standalone: true,
  imports: [FormsModule, DecimalPipe, CheckboxFieldComponent, IconComponent, ProviderOptionsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './settings.page.html',
  styleUrl: './settings.page.scss',
})
export class SettingsPageComponent implements OnInit {
  readonly preferences = inject(PreferencesService);
  private readonly api = inject(ApiService);
  readonly providers = signal<ProviderStatus[]>([]);
  readonly providersError = signal<string | null>(null);
  readonly settings = computed(() => this.preferences.preferences()?.settings ?? null);
  readonly ui = computed(() => this.preferences.preferences()?.ui ?? null);

  providersFor(task: ProviderStatus['task']): ProviderStatus[] {
    return this.providers().filter(provider => provider.task === task);
  }

  activeProvider(task: ProviderStatus['task'], id: string): ProviderStatus | undefined {
    return this.providers().find(provider => provider.task === task && provider.id === id);
  }

  patchProviderOption(provider: ProviderStatus, option: ProviderOption, value: unknown): void {
    const current = this.preferences.preferences();
    if (!current) return;
    const allProviderOptions = current.settings.provider_options ?? {};
    const providerValues = allProviderOptions[provider.id] ?? {};
    const typedValue = option.type === 'number' ? Number(value) : value;
    this.preferences.updatePreferences({
      ...current,
      settings: {
        ...current.settings,
        provider_options: {
          ...allProviderOptions,
          [provider.id]: { ...providerValues, [option.key]: typedValue },
        },
      },
    });
  }

  ngOnInit(): void {
    this.api.providers().subscribe({
      next: result => this.providers.set(result.providers),
      error: () => this.providersError.set('État des providers indisponible.'),
    });
  }
  patch<K extends keyof GlimioSettings>(key: K, value: GlimioSettings[K]): void {
    const current = this.preferences.preferences();
    if (!current) return;
    const updated: PreferencesPayload = { ...current, settings: { ...current.settings, [key]: value } };
    this.preferences.updatePreferences(updated);
  }

  patchSessionRoot(value: string): void {
    const current = this.preferences.preferences();
    if (current) this.preferences.updatePreferences({ ...current, ui: { ...current.ui, session_root: value } });
  }

  patchLanguage(value: 'fr' | 'en'): void {
    const current = this.preferences.preferences();
    if (current) this.preferences.updatePreferences({ ...current, ui: { ...current.ui, language: value } });
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
