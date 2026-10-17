# Préparation de la refonte du Manager — 17 octobre 2026

Lecture seule des branches applicatives et des captures existantes. **Aucune refonte commencée** : terminer le lot actuel d'audit/nettoyage et sa publication avant de modifier l'interface. La cible utilisateur est une refonte complète de l'expérience du Manager, avec conservation des moteurs, profils personnels et travaux utiles déjà préparés.

## Relecture du rapport global

Les constats Manager, la base livrée `2847c799` et les défauts GMFSS sont corrects. Deux précisions transmises au coordinateur :

- La conversion d'une politique temporelle inconnue vers Fast existe déjà dans PLAYER .82, `AnimeJaNaiPlatform/PlatformServices.cs:23`. Elle ne doit pas être attribuée exclusivement à la branche de nettoyage ; le renommage resize Bilinear, lui, est pending.
- Un aperçu de profil montre le demandé/résolu. Sans média ouvert, certaines dimensions restent inconnues ; l'identité réellement chargée relève d'AH-234 et l'enveloppe mémoire d'AH-53. Ne pas promettre ces observations comme déjà disponibles dans le petit plan initial AH-339.

## Carte des sources à réunir

Tous les worktrees mentionnés sont sous `/home/ta2b/.animejanai-tools/work/`.

| Source | État vérifié | Utilisation sûre |
|---|---|---|
| `manager-fruc-protection-20261017`, `2847c799` | Propre ; Manager .81 repris dans .82. Quatre catégories, HDR TrueHDR unique ; ancien éditeur/profils et FRUC encore présents. | Base connue de la prochaine branche Manager. Ne pas prendre arbitrairement le checkout utilisateur `hdr-settings-0.8`, qui pointe ailleurs. |
| `manager-chain-cleanup-20261017` | Même HEAD ; 7 fichiers modifiés, 3 nouveaux projets de tests non suivis. Retrait ancien éditeur/profils/globals conversion ; HDR mpv et migration. | Reprendre ses changements sémantiques et tests, corriger la fidélité/position du resize et la validation avant livraison. Le XAML peut ensuite être réorganisé. |
| `manager-remove-fruc-20261017` | **Diff suivi strictement identique** au précédent et 6 fichiers de tests non suivis identiques octet par octet. | Ce n'est pas une deuxième implémentation du retrait FRUC. N'appliquer qu'une copie du patch. AH-328 reste à réaliser. |
| `lot-51-chain-cleanup-20261017` PLAYER, `e5df509` + dirty | Contrat partagé `PlatformServices`, routage Lua HDR/profils, macOS, nouveau `pipeline-hdr.lua`, tests. | Reporter sur le PLAYER le plus récent après .83 ; conserver les preuves mais corriger le resize. Ne pas livrer seulement le Manager sans ce routage correspondant. |
| `manager-vfi-preparation-20261017`, `d4b868f` | Un commit de 6 fichiers sur `2847c799`, puis 4 lignes dirty dans `PreparationViewModel`. | Conserver ViewModel/protocole/settings et nouvelle vue. Corriger cycle annulation ; intégrer la navigation dans la refonte au lieu de reprendre tout l'ancien écran. |
| `lot-54-vfi-preparation-20261017` PLAYER, `c475aee` | Commits `c3f56ea`/`c475aee` sur `e5df509`, puis 7 fichiers dirty : codecs et packaging worker. | Garder contrat/worker original, corrections codecs et fichiers livrés. Corriger validation 60 s et publication avant qualification finale AH-313. |

Sur les différences suivies examinées, lot51 ne recoupe les commits .81→.82 que dans `docs/REPRISE.md` ; lot54 n'a aucun recouvrement textuel. Cela facilite le report mais ne prouve pas la compatibilité fonctionnelle. Dans le Manager, lot51 et GMFSS touchent tous deux `MainWindowViewModel.cs` et `MainWindow.axaml` : réintégrer les petits raccords GMFSS dans la nouvelle navigation, sans écraser les suppressions de lot51. Le code de fermeture de fenêtre doit toujours annuler/attendre le job possédé.

## Direction UX concrète

