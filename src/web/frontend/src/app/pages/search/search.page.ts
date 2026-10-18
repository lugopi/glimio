import { ChangeDetectionStrategy, Component, OnDestroy, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subscription, timer, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { SearchResult } from '../../core/api.models';
import { PreferencesService } from '../../core/preferences.service';
import { ToastService } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';

@Component({
  standalone: true,
  imports: [FormsModule, RouterLink, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './search.page.html',
  styleUrl: './search.page.scss',
})
export class SearchPageComponent implements OnDestroy {
  private readonly api = inject(ApiService);
  private readonly preferences = inject(PreferencesService);
  private readonly toast = inject(ToastService);
  private poll?: Subscription;
  readonly query = signal('');
  readonly running = signal(false);
  readonly searchId = signal<string | null>(null);
  readonly result = signal<SearchResult | null>(null);

  ngOnDestroy(): void { this.poll?.unsubscribe(); }

  runSearch(): void {
    if (this.running()) return;
    const query = this.query().trim();
    const settings = this.preferences.preferences()?.settings;
    if (query.length < 2) { this.toast.show('Saisissez une question ou quelques mots-clés.', 'error'); return; }
    if (!settings) { this.toast.show('Les paramètres ne sont pas encore chargés.', 'error'); return; }
    this.running.set(true); this.result.set(null);
    this.api.startSearch(query, settings).subscribe({
      next: created => {
        this.searchId.set(created.id);
        this.poll = timer(0, 250).pipe(
          switchMap(() => this.api.search(created.id)),
          takeWhile(value => !['completed', 'cancelled', 'error'].includes(value.state), true),
        ).subscribe({
          next: result => { this.result.set(result); if (['completed', 'cancelled', 'error'].includes(result.state)) { this.running.set(false); this.searchId.set(null); } },
          error: error => { this.toast.show(`La recherche a échoué : ${error.message}`, 'error'); this.running.set(false); this.searchId.set(null); },
        });
      },
      error: error => { this.toast.show(`Impossible de démarrer la recherche : ${error.message}`, 'error'); this.running.set(false); },
    });
  }

  cancelSearch(): void {
    const id = this.searchId(); if (!id) return;
    this.api.cancelSearch(id).subscribe({ next: () => this.toast.show('Demande d’annulation envoyée.', 'success'), error: error => this.toast.show(error.message, 'error') });
  }
}
