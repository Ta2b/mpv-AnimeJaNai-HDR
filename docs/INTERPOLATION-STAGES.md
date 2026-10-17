# Étages ordonnés — Linux NVIDIA

Ce document décrit le contrat du lecteur et du Manager du lot 57, en cours de
préparation. Les rapports de qualification des versions antérieures restent
historiques : ils ne constituent pas une liste des moteurs encore disponibles.

## Catégories et exécution

Chaque étage conserve sa catégorie : **Interpolation**, **Upscale**,
**Downscale** ou **HDR**. La technologie se choisit à l’intérieur de la catégorie.
Les IDs, les options, l’ordre et les étages désactivés sont conservés dans le
profil. Un moteur absent ou une option inconnue produit une incompatibilité
explicite ; il n’est jamais remplacé silencieusement.

Le moteur ordonné Linux NVIDIA propose :

- `interpolate/rife/tensorrt` : facteur entier 2..8 par étage, modèle RIFE,
  ensemble, seuil de scène et politique Quality/Fast propres à cet étage.
- `upscale/onnx/tensorrt` : modèle spatial ONNX. Les étages d’upscale ne portent
  plus de nouveau réglage de réduction de résolution.
- `resize/area/cuda` : intégration Area sur les plans YUV444P16.
- `resize/spline36/tensorrt` ou `resize/spline36/cuda` : Spline36 du moteur natif,
  réutilisé dans une chaîne sans modèle ONNX. Ce sont deux noms de runtime pour
  le même chemin NVIDIA ; la bibliothèque TensorRT du paquet reste nécessaire.
- `hdr/nvidia-truehdr/cuda` : conversion TrueHDR avec SDK Maxine Core et feature
  TrueHDR installés séparément. Le mode HDR mpv est un traitement de rendu mpv,
  distinct de ce fournisseur CUDA ; sa disponibilité relève du lecteur/Manager.

Les facteurs temporels se multiplient : Quality ×2 puis Fast ×2 produit ×4.
Au maximum 16 étages et un facteur cumulé 16 ; le budget par défaut des pixels
possédés est 512 Mio, hors espace de travail interne TensorRT/SDK. Les fractions
RIFE des profils historiques équivalents restent sur leur chemin ABI9. Les
fractions mixtes et modèles de super-résolution temporelle ne sont pas exécutés
par ce pipeline. Les autres méthodes d’interpolation restent des intégrations
séparées du backlog ; leur présence dans un catalogue ne les rend pas exécutables.

## Résolution, fusion et fidélité

Un Downscale applique une hauteur plafond (`target_height`, 32..8192) ou un
pourcentage entier (`target_percent`, 1..100), jamais les deux. Il réduit à sa
position dans la chaîne : **Downscale → Interpolation → Upscale** permet donc
l’interpolation à la résolution réduite. Spline36 conserve les règles géométriques
du redimensionneur natif ; Area arrondit au pixel le plus proche. Aucun alias
« bilinear » ne masque un autre algorithme.

La migration d’un redimensionnement historique n’autorise pas son déplacement
arbitraire. Pour un schéma historiquement représentable, le lecteur conserve le
chemin natif historique et ses pixels. Un nouveau Spline36 indépendant travaille
sur le pont YUV444P16 du pipeline : son algorithme peut être comparé exactement au
redimensionneur natif en 4:4:4, sans promettre une équivalence avec les anciens
allers-retours NV12/P010. Les profils non représentables ne doivent pas être
rabattus silencieusement sur l’ancien ordre.

Les étages d’interpolation/upscale consécutifs forment un groupe logique. Les
blocs TensorRT compatibles sont fusionnés en conservant l’ordre et la politique
RIFE. Fast ×4 suivi d’upscale réutilise les sources déjà agrandies et le mouvement.
Fast ×2 garde un bloc natif séparé : les variantes fusionnées testées au lot 55
n’ont pas établi de bénéfice. Plusieurs étages RIFE peuvent donc appartenir à un
même groupe sans partager un contexte natif. Downscale et HDR sont des frontières
explicites ; aucune fusion ne les déplace. Quality conserve ses prédictions
complètes ; Fast conserve son compromis de reconstruction.

