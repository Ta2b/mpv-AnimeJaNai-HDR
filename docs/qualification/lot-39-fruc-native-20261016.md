# FRUC natif CUDA — Fast expérimental, 16 octobre 2026

[AH-296](https://tatoub.atlassian.net/browse/AH-296), parent
[AH-154](https://tatoub.atlassian.net/browse/AH-154). Interface générale
[AH-58](https://tatoub.atlassian.net/browse/AH-58) toujours ouverte : ce provider
ne prétend pas intégrer les autres méthodes ou toutes leurs capacités.

## Livrable et utilité

Module indépendant `libaji_fruc.so` et kernels propres `aji_fruc.fatbin`.
Source backend `f8da50a014fbf020bc3027e9bafc13feebb6323e`, base `861ab52`.
Interface [interpolator.h](../../native/common/interpolator.h), factory
[fruc.h](../../native/common/fruc.h), sans modifier les API RIFE/ABI9 existantes.
Deux entrées, un médian scalaire, lookahead1, worker borné1–4 jobs ; Submit et
Complete ne patientent ni pour une inférence ni pour une place dans la file.
Create/reset/drain/destroy restent des opérations de cycle de vie bloquantes.

Trois buffers RGBA persistants enregistrés auprès du SDK. Réutilisation des
pixels **possédés** de la source adjacente seulement après correspondance de
l'identité complète ; aucun owner client conservé après completion. Discontinuité
ou identité inconnue : SDK réamorcé. Dépendances CUDA enregistrées, références
équilibrées, annulation avant départ, seek/génération, notification terminale,
remontée des répétitions SDK et erreurs sans retry ni repli CPU silencieux.

Entrées CUDA RGB8/full, NV12/left SDR et YUV444P16 ; sorties RGB8/YUV444P16.
Matrices601/709/2020 explicites, mêmes primaires/transfert, aucune rotation.
**Précision FRUC interne8bits**, même dans un conteneur YUV16bits. PQ/HLG/P010,
phases autres que0.5, carte spatiale, CPU et devices étrangers refusés.
Fast nécessite `ALLOW_FAST` ; Quality, modèles et réglages par défaut conservés.

L'utilité est un raccord GPU composable, sans staging CPU des pixels, autour
d'un SDK bloquant. Le bénéfice comparatif RIFE→FRUC déjà acquis est détaillé
dans le [rapport AH-300](lot-39-hybrid-interpolation-20261016.md) ; les temps
présents ne démontrent pas encore la cadence du lecteur.

## Contrôles courts acquis

Même RTX4070Ti12Go/Linux, driver615.78.08, SDK5.0.7 utilisateur et six sources
720p du lot38. Aucun modèle ni poids modifié, aucune compilation concurrente.

- Cinq médianes natives, zéro répétition ; un amorçage, six conversions d'entrée,
  six appels SDK : source adjacente réellement réutilisée. Buffers propres
  bornés11 059 200octets, hors allocations internes SDK. Submit≈0.010–0.021ms
  observé, sans en déduire une latence garantie.
- Crop non nul, offset et stride rembourré, padding inchangé, PTS négatifs,
  descripteurs et owners conservés. Onze refus typés avant acquisition.
- Événement producteur réellement pending, file pleine sans retain ; deuxième
  job annulé sans écriture, actif terminé. Seek avec génération neuve, anciens
  tickets retirés et IDs suivants monotones. Erreur contrôlée du kernel de sortie
  après vrai Process : références libérées, sortie rejetée, provider indisponible
  jusqu'au reset. Aucun plantage matériel ou device reset provoqué.
- Médiane RIFE3 déjà acquise réutilisée : source3 + médiane → FRUC natif → SPAN
  sur GPU, sortie2560×1440. FRUC5.948ms complet ; SPAN105.116ms **premier appel
  froid**, non comparable au coût chaud8.5ms du lot38. PTS/durée et vues préservés.
- Conversions indépendamment contrôlées : packYUV444 full BT709 delta max0code
  RGB8 ; packNV12 limited/left delta max1code RGB8, dont bords de crop ; sortie
  YUV444 delta max1code16bits. Tolérances de matrices flottantes définies avant
  ces contrôles. NV12 synthèse complète, autres matrices/GPU et HDR non qualifiés.

Le module ne lie que DriverCUDA et bibliothèques système : aucune dépendance
CUDART/TRT, aucun import HtoD/DtoH. Le client charge aussi TRT/CUDART13 après
création SDK/CUDART11 : coexistence observée dans ce processus. Les uploads et
captures du **client de test** restent externes au provider/raccord GPU.

## Échec exact conservé et limite SDK

Le premier contrôle strict pixel-exact a échoué. L'alpha255 du pack initial a
été corrigé à1 pour correspondre au prototype. Contrôle GPU indépendant : les
**six entrées RGBA sont ensuite exactement identiques** à la référence.

Le contrôle corrigé reste différent :63/500/1031/103/167composantes sur chacune
des cinq images (2 764 800composantes/image), deltas maxima19/11/5/94/4.
Ce résultat n'est **pas** transformé en succès pixel-exact par changement de seuil.
Pour lever cette ambiguïté, seul le premier couple du prototype inchangé a été
rejoué :95composantes changent, delta max85/255. Le SDK lui-même n'est donc pas
bit-reproductible dans ces conditions. Qualification exacte **non concluante**,
cause interne des pixels isolés non établie. Pas de boucle de répétitions.

Inspection du quart natif, du quart prototype et du RIFE direct déjà acquis :
les dentelures et défauts bouche/occultation FRUC persistent. Le chemin natif
reste utilisable comme **Fast expérimental**, aucune équivalence Quality ou
validation perceptuelle universelle. Les résultats de cycle de vie et conversion
sont concluants indépendamment de cette limite de synthèse SDK.

## Reproduction et livraison

[Client](../../tests/inference/fruc_surface_check.py), cas `rgb`, `lifecycle`,
`yuv-span`. Spec JSON : `provider,fatbin,sdk,runtime,input,reference,width,height,output`.
`input` contient les six RGB24, `reference` les cinq RGBA du prototype acquis.
CasYUV : ajouter `span_spec,rife_median` avec les plans déjà préparés.
Cas lifecycle : compiler [l'interposeur de test](../../tests/inference/fruc_cuda_failure.c)
avec les headers CUDA et le charger via `LD_PRELOAD` dans ce seul processus.
L'erreur simulée ne provoque aucune panne du GPU. Les reçus concluants ou
observations RGB existantes empêchent un replay implicite.

Build backend : définir `AJI_FRUC_ROOT` au répertoire externe `NvOFFRUC` contenant
`Interface/NvOFFRUC.h`, puis construire uniquement la cible `aji_fruc`. Les kernels
couvrent SM75/80/86/89/90/100/120 et PTX120 ; compilation portable, qualification
matérielle limitée à SM89. Binaire hôte glibc≥2.34 et GLIBCXX_3.4.30.

SHA256 module `f320f5cc51f3aeec8385a49896e0aa2e1483c86394763a30610f09f2d5df13c1` ;
fatbin `f9c8c551aec2ee87cd1b7c3097d8538546b1de0cf8eb9569de43d5853e572469`.
Le paquet Linux livre seulement ce code propre avec sa provenance et son README.
Le SDK, son runtime et ses headers restent installés séparément par l'utilisateur.
Windows inchangé ; aucun poids supplémentaire redistribué.

Artefacts privés : `artifacts/performance/lots-20261016/lot-39/`, reçus lifecycle
et YUV-SPAN, observations RGB/alpha initial exclu, contrôle d'entrées et contrôle
prototype limité, captures et logs. Packaging C# compilé sans warning/erreur.
Release3.8.0.71 publiée, trois plateformes success et quinze assets ; module/fatbin
de l’overlay Linux téléchargé identiques aux fichiers qualifiés. AH-296/AH-300 Done. Chaîne complète du lecteur AH-301 et éditeur Manager
AH-302 restent à faire ; aucune option FRUC du Manager prétendue livrée ici.
