# Nettoyage documentaire et code mort — 17 octobre 2026

Suivi AH-334 (audit/documentation) et AH-340 (code). Demande utilisateur : documents utiles aux reprises IA, moins de doublons, suppression des dépendances/code réellement morts, qualité préservée.

## Documents réellement traités

Inventaire de **281 documents**, suivis et non suivis, hors SDK, modèles/caches, fichiers générés bin/obj et artefacts lourds. Le classement fichier par fichier distingue lecture ciblée du contenu et inventaire de métadonnées ; il ne prétend pas que chaque ligne de toutes les archives a été relue.

**23 documents condensés, 5 fichiers redondants retirés**, après sauvegarde vérifiée de **51 originaux**. Sur les fichiers traités : **4 147 584 → 61 703 octets actifs**. L’archive compacte conserve intégralement le contenu original ; cette réduction ne compte pas comme suppression des preuves. [Reçu détaillé](document-cleanup.json), [inventaire initial](document-inventory.json), [récupération](../ARCHIVES.md).

- AGENTS/CLAUDE/REPRISE/ETAT-PROJET convergent vers **ETAT-COURANT**.
- TODO et INDEX-JIRA pointent vers le backlog vivant et la revue individuelle, sans second état de tickets à maintenir.
- Les contrats Quality/Fast et le guide d’étages distinguent le livré, les limites et les demandes non livrées. Le schéma de profil est conservé.
- Le rapport de qualification du 15 octobre garde ses mesures ; seuls les préambules de reprise périmés sont retirés.
- DEVELOPMENT et RELEASE remplacent les anciennes interdictions de tests et procédures/version « actuelles » dépassées par les règles et les sources réelles.
- Les relais historiques gardent de courtes redirections. Les deux copies source-snapshot ne servent plus de points d’entrée avec des liens relatifs cassés.
- Retraits après archive : PROMPT-REPRISE-IMPLEMENTATION, backlog-import.csv, backlog-plan-before-validation-policy.json, backlog-plan.json, validation-policy-update-plan.json. L’outil d’export initial reste historique et ne doit pas régénérer le backlog courant.

Preuves de lots, reçus de publication/commentaires, contrats utiles, licences et notices conservés. Le comparatif utilisateur est inchangé. Aucun SDK, média, modèle, cache, fichier d’installation utilisateur ou worktree original n’est supprimé. Les historiques Jira ne sont pas rejoués automatiquement.

L’inventaire relevait 62 liens manquants dans le checkout ancien : 31 existent dans les sources .82, 21 appartiennent aux snapshots désormais redirigés, d’autres aux nouveaux exports en cours. Deux liens SETTINGS des documents embarqués restent à corriger dans un futur lot de documentation produit ; ne pas confondre ce constat avec une régression du moteur.

## Code supprimé et utilité

Base isolée .82, changement livré par le lot .83, source `dee1f6b1f38db7a4071ada4b2926ccd1f853dcf7` :

| Suppression | Preuve d’absence d’utilité / contrôle |
|---|---|
| Champ `Platform.ManagerAsset` et deux arguments | Aucun lecteur, sérialisation ni réflexion ; noms HDR actifs conservés. Compilation builder2,98s, 0warning/erreur. |
| Fonction Lua locale `bridged()` | Aucun appel/callback ; syntaxe Lua valide après retrait. |
| Deuxième copie scripts/shaders dans AppRun | Boucle précédente réalise déjà la copie ; fixture CPU31entrées identiques (contenu/modes/symlinks), ajouts utilisateur conservés, invocations cp7→5. Syntaxe shell valide. |

[Qualification lot56](../archive/2026-10-17/qualification/lot-56-cleanup-20261017.md), [preuve builder](managerasset-cleanup-check.json). Aucun changement du moteur, des modèles, de Quality/Fast ou du flux vidéo, aucun gain FPS revendiqué. Pas de nouveau benchmark vidéo nécessaire. La publication est contrôlée séparément avant Done.

## Retraits non effectués sans preuve suffisante

[Inventaire des 14 candidats](deadcode-candidates.json), [analyse moteurs/lecteur](deadcode-dependencies.md), [analyse Manager/packaging](deadcode-manager-packaging.md).

- `exec_ref.cpp`, callbacks ORT/CRTP, chargements via réflexion/ViewLocator et modèles énumérés restent utilisés : une recherche textuelle naïve produirait des faux positifs.
- FRUC est encore une dépendance de build du pipeline et un chemin livré. Son retrait relève du lot complet AH-328, avec migration et fichiers installés, pas d’un effacement opportuniste.
- Les packages UI Fluent/HyperText et EngineStore sont des candidats à revoir pendant la refonte ; absence de référence visible seule insuffisante sans contrôle du rendu et des services. SevenZipExtractor/SharpZipLib sont réellement utilisés.
- Les couches Linux/Windows et helper TrueHDR historique/nouveau pipeline n’ont pas la même provenance ; « doublon » ne signifie pas automatiquement interchangeable.

## Reprise et entretien

Après un lot, remplacer les faits dans ETAT-COURANT et ajouter un reçu daté ; ne plus empiler plusieurs « points courants ». Les analyses longues restent dans audit/qualification et ne sont lues que si le ticket le nécessite. Pour les autres dépôts, suivre la [carte des sources](repositories.md) ; le README de l’ancien helper backend et les documents Manager demandent aussi une clarification de leurs routes et versions lors des lots concernés.

La prochaine demande est la **refonte entière de l’expérience Manager**, suivie sous AH-224 par AH-341/342/343, en conservant la composition libre des quatre catégories. [Préflight des branches et parcours](manager-redesign-preflight.md). Les profils préexistants et les capacités des moteurs restent des contrats, pas des paramètres à simplifier silencieusement.