## HDR et retrait de FRUC

Un seul étage HDR est permis par profil, toutes chaînes et étages désactivés
compris. Les moteurs d’interpolation/upscale actuels traitent du SDR ; la
conversion TrueHDR doit être le dernier étage actif. Les pixels sont annoncés
PQ/BT.2020 uniquement après conversion réussie. Un HDR seul préserve une source
native PQ/HLG BT.2020 et ses métadonnées.

TrueHDR passe par SDR BT.709 → RGBA8 SDK → RGB10A2 PQ BT.2020 → YUV444P16 limité.
Le SDK produit 10 bits effectifs, sans restauration des détails absents de son
entrée 8 bits. Le pic 400..2000 nits est un réglage de destination, pas un MaxCLL
inventé. Core, feature et dépendances restent installés localement par
l’utilisateur ; aucune redistribution du SDK n’est ajoutée.

**NVIDIA FRUC est retiré** à la demande de l’utilisateur (AH-328) : pas de choix
actif, de fournisseur natif ni de cible de compilation/asset FRUC. Un ancien
étage FRUC conserve ses données et affiche une incompatibilité explicite. Il faut
le retirer ou le désactiver avant la lecture ; aucune conversion automatique vers
RIFE ou Optical Flow n’est effectuée. Les rapports FRUC antérieurs restent les
preuves historiques des défauts qui ont motivé ce retrait.

## Exemple de contrat écrit par le Manager

Conserver les paramètres globaux et les limites de sélection de la chaîne. Cet
extrait montre seulement les étages ; les modèles doivent être présents dans le
paquet/cache. Le Manager fournit les chemins des bibliothèques du lecteur.

```ini
[slot_1]
chain_1_pipeline_version=1
chain_1_stage_count=3
chain_1_stage_1_id=down-first
chain_1_stage_1_kind=resize
chain_1_stage_1_method=spline36
chain_1_stage_1_runtime=tensorrt
chain_1_stage_1_target_height=720
chain_1_stage_2_id=rife-second
chain_1_stage_2_kind=interpolate
chain_1_stage_2_method=rife
chain_1_stage_2_runtime=tensorrt
chain_1_stage_2_model=426
chain_1_stage_2_factor_numerator=4
chain_1_stage_2_factor_denominator=1
chain_1_stage_2_policy=quality
chain_1_stage_2_ensemble=no
chain_1_stage_2_scene_detect_threshold=0.150
chain_1_stage_3_id=span-last
chain_1_stage_3_kind=upscale
chain_1_stage_3_method=onnx
chain_1_stage_3_runtime=tensorrt
chain_1_stage_3_model=2x_AnimeJaNai_HD_V3.1Sharp1_Performance_SPANF3_b5f48_unshuffle_fp16
```

## Qualification et diagnostic

Les compteurs `pipeline-active`, `pipeline-factor`, `pipeline-*-requests`,
`pipeline-peak-pixel-bytes` et `pipeline-cpu-pixel-copies` décrivent l’exécution.
Une requête ne prouve pas le nombre de kernels : une coupure peut recopier une
source. Aucun pixel ne transite par le CPU dans le moteur ordonné ; initialisation
et exécution sont asynchrones, avec annulation des constructions en cours.

Le lot 55 qualifie la fusion sur Linux/RTX 4070 Ti : pixels Quality/hybrides,
cadence, EOF, propriétaires et invalidations. Son gain Fast ×4 local ne garantit
pas les FPS affichés, une chaîne HDR complète ou les autres matériels.
Voir [qualification lot 55](qualification/lot-55-rife-fusion-20261017.md).
Le lot 57 vérifie séparément le retrait FRUC et le nouvel étage Spline36 ; ses
résultats ciblés et limites sont consignés dans le rapport de ce lot. Une
compilation portable ne vaut pas qualification sur chaque architecture CUDA.
