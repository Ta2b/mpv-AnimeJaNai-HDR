# Diagnostic documentaire — 17 octobre 2026

Inventaire figé avant tri : **281 documents**, **5 409 354 octets** ; parcours filesystem des fichiers suivis et non suivis, avec exclusions explicites des artefacts, caches/builds, SDK utilisateur et métadonnées Git. Les propositions de classement ne prouvent pas que chaque phrase a été auditée : `review_level` sépare lecture ciblée, structure et document nouvellement rédigé.

## Changements réalisés par cet agent

- Création de `docs/ETAT-COURANT.md` : état .82, SHA, résultats/limites, demandes encore non livrées et règles stables, sans reprise automatique d’une ancienne pause ou file de lots.
- Création de `docs/ARCHIVES.md` : navigation logique vers preuves et historiques. Aucun déplacement ni suppression d’un fichier antérieur.
- Inventaire `document-inventory.json`, diagnostic des liens `document-links-classified.json`.

## Condensation à réaliser par l’agent principal

1. AGENTS/CLAUDE/REPRISE/ETAT-PROJET : un seul point d’entrée courant. CLAUDE contient encore tests interdits et absence de suite ; remplacer ces assertions périmées. Conserver architecture pertinente près des guides techniques.
2. TODO/INDEX-JIRA/README-Jira : garder critères et correspondances utiles, arrêter la duplication des statuts/totaux/imports. Le backlog initial de 222 tâches n’est pas le backlog courant de l’audit.
3. CHANTIER-QUALITY-FAST : contrat durable et liens vers mesures ; archive compressée de l’original avec les checkpoints.
4. QUALIFICATION-FEATURES : retirer seulement préambules de reprise périmés, conserver les cas concluants détaillés, leurs limites et leurs artefacts.
5. Retirer PROMPT-REPRISE-IMPLEMENTATION après archivage : il impose AH-11 et répète les règles stables ; aucun autre prompt ne doit imposer un ancien prochain lot.
6. Historiques longs CHANTIER-PERFORMANCE-RELAIS/RIFE-165HZ/GPU-SPECIALISE, catalogue OPTIMISATIONS, audit15oct, DECOUPAGE et PAUSE : conserver contenu original récupérable, rendre le rôle historique explicite. Ne pas déplacer les preuves pour seulement réduire un compte de fichiers.

## Contradictions précises à neutraliser

- `CLAUDE.md:19` : « no tests/benchmarks authorized » contredit le mandat du 15/16 octobre ; les autres mentions de CI sans tests décrivent une configuration passée, pas une interdiction de qualification locale.
- `docs/REPRISE.md:5` : pause générale et .82 non publiée malgré .82 vérifiée en ligne 1. Les checkpoints .79/.81 et l’ancien prochain AH-259 ne doivent plus être des instructions.
- `docs/TODO-PERFORMANCE-INTERPOLATION.md:3,15` : .72/AH-302 en cours, puis prochain AH-259. Les tickets et reçus contemporains ont priorité.
- `docs/PROMPT-REPRISE-IMPLEMENTATION.md:5` : démarrage imposé REF-01/AH-11 sans rapport avec la tâche actuelle.
- `docs/jira/INDEX-JIRA.md` : 222 tâches et recherches de modèles reportées sont des données d’import ; demandes ultérieures de nouveaux interpolateurs et retrait FRUC les ont dépassées.
- Les anciens rapports FRUC restent des preuves datées : préserver leur contenu ne signifie pas continuer son intégration, désormais remplacée par AH-328.

## Liens locaux absents : distinguer contexte de branche et véritable erreur

62 liens cibles n’existaient pas au moment exact de capture. Répartition après confrontation avec la source livrée .82 :

- `embedded_document_wrong_relative_settings_link` : 2.
- `generated_after_snapshot` : 2.
- `audit_export_in_progress_parent_agent` : 6.
- `present_in_release_worktree_missing_in_older_root` : 31.
- `snapshot_copied_to_different_directory_relative_links_not_rebased` : 21.

Les références vers tests/surfaces/outils ajoutés après le HEAD documentaire racine existent souvent dans le worktree de livraison .82 : elles ne démontrent pas une suppression de code. Préférer un lien source immuable ou préciser la révision d’exécution plutôt que copier des tests pour « réparer » le checkout documentaire.

Les snapshots Jira ont été copiés sous `docs/jira` en conservant des liens relatifs initialement valables sous `docs` ; ce sont des copies de provenance, à annoter comme telles plutôt que transformer leur contenu historique. Les deux liens SETTINGS des documents embarqués ANALYSE/PARTAGE pointent réellement dans un mauvais répertoire. Les exports de l’audit principal étaient encore en cours lors de cette vérification.

Aucun crawl réseau, compilation ou essai vidéo n’est nécessaire pour ce tri. Préserver les SHA des originaux dans une archive avant condensation permet de retrouver tout détail omis du point d’entrée compact.
