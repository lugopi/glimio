import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ProviderOption, ProviderStatus } from '../core/api.models';

@Component({
  selector: 'glimio-provider-options',
  standalone: true,
  imports: [FormsModule, NgTemplateOutlet],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './provider-options.component.html',
  styleUrl: './provider-options.component.scss',
})
export class ProviderOptionsComponent {
  readonly provider = input.required<ProviderStatus>();
  readonly values = input<Record<string, unknown>>({});
  readonly showAllOptions = input(false);
  readonly optionChange = output<{ option: ProviderOption; value: unknown }>();

  options(advanced: boolean): ProviderOption[] {
    return this.provider().options.filter(option => this.showAllOptions() || option.advanced === advanced);
  }

  value(option: ProviderOption): unknown {
    return this.values()[option.key] ?? option.default;
  }

  update(option: ProviderOption, value: unknown): void {
    this.optionChange.emit({ option, value: option.type === 'number' ? Number(value) : value });
  }
}
