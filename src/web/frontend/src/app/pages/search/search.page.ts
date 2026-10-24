import { ChangeDetectionStrategy, Component, computed, HostListener, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { SearchSource, SessionSummary } from '../../core/api.models';
import { SearchSourcesComponent } from './search-sources.component';
import { SearchSessionPickerComponent } from './search-session-picker.component';
import { DocumentExportService } from '../../shared/document-export.service';
import { ToastService } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { renderMarkdownToHtml } from '../../shared/markdown';
import { SearchStateService } from './search-state.service';

@Component({
  standalone: true,
  imports: [FormsModule, IconComponent, SearchSourcesComponent, SearchSessionPickerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './search.page.html',
  styleUrl: './search.page.scss',
})
export class SearchPageComponent {
  readonly state = inject(SearchStateService);
  private readonly api = inject(ApiService);
  private readonly documentExport = inject(DocumentExportService);
  private readonly toast = inject(ToastService);
  readonly query = this.state.query;
  readonly running = this.state.running;
  readonly searchId = this.state.searchId;
  readonly result = this.state.result;
  readonly page = signal(1);
  readonly pageSize = signal(10);
  readonly sessions = signal<SessionSummary[]>([]);
  readonly selectedSessions = signal<SessionSummary[]>([]);
  readonly sessionPickerOpen = signal(false);
  readonly sessionFilter = signal('');
  readonly mentionTerm = signal<string | null>(null);
  readonly excludedSourceSelection = signal<Record<string, boolean>>({});
  readonly sources = computed(() => this.result()?.sources ?? []);
  readonly isSessionSelectedFn = (id: string) => this.isSessionSelected(id);
  readonly sessionDateLabelFn = (value?: string, fallback = '') => this.sessionDateLabel(value, fallback);
  readonly durationLabelFn = (value?: number | null) => this.durationLabel(value);
  readonly sourceIncludedFn = (source: SearchSource) => this.sourceIncluded(source);
  readonly sourceBadgeLabelFn = (source: SearchSource) => this.sourceBadgeLabel(source);
  readonly sourceRetryMessage = computed(() => this.result()?.state === 'cancelled' ? 'La synthèse a été annulée. Vous pouvez la relancer avec les extraits conservés.' : 'La synthèse n’a pas pu être générée. Réessayez avec les extraits conservés.');
  readonly visibleSources = computed(() => {
    const start = (this.page() - 1) * this.pageSize();
    return this.sources().slice(start, start + this.pageSize());
  });
  readonly matchingSessions = computed(() => {
    const term = (this.mentionTerm() ?? this.sessionFilter()).trim().toLocaleLowerCase();
    const selectedIds = new Set(this.selectedSessions().map(session => session.id));
    const isMention = this.mentionTerm() !== null;
    return this.sessions()
      .filter(session => !isMention || !selectedIds.has(session.id))
      .filter(session => !term || session.title.toLocaleLowerCase().includes(term) || session.id.toLocaleLowerCase().includes(term));
  });
  readonly filteredSessions = computed(() => this.matchingSessions().slice(0, 8));
  readonly pickerSessions = computed(() => this.matchingSessions().slice(0, 1000));
  readonly suggestionOpen = computed(() => this.mentionTerm() !== null);
  readonly answerHtml = computed(() => renderMarkdownToHtml(this.result()?.answer ?? ''));
  readonly includedSourceCount = computed(() => this.sources().filter(source => this.sourceIncluded(source)).length);
  readonly hasPendingSourceChanges = computed(() => this.sources().some(source => {
    const id = this.sourceIdentity(source);
    return (this.excludedSourceSelection()[id] ?? (source.included !== false)) !== (source.included !== false);
  }));

  constructor() {
    this.api.sessions({ limit: 'all' }).subscribe({
      next: response => this.sessions.set(response.items),
    });
  }

  sessionDateLabel(value?: string, fallback = ''): string {
    if (!value) return fallback;
    const date = new Date(value);
    const locale = document.documentElement.lang === 'en' ? 'en-CH' : 'fr-CH';
    return Number.isNaN(date.getTime())
      ? value
      : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }

  durationLabel(value?: number | null): string {
    if (value == null || !Number.isFinite(value) || value < 0) return '—';
    const seconds = Math.floor(value);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    const pad = (n: number) => String(n).padStart(2, '0');
    return hours > 0 ? `${hours}:${pad(minutes)}:${pad(rest)}` : `${pad(minutes)}:${pad(rest)}`;
  }

  runSearch(): void {
    if (this.mentionTerm() !== null) return;
    this.state.runSearch(this.selectedSessions().map(session => session.id));
    if (this.running() && !this.result()) {
      this.page.set(1);
      this.excludedSourceSelection.set({});
      this.sessionPickerOpen.set(false);
    }
  }

  onQueryChange(value: string): void {
    this.query.set(value);
    const match = value.match(/@([^@\n]*)$/);
    this.mentionTerm.set(match ? match[1].trim() : null);
    this.sessionPickerOpen.set(false);
  }

  addSession(session: SessionSummary): void {
    if (!this.selectedSessions().some(item => item.id === session.id)) {
      this.selectedSessions.update(current => [...current, session]);
    }
    if (this.mentionTerm() !== null) {
      this.query.set(this.query().replace(/(?:^|\s)@[^@\n]*$/, '').trimEnd());
      this.mentionTerm.set(null);
    }
    this.sessionFilter.set('');
    this.sessionPickerOpen.set(false);
  }

  removeSession(id: string): void {
    this.selectedSessions.update(current => current.filter(session => session.id !== id));
  }

  toggleSession(session: SessionSummary): void {
    if (this.selectedSessions().some(item => item.id === session.id)) {
      this.removeSession(session.id);
    } else {
      this.selectedSessions.update(current => [...current, session]);
    }
  }

  toggleSessionPicker(): void {
    this.sessionPickerOpen.update(open => !open);
    if (this.mentionTerm() !== null) {
      this.query.set(this.query().replace(/(?:^|\s)@[^@\n]*$/, '').trimEnd());
    }
    this.mentionTerm.set(null);
  }

  isSessionSelected(id: string): boolean {
    return this.selectedSessions().some(session => session.id === id);
  }

  sourceIdentity(source: SearchSource): string {
    return source.source_id ?? String(source.source_number);
  }

  sourceIncluded(source: SearchSource): boolean {
    return this.excludedSourceSelection()[this.sourceIdentity(source)] ?? (source.included !== false);
  }

  sourceBadgeLabel(source: SearchSource): string {
    const pendingIncluded = this.sourceIncluded(source);
    const committedIncluded = source.included !== false;
    if (pendingIncluded !== committedIncluded) return pendingIncluded ? 'À inclure' : 'À exclure';
    return committedIncluded ? `Source ${source.citation_number ?? source.source_number}` : 'Exclu';
  }

  toggleSource(source: SearchSource): void {
    const id = this.sourceIdentity(source);
    this.excludedSourceSelection.update(selection => ({
      ...selection,
      [id]: !this.sourceIncluded(source),
    }));
  }

  confirmSourceSelection(): void {
    const sourceIds = this.sources()
      .filter(source => this.sourceIncluded(source))
      .map(source => this.sourceIdentity(source));
    if (sourceIds.length === 0 || this.running()) return;
    this.page.set(1);
    this.state.regenerateSynthesis(sourceIds);
  }

  changePageSize(value: number | string): void {
    const nextSize = Number(value);
    if (![5, 10, 25, 50].includes(nextSize)) return;
    this.pageSize.set(nextSize);
    this.page.set(1);
  }

  exportAnswerMarkdown(): void {
    const answer = this.result()?.answer;
    if (!answer?.trim()) return;
    this.documentExport.downloadMarkdown(answer, 'Synthèse générale', this.searchId() ?? 'synthese-generale');
    this.toast.show('Synthèse générale exportée au format Markdown.', 'success');
  }

  printAnswerPdf(): void {
    const answer = this.result()?.answer;
    if (!answer?.trim()) return;
    if (!this.documentExport.openPrintView(answer, 'Synthèse générale')) {
      this.toast.show('Autorisez les fenêtres contextuelles pour imprimer ou enregistrer la synthèse en PDF.', 'info');
    }
  }

  @HostListener('document:click', ['$event'])
  closeSummaryActionsOnOutsideClick(event: MouseEvent): void {
    const target = event.target;
    if (!(target instanceof Node)) return;
    document.querySelectorAll<HTMLDetailsElement>('details.search-summary-actions-menu[open]').forEach(menu => {
      if (!menu.contains(target)) menu.open = false;
    });
  }

  @HostListener('document:keydown.escape')
  closeSummaryActionsOnEscape(): void {
    document.querySelectorAll<HTMLDetailsElement>('details.search-summary-actions-menu[open]').forEach(menu => {
      menu.open = false;
    });
  }

  cancelSearch(): void { this.state.cancelSearch(); }
}
