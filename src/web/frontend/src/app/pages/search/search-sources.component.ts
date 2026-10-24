import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { SearchSource } from '../../core/api.models';
import { IconComponent } from '../../shared/icon.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { SelectableListComponent } from '../../shared/selectable-list.component';

@Component({
  selector: 'glimio-search-sources',
  standalone: true,
  imports: [FormsModule, RouterLink, IconComponent, PaginationComponent, SelectableListComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './search-sources.component.html',
  styleUrl: './search-sources.component.scss',
})
export class SearchSourcesComponent {
  @Input() sources: SearchSource[] = [];
  @Input() totalSources = 0;
  @Input() includedCount = 0;
  @Input() running = false;
  @Input() pendingChanges = false;
  @Input() retryMessage = '';
  @Input() page = 1;
  @Input() pageSize = 10;
  @Input() sourceIncluded: (source: SearchSource) => boolean = () => true;
  @Input() sourceBadgeLabel: (source: SearchSource) => string = source => String(source.source_number);
  readonly sourceTrackKey = (source: SearchSource, _index: number) => source.source_id ?? `${source.source_number}:${source.session_id}:${source.filename}`;
  readonly sourceIsIncluded = (source: SearchSource) => this.sourceIncluded(source);
  readonly sourceIsExcluded = (source: SearchSource) => !this.sourceIncluded(source);
  @Output() readonly toggleSource = new EventEmitter<SearchSource>();
  @Output() readonly confirmSelection = new EventEmitter<void>();
  @Output() readonly pageChange = new EventEmitter<number>();
  @Output() readonly pageSizeChange = new EventEmitter<number>();
}
