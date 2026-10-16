# Lot 19 — export de rapports comparables

AH-25 / OBS-07. Base .50, source `d8fe421176c54386ff389ad16186e16594468d4b`. Outil Python stdlib à la demande, indépendant du lecteur ; pins GPU/Manager, modèles et calcul d’image inchangés. Contrat et commandes : [RAPPORTS-PERFORMANCE](../RAPPORTS-PERFORMANCE.md).

Avant : rapports de tests spécifiques à chaque cas, aucun exporteur commun des distributions/conditions de comparaison. Après : export JSON à partir de mesures brutes identifiées, scopes réseau résident/chaîne sans affichage/lecture présentée distincts, comparabilité contrôlée, empreintes des traces/script, médiane/P95/P99/max/coût par paire, ratio média/mural et ressources observées. Compilation/warm-up/incomplet exclus, capteurs absents explicitement inconnus. Pas de collecte périodique ou de fabrication de métriques depuis des moyennes.

## Essai court ciblé

`tests/performance/report_check.py tools/performance-report.py OUT`, une invocation de 0,2 s environ, données **synthétiques déclarées fixtures** et résultats calculés indépendamment à la main :

- Durées 1/2/3/4 ms : médiane2,5 ; P95=3,85 ; P99=3,97 ; max4. Valeurs compile10000/warmup1000 et incomplet200 exclues, compteurs d’exclusion vérifiés. Coûts par paire5/7 ms : médiane6, sans remultiplication RIFE.
- Fenêtre média3 s/mur2 s : débit1,5. Diviser les latences par deux laisse ce débit mural identique ; l’outil distingue bien les deux métriques et ne déclare aucun gain établi.
- Compteurs de fixture : 120 J/2 s=60 W, allocations/bytes conservés. Température50→54 °C sur2 s : delta4, pente2 °C/s, **stabilité non établie**.
- Ressources absentes : `not_measured`. Scope différent ou charge de bureau inconnue : comparaison refusée, pas de fichier. Fenêtre incluant warm-up : refus. Destination déjà existante : contenu préservé.

Revue complémentaire du contexte : une valeur de modèle imbriquée `unknown` doit aussi interdire la comparaison. Garde récursive ajoutée ; **seul ce nouveau cas** exécuté (`--nested-context-only`), rapport individuel partiel permis et paire refusée. Les cas conclusifs antérieurs ne sont pas rejoués ; la garde ne modifie pas les distributions/unités testées.

Artefacts dans `artifacts/performance/lots-20261016/lot-19/`, dont traces before/after déclarées fixtures, rapports, logs, `summary.json` et `nested-context-summary.json`. Syntaxe Python et diff vérifiés. Aucun benchmark réel du lecteur effectué ni gain FPS revendiqué pour un outil de rapport ; utilité établie par exactitude des statistiques, contrôle des conditions et refus des conclusions trompeuses. Aucun changement de calcul d’image.

## Limites et livraison

Le collecteur reste responsable des mesures brutes, identités réellement chargées, capteurs et observation de présentation. L’exporteur ne vérifie pas indépendamment leurs déclarations ; ces limites restent visibles dans chaque JSON. Une courte série ne prouve ni la stabilité du débit ni celle de la température. Les collecteurs/placements natifs restent leurs tickets d’instrumentation, sans être déclarés livrés ici.

Source/outil dans l’archive source du projet, commande Python documentée ; aucun ajout de dépendance au runtime du lecteur. Release du lot prévue .51, après push et qualification ; AH-25 reste In Progress jusqu’à vérification de la publication complète.
