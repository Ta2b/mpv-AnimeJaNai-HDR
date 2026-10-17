# Lot 55 — Fusion RIFE / upscale — 17 octobre 2026

Statut : **3.8.0.82 qualifiée localement, publication en cours**. Tickets [AH-331](https://tatoub.atlassian.net/browse/AH-331) et [AH-332](https://tatoub.atlassian.net/browse/AH-332) en cours jusqu’à vérification des assets. Backend `463a0c73b6f2e77df09f908a3fef2bf5898cb5a1`, bundle `5217111b754412338fe94d236d80f39dcd42b957`, Manager conservé `2847c799` (pin exact dans `manager-source-ref.txt`).

## Cause et correction

Le chemin ordonné séparait RIFE et l’upscaler en deux contextes TensorRT. Un contexte RIFE sans opération spatiale a `active=false`, tandis que `warp_ready()` exige un contexte actif : la politique Fast ne pouvait donc pas utiliser sa synthèse par mouvement sur les images upscalées. Elle exécutait des prédictions complètes, puis l’upscale sur les images émises.

La correction regroupe les maillons actifs consécutifs interpolation/upscale et fusionne les blocs compatibles avec l’ABI9, en conservant leur ordre. Les maillons restent distincts dans le profil. Plusieurs RIFE peuvent nécessiter plusieurs contextes dans un même groupe. Downscale, HDR et frontières de fournisseurs restent respectés. Les endpoints et préparations réutilisables passent d’une paire à la suivante seulement lorsque les identités et vues des sources concordent ; le préfixe upscale→RIFE conserve ses images déjà upscalées.

Une garde interdit la fusion RIFE→upscale lorsque le resize attaché au premier modèle serait remonté avant RIFE. Les options historiques sont lues en `double` : `100.5 %` ne peut plus être tronqué à `100 %`. Les valeurs non finies sont rejetées. Le contrôle de diff passe ; ce garde a été corrigé par revue, sans essai GPU dédié.

## Essai ciblé et résultats

Les reçus sont dans `artifacts/performance/lots-20261017/lot-55/` du dépôt de travail utilisateur. Chaque ligne ci-dessous correspond au `summary.json` du répertoire indiqué. Les deux valeurs sont les durées natives des paires 1 et 2, en millisecondes, après la première paire ; initialisation, première paire et EOF sont conservés dans les reçus mais exclus de cette comparaison. Ce sont des observations courtes sur la même machine et les mêmes entrées, pas des FPS affichés.

| Cas / reçu | Paire 1 | Paire 2 | Décision |
|---|---:|---:|---|
| Fast ×4 avant — `before-fast` | 60.522 | 58.831 | Référence séparée |
| Fast ×4 fusionné — `after-fast` | 18.298 | 18.371 | Gain utile établi pour ce cas sans HDR |
| Quality ×4 avant — `before-quality` | 49.653 | 52.936 | Référence Quality |
| Quality ×4 fusionné — `after-quality` | 51.089 | 52.282 | Pixels exacts ; gain temporel non concluant |
| Quality ×2→Fast ×2 avant — `before-hybrid` | 39.576 | 38.760 | Référence hybride |
| Hybride, fusion Fast ×2 avec warp — `after-hybrid` | 51.093 | 49.540 | Variante rejetée : régression observée |
| Hybride, fusion Fast ×2 en prédiction complète — `after-hybrid-full2` | 56.054 | 45.651 | Variante rejetée : bénéfice non établi |
| Hybride, Fast ×2 séparé — `after-hybrid-final` | 55.961 | 50.724 | Plan séparé rétabli et pixels exacts ; performance non rétablie par ce seul reçu |
| Quatre maillons avant — `before-four-links` | 54.249 | 53.681 | Référence |
| Quatre maillons, groupe final — `after-four-links` | 56.461 | 52.433 | Pixels exacts ; gain temporel non concluant |
| Fast ×4 + HDR avant — `before-fast-hdr` | 45.885 | 45.817 | Référence complète |
| Fast ×4 + HDR fusionné — `after-fast-hdr` | 46.240 | 46.241 | Fonctionnement établi ; gain complet non concluant |
| Fast ×4 + HDR, fusion désactivée — `fusion-off-fast-hdr` | 63.116 | 55.142 | Ablation diagnostique ; dispersion entre observations |

Le chemin Fast ×4 fusionné montre dans `after-fast.log` quatre endpoints upscalés par le cache Fast, neuf images synthétisées par warp et deux promotions sur trois paires. Les compteurs `spatial_predictions` du pipeline comptent les appels de l’adaptateur, pas uniquement les exécutions réelles du modèle : ils ne doivent pas être interprétés comme un coût GPU.

La fusion Fast ×2 n’amortit pas le travail de mouvement/endpoints sur ce cas hybride. Le plan final garde donc ce maillon dans son bloc natif séparé, au sein du groupe logique. Les treize images finales de `after-hybrid-final` sont identiques à `before-hybrid`, ainsi que les PTS, durées, flags et métadonnées couleur. Les temps finaux restent supérieurs au premier reçu ; aucun retour aux performances antérieures de l’hybride n’est revendiqué sur cette base.

Les treize images de `before-quality` / `after-quality` et de `before-four-links` / `after-four-links` ont également des SHA-256 identiques, avec mêmes PTS, durées, flags, dimensions, facteur et couleur. La variante Fast ×4 réactive un compromis Fast : ses images interpolées diffèrent de la référence complète ; ce gain n’est pas présenté comme une optimisation sans perte de Quality.

Le cas quatre maillons est **modèle ONNX identité ×1→Quality ×2→Fast ×2→SPAN ×2**. Le log final confirme un groupe logique de quatre maillons et trois blocs natifs : identité+Quality fusionnés, Fast séparé, SPAN séparé. Le premier modèle est un contrôle de passage spatial ×1 ; ce cas ne qualifie pas deux upscalers ×2 successifs.

Avec TrueHDR terminal, l’ablation désactivée reproduit exactement les treize images de la référence HDR avant fusion. Les temps de cette ablation et de la référence initiale divergent malgré les mêmes sorties ; le gain complet HDR reste donc non concluant. Le travail HDR reste terminal et aucun déplacement implicite avant interpolation n’est introduit. L’exploration de cet ordre est suivie séparément dans [AH-333](https://tatoub.atlassian.net/browse/AH-333).

## Périmètre et reproduction

- Sonde : `tests/inference/pipeline_fusion_probe.py`, paramètres `*.spec.json`, configurations `fast.conf`, `quality.conf`, `hybrid.conf`, `four-links.conf` et `fast-hdr.conf` dans le lot.
- Entrée : `artifacts/performance/lots-20261016/lot-38/input-300s.rgb`, images d’indices 2, 3, 4 et 5, 1280×720, conversion de contrôle en YUV444P16 SDR. Sortie : treize images 2560×1440, facteur 4, base temporelle 1001/96000, PTS 0 à 12, durée finale 4.
- Modèles/caches isolés dans `lot-55/onnx` et `lot-55/rife` ; RIFE v4.26 et SPAN Sharp1 Performance. La source est déjà en 720p : la descente 1080p→720p réelle et le décodage NVDEC ne sont pas qualifiés par cette sonde.
- Bibliothèques avant : `/home/ta2b/.animejanai-tools/work/binaries-fruc-protection-20261017/linux-x64/`. Bibliothèques candidates : `rife-regression-build-20261017/libaji_pipeline.so` et `rife-regression-trt-build-20261017/libaji_trt.so`, sous le même répertoire de worktrees. Les variantes ont été reconstruites à ces chemins ; les reçus ne figent pas leur SHA binaire historique. Les empreintes de livraison devront être ajoutées avec le bundle final.
- Lancer la sonde avec le JSON choisi et les dépendances CUDA/TensorRT du lecteur dans `LD_LIBRARY_PATH`. Pour HDR, ajouter les répertoires `lib` du SDK VideoFX, de `features/nvvfxtruehdr` et des dépendances sous `VideoFX/external`. `AJI_PIPELINE_TRACE=1` produit les traces ; `AJI_PIPELINE_FUSION=0` sert à l’ablation. Employer une nouvelle destination seulement si une ambiguïté ou une correction justifie un nouvel essai ; la sonde refuse d’écraser un reçu concluant.
- Chaque reçu réussi vérifie l’achèvement, les descripteurs inchangés et la libération des propriétaires. Tous rapportent zéro échec, zéro copie de pixels CPU dans le fournisseur ; le téléchargement des sorties pour preuve est hors chronométrage.
- Aucun résultat de débit d’affichage, de rendu HDR physique, de stabilité prolongée, d’autres GPU/OS ou de tous les modèles n’est déduit de ces essais. Les contrôles complémentaires ci-dessous passent ; publication encore à vérifier.

Empreinte SHA-256 de l’entrée : `ff88858e1830323b9a85de0719477f9a7fed36385ef4f32670122322388bc6fb`.
Empreinte du modèle identité : `d7dd69d4eed6d0cbddf2c84779261332330c44fdaab0c67bc3e666feb24cc029`.

Les tableaux `hashes` de chaque reçu contiennent les empreintes complètes des treize images, également conservées en `.npy`. Empreintes des reçus principaux, calculées après lecture :

| Reçu `summary.json` | SHA-256 |
|---|---|
| `before-fast` | `304ba8003e46d425e54651428719376160cfd044be3c98c66b2414cc90896bcf` |
| `after-fast` | `5a47b0fb77ab79a2204c0ef261cd8da24d6d222de313cb9b0cef13f061424927` |
| `before-quality` | `36398e514e370bf2d8657d0b62bf306f0eb0db0c86bf6e8ede28e4e414500de5` |
| `after-quality` | `dd28f73fe8547a16867929de3418ff16563e2e78a3202f0913fc7ce8bc1434f0` |
| `before-hybrid` | `e4845733ed35311f37544006ce49ef21192015e9bb89b5658c26c0d0389b50ff` |
| `after-hybrid-final` | `ef66ce664108ddabf0ce2def555782c7eea86b2734ecd49118d650ecedb7ccbf` |
| `before-four-links` | `676ccd92f4b32206a792554073238bbb65e1f385cf45fb0df0d22d0a138e618b` |
| `after-four-links` | `af3a4a4793eec04958ef64d4049b437eb73e5528ade13d9af3649e8dad0a8b24` |

## Contrôles finaux et décision

- Hybride sans écriture/téléchargement entre appels (`defer_download=true`) : `before-hybrid-burst` 40.385/38.672 ms ; `after-hybrid-burst` 58.263/38.347 ms. Les treize sorties sont exactes. Le dernier intervalle rejoint la référence, mais un intervalle transitoire reste plus lent : gain hybride et stabilité temporelle non concluants sur cet essai bref. Aucun essai supplémentaire lancé pour rechercher un résultat favorable. Le plan final garde les blocs Fast×2 séparés.
- `four-links-reset` : remise à zéro génération2 après les trois couples et EOF, nouveau traitement du dernier couple ; quatre sorties, pixels/PTS/durées/provenance exacts, tickets monotones et propriétaires équilibrés. Invalidation des caches préfixe et endpoint vérifiée.
- `player-fast-hdr` : source réelle H264 NV12 1920×1080, Area720, RIFE×4, SPAN1440, TrueHDR. mpv/NVDEC produit neuf images YUV444P16 2560×1440, cadence rationnelle et durée finale correctes, propriétaires14/14 live0. Le lecteur rebascule normalement le début non nul de la source à zéro : le contrôle a été corrigé puis les fichiers existants revalidés, sans refaire la lecture. Cette vérification n’est pas une mesure de FPS d’affichage.
- Contrôle CPU du plan : groupes maximaux, frontières fournisseurs/resize/HDR, maillons désactivés, politiques et ordre, exception Fast×2. Revue indépendante du cache/promotion/ordre ; garde des pourcentages décimaux corrigé.
- Les échecs de lancement liés au venv sans NumPy, au GPU masqué par le sandbox et aux bibliothèques SDK/lecteur absentes du LD_LIBRARY_PATH de la sonde sont exclus des mesures. Les données utilisateur ne sont pas modifiées.
- Relink portable `$ORIGIN` : `.text` et `.nv_fatbin` exacts avant/après, preuve `portable-link-check.json`. Modules livrés : `libaji_trt.so` et alias RTX SHA256 `c6f2fce428e2b3b931c7c4ffb7b589513ba9653fc6693ee20d1eeed5c21fa713`, pipeline `04733106673129bd508acee4f4068323cc63609aaffb35e331844b0b39140c28`, fatbin inchangé `1d9ca93cd2cc5e4ce5e944a5179d21687e7c9ab853f360f02bbfd96d19ca5b5d`.

Décision : conserver la fusion compatible Fast×4, utile et qualifiée ; préserver la référence Quality ; garder Fast×2 séparé. Le cache préfixe est un prérequis pour ne pas répéter l’upscale des mêmes sources à chaque phase lors de la fusion upscale→RIFE ; aucun gain FPS autonome n’est revendiqué pour ce cas. Le coût terminal HDR et l’exploration d’un autre ordre restent distincts (AH-333).
