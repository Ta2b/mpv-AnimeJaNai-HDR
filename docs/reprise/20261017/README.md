# Reprise guidée — 17 octobre 2026

Ces procédures sont écrites pour une IA qui reprend sans le contexte de conversation. Elles sont aussi publiées **dans les descriptions Jira**, avec l'ancien périmètre conservé en dessous. Lire `docs/ETAT-COURANT.md`, puis uniquement le guide du ticket choisi et les contrats qu'il cite. Ne pas charger tous les guides ni réimporter le backlog AH.

## État et références

La release3.8.0.84 est **publiée et vérifiée**, trois CI réussies et17 assets. AH-313/325/326/328/341/342/343 sont Done ; les parents et reliquats restent ouverts. Aucun candidat du prochain lot n’est inclus dans cette release.

- PLAYER .84 : `f626ceb2154f1b90ff5c4e275e8bb31a969f1bc6` ; Manager `f1f85962f8e86e5f37d84501f37f72b6d1780828` compilé avec source partagée `69aca0b866a8625bb53bc265d308743cd1314269`.
- Backend Linux .84 : `36f3d94491b51d334dc9420ce6d5192b086b0a8f` ; bundle GPU `e48fb15b048db5ea39d3becbe9fdede6764f1941`.
- Sources isolées PLAYER/Manager : `/home/ta2b/.animejanai-tools/work/{lot-57-manager-ux-20261017,manager-ux-20261017}`. Le checkout documentaire racine contient des modifications utilisateur et peut être plus ancien : ne pas l'utiliser comme source de release.
- AH345/AH346 sont livrés depuis .85. AH344 : backend compilé/déjà livré, lecteur Windows apparié construit et livraison .103 en cours ; AH367 porte la qualification GPU restante. Les anciens patches sont des archives. Lire ETAT et Jira pour l’état courant.

## Ordre conseillé pour reprendre

