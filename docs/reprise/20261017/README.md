# Reprise guidée — 17 octobre 2026

Lire d’abord [ETAT-COURANT](../../ETAT-COURANT.md), puis la description Jira et le guide du seul ticket choisi. Cet index n’est pas une seconde liste de statuts ; les reçus de release et Jira font foi. Ne pas réimporter le backlog AH ni rejouer les catalogues de tests.

## Travail courant

- [AH369](AH-369.md) : ajout d’étapes du Manager, correctif UI qualifié, livraison .106 vérifiée. Préserver les quatre catégories, composition libre, sélection et HDR unique.
- [AH368](AH-368.md) : étude d’ordonnancement Quality RIFE→SPAN, procédure détaillée dans Jira, prototype local compilé, qualification numérique/gain encore absents ; backend de départ118c272. Reprendre après AH369.
- [AH329](AH-329.md), [AH208](AH-208.md), [AH73](https://tatoub.atlassian.net/browse/AH-73) : débit Quality×4/fusion toujours ouverts. Une chaîne logique fusionnée ne prouve ni un seul moteur ni le respect du budget24fps. Garder les frontières numériques et chaque prédiction Quality.
- [AH367](AH-367.md) : qualification GPUWindows native du couple lecteur/DML livré .103, matériel encore absent. Ne pas reconstruire le producteur apparié de deux heures déjà publié.
- [AH119](AH-119.md), [AH120](AH-120.md), [AH131](AH-131.md), [AH93](AH-93.md) : parents CoreML/Metal/Vulkan/DML ouverts pour leurs frontières restantes, pas une reprise de leurs sous-tickets conclus.

## Résultats à réutiliser

Les guides portent les détails et les limites ; ETAT et les reçus de chaque version portent les SHA de livraison.

| Guides | Résultat déjà conclu |
| --- | --- |
| [AH357](AH-357.md) | Raccord natif de l’encodeur partagé rejeté : divergenceQuality, candidat hors production ; .105 documentation/outils seuls. |
| [AH350](AH-350.md) | Import expérimental VideoToolbox NV12SDR709→Metal, vrai mpv qualifié ; .104, aucune entrée SPAN/RIFE ni sortie rendu complète. |
| [AH344](AH-344.md) | LecteurWindows/DML appariés, implémentation/compilation/livraison .103 ; GPU restant AH367. |
| [AH353](AH-353.md), [AH339](AH-339.md) | Plan canonique macOS et hook de préchargement .102. |
| [AH366](AH-366.md) | Métadonnées ONNX en streaming .101, allocations supprimées ; aucun FPS d’inférence revendiqué. |
| [AH365](AH-365.md), [AH364](AH-364.md), [AH349](AH-349.md), [AH335](AH-335.md) | SPANCoreML résident, cache transactionnel, SPANMetal résident, préservation des configurations .96–.99. |
| [AH362](AH-362.md), [AH363](AH-363.md), [AH351](AH-351.md) | Route Quality Linux, identité bundle et SPANVulkan .94–.95. |
| [AH341](AH-341.md), [AH342](AH-342.md), [AH343](AH-343.md) | Navigation, profils modulaires et page moteurs/préparation ; AH369 corrige un vrai parcours de clic que les contrôles initiaux ne couvraient pas. |

Les autres guides numérotés restent accessibles directement depuis Jira. Les patches dans `patches/` et leurs preuves dans `preuves/` sont des archives de passation : vérifier leurs bases et les commits déjà intégrés avant toute application. Ne pas réappliquer AH344/345/346 ni remplacer un fichier actuel par un ancien miroir.

## Exécution et clôture

Checkouts isolés ; préserver profils, médias, SDK, modèles et modifications utilisateur. Pas de git add-A/reset/clean global ni push au backend original. In Progress au début ; Done après périmètre complet, qualification nécessaire et livraison vérifiée, parents partiels ouverts.

Lancer les builds puis avancer sur une tâche indépendante ; vérifier à sa fin par SHA complet. Aucun watch ou boucle d’attente. Essai moteur court avant/après, mêmes entrées/modèles/réglages/machine, arrêt à conclusion suffisante ; pas de replay concluant. UI/docs/packaging : contrôle simple adapté. Séparer travail supprimé, gain théorique et mesure réelle ; matériel absent ou bruit = limite explicite.
