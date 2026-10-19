import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { PaginationComponent } from '../../shared/pagination.component';
import { IconComponent } from '../../shared/icon.component';
import { renderMarkdownToHtml } from '../../shared/markdown';
import { SearchStateService } from './search-state.service';

@Component({
  standalone: true,
  imports: [FormsModule, RouterLink, IconComponent, PaginationComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './search.page.html',
  styleUrl: './search.page.scss',
})
export class SearchPageComponent {
  readonly state = inject(SearchStateService);
  readonly query = this.state.query;
  readonly running = this.state.running;
  readonly searchId = this.state.searchId;
  readonly result = this.state.result;
  readonly page = signal(1);
  readonly pageSize = 5;
  readonly sources = computed(() => this.result()?.sources ?? []);
  readonly visibleSources = computed(() => {
    const start = (this.page() - 1) * this.pageSize;
    return this.sources().slice(start, start + this.pageSize);
  });
  readonly answerHtml = computed(() => renderMarkdownToHtml(this.result()?.answer ?? ''));

  runSearch(): void {
    this.page.set(1);
    this.state.runSearch();
  }

  cancelSearch(): void { this.state.cancelSearch(); }
}
