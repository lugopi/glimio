import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class LibraryStateService {
  readonly total = signal(0);
}
