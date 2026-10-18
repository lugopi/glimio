import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { NgIconComponent, provideIcons } from '@ng-icons/core';
import { glimioIconKey, GLIMIO_ICONS } from './icon-registry';

@Component({
  selector: 'glimio-icon',
  standalone: true,
  imports: [NgIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [provideIcons(GLIMIO_ICONS)],
  template: `<ng-icon [name]="iconKey()" [class.icon--large]="size() === 'large'" class="icon" aria-hidden="true"></ng-icon>`,
  styleUrl: './icon.component.scss',
})
export class IconComponent {
  readonly name = input.required<string>();
  readonly size = input<'normal' | 'large'>('normal');
  readonly strokeWidth = input('1.6');
  readonly iconKey = computed(() => glimioIconKey(this.name()));
}
