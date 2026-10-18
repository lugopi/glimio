import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'glimio-icon',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './icon.component.html',
  styleUrl: './icon.component.scss',
})
export class IconComponent {
  readonly name = input.required<string>();
  readonly size = input<'normal' | 'large'>('normal');
  readonly strokeWidth = input('1.6');
  spriteHref(): string { return `/static/vendor/heroicons/heroicons.svg#${this.name()}`; }
}
