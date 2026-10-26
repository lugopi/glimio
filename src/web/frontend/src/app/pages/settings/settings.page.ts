import { ChangeDetectionStrategy, Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { GlimioSettings, PreferencesPayload, ProviderOption, ProviderStatus } from '../../core/api.models';
import { PreferencesService } from '../../core/preferences.service';
import { ApiService } from '../../core/api.service';
import { ProviderDependency, requiredProviderDependencies as findRequiredProviderDependencies, requiredProviderIdsForTask as findRequiredProviderIdsForTask } from '../../core/provider-dependencies';
import { CheckboxFieldComponent } from '../../shared/checkbox-field.component';
import { IconComponent } from '../../shared/icon.component';
import { ProviderOptionsComponent } from '../../shared/provider-options.component';
import { summaryFormatLabel } from '../../shared/summary-formats';

@Component({
  standalone: true,
  imports: [FormsModule, RouterLink, CheckboxFieldComponent, IconComponent, ProviderOptionsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './settings.page.html',
  styleUrl: './settings.page.scss',
})
export class SettingsPageComponent implements OnInit, OnDestroy {
  readonly preferences = inject(PreferencesService);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  readonly providers = signal<ProviderStatus[]>([]);
  readonly providersError = signal<string | null>(null);
  private providerReadinessDirty = false;
  private preferencesSavedSubscription?: Subscription;
  private providerNavigationSubscription?: Subscription;
  private requestedProviderNavigation: { providerId: string; fallbackProviderId: string | null; task: string | null } | null = null;
  readonly settings = computed(() => this.preferences.preferences()?.settings ?? null);
  readonly ui = computed(() => this.preferences.preferences()?.ui ?? null);
  readonly requiredProviderDependencies = computed(() => {
    const value = this.settings();
    if (!value) return [];
    return findRequiredProviderDependencies(this.providers(), [
      value.media_provider,
      value.audio_enhancement_provider,
      value.source_separation_provider,
      value.speaker_embedding_provider,
      value.diarization_provider,
      value.transcription_provider,
      value.text_provider,
    ]);
  });

  providerText(provider: ProviderStatus, value: string): string {
    const language = this.preferences.preferences()?.ui.language ?? 'fr';
    return provider.translations?.[language]?.[value] ?? value;
  }

  providersFor(task: ProviderStatus['task']): ProviderStatus[] {
    return this.providers().filter(provider => provider.task === task);
  }

  requiredByText(dependency: ProviderDependency): string {
    return dependency.requiredBy
      .map(provider => this.providerText(provider, provider.name))
      .join(', ');
  }

  requiredProviderIdsForTask(providerId: string, task: ProviderStatus['task']): string[] {
    return findRequiredProviderIdsForTask(this.providers(), providerId, task);
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
    if (option.type === 'path') this.providerReadinessDirty = true;
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
    this.providerNavigationSubscription = this.route.queryParamMap.subscribe(params => {
      const providerId = params.get('provider');
      this.requestedProviderNavigation = providerId
        ? { providerId, fallbackProviderId: params.get('fallback'), task: params.get('task') }
        : null;
      if (providerId) this.scrollToRequestedProvider();
    });
    this.preferencesSavedSubscription = this.preferences.preferencesSaved$.subscribe(() => {
      if (!this.providerReadinessDirty) return;
      this.providerReadinessDirty = false;
      this.refreshProviders();
    });
    this.refreshProviders();
  }

  ngOnDestroy(): void {
    this.preferencesSavedSubscription?.unsubscribe();
    this.providerNavigationSubscription?.unsubscribe();
  }

  /** Deep links from dependency warnings open the exact provider or its requiring provider. */
  private scrollToRequestedProvider(attempt = 0): void {
    const request = this.requestedProviderNavigation;
    if (!request || typeof document === 'undefined') return;
    window.requestAnimationFrame(() => {
      if (this.requestedProviderNavigation !== request) return;
      const ids = [
        request.task ? `provider-settings-task-${request.task}` : null,
        `provider-settings-${request.providerId}`,
        request.fallbackProviderId ? `provider-settings-${request.fallbackProviderId}` : null,
      ].filter((id): id is string => !!id);
      const target = ids
        .map(id => document.getElementById(id))
        .find((element): element is HTMLElement => element instanceof HTMLElement);
      if (!target) {
        // Provider data can arrive after route activation. Retry briefly, then
        // the provider refresh below will retry again if needed.
        if (attempt < 12) this.scrollToRequestedProvider(attempt + 1);
        return;
      }
      for (let parent: HTMLElement | null = target; parent; parent = parent.parentElement) {
        if (parent instanceof HTMLDetailsElement) parent.open = true;
      }
      // A deep link should reveal the ready provider's fields too, not stop at
      // the card whose option accordion is intentionally collapsed by default.
      target.querySelectorAll('details').forEach(details => { details.open = true; });
      window.requestAnimationFrame(() => {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.focus({ preventScroll: true });
      });
      this.requestedProviderNavigation = null;
    });
  }

  refreshProviders(): void {
    this.api.providers().subscribe({
      next: result => {
        this.providers.set(result.providers);
        this.providersError.set(null);
        if (this.requestedProviderNavigation) this.scrollToRequestedProvider();
      },
      error: () => this.providersError.set('État des providers indisponible.'),
    });
  }

  updateProviderStatus(status: ProviderStatus): void {
    this.providers.update(current => current.map(provider => provider.id === status.id ? status : provider));
  }
  patch<K extends keyof GlimioSettings>(key: K, value: GlimioSettings[K]): void {
    const current = this.preferences.preferences();
    if (!current) return;
    const advancedKeys: (keyof GlimioSettings)[] = ['context', 'max_tokens', 'analysis_tokens', 'analysis_retries', 'analysis_max_splits', 'no_review'];
    const updated: PreferencesPayload = { ...current, settings: {
      ...current.settings, [key]: value,
      ...(advancedKeys.includes(key) ? { processing_profile: 'custom' as const } : {}),
    } };
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

  generationValue(key: 'context' | 'max_tokens' | 'analysis_tokens' | 'analysis_retries' | 'analysis_max_splits' | 'no_review'): number | boolean {
    const value = this.settings();
    if (!value) return key === 'no_review' ? false : 0;
    if (value.processing_profile === 'custom') return value[key];
    if (key === 'context') return value.context;
    return this.preferences.config()?.processing_profiles?.[value.processing_profile]?.[key] ?? value[key];
  }

  generationReadOnly(): boolean { return this.settings()?.processing_profile !== 'custom'; }

  audioBitrateValue(value: string | number): GlimioSettings['audio_bitrate_kbps'] {
    const bitrate = Number(value);
    return ([128, 256, 384, 512, 768] as const).includes(bitrate as 128 | 256 | 384 | 512 | 768)
      ? bitrate as GlimioSettings['audio_bitrate_kbps']
      : 256;
  }
  formatLabel(value: string): string { return summaryFormatLabel(value); }
}
