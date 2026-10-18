import { ChangeDetectionStrategy, Component, HostListener, OnInit, effect, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs';
import { PreferencesService } from './core/preferences.service';
import { LibraryStateService } from './core/library-state.service';
import { ToastService } from './core/toast.service';
import { IconComponent } from './shared/icon.component';
import { ThemeName } from './core/api.models';

@Component({
  selector: 'glimio-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent implements OnInit {
  readonly preferences = inject(PreferencesService);
  readonly toasts = inject(ToastService);
  private readonly router = inject(Router);
  private readonly libraryState = inject(LibraryStateService);
  readonly mobileMenuOpen = signal(false);
  readonly currentPath = signal('/recording');
  readonly libraryCount = this.libraryState.total.asReadonly();
  readonly theme = signal<ThemeName>('dark');
  readonly currentPage = signal('Enregistrement');

  constructor() {
    effect(() => {
      const saved = this.preferences.preferences();
      if (saved) this.theme.set(saved.ui.theme);
    });
  }

  ngOnInit(): void {
    this.preferences.load();
    this.router.events.pipe(filter(event => event instanceof NavigationEnd)).subscribe(event => {
      const url = (event as NavigationEnd).urlAfterRedirects.split('?')[0];
      this.currentPath.set(url);
      this.currentPage.set(({ '/recording': 'Enregistrement', '/library': 'Bibliothèque', '/search': 'Recherche intelligente', '/settings': 'Paramètres' } as Record<string, string>)[url] ?? 'Enregistrement');
      this.closeMobileMenu();
    });
  }

  toggleMobileMenu(): void { this.mobileMenuOpen.update(open => !open); }
  closeMobileMenu(): void { this.mobileMenuOpen.set(false); }

  @HostListener('document:keydown.escape') onEscape(): void { this.closeMobileMenu(); }
  @HostListener('document:click', ['$event']) onOutsideClick(event: MouseEvent): void {
    const target = event.target;
    if (target instanceof Element && !target.closest('.sidebar')) this.closeMobileMenu();
  }

  setTheme(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as ThemeName;
    this.theme.set(value);
    const current = this.preferences.preferences();
    if (current) this.preferences.updatePreferences({ ...current, ui: { ...current.ui, theme: value } });
    else this.preferences.applyTheme(value);
  }

  reloadConfig(): void { this.preferences.load(); this.toasts.show('Configuration actualisée.', 'success'); }

  async copySessionRoot(): Promise<void> {
    const path = this.preferences.sessionRoot();
    if (!path || path === '—') { this.toasts.show('Le chemin du dossier des séances est indisponible.', 'error'); return; }
    try {
      await navigator.clipboard.writeText(path);
      this.toasts.show('Chemin du dossier copié.', 'success');
    } catch {
      this.toasts.show('Copie indisponible dans ce navigateur.', 'error');
    }
  }
}
