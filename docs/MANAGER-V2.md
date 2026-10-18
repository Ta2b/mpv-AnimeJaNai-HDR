# Manager v2 : diagnostic, conception et lots de travail

Écrit le 18 octobre 2026 pour l'exécutant du lot Manager (AH-379 et sous-tâches, AH-403 à AH-406). Source du Manager livré : dépôt `AnimeJaNaiManager-HDR`, branche `impl/manager-v2-20261018` (worktree `~/.animejanai-tools/work/lot-85-manager-add-step-20261017`, base `714d48e`). Le checkout `~/Documents/AnimeJaNaiManager-HDR` est l'ancienne lignée `hdr-settings-0.8` : ne pas le construire ni l'exécuter (il écrit l'ancien format et efface les étapes, voir §1.2). Le contrat côté fichiers est dans [CONTRAT-PROFILS-V2.md](CONTRAT-PROFILS-V2.md).

## 1. Diagnostic (installation de l'auteur, RTX 4070 Ti, lecteur 3.8.0.107, Manager 714d48e)

1. **Deux chemins de contrôle du HDR.** L'étape HDR du profil (désactivée par l'utilisateur) et le script global (`animejanai-rtx.conf`, `hdr=yes`) : le journal du lecteur montre « Applied RTX Video: TrueHDR » avec l'étape HDR à `enabled=no`. De plus la migration automatique `MigrateLegacyHdr` avait recopié dans chaque profil une étape TrueHDR avec `contrast=200`, `saturation=200` (sauvegarde du 17/10 07:26) : c'est le « HDR surpuissant ». Décision : **le HDR devient un réglage global** (désactivé / mpv / TrueHDR), appliqué automatiquement après la dernière étape ; plus d'étape HDR dans la chaîne.
2. **Profils vidés.** Le 17/10 à 07:48 un Manager de l'ancienne lignée (`rife_engine=old`) a réécrit `animejanai.conf` sans les clés d'étapes : quatre profils sur six sont restés vides (`stage_count=0`, aucun modèle). Réparés à la main le 18/10 depuis la sauvegarde de 07:26 (`animejanai.conf.avant-reparation-*.bak` conservé). Garde demandée : refuser d'écrire un fichier qui perdrait des étapes connues, `config_version=4`.
3. **Règles fantômes** `chain__min_resolution=…` : `AddChain()` ajoute une `UpscaleChain` sans `ChainNumber` ; l'auto-sauvegarde écrit les clés avec un numéro vide avant `UpdateChainHeaders()`, et `IniPreservingSave.Merge` les conserve ensuite pour toujours. Résultat chez l'utilisateur : `chain__rife=no … chain__rife_before_upscale=yes` dans deux profils.
4. **Clés héritées périmées** : les miroirs `chain_1_rife=yes` restent quand l'étape RIFE est désactivée (la projection n'est émise que si elle est « sans perte », le merge garde l'ancienne valeur). Le lecteur lit alors une chaîne incohérente.
5. **TrueHDR « ne fonctionne pas »** : `OptionalSdkViewModel.TrueHdrReady` exige `PipelineReaderFeatures.HasTrueHdr(inference)`, qui charge `inference/libaji_pipeline.so` ; sous AppImage c'est un lien vers `/tmp/.mount_*` **pendant** dès que le Manager n'est pas lancé depuis le lecteur en cours. Le SDK est pourtant installé (`/usr/local/VideoFX`) et le moteur l'utilise. Le choix « NVIDIA TrueHDR » retombe en silence sur `mpv`.
6. **« RIFE perd de la résolution »** : les profils Linux par défaut (`profiles/linux-nvidia/animejanai.conf`, hérités de l'ère Vulkan) réduisent la source à 720p/360p/240p avant RIFE ; le résultat (1440p au lieu de 2160p) n'est affiché nulle part. Rien ne dit à l'utilisateur ce que produit son profil.
7. Défauts d'ergonomie déjà relevés dans l'[audit du 17 octobre, §7](AUDIT-PERFORMANCE-QUALITE-MANAGER-2026-10-17.md) : résultat invisible, aucune notion de coût, état « Unavailable » à côté d'une case cochée, étape créée inactive, vocabulaire instable, anglais, facteur RIFE en fraction, modèle en texte libre, page Moteurs trop technique, bandeau permanent.

## 2. Conception

### 2.1 Vocabulaire (FR, l'interface passe en français ; EN conservé en ressource)

profil → règle (condition de résolution/cadence) → étapes (traitement) → technologie. « Moteur » = backend d'inférence (TensorRT, Vulkan…). « Conversion HDR » = réglage global. Le lecteur parle déjà français (OSD).

### 2.2 Page Profils

- En-tête : nom, étoile « profil de démarrage », actions (dupliquer, importer, exporter, supprimer) visibles.
- **Résumé calculé** sous le nom, pour la source type de la règle (sa résolution maximale ou 1080p/23,976 si libre) : `1920×1080 23,976 i/s → Réduction 720p → RIFE ×2 → SPAN ×2 → 2560×1440 47,95 i/s`, avec un avertissement si une réduction fait sortir le profil sous la résolution de la source, et plus tard (AH-380) le coût estimé.
- Liste des étapes, trois états : **active**, **inactive**, **bloquée** (cause lisible + action : « Installer TensorRT », « Importer le SDK », « Choisir un modèle »). Une étape créée est active quand sa technologie est disponible.
- Détail de l'étape : réglages essentiels d'abord (technologie, modèle dans une liste fermée, facteur en préréglages ×2/×3/×4/écran), « avancé » replié. Plus de catégorie HDR.
- Règles d'activation en bas, repliées.

### 2.3 Page Réglages

- Groupe **Conversion HDR** : `Désactivée` / `Conversion mpv` / `NVIDIA TrueHDR` ; TrueHDR grisé avec la cause (§6 du contrat) et le bouton « Importer le SDK » ; texte « appliquée après la dernière étape de chaque profil ». Apparence HDR (existant) en dessous.
- Affichage (existant), lecture et rendu (existant), diagnostics (existant).

### 2.4 Page Moteurs

- Un bouton « Installer les composants recommandés » et l'état en une ligne ; tout l'expert replié (TensorRT, chemins GMFSS, FFmpeg). Message Linux correct (pas « AnimeJaNaiUpdater.exe not found »).

### 2.5 Profils par défaut (Linux NVIDIA TensorRT)

Remplacer les gabarits Vulkan (réductions 720p/360p/240p) par : « Qualité 1080p → 2160p », « Qualité 1080p → 2160p + RIFE ×2 », « Performance 720p → 1440p », « Léger 480p → 960p » ; les gabarits Vulkan restent pour `linux-amd`. Noms en français, sans « Linux Vulkan » quand le backend est TensorRT.

## 3. Lots de travail

### WP1 (lecteur, fait sur Fable 5.1 max, branche PLAYER `impl/manager-urgent-20261018`)

Contrat §4 et §5 côté scripts : `interpolation-stages.lua` (`normalize`, projection générée, `resolve` sans HDR), `linux-playback.lua` (HDR global, instantané normalisé, étape HDR injectée pour la route ordonnée, sidecar supprimé quand non voulu), `linux-hdr.lua`, `pipeline-hdr.lua`, `gpu-policy.lua` ; `AppRun` exporte `ANIMEJANAI_IMAGE_DIR` ; tests Lua mis à jour ; profils par défaut `linux-nvidia`.

### WP2 (Manager, **Fable 5.1 medium**, ultracode non, branche `impl/manager-v2-20261018`)

1. `MainWindowViewModel.AddChain` : numéroter avant l'ajout ; `ParsedAnimeJaNaiConf` ignore une règle sans numéro ; à la sauvegarde, purger `chain__*`, les clés héritées des sections écrites, `hdr_stage_controlled`, et écrire `config_version=4` (`IniPreservingSave.Merge` conserve seulement les clés inconnues hors de ces familles).
2. `InterpolationStages.cs` : retirer la catégorie HDR (`AddHdrStage`, `MethodChoices` hdr, `IsHdr`…) ; à la lecture, une étape `hdr` est retirée et convertie en réglage global (règle du contrat §5) avec avis unique (`ProfileMigrationNotice`) ; `WritePipeline` n'émet plus de projection héritée.
3. `HdrSettings.cs` : supprimer `ConversionInProfiles`/`RetireLegacyConversion` ; `HdrConversion` + `Backend` (`mpv`/`rtx`, plus de `auto` écrit) toujours écrits ; `MigrateLegacyHdr` supprimé.
4. `OptionalSdkViewModel` / `PipelineReaderFeatures` / `InterpolationStage.InferenceDirectory` : repli sur `ANIMEJANAI_IMAGE_DIR/animejanai/inference` quand le fichier du dossier de données manque ou est un lien pendant ; `TrueHdrStatus` donne la cause exacte ; Réglages → bouton radio TrueHDR grisé avec cette cause.
5. Résumé calculé (`UpscaleChain.Summary` : résolution de sortie et cadence depuis les étapes actives et les facteurs des modèles ONNX, lus via `OnnxInputShape`/noms `2x_`), affiché dans `MainWindow.axaml` sous le nom du profil ; avertissement « réduit sous la source ».
6. Trois états d'étape et création active (AH-381) ; préréglages de facteur et liste fermée des modèles (AH-383) ; profils par défaut TensorRT (§2.5) via `profiles/linux-nvidia` du lecteur + « Ajouter les profils recommandés » dans le Manager.
7. Contrôles : `dotnet run --project tests/ProfileRoundTrip` (ajouter : fichier v3 avec étape HDR 200/200 → v4 sans étape, réglage global, avis ; fichier avec `chain__` → purgé ; règle ajoutée → numérotée) ; rendu sans tête `tests/NavigationUi` (voir la mémoire « Manager headless render ») ; `AJN_UI_PLATFORM=macos` pour vérifier que macOS ne change pas.

### WP3 (Manager, Fable 5.1 medium) : lexique et français, page Moteurs simplifiée, Engines/Settings allégés, glisser-déposer, confirmation de sauvegarde, coût estimé (AH-380), AH-382, AH-383.

### Livraison

Push de `impl/manager-v2-20261018` → CI `build-hdr.yml` publie `hdr-<sha>` ; `manager-source-ref.txt` du lecteur = ce sha ; release lecteur avec WP1 (`release-version.txt`). Les moteurs du lot B sortent après leur revue, dans une release suivante.
