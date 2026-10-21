import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ProviderOption, ProviderStatus } from '../core/api.models';
import { CheckboxFieldComponent } from './checkbox-field.component';

@Component({
  selector: 'glimio-provider-options',
  standalone: true,
  imports: [FormsModule, NgTemplateOutlet, CheckboxFieldComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './provider-options.component.html',
  styleUrl: './provider-options.component.scss',
})
export class ProviderOptionsComponent {
  readonly provider = input.required<ProviderStatus>();
  readonly values = input<Record<string, unknown>>({});
  readonly showAllOptions = input(false);
  readonly perJobOnly = input(false);
  readonly optionChange = output<{ option: ProviderOption; value: unknown }>();

  options(advanced: boolean): ProviderOption[] {
    const values = this.values();
    return this.provider().options.filter(option => (this.showAllOptions() || option.advanced === advanced)
      && (this.perJobOnly() ? option.per_job : !option.per_job)
      && (!option.depends_on || values[option.depends_on] === option.depends_value));
  }

  value(option: ProviderOption): unknown {
    return this.values()[option.key] ?? option.default;
  }

  fieldId(option: ProviderOption): string {
    return `${this.provider().id}-${option.key}`.replace(/[^a-zA-Z0-9_-]/g, '-');
  }

  update(option: ProviderOption, value: unknown): void {
    this.optionChange.emit({ option, value: option.type === 'number' ? Number(value) : value });
  }
}
