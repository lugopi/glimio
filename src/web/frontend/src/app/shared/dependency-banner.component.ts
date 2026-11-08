import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { IconComponent } from './icon.component';

export interface DependencyBannerIssue {
  key: string;
  message: string;
  providerId?: string;
  fallbackProviderId?: string;
  requiredProviderIds?: string[];
  linkLabel?: string;
  linkTask?: string | null;
}

@Component({
  selector: 'glimio-dependency-banner',
  standalone: true,
  imports: [RouterLink, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dependency-banner.component.html',
  styleUrl: './dependency-banner.component.scss',
})
export class DependencyBannerComponent {
  readonly title = input.required<string>();
  readonly role = input<'status' | 'alert'>('status');
  readonly description = input<string | null>(null);
  readonly issues = input<DependencyBannerIssue[]>([]);
  readonly settingsActionLabel = input<string | null>(null);
  readonly actionLabel = input<string | null>(null);
  readonly actionDisabled = input(false);
  readonly action = output<void>();
}
