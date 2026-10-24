import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SessionSummary } from '../../core/api.models';
import { IconComponent } from '../../shared/icon.component';
import { SelectableListComponent } from '../../shared/selectable-list.component';

@Component({
  selector: 'glimio-search-session-picker',
  standalone: true,
  imports: [FormsModule, IconComponent, SelectableListComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './search-session-picker.component.html',
  styleUrl: './search-session-picker.component.scss',
})
export class SearchSessionPickerComponent {
  @Input() sessions: SessionSummary[] = [];
  @Input() selectedCount = 0;
  @Input() filter = '';
  @Input() isSelected: (id: string) => boolean = () => false;
  @Input() dateLabel: (value?: string, fallback?: string) => string = (_value, fallback = '') => fallback;
  @Input() durationLabel: (value?: number | null) => string = () => '—';
  readonly sessionTrackKey = (session: SessionSummary, _index: number) => session.id;
  readonly sessionIsHighlighted = (session: SessionSummary) => this.isSelected(session.id);
  @Output() readonly filterChange = new EventEmitter<string>();
  @Output() readonly toggleSession = new EventEmitter<SessionSummary>();
  @Output() readonly close = new EventEmitter<void>();
}
