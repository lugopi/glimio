import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';
import { DependencyBannerComponent } from './dependency-banner.component';

describe('DependencyBannerComponent', () => {
  let fixture: ComponentFixture<DependencyBannerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DependencyBannerComponent],
      providers: [provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(DependencyBannerComponent);
    fixture.componentRef.setInput('title', 'Configuration requise');
    fixture.componentRef.setInput('issues', [{
      key: 'transcription',
      message: 'Le moteur de transcription n’est pas prêt.',
      providerId: 'whisper-local',
      fallbackProviderId: 'whisper-local',
      requiredProviderIds: ['ffmpeg-runtime'],
      linkLabel: 'Provider requis :',
    }]);
    fixture.detectChanges();
  });

  it('renders one accessible banner and links required providers to settings', () => {
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('[role="status"]')).not.toBeNull();
    expect(element.textContent).toContain('Configuration requise');
    expect(element.textContent).toContain('Le moteur de transcription n’est pas prêt.');
    const link = element.querySelector('a') as HTMLAnchorElement;
    expect(element.textContent).toContain('Provider requis :');
    expect(link.textContent).toBe('ffmpeg-runtime');
    expect(link.getAttribute('href')).toContain('/settings');
  });

  it('supports assertive announcements for blocking dependency issues', () => {
    fixture.componentRef.setInput('role', 'alert');
    fixture.detectChanges();
    const banner = (fixture.nativeElement as HTMLElement).querySelector('.dependency-banner');
    expect(banner?.getAttribute('role')).toBe('alert');
    expect(banner?.getAttribute('aria-live')).toBe('assertive');
  });

  it('does not render an empty banner when there are no issues', () => {
    fixture.componentRef.setInput('issues', []);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.dependency-banner')).toBeNull();
  });
});
