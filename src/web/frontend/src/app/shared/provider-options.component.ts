import { ChangeDetectionStrategy, Component, OnDestroy, computed, inject, input, output, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subscription, switchMap, takeWhile, timer } from 'rxjs';
import { ApiService } from '../core/api.service';
import { PreferencesService } from '../core/preferences.service';
import { ProviderInstallStatus, ProviderOption, ProviderStatus } from '../core/api.models';
import { missingProviderDependencyIds } from '../core/provider-dependencies';
import { CheckboxFieldComponent } from './checkbox-field.component';
import { IconComponent } from './icon.component';

@Component({
  selector: 'glimio-provider-options',
  standalone: true,
  imports: [FormsModule, NgTemplateOutlet, RouterLink, CheckboxFieldComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './provider-options.component.html',
  styleUrl: './provider-options.component.scss',
})
export class ProviderOptionsComponent implements OnDestroy {
  readonly provider = input.required<ProviderStatus>();
  readonly values = input<Record<string, unknown>>({});
  readonly showAllOptions = input(false);
  /** In settings, let users collapse option fields for providers that are ready. */
  readonly collapsible = input(false);
  readonly perJobOnly = input(false);
  /** Resource links belong to setup/settings screens, not the recording workflow. */
  readonly showSetupLinks = input(true);
  readonly optionChange = output<{ option: ProviderOption; value: unknown }>();
  readonly installFinished = output<void>();
  readonly readinessChecked = output<ProviderStatus>();
  readonly installation = signal<ProviderInstallStatus | null>(null);
  readonly postInstallStatus = signal<ProviderStatus | null>(null);
  readonly checkingReadiness = signal(false);
  readonly readinessError = signal<string | null>(null);
  readonly installingPython = computed(() => ['queued', 'running'].includes(this.installation()?.state ?? ''));
  private readonly api = inject(ApiService);
  private readonly preferences = inject(PreferencesService);
  private verifiedInstallId: string | null = null;
  private startSubscription?: Subscription;
  private pollSubscription?: Subscription;

  options(advanced: boolean): ProviderOption[] {
    const values = this.values();
    return this.provider().options.filter(option => (this.showAllOptions() || option.advanced === advanced)
      && (this.perJobOnly() ? option.per_job : !option.per_job)
      && (!option.depends_on || values[option.depends_on] === option.depends_value));
  }

  value(option: ProviderOption): unknown {
    return this.values()[option.key] ?? option.default;
  }

  fieldId(option: ProviderOption): string {
    return `${this.provider().id}-${option.key}`.replace(/[^a-zA-Z0-9_-]/g, '-');
  }

  /** Translate provider-owned metadata using the provider's own catalogue. */
  providerText(value: string): string {
    const language = this.preferences.preferences()?.ui.language ?? 'fr';
    return this.provider().translations?.[language]?.[value] ?? this.translateProviderTemplate(value, language);
  }

  private translateProviderTemplate(value: string, language: string): string {
    const entries = this.provider().translations?.[language] ?? {};
    for (const [template, translated] of Object.entries(entries)) {
      const marker = '{path}';
      const index = template.indexOf(marker);
      if (index < 0) continue;
      const prefix = template.slice(0, index);
      const suffix = template.slice(index + marker.length);
      if (value.startsWith(prefix) && value.endsWith(suffix) && value.length >= prefix.length + suffix.length) {
        const path = value.slice(prefix.length, value.length - suffix.length || undefined);
        return translated.replace(marker, path);
      }
    }
    return value;
  }

  missingText(value: string): string { return this.providerText(value); }

  missingItems(): Array<{ text?: string; providerId?: string }> {
    const items: Array<{ text?: string; providerId?: string }> = this.provider().missing.map(value => {
      const match = value.match(/^(?:provider requis|required provider)\s*:\s*(.+)$/i);
      const providerId = match?.[1]?.trim();
      return providerId ? { providerId } : { text: this.providerText(value) };
    });
    const displayedIds = new Set(items.flatMap(item => item.providerId ? [item.providerId] : []));
    const structuredItems = missingProviderDependencyIds(this.provider())
      .filter(providerId => !displayedIds.has(providerId))
      .map(providerId => ({ providerId }));
    return [...items, ...structuredItems];
  }

  missingPythonPackages(status: ProviderStatus): string[] {
    return status.missing.filter(item => /(?:paquet Python|Python package)/i.test(item));
  }

  update(option: ProviderOption, value: unknown): void {
    if (option.type === 'path') {
      this.postInstallStatus.set(null);
      this.readinessError.set(null);
    }
    this.optionChange.emit({ option, value: option.type === 'number' ? Number(value) : value });
  }

  checkReadiness(): void {
    if (this.checkingReadiness()) return;
    this.checkingReadiness.set(true);
    this.readinessError.set(null);
    this.api.providers().subscribe({
      next: response => {
        const status = response.providers.find(item => item.id === this.provider().id);
        if (status) this.readinessChecked.emit(status);
        else this.readinessError.set('Impossible de retrouver ce provider dans le résultat de vérification.');
        this.checkingReadiness.set(false);
      },
      error: () => {
        this.checkingReadiness.set(false);
        this.readinessError.set('Impossible de vérifier les ressources locales. Réessayez après la sauvegarde des chemins.');
      },
    });
  }

  installPythonDependencies(): void {
    if (!this.provider().python_install_available || this.installingPython()) return;
    this.startSubscription?.unsubscribe();
    this.pollSubscription?.unsubscribe();
    this.postInstallStatus.set(null);
    this.checkingReadiness.set(false);
    this.verifiedInstallId = null;
    this.installation.set({
      id: '', provider_id: this.provider().id, state: 'queued',
      message: 'Préparation de l’installation…', output: '', returncode: null,
      restart_required: this.provider().restart_after_python_install,
    });
    this.startSubscription = this.api.installProviderDependencies(this.provider().id).subscribe({
      next: result => {
        if (result.install.state === 'succeeded') {
          this.verifyInstallation(result.install);
        } else {
          this.installation.set(result.install);
          if (['queued', 'running'].includes(result.install.state) && result.install.id) this.pollInstallation(result.install.id);
        }
      },
      error: error => this.installation.set({
        id: '', provider_id: this.provider().id, state: 'failed',
        message: error instanceof Error ? error.message : 'Impossible de démarrer l’installation.',
        output: '', returncode: null, restart_required: false,
      }),
    });
  }

  private pollInstallation(installId: string): void {
    this.pollSubscription?.unsubscribe();
    this.pollSubscription = timer(500, 1000).pipe(
      switchMap(() => this.api.providerInstallStatus(installId)),
      takeWhile(response => ['queued', 'running'].includes(response.install.state), true),
    ).subscribe({
      next: response => {
        if (response.install.state === 'succeeded') this.verifyInstallation(response.install);
        else this.installation.set(response.install);
      },
      error: error => this.installation.set({
        id: installId, provider_id: this.provider().id, state: 'failed',
        message: error instanceof Error ? error.message : 'Impossible de lire l’état de l’installation.',
        output: '', returncode: null, restart_required: false,
      }),
    });
  }

  private verifyInstallation(install: ProviderInstallStatus): void {
    if (install.state !== 'succeeded' || !install.id || this.verifiedInstallId === install.id) return;
    this.verifiedInstallId = install.id;
    this.checkingReadiness.set(true);
    this.installation.set(install);
    this.api.providers().subscribe({
      next: response => {
        const refreshed = response.providers.find(item => item.id === this.provider().id) ?? null;
        this.postInstallStatus.set(refreshed);
        this.checkingReadiness.set(false);
        const needsRestart = !refreshed || this.missingPythonPackages(refreshed).length > 0;
        this.installation.set({ ...install, restart_required: needsRestart });
        this.installFinished.emit();
      },
      error: () => {
        this.checkingReadiness.set(false);
        this.postInstallStatus.set(null);
        this.installation.set({ ...install, restart_required: true });
        this.installFinished.emit();
      },
    });
  }

  ngOnDestroy(): void {
    this.startSubscription?.unsubscribe();
    this.pollSubscription?.unsubscribe();
  }
}
