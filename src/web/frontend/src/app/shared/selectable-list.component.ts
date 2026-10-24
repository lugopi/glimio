import { ChangeDetectionStrategy, Component, ContentChild, Input, TemplateRef } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';

export interface SelectableListRowContext<T> {
  $implicit: T;
  index: number;
}

@Component({
  selector: 'glimio-selectable-list',
  standalone: true,
  imports: [NgTemplateOutlet],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './selectable-list.component.html',
  styleUrl: './selectable-list.component.scss',
})
export class SelectableListComponent<T> {
  @Input() items: readonly T[] = [];
  @Input() trackKey: (item: T, index: number) => unknown = (_item, index) => index;
  @Input() highlighted: (item: T) => boolean = () => false;
  @Input() muted: (item: T) => boolean = () => false;
  @Input() surface = false;
  @Input() scrollable = false;

  @ContentChild('row', { read: TemplateRef }) rowTemplate?: TemplateRef<SelectableListRowContext<T>>;
  @ContentChild('empty', { read: TemplateRef }) emptyTemplate?: TemplateRef<unknown>;

  trackItem(item: T, index: number): unknown {
    return this.trackKey(item, index);
  }

  isHighlighted(item: T): boolean {
    return this.highlighted(item);
  }

  isMuted(item: T): boolean {
    return this.muted(item);
  }
}
