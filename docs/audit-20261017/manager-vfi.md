# Audit Manager, profils, SDK et préparation VFI — 17 octobre 2026

Revue en lecture seule du code applicatif ; aucun GPU ni modification de profil. Référence livrée : Manager `2847c799` (3.8.0.81, encore épinglé par le lot55/.82), lue par `git show`. Les changements des worktrees `manager-chain-cleanup-20261017` (lot51) et `manager-vfi-preparation-20261017` (lot54, HEAD `d4b868f`) sont **non livrés**. Le worktree `manager-remove-fruc-20261017` contient actuellement le même nettoyage préparatoire que lot51, pas un retrait effectif de FRUC.

## État des demandes

| Demande | Code livré 2847c799 | Travail non livré |
|---|---|---|
| Quatre catégories fixes | Oui : Interpolation, Upscale, Downscale, HDR ; technologies limitées à leur catégorie | Conservées |
| Downscale indépendant | Area disponible ; l'ancien resize attaché reste dans les imports et l'ancien éditeur | Normalisation automatique vers un maillon séparé, mais intitulé et ordre encore à corriger |
| Un HDR par profil | Oui, y compris HDR inactif, compté sur toutes les règles | Conservé |
| HDR mpv dans la chaîne | **Absent** ; seul NVIDIA TrueHDR, création conditionnée au SDK Linux | mpv/gpu-next ajouté, routage partagé requis |
| Retirer ancien éditeur et trois profils intégrés | **Non** ; bascule, ancien éditeur, liste de profils intégrés présents | Retrait codé ; anciens defaults 1001..1003 deviennent Off avec explication |
| Réglages conversion HDR uniquement dans profils | Globals masqués selon le profil courant mais toujours conservés et utilisés pour d'autres profils | Migration puis retrait des globals après sauvegarde canonique ; écran et réglages d'apparence distincts conservés |
| Quality/Fast seulement pour RIFE | Sélecteur de maillon visible seulement pour RIFE ; ancien mode partagé encore dans l'ancien éditeur | Ancienne UI retirée ; clé globale encore utilisée par la projection de compatibilité |
| Retirer FRUC | **Non** : choix, SDK, avertissement et protection présents | Le retrait n'est pas encore implémenté dans les worktrees examinés |
| Installation SDK par archive | Import Optical Flow ZIP et Maxine Core/TrueHDR ZIP/tar, chemins gérés, onboarding et réglages ultérieurs | Dépendance restante AH-324 : archive feature NGC originale à qualifier |
| GMFSS utilisable | Pas d'UI de préparation livrée | Onglet préparateur, worker FP32, sources/poids vérifiés, annulation, codecs et packaging en cours |

Preuves livrées : `Views/InterpolationStages.axaml:5–31,58–61`, `ViewModels/InterpolationStages.cs:147–168,289–294`, `Views/MainWindow.axaml:105,741–820`, `ViewModels/MainWindowViewModel.cs:167`, `ViewModels/OptionalSdkViewModel.cs:25–74`. Chemins sous `/home/ta2b/.animejanai-tools/work/manager-fruc-protection-20261017/AnimeJaNaiConfEditor/` (HEAD exact `2847c799`).

## Défauts concrets à traiter

1. **P1 — Migration resize trompeuse, lot51 non livrable telle quelle (AH-325/AH-321).** `lot-51.../AnimeJaNaiPlatform/PlatformServices.cs:401–440` transforme le resize historique en `bilinear` puis le refusionne avec l'upscaler. Le checkpoint `docs/jira/PAUSE-20261017.md:55` établit que le noyau TensorRT concerné annonce Spline36, pas Bilinear. Le test de migration attend `RIFE → resize → upscale`, sans avoir établi la place effective du pré-resize dans le chemin historique `rife-first/has_pre_resize`. Garder la fidélité numérique et exposer le véritable ordre avant tout changement d'intitulé. Un alias explicite « resize historique » temporaire vaut mieux qu'une promesse algorithmique erronée. La conversion livrée vers Area est, elle, annoncée comme changement de rééchantillonnage, pas comme migration exacte.

2. **P1 — Création des nouveaux maillons verrouillée sur TensorRT, y compris sur les autres plateformes.** Livré `InterpolationStages.cs:142,149–150` ; pending lot51 `:69,76–77` : RIFE et ONNX sont créés avec runtime `tensorrt`, Downscale avec `cuda`. La technologie disponible à l'utilisateur ne permet pas de changer ce runtime. Dans le livré, `Availability` refuse aussi toute activation ordonnée hors Linux (`:423–425`), même lorsque la projection legacy est compatible. Lot51 ajoute cette projection, mais les nouvelles étapes restent créées TensorRT : AMD/Vulkan, ORT ou Apple ne peuvent toujours pas créer naturellement leurs maillons. Résoudre le provider à partir du backend sélectionné et de ses capacités ; ne proposer que les combinaisons exécutables, conserver les imports d'une autre machine lisibles.

