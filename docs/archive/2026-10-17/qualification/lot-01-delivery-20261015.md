# Lot 01 — AH-229 / DEL-06, 15 octobre 2026

Release prévue : **3.8.0.32** ; parent source `55bbc8503736b29740e3857b0cd01132dbd64873`. Travail isolé dans `/home/ta2b/.animejanai-tools/work/tickets-20261015`. Aucun fichier utilisateur repris dans le commit.

## Changement et bénéfice

Les trois workflows utilisent un groupe par commit et ne s’annulent plus entre lots. Après publication réussie, un petit job commun prend le verrou `release-latest` et compare les numéros avant de promouvoir. Seule cette promotion attend les autres plateformes ; les compilations restent indépendantes. `queue: max` évite l’annulation des promotions en attente. L’ordre manifest/paquet de l’Updater reste celui de la référence.

## Essai nécessaire et résultat

`python3 tests/release/publication_check.py` exécute les scripts réels avec une API `gh` simulée : mêmes versions et même ordre de fin (3.8.0.33 puis 3.8.0.32). Référence `55bbc85` : latest régresse à .32. Candidat : latest reste .33. Une promotion répétée ne modifie rien ; un upload échoué retourne une erreur et garde latest. Ordre des uploads inchangé. Essai concluant, non répété. Artefact local : `artifacts/performance/lots-20261015/lot-01/publication.json` du worktree utilisateur.

Bénéfice : permettre l’enchaînement demandé sans perdre les builds précédents. Pas de gain FPS attendu, aucune modification de la chaîne d’image ; moteurs et modèles épinglés inchangés. Pas d’essai GPU nécessaire pour ce changement de publication.

`bash -n` passe. Actionlint 1.7.12 vérifie les quatre workflows après exclusion de son seul diagnostic de schéma périmé sur `queue`. Cette propriété est documentée officiellement : https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency. La validation serveur et les builds réels restent à observer après push ; ce test simulé ne les remplace pas.

## État et suite

AH-229 : incrément livraison concurrente implémenté et qualifié localement ; ticket global non clos. Commentaire Jira préparé, non envoyé (connecteur absent). Release non déclarée complète avant vérification des assets. Ancienne référence 3.8.0.31 conservée. Le lot suivant (AH-11, export de référence) commence pendant les builds de ce lot.
