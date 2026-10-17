# Audit architecture, publication et maintenance — 17 octobre 2026

Périmètre : source préparée pour 3.8.0.82, commit `0f3f6bfb7e76ca15647d74fc5a91405d3072be69`, worktree `/home/ta2b/.animejanai-tools/work/lot-55-rife-regression-20261017`. La lecture du code ne prouve ni la livraison de tous les artefacts ni leur chargement effectif. Aucun code produit, profil utilisateur ou ticket modifié. Deux essais CPU isolés : lanceur, puis méthodes de préservation/extraction copiées verbatim depuis la production ; aucun GPU.

## Conclusion

Le plus gros risque d’architecture est la coexistence de plusieurs autorités pour le même état : version déclarée, bibliothèques réellement chargées, `.pack-*`, `components.json`, manifestes, réglages historiques et pipeline ordonné. Avant d’ajouter des optimisations, rendre cet état cohérent et visible évitera de mesurer un autre moteur que celui qu’on croit qualifier. La structure multi-repos n’est pas en soi un défaut : les références immuables et contrats versionnés sont utiles. Le travail nécessaire concerne la résolution effective, les migrations et les transactions, pas une réécriture générale.

## Constats prioritaires

### A1 — P1 : une mise à jour AppImage peut laisser un ancien moteur local actif

**Preuve** : `installer/linux/AppRun:254–260` positionne `ANIMEJANAI_INFERENCE_DIR` sur le dossier inscriptible puis remplace uniquement liens symboliques et fichiers absents. Un fichier régulier `libaji_trt_rtx.so` d’une ancienne installation reste inchangé. `AppRun:149–152` renouvelle pourtant `version.txt`/`manifest.json`. L’inspection antérieure du profil utilisateur a effectivement trouvé une bibliothèque RTX régulière plus vieille ; ce constat de code confirme le mécanisme, sans affirmer quelle bibliothèque a été chargée dans une ancienne session.

**Essai réalisé** : exécution du vrai AppRun dans une fausse image et un XDG_DATA_HOME isolé. Résultat succès 0, manifeste neuf, fichier moteur régulier toujours ancien. Reçu `launcher-proof.json`. Aucun nouvel essai nécessaire pour établir le défaut.

**Approche** : distinguer moteurs gérés par l’application, runtimes téléchargés et overrides explicites. Résoudre les moteurs gérés depuis un répertoire identifié par contenu/version ; conserver les overrides dans un espace séparé visible. Au démarrage consigner chemin résolu + hash + ABI du module réellement chargé. Ne jamais effacer arbitrairement les SDK/modèles utilisateur.

**Rattachement** : approfondir AH-330, avec sous-tâche chargement et migration. Critère : ancienne copie régulière + nouvelle release ne peuvent plus produire une version déclarée neuve et un moteur ancien sans avertissement explicite.

### A2 — P1 : retirer un script géré de la distribution ne le retire pas d’une installation AppImage

**Preuve** : `installer/linux/AppRun:103–106,125–126` recopie les répertoires par-dessus les anciens sans supprimer les fichiers retirés. Un script Lua retiré continue donc à être autoloadé. L’essai unique A1 constate également `retired-managed.lua` conservé alors que le payload ne le contient plus.

**Approche** : inventaire de fichiers gérés, suppression des seuls fichiers précédemment gérés et maintenant retirés ; répertoire utilisateur distinct. Ne pas transposer aveuglément le `rm -rf` macOS (`installer/macos/launcher.sh:14–17`) aux répertoires pouvant contenir des personnalisations.

**Acceptation** : fixture v1→v2 avec script retiré, script modifié, script ajouté par l’utilisateur : retirer seulement le géré obsolète. Prioritaire pour la suppression FRUC et des anciens chemins HDR/chaînes (AH-328, AH-325, AH-326).

### A3 — P1 : la protection des configurations disparaît si le manifeste local est absent ou corrompu

**Preuve** : `AnimeJaNaiUpdater/Program.cs:1282–1284` charge exclusivement les chemins préservés du manifeste local ; `1345–1361` attrape toute erreur et retourne un ensemble vide. `CopyTree:1307–1316` peut alors écraser `animejanai.conf`, `mpv.conf`, les banques et réglages HDR pendant une mise à jour complète. Une installation ancienne sans manifeste constitue aussi ce chemin ; la sauvegarde actuelle ne vise que `input.conf` (`991`, `1364`).

