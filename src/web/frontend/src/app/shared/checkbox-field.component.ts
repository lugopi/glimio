import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'glimio-checkbox-field',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './checkbox-field.component.html',
  styleUrl: './checkbox-field.component.scss',
})
export class CheckboxFieldComponent {
  readonly fieldId = input.required<string>();
  readonly title = input.required<string>();
  readonly description = input.required<string>();
  readonly checked = input(false);
  readonly disabled = input(false);
  readonly checkedChange = output<boolean>();
}
