import { describe, expect, it } from 'vitest';
import { ProviderStatus } from './api.models';
import { missingProviderDependencyIds, requiredProviderDependencies, requiredProviderIdsForTask } from './provider-dependencies';

function provider(id: string, requires: string[] = []): ProviderStatus {
  return { id, name: id, requires } as ProviderStatus;
}

function ids(providers: readonly ProviderStatus[]): string[] {
  return providers.map(provider => provider.id);
}

describe('requiredProviderDependencies', () => {
  it('returns a direct dependency with the provider that requires it', () => {
    const denoise = provider('ffmpeg-denoise', ['ffmpeg']);
    const ffmpeg = provider('ffmpeg');
    const dependencies = requiredProviderDependencies(
      [denoise, ffmpeg],
      ['ffmpeg-denoise'],
    );

    expect(ids(dependencies.map(dependency => dependency.provider))).toEqual(['ffmpeg']);
    expect(dependencies[0].requiredBy.map(requiring => requiring.id)).toEqual(['ffmpeg-denoise']);
  });

  it('walks transitive dependencies and reports the selected root as the requirer', () => {
    const separator = provider('speechbrain-sepformer', ['ffmpeg', 'speechbrain-ecapa']);
    const ffmpeg = provider('ffmpeg', ['ffmpeg-runtime']);
    const runtime = provider('ffmpeg-runtime');
    const ecapa = provider('speechbrain-ecapa');
    const dependencies = requiredProviderDependencies(
      [separator, ffmpeg, runtime, ecapa],
      ['speechbrain-sepformer'],
    );

    expect(ids(dependencies.map(dependency => dependency.provider))).toEqual([
      'ffmpeg',
      'speechbrain-ecapa',
      'ffmpeg-runtime',
    ]);
    expect(dependencies.every(dependency => dependency.requiredBy.map(item => item.id).join() === 'speechbrain-sepformer')).toBe(true);
  });

  it('does not return a dependency that is already selected', () => {
    const separator = provider('speechbrain-sepformer', ['ffmpeg', 'speechbrain-ecapa']);
    const ffmpeg = provider('ffmpeg');
    const ecapa = provider('speechbrain-ecapa', ['torch']);
    const torch = provider('torch');
    const dependencies = requiredProviderDependencies(
      [separator, ffmpeg, ecapa, torch],
      ['speechbrain-sepformer', 'speechbrain-ecapa'],
    );

    expect(ids(dependencies.map(dependency => dependency.provider))).toEqual(['ffmpeg', 'torch']);
    const torchDependency = dependencies.find(dependency => dependency.provider.id === 'torch');
    expect(torchDependency?.requiredBy.map(item => item.id)).toEqual(['speechbrain-ecapa']);
  });

  it('returns no dependency when selected providers declare none', () => {
    const native = provider('native');
    const none = provider('no-enhancement');

    expect(requiredProviderDependencies([native, none], ['native', 'no-enhancement'])).toEqual([]);
  });

  it('ignores unknown identifiers', () => {
    const denoise = provider('ffmpeg-denoise', ['ffmpeg', 'missing-provider']);
    const ffmpeg = provider('ffmpeg');

    expect(ids(requiredProviderDependencies([denoise, ffmpeg], ['ffmpeg-denoise']).map(dependency => dependency.provider))).toEqual(['ffmpeg']);
    expect(requiredProviderDependencies([denoise], ['unknown-provider'])).toEqual([]);
  });

  it('merges requirers when several selected providers need the same dependency', () => {
    const denoise = provider('ffmpeg-denoise', ['ffmpeg']);
    const deepfilter = provider('deepfilternet', ['ffmpeg']);
    const ffmpeg = provider('ffmpeg');
    const dependencies = requiredProviderDependencies(
      [denoise, deepfilter, ffmpeg],
      ['ffmpeg-denoise', 'deepfilternet'],
    );

    expect(dependencies).toHaveLength(1);
    expect(dependencies[0].requiredBy.map(item => item.id)).toEqual(['ffmpeg-denoise', 'deepfilternet']);
  });
});


describe('missingProviderDependencyIds', () => {
  it('prefers structured dependency details and preserves unknown plugin IDs', () => {
    const value = {
      ...provider('speechbrain-sepformer'),
      missing: ['provider requis : speechbrain-ecapa'],
      details: { missing_provider_dependencies: ['speechbrain-ecapa', 'plugin-not-installed'] },
    } as ProviderStatus;

    expect(missingProviderDependencyIds(value)).toEqual(['speechbrain-ecapa', 'plugin-not-installed']);
  });

  it('falls back to missing messages when structured details are not available', () => {
    const value = {
      ...provider('speechbrain-sepformer'),
      missing: ['checkpoint absent', 'provider requis : speechbrain-ecapa', 'Required provider: torch-runtime'],
    } as ProviderStatus;

    expect(missingProviderDependencyIds(value)).toEqual(['speechbrain-ecapa', 'torch-runtime']);
  });
});


describe('requiredProviderIdsForTask', () => {
  it('resolves required providers by role without depending on provider IDs', () => {
    const separator = { ...provider('new-separator', ['audio-tool', 'voice-identity']) , task: 'separation' } as ProviderStatus;
    const audioTool = { ...provider('audio-tool'), task: 'media' } as ProviderStatus;
    const identity = { ...provider('voice-identity', ['embedding-runtime']), task: 'speaker_embedding' } as ProviderStatus;
    const runtime = { ...provider('embedding-runtime'), task: 'media' } as ProviderStatus;

    expect(requiredProviderIdsForTask([separator, audioTool, identity, runtime], 'new-separator', 'speaker_embedding'))
      .toEqual(['voice-identity']);
  });

  it('handles unavailable roots and dependency cycles safely', () => {
    const first = { ...provider('first', ['second']), task: 'separation' } as ProviderStatus;
    const second = { ...provider('second', ['first']), task: 'speaker_embedding' } as ProviderStatus;

    expect(requiredProviderIdsForTask([first, second], 'missing-root', 'speaker_embedding')).toEqual([]);
    expect(requiredProviderIdsForTask([first, second], 'first', 'speaker_embedding')).toEqual(['second']);
  });
});
