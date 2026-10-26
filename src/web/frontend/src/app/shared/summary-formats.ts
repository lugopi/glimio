/** Shared output-format choices for the recording defaults and per-session options. */
export const summaryFormatOptions = [
  {
    code: 'auto',
    label: 'Automatique',
    description: 'Glimio choisit le format selon le but du contenu ; en cas de doute, il utilise la synthèse générale.',
  },
  {
    code: 'summary',
    label: 'Résumé général',
    description: 'Pour les contenus variés : vue d’ensemble par thèmes, explications et points importants.',
  },
  {
    code: 'narrative',
    label: 'Récit narratif',
    description: 'Pour les livres audio, fictions et roleplays : événements, scènes, personnages et évolution du récit.',
  },
  {
    code: 'dialogue',
    label: 'Dialogue / conversation',
    description: 'Pour les échanges, interviews et débats : points de vue, questions, réponses et désaccords.',
  },
  {
    code: 'learning',
    label: 'Cours / explication',
    description: 'Pour les cours, tutoriels et exposés : concepts, étapes, démonstrations et exemples.',
  },
  {
    code: 'daily',
    label: 'Point d’avancement',
    description: 'Pour les daily et suivis de projet : travail terminé, en cours, blocages et prochaines étapes.',
  },
  {
    code: 'technical',
    label: 'Analyse technique',
    description: 'Pour expliquer ou résoudre un sujet technique : fonctionnement, causes, solutions et limites.',
  },
  {
    code: 'formal',
    label: 'Réunion formelle',
    description: 'Pour un procès-verbal : sujets, décisions et actions explicites, sans rien inventer.',
  },
  {
    code: 'brainstorm',
    label: 'Idéation / brainstorming',
    description: 'Pour explorer des idées : pistes, variantes, avantages et limites, sans inventer de consensus.',
  },
] as const;

export type SummaryFormatCode = typeof summaryFormatOptions[number]['code'];

export function summaryFormatLabel(value: string): string {
  return summaryFormatOptions.find(option => option.code === value)?.label ?? value;
}

export function summaryFormatDescription(value: string): string {
  return summaryFormatOptions.find(option => option.code === value)?.description
    ?? 'Glimio produira une synthèse fidèle au contenu source.';
}
