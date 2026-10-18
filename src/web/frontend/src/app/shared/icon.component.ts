import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { glimioIconKey, GLIMIO_ICONS } from './icon-registry';

@Component({
  selector: 'glimio-icon',
  standalone: true,
  imports: [NgIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './icon.component.html',
  styleUrl: './icon.component.scss',
  providers: [provideIcons(GLIMIO_ICONS)],
})
export class IconComponent {
  readonly name = input.required<string>();
  readonly size = input<'normal' | 'large'>('normal');
  /** Registry key in @ng-icons (see icon-registry.ts). */
  readonly iconKey = computed(() => glimioIconKey(this.name()));
}
