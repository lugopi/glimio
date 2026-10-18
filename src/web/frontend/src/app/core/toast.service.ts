import { Injectable, signal } from '@angular/core';

export interface ToastMessage {
  id: number;
  message: string;
  kind: 'success' | 'error' | 'info';
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly messages = signal<ToastMessage[]>([]);
  private nextId = 1;

  show(message: string, kind: ToastMessage['kind'] = 'info'): void {
    const id = this.nextId++;
    this.messages.update(items => [...items, { id, message, kind }]);
    window.setTimeout(() => this.dismiss(id), 4000);
  }

  dismiss(id: number): void {
    this.messages.update(items => items.filter(item => item.id !== id));
  }
}
