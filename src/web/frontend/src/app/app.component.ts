import { ChangeDetectionStrategy, Component, HostListener, OnInit, computed, effect, inject, signal } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { HttpClient } from '@angular/common/http';
import { Router, RouterLink, RouterLinkActive, RouterOutlet, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs';
import { PreferencesService } from './core/preferences.service';
import { LibraryStateService } from './core/library-state.service';
import { ToastService } from './core/toast.service';
import { IconComponent } from './shared/icon.component';
import { ThemeName } from './core/api.models';
import { ApiService } from './core/api.service';

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
  private readonly api = inject(ApiService);
  readonly mobileMenuOpen = signal(false);
  readonly sidebarCollapsed = signal(window.innerWidth <= 1100 && window.innerWidth > 850);
  private compactViewport = window.innerWidth <= 1100 && window.innerWidth > 850;
  readonly currentPath = signal('/recording');
  readonly libraryCount = this.libraryState.total.asReadonly();
  readonly theme = signal<ThemeName>('dark');
  readonly currentPage = signal('Enregistrement');

  /**
   * Logo Glimio injecté en ligne : le calque principal et la vague utilisent
   * currentColor ; la vague conserve une opacité propre pour créer sa profondeur.
   * Le SVG garde un viewBox légèrement étendu afin de ne pas couper les tracés.
   * Le fichier public/brand/glimio.svg est nettoyé des métadonnées Inkscape ;
   * le nettoyage ci-dessous reste un repli défensif (déclaration XML,
   * commentaires, attributs sodipodi:/inkscape:, dimensions fixes).
   */
  private readonly http = inject(HttpClient);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly rawBrandLogo = signal<string | null>(null);
  readonly brandLogo = computed<SafeHtml | null>(() => {
    const svg = this.rawBrandLogo();
    if (!svg) return null;
    let cleaned = svg
      // Déclaration XML et commentaires (non valides en HTML inline).
      .replace(/<\?xml[^>]*\?>/g, '')
      .replace(/<!--[\s\S]*?-->/g, '')
      // Métadonnées Inkscape : éléments nommés…
      .replace(/<(defs|metadata|namedview)\b[\s\S]*?<\/\1>/g, '')
      .replace(/<(defs|metadata|namedview)\b[^>]*\/>/g, '')
      // …et attributs d'espace de noms restants (sodipodi:, inkscape:).
      .replace(/\s(?:sodipodi|inkscape):[a-zA-Z-]+="[^"]*"/g, '');
    // Force le SVG à s'adapter à son conteneur sans imposer une taille native
    // susceptible de déborder dans le bandeau responsive.
    cleaned = cleaned.replace(/<svg\b[^>]*>/g, tag => {
      // Normalize rather than append SVG attributes: duplicate width/height or
      // preserveAspectRatio attributes can produce inconsistent browser parsing.
      const normalized = tag
        .replace(/\s(?:width|height|class|preserveAspectRatio)="[^"]*"/g, '')
        .replace(/>$/, '');
      const withBox = /\sviewBox="[^"]*"/.test(normalized)
        ? normalized
        : normalized + ' viewBox="0 -12 512 524"';
      return withBox + ' width="100%" height="100%" class="brand-logo" preserveAspectRatio="xMidYMid meet">';
    });
    return this.sanitizer.bypassSecurityTrustHtml(cleaned);
  });

  constructor() {
    effect(() => {
      const saved = this.preferences.preferences();
      if (saved) this.theme.set(saved.ui.theme);
    });
  }

  ngOnInit(): void {
    // Hydrate the sidebar count on app startup, without waiting for the user to open the library.
    this.api.sessions({ limit: 1, offset: 0 }).subscribe({
      next: result => this.libraryState.total.set(result.count),
      error: () => { /* The library page retries when it opens. */ },
    });
    this.http.get('brand/glimio.svg', { responseType: 'text' })
      .subscribe({
        next: svg => this.rawBrandLogo.set(svg),
        error: () => this.rawBrandLogo.set(null),
      });
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

  toggleSidebar(): void { this.sidebarCollapsed.update(collapsed => !collapsed); }

  @HostListener('window:resize') onWindowResize(): void {
    const compact = window.innerWidth <= 1100 && window.innerWidth > 850;
    if (compact !== this.compactViewport) this.sidebarCollapsed.set(compact);
    this.compactViewport = compact;
  }

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