1. Vérifier le reçu [release .84](../../jira/release-20261017-3.8.0.84.json) et finir uniquement les vérifications manquantes. Ne pas rejouer les essais concluants du lot57 ni reconstruire le Manager déjà publié.
2. Intégrer les changements prêts avec **un seul checkout backend** : [AH-345](AH-345.md) (score Fast>3), [AH-346](AH-346.md) (attentes des copies finales), [AH-344](AH-344.md) (cache DML exact). Préserver des commits distincts. Les deux premiers touchent des fichiers distincts, le troisième DML ; les producteurs Windows et Linux peuvent avancer en parallèle.
3. AH-344 nécessite le lecteur Windows patché avec la DLL. Le guide donne les deux producteurs et leurs pins distincts. Le même build spécialisé Windows peut fournir les DLL TRT d'AH-345 : ne pas les oublier en ne copiant que DirectML.
4. Pour les travaux Quality, traiter [AH-330](AH-330.md) (module réellement chargé), puis [AH-329](AH-329.md) et [AH-347](AH-347.md) (pads d'entrée paresseux). AH-345 et AH-347 touchent le même fichier : intégrer le premier avant de développer le second.
5. [AH-208](AH-208.md) coordonne le diagnostic et les gardes de fusion. Groupe logique ne signifie pas bloc natif unique. Garder la séparation Fast×2 décidée au lot55 ; Quality conserve toutes ses prédictions et ses frontières numériques.
6. En parallèle, choisir **un** premier sous-lot multiplateforme : [AH-348](AH-348.md) CoreML diagnostic, [AH-349](AH-349.md) Metal SPAN, [AH-350](AH-350.md) VideoToolbox, [AH-351](AH-351.md) Vulkan SPAN. Les parents [AH-121](AH-121.md), [AH-119](AH-119.md), [AH-120](AH-120.md), [AH-131](AH-131.md) restent ouverts pour leurs autres frontières. Les API et besoins des moteurs ne sont pas à uniformiser artificiellement.

## Ce qui est déjà codé dans .84

| Ticket | Travail et reprise |
|---|---|
| [AH-341](AH-341.md) | Navigation du Manager ; vérifier la livraison, pas de refonte à recommencer. |
| [AH-342](AH-342.md) | Profils libres et quatre catégories ; préserver l'ordre/activation et l'unicité HDR. |
| [AH-343](AH-343.md) | Moteurs/composants et page Préparer. |
| [AH-325](AH-325.md) | Ancien éditeur et trois profils intégrés retirés ; migration fidèle. |
| [AH-326](AH-326.md) | HDR mpv/TrueHDR par profil, doublons globaux retirés. |
| [AH-328](AH-328.md) | FRUC retiré, anciens profils préservés/incompatibilité explicite. |
| [AH-313](AH-313.md) | Préparation GMFSS réelle, limites CFR SDR8 CUDA/CuPy. |
| [AH-321](AH-321.md) | Area/Spline36 exécutés ; conclusion comparative restante [AH-352](AH-352.md). |
| [AH-339](AH-339.md) | Plan commun ; reliquat de décisions macOS [AH-353](AH-353.md). |
| [AH-224](AH-224.md) | Parent UX, ouvert tant que ses enfants/périmètres restent partiels. |
| [AH-93](AH-93.md) | Parent DML, cache exact AH-344 ne termine pas Fast/retiming. |

Jira n'autorise pas de sous-ticket sous un sous-ticket : AH-352 est rattaché à AH-297 comme AH-321 ; AH-353 est rattaché à AH-224 comme AH-339. Le reliquat est explicitement lié dans leurs descriptions. Ne pas recréer ces tickets.

## Sauvegardes et application des patches

Les quatre patches dans `patches/` contiennent le code préparé : AH-344 backend/PLAYER, AH-345 TRT, AH-346 pipeline. `preuves/` conserve les manifestes et les preuves courtes. Les empreintes sont dans `manifest.json`. Les sources candidates sous `/tmp` peuvent disparaître ; les patches versionnés sont la sauvegarde portable. Les binaires Linux candidats sont aussi dans `/home/ta2b/.animejanai-tools/work/lot-58-engine-handoff-20261017/` avec `SHA256.json`, hors Git.

Avant application : vérifier le SHA de base, `git status --short`, `git diff --check`, puis `git apply --check`. Appliquer une seule fois dans un checkout isolé. Ne jamais remplacer tout le `Program.cs` avec un miroir ancien. Les `origin` de plusieurs clones backend pointent un dossier local : pousser vers l'URL GitHub explicite donnée dans le guide. Aucun `git add -A`, `reset --hard`, nettoyage global ni mutation du backend utilisateur.

Lancer les builds puis poursuivre une tâche indépendante ; relever leur résultat à la fin de cette tâche. Pas de `gh run watch` ni polling. Retenir le run par **headSha**, pas parce qu'il est le dernier de la liste. Une compilation, un asset publié, son intégration dans le lecteur et son exécution native sont des preuves différentes.

Les contrôles ne sont pas une batterie obligatoire. Revue/compilation suffisent quand l'effet est établi ; essai court pour un doute réel ou une mesure effectivement revendiquée. Ne pas répéter un résultat concluant. Pas de gain FPS inventé, pas de qualité approximative sous le nom Quality, pas de qualification Windows/macOS/AMD/Intel déduite d'un GPU NVIDIA Linux.

## Fin de chaque ticket

In Progress au début du travail effectif ; commentaire de preuve court : versions/SHA, commande ou revue, résultat, limites, décision et lien de livraison. Done seulement après le périmètre complet et la vérification du paquet requis. Découper le reste, garder son parent ouvert. Mettre à jour ETAT-COURANT en remplaçant les faits périmés.

[AH-362 — route ABI9 Linux et configuration immuable](AH-362.md), suite explicite d’AH330 après AH361 ; voir ETAT-COURANT pour le statut de livraison.

[AH-364 — générations transactionnelles CoreML](AH-364.md), tranche d’AH254/AH32, et AH365 — SPAN CoreML résident, tranche d’[AH119](AH-119.md). AH349 est Done après .96, AH335 Done après .97 ; ETAT-COURANT et reçus remplacent les statuts datés du plan initial ci-dessus.
