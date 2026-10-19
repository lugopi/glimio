import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { IconComponent } from './icon.component';

type PageToken = number | 'ellipsis-start' | 'ellipsis-end';

@Component({
  selector: 'glimio-pagination',
  standalone: true,
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './pagination.component.html',
  styleUrl: './pagination.component.scss',
})
export class PaginationComponent {
  readonly page = input.required<number>();
  readonly pageSize = input.required<number>();
  readonly totalItems = input.required<number>();
  readonly label = input('Pagination');
  readonly pageChange = output<number>();
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.totalItems() / Math.max(1, this.pageSize()))));
  readonly rangeStart = computed(() => this.totalItems() === 0 ? 0 : (this.page() - 1) * this.pageSize() + 1);
  readonly rangeEnd = computed(() => Math.min(this.page() * this.pageSize(), this.totalItems()));
  readonly pageTokens = computed<PageToken[]>(() => {
    const total = this.totalPages();
    const current = Math.min(Math.max(1, this.page()), total);
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    if (current <= 4) return [1, 2, 3, 4, 5, 'ellipsis-end', total];
    if (current >= total - 3) return [1, 'ellipsis-start', total - 4, total - 3, total - 2, total - 1, total];
    return [1, 'ellipsis-start', current - 1, current, current + 1, 'ellipsis-end', total];
  });

  isPageNumber(token: PageToken): token is number { return typeof token === 'number'; }

  selectPage(page: number): void {
    if (page >= 1 && page <= this.totalPages() && page !== this.page()) this.pageChange.emit(page);
  }
}