**Approche** : noyau stable de chemins utilisateur préservés dans le code, enrichi par le manifeste ; refuser une migration destructive ambiguë, sauvegarde ciblée avant application. Pas de besoin d’un nouveau format de profil pour corriger ceci.

**Acceptation** : un test temporaire manifeste absent puis JSON invalide conserve profils/banques/raccourcis ; aucune suppression de fichiers utilisateur. Essai CPU réalisé avec les vraies méthodes extraites verbatim : manifeste absent et JSON invalide donnent `SHIPPED DEFAULT` à la place du profil utilisateur ; contrôle manifeste valide conserve `USER PROFILE`. Reçu `updater-preserve-proof.json`. Aucun profil réel touché.

### A4 — P1 : installation/mise à jour de composants sans transaction ni verrou commun

**Preuve** : `AnimeJaNaiUpdater/Program.cs:1894–1915` utilise le même dossier temporaire `animejanai-packs`, extrait directement dans l’installation active puis enregistre l’état. AppRun fait une seconde implémentation (`188–207`) avec archive fixe dans DATA et extraction directe. Une interruption peut laisser runtime/builder incohérents ; deux lanceurs peuvent partager la même archive. La mise à jour dossier copie l’application avant `RefreshPacksAsync` (`998–1001`), sans restauration si les composants échouent.

**Approche** : unique service d’installation invoqué par le lanceur et le Manager, verrou par installation, staging unique, contrôle contenu/ABI, publication par renommage d’un répertoire de version, état écrit après validation. Les variantes AppImage/macOS possèdent déjà une logique de remplacement qui peut servir de référence (`ReplaceBundle:934–952`).

**Acceptation** : injection d’échec à l’extraction et avant publication ; version antérieure encore démarrable, nouvelle installation rejouable ; deux installations concurrentes se sérialisent. Aucun benchmark vidéo requis.

### A5 — P1 : contrôle d’intégrité des packs fondé sur présence et somme des tailles, pas sur le contenu

**Preuve** : génération `BuildMpvUpscale2xAnimeJaNai/Program.cs:1508–1528,1562–1577` émet tailles/fichiers mais aucun hash d’archive ; réutilisation par version de dépendance et taille totale. `AnimeJaNaiUpdater/Program.cs:1641–1663` considère toutes tailles égales comme contenu conforme ; `1905–1906` extrait sans vérification cryptographique. AppRun ne vérifie pas non plus les archives (`199–202`). Ce défaut concerne en premier lieu les installations accidentellement incohérentes, même sans attaquant.

**Approche** : identité SHA-256 pour chaque pack et manifeste de fichiers (liens explicitement décrits), hash avant extraction et validation minimale après staging. Pour la vérification courante, cache de validation lié à identité/mtime plutôt que rehasher des gigaoctets à chaque vidéo. La même identité doit piloter la réutilisation CI et l’installation.

**Acceptation** : modifier un octet sans changer la taille, le pack doit être refusé. Un pack inchangé doit rester réutilisable. Regrouper avec A4 dans un même contrat d’installation, avec sous-tâches séparées et terminables.

### A6 — P2 : divergence du parsing de configuration et de la détection des composants

**Preuve** : `animejanai_backend.lua:42–66` ne reconnaît pas les espaces autour de `=`, scanne uniquement `chain_N_rife=yes/true` ; AppRun reconnaît des espaces mais cherche lui aussi uniquement l’ancien `chain_N_rife` (`235–239`). Le contrat canonique ordonné C# (`PlatformServices.cs:342–369`) décrit plutôt `stage_N_kind/method/runtime/enabled`. La suppression demandée des paramètres historiques cassera la détection anticipée du besoin de RIFE si ces consommateurs ne migrent pas ensemble. Les modèles présents sont validés par « un quelconque .onnx » (`backend.lua:122–136`), pas par le modèle sélectionné.

**Approche** : un petit résolveur de profil donnant JSON plan/capacités/dépendances effectives, ou au minimum corpus commun de fixtures partagé C#/C++/Lua avec version explicite. Aucun besoin d’un service distant. AppRun doit demander le plan au helper au lieu de maintenir un parseur grep.

