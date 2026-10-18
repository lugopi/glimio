# Licence, réutilisation commerciale et marque

## Choix du projet : GNU AGPL v3 ou ultérieure

Glimio adopte `AGPL-3.0-or-later` pour le code du projet. Cette licence copyleft est plus protectrice que MIT : les personnes qui distribuent une version modifiée doivent fournir le code source correspondant sous la licence AGPL, et une version modifiée mise à disposition des utilisateurs à travers un réseau doit leur offrir l’accès au code source correspondant. L’attribution et les notices de licence doivent être conservées.

**Limite importante : l’AGPL n’interdit pas la vente.** Une entreprise peut vendre une distribution conforme à l’AGPL, tant qu’elle respecte les obligations de licence, notamment la fourniture du code source correspondant. Les licences reconnues comme Open Source ne peuvent pas interdire l’usage commercial ou la vente, ni obliger un acteur à faire une contribution amont ou un don. C’est une condition de la définition Open Source de l’OSI : <https://opensource.org/osd>.

Cela veut dire qu’aucune licence libre ne peut garantir qu’un tiers ne vendra jamais sa propre distribution de Glimio. Le compromis choisi vise plutôt à empêcher un fork fermé : les dérivés distribués et les versions modifiées mises à disposition sur réseau restent soumis au copyleft AGPL.

## Si l’objectif commercial doit devenir obligatoire

Une clause imposant aux entreprises de contribuer au dépôt amont, de payer, de sponsoriser, ou leur interdisant de vendre n’est pas une licence Open Source reconnue. Il faudrait adopter une licence *source-available* avec restriction commerciale (par exemple une licence personnalisée ou la Business Source License configurée avec un changement de licence futur). Cela rendrait toutefois le projet moins ouvert et compliquerait l’utilisation par des tiers. Ne pas ajouter une telle clause à l’AGPL : cela créerait des conditions supplémentaires incompatibles avec l’objectif Open Source.

Pour encourager le soutien sans fermer les forks, le projet peut inviter les sociétés qui utilisent Glimio à financer le développement, publier leurs améliorations et sponsoriser les contributeurs, sans en faire une obligation légale.

## Protéger l’identité de Glimio

La licence du code n’accorde pas automatiquement le droit de se présenter comme le projet officiel ni d’utiliser les marques, logos, domaines ou éléments d’identité de Glimio. Conserver un nom de produit et des logos identifiables est une mesure pratique pour différencier le projet officiel des forks ; les droits et protections exacts dépendent toutefois de l’usage et des juridictions. Cette note n’est pas un avis juridique et ne prétend pas qu’une marque est enregistrée.

## Modèles et binaires

L’AGPL ne s’étend pas automatiquement aux poids IA et exécutables tiers. Chaque composant doit conserver ses conditions séparées ; consulte [`MODELS.md`](MODELS.md). En particulier, vérifie la quantification GGUF LFM exacte et les notices de toute conversion ONNX avant toute redistribution.
