# Lot 38 — Premières décisions GMFSS Fortuna et NVIDIA FRUC

[AH-294](https://tatoub.atlassian.net/browse/AH-294) / parent AH-141 et
[AH-295](https://tatoub.atlassian.net/browse/AH-295) / parent AH-154.
Lot complet **d'évaluation**, avant portage natif au lecteur. Les parents,
l'interface générale AH-58 et le portage multi-backend restent ouverts.

## Décision

**FRUC : approfondir une voie Fast explicite, opt-in Linux/RTX**, suivie dans
[AH-296](https://tatoub.atlassian.net/browse/AH-296). Son coût faible est utile,
mais les contours dentelés, petits trous et déformations autour de la bouche
observés dans cet extrait persistent après SPAN. Exclure l'activation par défaut
dans Quality. Commencer au médian ×2 réellement exercé ; les autres phases,
formats, HDR, OS et GPU restent à qualifier. Aucune amélioration générale de
qualité ni cadence du lecteur promises.

**GMFSS Fortuna : conserver le comparateur pour recherche/lecture préparée ;
le portage natif généralisé n'est pas justifié par ce premier résultat.**
L'inférence fonctionne et les traits inspectés restent cohérents ; aucun gain
visuel décisif face à RIFE n'est établi sur ce plan. Le prototype FP32 consomme
beaucoup de temps et de mémoire. La préparation par paire domine ; les huit
softsplats ne constituent pas à eux seuls le poste principal. Un éventuel
approfondissement doit d'abord établir un bénéfice sur un cas visuel précis et
réduire/porter la préparation, plutôt que présumer qu'un kernel softsplat suffit.
Ce constat ne classe pas définitivement l'algorithme : eager FP32, TensorRT
FP16 et runtime propriétaire ne sont pas des implémentations équivalentes.
Union AH-142 reste une variante distincte, avec sa branche IFNet à évaluer.

## Entrées et références figées

RTX 4070 Ti, pilote 615.78.08, Linux ; CUDA toolkit13.4, PyTorch2.14.1+cu130,
CuPy14.2.0, TensorRT11.3.0. Une observation finale après essais indique43°C et
42.57W ; ce n'est pas une mesure de consommation pendant inférence.

Six images consécutives d'un extrait anime local à300s, source1080p BT709 limité
24000/1001fps, réduites une seule fois à1280×720 RGB24 par FFmpeg/bilinear.
Le plan contient deux déplacements de pose, des contours occultants et des
poses tenues avec bruit de codec. Cinq intermédiaires au même instant t=0.5
par candidat. Cette fenêtre suffit à la première décision ci-dessus ; elle ne
certifie pas la stabilité sur un épisode ni l'ensemble des scènes anime.
Les images source, poids et SDK restent hors du paquet public.

RGB24 SHA256 `ff88858e1830323b9a85de0719477f9a7fed36385ef4f32670122322388bc6fb`.
FRUC reçoit les mêmes composantes RGB8 en RGBA, alpha1 comme le sample officiel.
RIFE reçoit une conversion full-range YUV444P16 BT709, sans sous-échantillonnage
chroma : erreur maximale du roundtrip CPU vérifié0.00546 code RGB8. Son propre
prétraitement FP16 et sa sortie YUV16 restent ceux du backend. Chaque modèle
garde sa normalisation et son padding : GMFSS48lignes en bas, RIFE24en haut/en
bas. La comparaison porte sur la même zone720p et les régions centrales
inspectées, pas sur une équivalence numérique entre algorithmes.

- **GMFSS** : dépôt officiel [98mxr/GMFSS_Fortuna](https://github.com/98mxr/GMFSS_Fortuna),
  révision `0fb7ac1dc292e2615217110dd9d82557845fb919`, chemin
  `model/GMFSS_infer_b.py`, scale1, FP32/TF32désactivé, vrai softsplat CUDA CuPy.
  `reuse()` une fois par paire, `inference(t)` une fois par instant ; aucune
  substitution par un warp arrière. Archive officielle GMFSS.zip SHA256
  `c60e55ac9984b651d2c39c8ce833c6792e4bd3b49ed28bd8ee39c18b631a8d96`.
- **RIFE Quality4.26** : ONNX
  `fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59`,
  plan `9c85de7691a0c10bfdf42bccda987c2632a100dd60f9e3d4005aae24f29c8545`,
  module livré .69 `20c29cdbdc34461a94e1cb746dd456334df7c6bb55d13f1d929b60be973389c7`.
  Dessins/retiming désactivés, chaque prédiction complète conservée.
- **FRUC** : SDK Optical_Flow_SDK_5.0.7 fourni par l'utilisateur,
  archive SHA256 `89b0923adc6f34fbe86e63cc17d5db452e34b945c03ba90d8e09bd1a0158e917`.
  CUDA DevicePtr/ARGBSurface, trois buffers persistants enregistrés, contexte
  CUDA dédié ; `Process` bloquant dans un processus CLI hors UI. Timestamps en
  millisecondes, état amorcé par une première source, puis cinq vrais couples.
  Runtime CUDA11.6 livré avec le SDK résolu par un lien isolé ; installation
  utilisateur intacte. SHA des trois fichiers utilisés dans `fruc/sdk-source.json`.

SHA256 des poids GMFSS officiels :

| Fichier | SHA256 |
|---|---|
| feat.pkl | `7442a19d7e2eda6c8f70ddb5b477cb00ae311626355a84393189d8f4d4b1f03c` |
| flownet.pkl | `31fa34960d6326f231c35db9070728419dbad78b463567601dfb6b34049789ef` |
| fusionnet.pkl | `58809ca28e2594bfbef49d68d8e675a33c477cee05d18d4c75035010019c68bf` |
| metric.pkl | `488d3ec1d7cfb04e84ee5a733b03086beb995cd3a51099d65e7a6e01e662fa16` |

## Mesures courtes et qualité

Exécution séquentielle, aucune compilation concurrente aux mesures.
Le premier couple est séparé du régime chaud, sans rejouer une référence
concluante pour remplir un quota. Durées des appels réellement instrumentées :

| Candidat | Premier intermédiaire | Quatre couples suivants, ms | Mémoire observée |
|---|---:|---|---|
| GMFSS eager FP32 | 2700.34ms | 230.37 / 213.24 / 213.80 / 214.05 | pic PyTorch6,948,852,224octets ; réservés6,994,001,920 |
| RIFE TRT Quality | 30.16ms | 14.54 / 13.85 / 14.12 / 14.36 | delta mémoire libre GPU454,492,160octets |
| FRUC CUDA/ARGB | 5.61ms | 1.99 / 5.45 / 3.68 / 1.99 | delta mémoire libre GPU123,797,504octets |

Les portées mémoire diffèrent : PyTorch exclut CuPy/driver ; les deltas GPU
sont globaux et peuvent inclure d'autres processus. Ce ne sont pas des mesures
comparables d'un même allocateur. Buffers client :16,588,800octets RIFE,
11,059,200octets FRUC. GMFSS : préparation chaude147–161ms, synthèse63–69ms,
dont les huit softsplats environ5.93–7.06ms. Aucun remplacement du softsplat
ni nouvelle optimisation n'est extrapolé de cette décomposition.

Préparation distincte : chargement GMFSS304ms, premier appel avec JIT/autotune
ci-dessus ; construction initiale du plan RIFE23.108s, plan SPAN2.506s ; setup
FRUC116.086ms et amorçage2.163ms. La durée globale CLI n'a pas été instrumentée
pour ces premières exécutions ; aucune durée totale ni P99 n'est inventée.
Le client livré capture aussi cette durée pour les cas futurs.

Les quinze sorties sont finies et différentes de chacun de leurs endpoints
RGB8. FRUC remonte zéro répétition parmi ses cinq intermédiaires ; aucun retry,
erreur de traitement ou échec de cleanup. La différence de pixels ne suffit
pas à garantir une bonne synthèse : les défauts FRUC sont visibles sur les
mêmes zones/instants où RIFE et GMFSS présentent des contours plus continus.
Revue de sorties et crops par l'agent ; pas de validation humaine en lecture
fluide ni de jugement universel de préférence perceptuelle.

**Même SPAN après interpolation** : F3 Performance Sharp1 Quality, ONNX
`72246eded3aab52f8d1a71613c0a1d900734b358d1820b62eb36f1ed376e1cf4`,
plan `920c313c8a53224dd1209db8d625532a85229687d821c5c38849d1c92d4d6d95`,
720→1440p. Une source d'amorçage distincte, puis l'intermédiaire du couple3
de chaque candidat :8.616ms RIFE,8.525ms GMFSS,8.507ms FRUC. Les petits écarts
SPAN ne prouvent aucun gain ; les défauts FRUC restent visibles après upscale.
Sommes descriptives des étages de ce couple :22.74/222.32/12.19ms respectivement.
Ce ne sont **pas** des temps mesurés du lecteur NVDEC→interpolation→SPAN→rendu :
préparation CPU, uploads/downloads du prototype, images source présentées,
décodage, mise en file et rendu ne sont pas inclus dans ces sommes.

## Diagnostics corrigés et limites de livraison

Le builder RIFE a échoué deux fois sur un chemin de bibliothèque incomplet,
avant toute mesure : `libnvinfer_builder_resource_sm89.so.11.3.0` a été résolu
dans le runtime de qualification existant ; seuls les artefacts privés de ce
lot ont été construits. Aucun backend/SDK utilisateur modifié.

La première version du client natif employait range0 au lieu de
`AJI_RANGE_FULL=2` : le backend interprétait0 en plage limitée. Ces résultats
RIFE/SPAN ont été conservés en dossiers `*-range0-diagnostic` et **exclus**.
Après correction, seuls les essais concernés ont été repris. Leurs pixels
diffèrent bien du diagnostic ; la référence valide est celle de ce rapport.
GMFSS et FRUC n'ont pas été rejoués. Les derniers ajouts au client concernent
la durée globale future et la publication sûre des fichiers, sans changement
du chemin d'inférence acquis ; compilation/lecture des artefacts suffisantes.

Le code officiel GMFSS porte une licence racine MIT ; l'archive de poids ne
contient pas de notice séparée, ses conditions de redistribution restent à
établir. Le SDK NVIDIA porte sa propre licence. Ce lot fournit des clients
indépendants exigeant ces ressources externes ; aucun poids, header, sample ou
binaire SDK n'est redistribué. L'accès au SDK est désormais résolu ; l'intégration
produit, le chargement optionnel et la distribution restent dans AH-154/AH-296.

## Reproduction et preuves

Clients : [GMFSS/RIFE/SPAN](../../tests/inference/vfi_candidate_probe.py),
[FRUC CUDA](../../tests/inference/fruc_probe.cpp). Le script Python prend un
JSON explicite : `input,width,height,output`, et `gmfss_source,weights` ou
`library,conf,models,rife,trtexec,identity_files`. Mode `span` : ajouter
`span_inputs`. Préparer les engines séparément ; le client exige un cache
existant. `python vfi_candidate_probe.py SPEC.json gmfss|rife|span`.
CuPy : `CUDA_PATH` et `CUDA_HOME` vers le toolkit local ; runtimes dans
`LD_LIBRARY_PATH`. Empreintes d'entrées/poids/plans présentes dans les reçus ;
les reçus concluants correspondants empêchent les répétitions.

Compiler FRUC : `g++ -std=c++17 -O2 -I SDK/NvOFFRUC/Interface
-I SDK/NvOFFRUC/NvOFFRUCSample/cudart_header tests/inference/fruc_probe.cpp
-Wl,-l:libcuda.so.1 -ldl -o probe`. Exécuter avec le runtime CUDA11 du SDK dans
`LD_LIBRARY_PATH` : `probe LIB INPUT.rgba 1280 720 23.976023976023978 PREFIX`.
Le reçu final n'est publié qu'après flush et cleanup réussis ; présence d'un
reçu final empêche une répétition accidentelle.

Artefacts privés `artifacts/performance/lots-20261016/lot-38/` : specs,
provenance des entrées, archives/hashes, traces des builds, `gmfss-result`,
`rife-result`, `fruc/result`, `span-result`, images/crops et diagnostics exclus.
Release prévue3.8.0.70 : clients et rapport ; moteurs/modèles/defaults du lecteur
inchangés. AH-294/AH-295 restent In Progress jusqu'à publication vérifiée.