Les captures montrent surtout un problème de hiérarchie : conditions d'activation toujours ouvertes, actions import/export proéminentes, longues notices techniques, mélange « chaîne »/« maillon », plusieurs grandes cartes ouvertes et réglages essentiels repoussés sous le pli. Le nettoyage lot51 supprime des doublons, mais conserve cette disposition ; il ne constitue pas à lui seul la refonte demandée.

Proposition à mettre en œuvre après le lot courant :

- Navigation stable **Profils / Préparer une vidéo / Moteurs et composants / Réglages**. Diagnostic et export de référence accessibles depuis une aide/état commun, sans multiplier les réglages concurrents.
- Dans un profil : nom, choix du profil de démarrage et résumé du résultat d'abord ; une ligne de traitement lisible, puis cartes compactes repliées. Une carte sélectionnée expose ses réglages. Un seul ajout propose les quatre catégories, puis la technologie se choisit dans sa catégorie.
- Distinguer les **règles d'application** du profil et les **étapes de traitement** ; présenter les conditions résolution/FPS dans une section secondaire. Résolution et cadence prévues visibles dans le résumé, exemple clairement identifié lorsque le média n'est pas connu.
- Conserver les choix experts dans des sections avancées. Quality/Fast uniquement dans RIFE ; downscale séparé ; HDR unique avec mpv/TrueHDR. Une position HDR non prise en charge est refusée explicitement, jamais déplacée silencieusement.
- Les moteurs indisponibles affichent une cause et une action d'installation. Réunir composants et SDK dans un même espace ; les chemins Python/poids de GMFSS restent accessibles dans la configuration du moteur plutôt que dans le formulaire principal. Préparation hors ligne distincte de la lecture en temps réel.
- Validation commune UI/sauvegarde/plan, état explicite enregistré/incomplet, import préservant les données inconnues. Les profils FRUC importés restent explicables lors du retrait ; aucun remplacement silencieux par RIFE.

Conserver Avalonia, le modèle persistant et les services utiles. Réorganiser les vues et extraire les responsabilités nécessaires suffit ; pas de nouveau moteur de graphe ni de langage de profil. Prévoir le flux principal à largeur réduite et au clavier, sans exiger le mode expert pour réussir un profil simple.

## Références visuelles et contrôles réutilisables

Captures disponibles sous la racine PLAYER, **repères historiques/pending**, pas captures du binaire utilisateur actuel :

- `artifacts/performance/lots-20261017/lot-51-chain-cleanup/ui/manager-profiles.png` et `categories-and-mpv-hdr.png` : nettoyage pending, pas livré .82. Première capture inspectée pendant cette revue.
- `artifacts/performance/lots-20261016/lot-46/ui/stage-categories-compact.png` : catégories historiques, inspectée ; SDK/maillons encore techniques.
- `artifacts/performance/lots-20261017/lot-48/ui/hdr-stage.png`, `lot-49/ui/optional-truehdr.png`, `lot-52-fruc-protection/ui/fruc-protection.png` : contrôles précis acquis.

Tests headless existants : `SettingsUi` (large/étroit, variantes plateforme), `ChainCleanup` (captures et migration), `ChainFollowups`, `ConversionRetirement`, `ProfileRoundTrip`, `InterpolationPersistence`, `OptionalSdks`. Adapter seulement ce que la refonte change, sans rejouer leurs campagnes concluantes. Aucun screenshot du nouveau préparateur GMFSS trouvé dans ces artefacts ; `Views/Preparation.axaml` reste sa source inspectable.

Reprise sûre : isoler la branche de refonte depuis les pins livrés, sauvegarder patches et fichiers non suivis avec leurs empreintes, reporter une seule fois lot51 et les fonctionnalités GMFSS retenues, puis corriger les défauts avant les nouveaux écrans. Qualifier les parcours utilisateur courts et la migration ; aucun benchmark vidéo pour la seule disposition UI. Les modifications du contrat/ordre de traitement demandent leur contrôle moteur ciblé séparé. Ne supprimer les worktrees ni les preuves antérieures avant intégration et publication vérifiées.
