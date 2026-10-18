import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
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

  it('shows the current range and page count', () => {
    expect(fixture.nativeElement.textContent).toContain('11–20 sur 25');
    expect(fixture.nativeElement.textContent).toContain('Page 2 / 3');
  });

  it('emits a previous page request from the shared control', () => {
    let requestedPage = 0;
    fixture.componentInstance.pageChange.subscribe(page => requestedPage = page);
    const previous = fixture.nativeElement.querySelector('button');
    previous.click();
    expect(requestedPage).toBe(1);
  });
});
