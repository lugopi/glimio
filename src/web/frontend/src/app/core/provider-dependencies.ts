import { ProviderStatus } from './api.models';


/**
 * Read provider dependencies that prevented a provider from becoming ready.
 * Prefer the structured API detail and fall back to the human-readable missing
 * entries for older provider payloads. Unknown IDs are preserved on purpose:
 * the settings page can still route to the requiring provider when a plugin is
 * absent from the current catalogue.
 */
export function missingProviderDependencyIds(provider: ProviderStatus): string[] {
  const declared = provider.details?.['missing_provider_dependencies'];
  const structuredIds = Array.isArray(declared)
    ? declared.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    : [];
  const messageIds = provider.missing.flatMap(value => {
    const match = value.match(/^(?:provider requis|required provider)\s*:\s*(.+)$/i);
    return match?.[1]?.trim() ? [match[1].trim()] : [];
  });
  return [...new Set([...structuredIds, ...messageIds])];
}

/** Return all known providers of a given task required by a provider's dependency graph. */
export function requiredProviderIdsForTask(
  providers: readonly ProviderStatus[],
  providerId: string,
  task: ProviderStatus['task'],
): string[] {
  const providersById = new Map(providers.map(provider => [provider.id, provider]));
  const root = providersById.get(providerId);
  if (!root) return [];
  const visited = new Set<string>([providerId]);
  const queue = [...root.requires];
  const requiredIds: string[] = [];

  for (let index = 0; index < queue.length; index += 1) {
    const dependencyId = queue[index];
    if (visited.has(dependencyId)) continue;
    visited.add(dependencyId);
    const dependency = providersById.get(dependencyId);
    if (!dependency) continue;
    if (dependency.task === task) requiredIds.push(dependency.id);
    queue.push(...dependency.requires);
  }
  return requiredIds;
}

/** A provider required by one or more selected providers. */
export interface ProviderDependency {
  /** The required provider, as reported by the providers API. */
  provider: ProviderStatus;
  /** Selected providers that require it, directly or through another dependency. */
  requiredBy: ProviderStatus[];
}

/**
 * Resolve the provider dependencies that must stay configurable.
 *
 * Selected providers are walked recursively through `requires`. A provider that
 * is already selected is never returned as a dependency, even when another
 * selected provider requires it, because it is already configurable in its own
 * settings block. Unknown identifiers are ignored so the UI tolerates a
 * catalogue that evolves independently.
 */
export function requiredProviderDependencies(
  providers: readonly ProviderStatus[],
  selectedProviderIds: readonly (string | null | undefined)[],
): ProviderDependency[] {
  const providersById = new Map(providers.map(provider => [provider.id, provider]));
  const selectedIds = new Set(
    selectedProviderIds.filter((id): id is string => !!id && providersById.has(id)),
  );
  const dependencies = new Map<string, ProviderDependency>();

  for (const selectedId of selectedIds) {
    const selected = providersById.get(selectedId);
    if (!selected) continue;
    const visited = new Set<string>([selectedId]);
    const queue = [...selected.requires];

    for (let index = 0; index < queue.length; index += 1) {
      const dependencyId = queue[index];
      if (selectedIds.has(dependencyId) || visited.has(dependencyId)) continue;
      visited.add(dependencyId);
      const provider = providersById.get(dependencyId);
      if (!provider) continue;

      let dependency = dependencies.get(dependencyId);
      if (!dependency) {
        dependency = { provider, requiredBy: [] };
        dependencies.set(dependencyId, dependency);
      }
      if (!dependency.requiredBy.includes(selected)) dependency.requiredBy.push(selected);
      queue.push(...provider.requires);
    }
  }

  return [...dependencies.values()];
}
