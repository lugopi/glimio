# Glimio — état de l’audit d’accessibilité

**Périmètre :** revue statique de l’interface HTML, CSS et JavaScript fournie dans ce dépôt de travail, plus calcul automatique des principales paires de jetons de contraste. Aucun scan axe-core dans un vrai navigateur ni test manuel avec un lecteur d’écran n’a encore été réalisé pour cette livraison. Ce document n’est pas une déclaration formelle de conformité ni un audit certifié.

**Référence utilisée :** WCAG 2.2, publiée comme recommandation du W3C. La conformité à un niveau signifie satisfaire tous les critères de succès applicables du niveau visé et des niveaux inférieurs. Le seul contraste ne suffit donc pas à revendiquer AAA.

Références officielles :

- [WCAG 2.2 — Recommendation (W3C)](https://www.w3.org/TR/WCAG22/)
- [WCAG 2.2 Quick Reference — Contrast (Enhanced), 1.4.6](https://www.w3.org/WAI/WCAG22/quickref/#contrast-enhanced)
- [WCAG 2.2 — critères ajoutés dans la version 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)
- [Méthodologie d’évaluation WCAG-EM 2.0](https://www.w3.org/TR/wcag-em-2/)

## Conclusion à ce stade

**Non : il n’est pas possible d’affirmer que Glimio respecte actuellement l’ensemble des exigences WCAG 2.2 AAA.** Une vérification statique du code et des jetons de couleur permet de contrôler certains points mais ne prouve pas le comportement réel de tous les écrans, états, navigateurs ou technologies d’assistance.

Les changements récents rendent les couleurs de texte principales plus contrastées, fournissent des états de focus visibles au niveau CSS et conservent des contrôles HTML natifs autant que possible. Cela représente une amélioration ; ce n’est pas une certification AAA ni encore une déclaration complète de conformité AA.

## Contraste : résultats calculés sur les jetons de thème

État recalculé pour les jetons de thème actuels de la version 0.2.0. La table mesure le ratio WCAG entre chaque couleur de texte/statut et `--c-surface-raised`, ainsi que le contraste du texte du bouton primaire (`--c-accent-contrast`) sur son fond (`--c-accent`). Le ratio est calculé à partir de la luminance relative sRGB avec `scripts/check_theme_contrast.py`.

| Thème | Texte principal | Texte atténué | Texte secondaire | Succès | Avertissement | Erreur | Texte du bouton primaire |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sombre | 13,90:1 | 9,43:1 | 8,11:1 | 9,75:1 | 10,12:1 | 8,76:1 | 8,48:1 |
| Clair | 15,41:1 | 7,42:1 | 8,52:1 | 7,80:1 | 7,50:1 | 7,92:1 | 8,44:1 |
| Minuit | 14,02:1 | 9,61:1 | 8,30:1 | 9,14:1 | 10,24:1 | 8,87:1 | 9,51:1 |
| Forêt | 12,86:1 | 8,88:1 | 7,80:1 | 8,69:1 | 9,25:1 | 8,00:1 | 10,40:1 |

Ces résultats dépassent 7:1 pour **les couleurs et fonds indiqués seulement**, ce qui respecte le seuil de contraste du texte normal AAA (critère 1.4.6) sur ces paires. Ce tableau ne porte pas sur toutes les combinaisons de couleurs du CSS, les états survolés/actifs, les éléments natifs du navigateur, les transparences/compositions, les images ou les contenus dynamiques.

## État par domaines

| Domaine | État | Éléments connus / validation nécessaire |
|---|---|---|
| Contraste de texte (1.4.6 AAA) | Partiellement vérifié | Les principales paires de jetons ci-dessus passent 7:1. Toutes les combinaisons réelles de texte, arrière-plans, liens, messages, survols et états d’erreur ne sont pas encore auditées. |
| Contraste non textuel (1.4.11 AA) | À vérifier | Mesurer toutes les bordures de champs, icônes significatives, indicateurs d’état et focus contre les couleurs adjacentes. |
| Utilisation au clavier (2.1.x) | À tester manuellement | Parcourir enregistrement, import, configuration avancée, bibliothèque, pagination, renommage/suppression, recherche et annulation sans souris. Vérifier l’absence de piège clavier. |
| Focus visible / non masqué (2.4.7 AA, 2.4.11 AA, 2.4.12 AAA, 2.4.13 AAA) | Partiellement préparé, conformité inconnue | Une règle `:focus-visible` est présente. Reste à mesurer contraste, épaisseur/étendue de l’indicateur AAA et vérifier qu’aucun overlay ne recouvre le focus. |
| Structure et noms accessibles (1.3.x, 2.4.x, 4.1.2) | À tester | Vérifier ordre des titres, libellés de tous les champs, noms des boutons à icône, annonces des changements d’état et de progression, rôles et relations avec un arbre d’accessibilité réel. |
| Agrandissement, reflow et espacement (1.4.4, 1.4.10 AA, 1.4.12 AA, 1.4.8 AAA) | À tester | Tester à 200 % et 400 %, fenêtre étroite, zoom texte, hauteur/espacement de ligne et absence de défilement bidimensionnel non nécessaire. |
| Cibles et gestes (2.5.5 AAA, 2.5.8 AA) | À mesurer | Vérifier la taille et l’espacement des petites cibles, notamment icônes et boutons de pagination. |
| Audio/vidéo et médias (1.2.x) | À examiner selon le contenu | L’application est centrée sur l’audio et peut afficher un lecteur natif. Examiner les exigences applicables selon que les médias font partie d’un contenu préenregistré, s’ils sont décoratifs ou si une transcription alternative est disponible. |
| Compréhension et erreurs (3.1.x, 3.3.x) | À tester | Examiner les messages d’erreur, les instructions, les aides contextuelles, les confirmations destructives, la prévention des erreurs et le niveau de lecture. |
| Mouvement, temporisation, mises à jour (2.2.x, 2.3.x) | À tester | Examiner les états en direct, animations, messages temporisés, clignotement éventuel et possibilité de réduire les animations. |
| Lecteurs d’écran et navigateurs | Non vérifié | Tester au minimum NVDA avec Firefox ou Chrome sous Windows et les navigateurs cibles réellement pris en charge. |

## Points spécifiques de Glimio à traiter

1. Vérifier les annonces accessibles lors des mises à jour de l’enregistrement, du suivi en direct, du statut de traitement, des résultats de recherche et de pagination. Une région `aria-live` globale ne suffit pas toujours à expliquer les changements pertinents.
2. Vérifier que le panneau « Réglages avancés » expose `aria-expanded` et `aria-controls` cohérents et que son contenu est retiré de l’ordre de tabulation lorsqu’il est fermé.
3. Vérifier clavier + lecteur d’écran pour renommer/supprimer une séance, les confirmations, les erreurs API, les sélecteurs de documents et les éléments de bibliothèque cliquables.
4. Contrôler le lecteur audio natif dans chaque navigateur cible ; ses commandes accessibles et son rendu ne sont pas complètement contrôlables par le CSS de l’application.
5. Ajouter une suite automatique basée sur axe-core (ou outil équivalent) dans un vrai navigateur pour repérer les erreurs statiques. Ces résultats devront être combinés avec les tests manuels, pas utilisés comme preuve isolée de conformité.
6. Après correction des défauts automatiques, réaliser une évaluation manuelle basée sur WCAG-EM, documenter les critères applicables un à un et faire tester les parcours principaux par des personnes utilisant des technologies d’assistance.

## Politique de déclaration

Tant que ces vérifications ne sont pas terminées, la formulation honnête à utiliser dans le README ou dans une présentation est : **« Glimio améliore progressivement son accessibilité ; le contraste des principales couleurs de texte a été renforcé, mais la conformité globale WCAG 2.2 AAA n’a pas été démontrée. »** Ne pas employer « certifié AAA », « conforme AAA » ou « 100 % accessible » sans preuves couvrant l’application complète.

## Typographie et styles navigateur — amélioration 0.2.4

- La taille de base du texte est maintenant `1rem` (généralement 16 px selon les réglages du navigateur), plutôt que 14 px fixe.
- Les tailles explicites de texte dans les styles runtime et les sources Tailwind utilisent `rem`; les textes auxiliaires les plus petits ont été relevés à environ 12 px ou davantage.
- Une feuille de normalisation compacte basée sur modern-normalize (licence MIT) est chargée avant les styles de l’application, afin de réduire les différences de styles par défaut entre navigateurs.
- Ces changements améliorent la mise à l’échelle et la cohérence, mais ne démontrent pas à eux seuls la conformité WCAG. Il faut toujours tester le zoom à 200–400 %, les préférences de taille de texte, les retours à la ligne et les composants dans un vrai navigateur.