**Acceptation** : profil uniquement ordonné, maillon désactivé, espaces, modèle absent, plusieurs interpolateurs ; toutes couches identifient les mêmes dépendances et le même ordre. Lier AH-325/326/332 et contrats pipelines déjà existants.

### A7 — P2 : des alias de politique inconnus deviennent silencieusement Fast

**Preuve** : `AnimeJaNaiPlatform/PlatformServices.cs:23–24` traduit tout autre texte que old/quality en fast ; migration legacy `390–394`. Un réglage inconnu/erroné peut dégrader la référence plutôt qu’être rejeté ou conservé comme inconnu. Le contrat explicite valide davantage, mais la migration reste concernée.

**Approche** : conversion fermée old→quality, new→fast, valeurs canoniques ; défaut documenté seulement en absence, erreur préservant le profil pour valeur inconnue. À rattacher à migration et fidélité, pas à un ticket de FPS.

### A8 — P2 : risque de blocage de l’extraction par lecture séquentielle des deux sorties

**Preuve** : `AnimeJaNaiUpdater/Program.cs:1263–1266` lit entièrement stderr avant stdout. Un extracteur remplissant stdout avant de fermer stderr bloque. L’assembleur applique déjà le bon motif concurrent (`Program.cs:1548–1553`).

**Approche/essai** : lire les deux flux simultanément, propagation exit code/cancel. Faux extracteur émettant plus d’un tampon pipe sur stdout puis stderr : un seul essai CPU suffit. Ce n’est pas une preuve que les archives habituelles dépassent aujourd’hui ce seuil.

## Architecture à conserver et renforcer

- Références de Manager et bundle GPU immuables ; contrôles ABI/TensorRT dans `InstallSpecializedInference:780–784` ; hashes du pipeline/FRUC vérifiés (`802–816`). Étendre ce même contrôle aux bibliothèques principales copiées sans vérifier les hashes du manifeste (`788–792`).
- Transactions de banques : verrou et détection de modifications concurrentes (`PlatformServices.cs:241–264`), écritures atomiques par fichier ; conserver et tester seulement les nouveaux chemins de migration.
- Contrat rationnel et pipeline explicite : préserve l’ordre, bloque version inconnue, évite aplatissement silencieux ; bonne base pour un plan compilé unique et un « expliquer ce profil ».
- Publication par plateforme indépendante, promotion latest monotone ; l’updater vérifie la présence de l’artefact de sa plateforme (`Updater:137–145`). Ne pas transformer cela en attente systématique de toutes les plateformes. Il reste utile d’afficher « publication de votre plateforme en cours » plutôt que UP_TO_DATE quand latest existe sans artefact local.
- Tests existants copiés depuis méthodes de production (`tests/updater-regressions/generate.py`) évitent une fausse réimplémentation, mais restent sensibles à extraction textuelle par comptage d’accolades. Extraire les services purs testables du top-level Program à l’occasion des changements A3/A4, sans refonte globale.

## Meilleure direction produit / technique

1. Diagnostic exportable d’une session réelle : profil normalisé, ordre, dimensions/cadence à chaque étape, chemin/hash du moteur chargé, transfert couleur, raison de fusion ou frontière, compteur de copies, coût par étape. Ceci rend les tickets de performance comparables et réduit les essais inutiles.
2. Séparer capacités « interface disponible », « module chargé », « API compatible », « modèle compilable », « qualifié sur ce matériel ». Les descriptions actuelles vont déjà dans ce sens ; appliquer le résultat au choix UI plutôt que présumer la compatibilité depuis le seul fabricant.
3. Identités de contenu de bout en bout pour modèles, moteurs, packs, plans compilés et reçus de qualification. Conserver les plans utilisateur et mettre l’optimisation dans le plan d’exécution, avec raisons visibles.
4. Réduire l’explosion des tickets en critères de sortie concrets : correction cohérence runtime → fiabilité mise à jour → modèle canonique → performance. Les méthodes d’interpolation expérimentales méritent une phase go/no-go courte avant intégration lourde.

Les points A1/A2/A3 sont reproduits, A4–A8 sont établis par inspection de chemins précis et leurs essais de validation proposés sont CPU. Aucune conclusion de performance GPU ou compatibilité universelle n’est tirée de cet audit.
