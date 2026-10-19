import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';
import { PaginationComponent } from './pagination.component';

describe('PaginationComponent', () => {
  let fixture: ComponentFixture<PaginationComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [PaginationComponent] }).compileComponents();
    fixture = TestBed.createComponent(PaginationComponent);
    fixture.componentRef.setInput('page', 2);
    fixture.componentRef.setInput('pageSize', 10);
    fixture.componentRef.setInput('totalItems', 25);
    fixture.detectChanges();
  });

  it('shows one range summary and labelled page-number controls', () => {
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('11–20 sur 25 éléments');
    expect(element.querySelectorAll('.pagination-summary')).toHaveLength(1);
    expect(element.querySelectorAll('.pagination-page')).toHaveLength(3);
    expect(element.querySelector('[aria-current="page"]')?.textContent?.trim()).toBe('2');
    expect(element.querySelector('[aria-label="Page 3"]')).not.toBeNull();
    expect(element.querySelector('[aria-label="Page suivante"]')).not.toBeNull();
  });

  it('emits a previous page request from the shared control', () => {
    let requestedPage = 0;
    fixture.componentInstance.pageChange.subscribe(page => requestedPage = page);
    const previous = fixture.nativeElement.querySelector('button[aria-label="Page précédente"]') as HTMLButtonElement;
    previous.click();
    expect(requestedPage).toBe(1);
  });

  it('keeps the range summary but hides redundant navigation for one page', () => {
    fixture.componentRef.setInput('page', 1);
    fixture.componentRef.setInput('pageSize', 10);
    fixture.componentRef.setInput('totalItems', 7);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('1–7 sur 7 éléments');
    expect(fixture.nativeElement.querySelector('.pagination-controls')).toBeNull();
  });

  it('does not render stale page information when there are no items', () => {
    fixture.componentRef.setInput('page', 1);
    fixture.componentRef.setInput('totalItems', 0);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('nav')).toBeNull();
    expect((fixture.nativeElement as HTMLElement).textContent.trim()).toBe('');
  });
});
