import { Injectable, computed, inject, signal } from '@angular/core';
import { debounceTime, distinctUntilChanged, EMPTY, Subject, switchMap, tap, catchError, finalize } from 'rxjs';
import { ApiService } from './api.service';
import { AppConfig, PreferencesPayload, ThemeName } from './api.models';
import { ToastService } from './toast.service';
import { InterfaceLanguageService } from './interface-language.service';

@Injectable({ providedIn: 'root' })
export class PreferencesService {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);
  private readonly interfaceLanguage = inject(InterfaceLanguageService);
  private readonly changes = new Subject<PreferencesPayload>();
  readonly config = signal<AppConfig | null>(null);
  readonly preferences = signal<PreferencesPayload | null>(null);
  readonly sessionRoot = computed(() => this.preferences()?.ui.session_root || this.config()?.session_root || '—');
  readonly isReady = computed(() => this.config() !== null);
  readonly isSaving = signal(false);

  constructor() {
    this.changes.pipe(
      debounceTime(450),
      distinctUntilChanged((a, b) => JSON.stringify(a) === JSON.stringify(b)),
      tap(() => this.isSaving.set(true)),
      switchMap(payload => this.api.savePreferences(payload).pipe(
        tap(saved => this.preferences.set(saved)),
        catchError(error => {
          this.toast.show(`La sauvegarde automatique a échoué : ${error.message}`, 'error');
          return EMPTY;
        }),
        finalize(() => this.isSaving.set(false)),
      )),
    ).subscribe();
  }

  load(): void {
    this.api.config().subscribe({
      next: config => {
        this.config.set(config);
        this.preferences.set(config.preferences);
        this.applyTheme(config.preferences.ui.theme);
        this.applyLanguage(config.preferences.ui.language);
      },
      error: error => this.toast.show(`Configuration indisponible : ${error.message}`, 'error'),
    });
  }

  updatePreferences(next: PreferencesPayload): void {
    this.preferences.set(next);
    this.applyTheme(next.ui.theme);
    this.applyLanguage(next.ui.language);
    this.changes.next(next);
  }

  applyTheme(theme: ThemeName): void {
    document.documentElement.dataset['theme'] = theme;
    document.documentElement.style.colorScheme = theme === 'light' ? 'light' : 'dark';
  }

  applyLanguage(language: 'fr' | 'en'): void {
    this.interfaceLanguage.setLanguage(language);
  }
}
