import { Injectable, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { SearchResult } from '../../core/api.models';
import { JobEventsService } from '../../core/job-events.service';
import { PreferencesService } from '../../core/preferences.service';
import { ToastService } from '../../core/toast.service';

/** Application-scoped state for smart search, preserved when opening a source session. */
@Injectable({ providedIn: 'root' })
export class SearchStateService {
  private readonly api = inject(ApiService);
  private readonly jobEvents = inject(JobEventsService);
  private readonly preferences = inject(PreferencesService);
  private readonly toast = inject(ToastService);
  private searchSubscription?: Subscription;

  readonly query = signal('');
  readonly running = signal(false);
  readonly searchId = signal<string | null>(null);
  readonly result = signal<SearchResult | null>(null);

  runSearch(): void {
    if (this.running()) return;
    const query = this.query().trim();
    const settings = this.preferences.preferences()?.settings;
    if (query.length < 2) {
      this.toast.show('Saisissez une question ou quelques mots-clés.', 'error');
      return;
    }
    if (!settings) {
      this.toast.show('Les paramètres ne sont pas encore chargés.', 'error');
      return;
    }

    this.searchSubscription?.unsubscribe();
    this.running.set(true);
    this.searchId.set(null);
    this.result.set(null);
    this.api.startSearch(query, settings, 20).subscribe({
      next: created => {
        this.searchId.set(created.id);
        this.searchSubscription = this.jobEvents.searchUpdates$.subscribe(result => {
          if (result.id === created.id && this.searchId() === created.id) this.applySearchResult(result);
        });
        // Hydrate once in case the worker emitted its first event before the
        // start request returned. Subsequent progress arrives through SSE.
        this.api.search(created.id).subscribe({
          next: result => { if (this.searchId() === created.id) this.applySearchResult(result); },
          error: error => {
            this.toast.show(`La recherche a échoué : ${error.message}`, 'error');
            this.running.set(false);
            this.searchId.set(null);
            this.searchSubscription?.unsubscribe();
          },
        });
      },
      error: error => {
        this.toast.show(`Impossible de démarrer la recherche : ${error.message}`, 'error');
        this.running.set(false);
      },
    });
  }

  cancelSearch(): void {
    const id = this.searchId();
    if (!id) return;
    this.api.cancelSearch(id).subscribe({
      next: () => this.toast.show('Demande d’annulation envoyée.', 'success'),
      error: error => this.toast.show(error.message, 'error'),
    });
  }

  private applySearchResult(result: SearchResult): void {
    const current = this.result();
    if (current?.id === result.id && current.updated_at && result.updated_at
        && current.updated_at.localeCompare(result.updated_at) > 0) return;
    this.result.set(result);
    if (['completed', 'cancelled', 'error'].includes(result.state)) {
      this.running.set(false);
      this.searchId.set(null);
      this.searchSubscription?.unsubscribe();
    }
  }
}