3. **P1 — Annulation indisponible au deuxième job GMFSS (AH-313, pending).** `PreparationViewModel.cs:97` notifie `IsBusy=true` avant `cancelRequested=false` et `completed=""`. Après succès ou annulation, `CanCancel` est notifié faux puis jamais renotifié pendant le nouveau travail. Réinitialiser l'état du job avant la notification. Contrôle ciblé : succès → nouveau job annulé, puis annulation → nouveau job annulé ; aucun modèle GPU nécessaire pour tester le cycle UI.

4. **P1 — Sortie longue GMFSS rejetée après préparation réussie (AH-313, pending).** `tools/interpolation/worker.py:82` impose `timeout=60` à `ffprobe -count_frames`, donc au décodage complet de la sortie. Un épisode dont cette vérification dépasse une minute est supprimé par le staging après toute l'inférence. Rendre le contrôle annulable et surveiller une inactivité réelle plutôt que la durée globale du film. Émettre un état « validation » distinct après l'inférence (la progression actuelle reste à 100 %).

5. **P2 — Validation et sauvegarde des options RIFE divergent.** Livré `InterpolationStages.cs:352,412,477–484` ; même structure pending : `scene_detect_threshold` est validé dans `Availability`, mais pas dans `ToStage`/validation du plan. L'édition d'un maillon déjà actif peut donc sauvegarder un texte vide ou hors [0,1] alors que l'UI le signale indisponible. Partager une validation typée utilisée par l'activation **et** la sauvegarde ; garder la dernière configuration valide pendant une saisie incomplète. Ne pas utiliser une chaîne anglaise `StartsWith("Files present")` comme indicateur fonctionnel (`:459–461`).

6. **P2 — Publication GMFSS conditionnée tardivement aux liens physiques.** `worker.py:149–151` utilise `os.link` sans vérification préalable du système de fichiers. FAT/exFAT ou certains montages ne le permettent pas : toute l'inférence est perdue à la fin. Vérifier la capacité dans le dossier de destination avant d'initialiser le modèle, ou prévoir une publication non écrasante portable. La protection d'une destination préexistante doit rester intacte.

## Architecture à privilégier

Un seul modèle de profil canonique : liste de règles, chacune contenant des étapes typées ; HDR unique par profil, en conservant sa position explicite dans la chaîne sélectionnée. La projection historique doit rester un adaptateur de lecture/exécution, jamais un deuxième éditeur mutable. Une table de capacités par provider doit fournir catégories, réglages, formats/couleurs, facteurs et disponibilité structurée ; la même validation doit alimenter UI, sauvegarde et diagnostic lecteur. Cela retire les conditions OS dispersées et les messages servant de booléens, sans réécrire les moteurs.

Pour le catalogue VFI, distinguer clairement « lecture en temps réel » et « préparer un fichier ». Le workflow GMFSS est pertinent comme première intégration exploitable, mais ne doit pas apparaître comme moteur natif disponible. Éviter de multiplier les chemins Python/SDK dans chaque maillon : une installation centrale des providers et un diagnostic de dépendances suffisent.

## Vérification courte acquise

Test CPU nouveau, sans rejouer le contrat lot42 : source trois images 64×64/24 Hz avec audio en flux0, vidéo en flux1. `lossless-rgb` + drop : six images/48 Hz, RGB byte-exact. `hevc44410-sdr` + copy : six images/48 Hz, métadonnées SDR et audio validés ; conversion RGB/YUV explicitement non pixel-exacte. Preuves copiées : `gmfss-codec-cpu-receipt.json`, `gmfss-codec-cpu-check.py`. `bash -n` valide AppRun, launcher et package macOS. Un premier échec concernait seulement l'option de couleur de la fixture (`gbr` remplacé par `0`), aucun résultat applicatif retenu de cet essai.

Aucun export GPU GMFSS du nouveau worker, aucun cycle UI d'annulation ni archive finale du lot54 n'a été qualifié ici. Avant livraison : corriger les deux défauts P1 GMFSS, un export réel très court face à la référence existante, annulation/réouverture, vérification des quatre fichiers worker dans les packages. Les contrôles lot51 déjà concluants restent acquis ; seul le problème de fidélité/ordre du resize doit être réexaminé.
