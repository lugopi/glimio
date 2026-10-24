import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';
import { IconComponent } from './icon.component';

@Component({
  selector: 'glimio-audio-track-item',
  standalone: true,
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './audio-track-item.component.html',
  styleUrl: './audio-track-item.component.scss',
})
export class AudioTrackItemComponent {
  @Input({ required: true }) track = '';
  @Input({ required: true }) label = '';
  @Input({ required: true }) src = '';
  @Input() disabled = false;
  @Input() canDisable = true;
  @Input() actionsDisabled = false;
  @Output() readonly toggleDisabled = new EventEmitter<void>();
  @Output() readonly deleteTrack = new EventEmitter<void>();
}
