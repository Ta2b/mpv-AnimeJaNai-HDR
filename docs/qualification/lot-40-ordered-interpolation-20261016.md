# Chaîne native ordonnée — 16 octobre 2026

[AH-301](https://tatoub.atlassian.net/browse/AH-301), parentAH-297.
Backend35c0049 (TRT79e8aa4 identique à35c), schéma partagé2628bab.
Reader Linux CUDA : RIFE×2 → FRUC×2 → même SPAN. Raccord réel, surfaces
canonisées YUV444P16 sur GPU, un worker persistant, file1–2 bornée, pool pixels
512MiB par défaut. Aucun pixel CPU dans le moteur. SR contigus regroupés.

## Utilité et qualité

La composition auparavant impossible est consommée par le lecteur ; ses
quarts viennent de FRUC, sa médiane de RIFE, avant le même upscaler. Le gain
local de l’ablation RIFE direct/hybride est déjà acquis dans le rapportAH-300
lot39 ; il n’est pas rejoué ni transformé en preuve FPS du lecteur. FRUC garde
ses compromis8bits SDR, dentelures et défauts bouche/occultation. Quality et
modèles de référence conservés ; aucune équivalence Quality du mixte.

Même RTX4070Ti12Go/Linux, driver615.78.08, CUDA13.4/TRT11.3, SDK5.0.7
utilisateur, mêmes plans RIFE4.26/SPAN et sources720p du lot38. Le modèle
RIFE4.26 ONNXfd6b…/plan9c85… et SPAN ONNX72246…/plan920c… restent inchangés.
Les identités complètes sont dans les reçus privés JSON sous lot40.

- CPU : schéma/version/IDs/fractions/migration et parser natif contrôlés.
  L’ancien5/2 avant/après SR reste sur ABI9 ; méthodes/options non implémentées,
  versions inconnues et FRUC Quality sont refusés explicitement.
- GPU natif, trois sources :9sorties2560×1440, huit sous-intervalles et dernière
  source conservée avec sa durée entière.3conversions source,2requêtesRIFE,
 4FRUC sans répétition,9SR avec endpoint adjacent possédé réutilisé.
  Pic pixels possédés138240000octets, hors SDK/TRT ; owners/padding/ROI/PTS
  équilibrés. Ces compteurs désignent des requêtes API, pas des kernels prouvés.
  Première rafale froide313.53ms puis27.46ms/4sorties et EOF0.25ms : observations
  distinctes, aucune conclusion FPS. Submit observé0.024–0.033ms.
- Qualité médiane commune : comparaison corrigée sur l’entrée normalisée
  float32 identique à la référence ; après même SPAN, **zéro composante différente**.
  L’essai initial normaliséfloat64 est exclu de cette comparaison (entrée typée
  différente). Son delta reste conservé, sans changer un seuil pour conclure.
- Vrai mpv/NVDEC : sourceH264 lossless/yuv420p720p trois images, FPS24000/1001,
  SHA03bc4b8463f1fad5cd076a3894ecb1c759cc94422590a6446bfe739b57f1f482.
 9sortiesYUV444P16 2560×1440, PTS0 à0.083416667s par pas1001/96000s,
  durée finale1001/24000s, aucune image future fictive. Durées natives contrôlées
  séparément de la quantification du muxer. Lecteur headless, pas de présentation
  Wayland/HDR physique revendiquée.
- Pause/seek puis slot1→0→1 : générations neuves, dimensions1280×720 puis
 2560×1440, pause conservée, extinction18retains/18releases/live0. Correction
  d’un redémarrage manquant après seek à format identique, cas acquis après fix.
  Deux échecs initiaux de harness (chemin IPC trop long, capture avant terminal)
  sont conservés/exclus ; les assertions ciblées ont été corrigées.
- File finale : vrai événement producteur pending, job actif terminé, job en
  attente annulé sans écriture, file pleine BUSY sans retain, génération/tickets
  monotones. Erreur de copie finale simulée après vrais étages : sortie rejetée,
  owners libérés, module indisponible jusqu’au reset.1terminé/1annulé/1échec.
  Médiane Quality exacte aussi avec le nouveau TRT. Aucun device reset provoqué.
- Initialisation asynchrone : vraie branche backend de construction avec cache
  privé vide et trtexec-stub contrôlé, Query BUSY, caps inchangées, destruction
  annule son enfant sans publier de plan incomplet. Create0.307ms/Destroy0.849ms
  observés ; ce cas ne prétend pas qualifier une compilation TRT réelle.
- Ancien chemin réellement exécuté : même mpv/nouvelle bibliothèque/source,
  RIFE5/2+SPAN sans schéma / schéma v1 strictement équivalent :6images,
  SHA256 de chaque frame et tous PTS **exactement identiques**.
- Lanceur réel sous harness : mixte×4 conservé malgré auto sync, autres slots
  classiques synchronisés5/2, runtime slot switch met à jour le tag TrueHDR,
  fichier source intact. Runtime nonTensorRT et modules absents explicitement
  refusés. Les paramètres pipeline explicites font aussi refuser un ancien mpv
  qui ne connaît pas ces options, au lieu d’ignorer les étages.

## Livraison et limites

Module pipeline finalSHA321e52c50c0819642c7539195fb646117d1e81184324a57329447b135fef9280,
fatbin912e8c30f67c64c7a9276484323fdd22bc09ca870aaaabecb5cff93a5756e21e.
Après les contrôles GPU, seule la métadonnée stage_count activé et le nom
ALLOW_FAST ont changé ; aucune arithmétique pixel/changement de file.
TRT livréSHA953c8f8f65cf9bf58140d1ad08a543f73b73ee8b9cfb5df506ff30063b92c414 :
CUDA fatbin exactement identique à la référence qualifiée20c29…,
SHA23766330f0d82b1a69660abff608b3f0630ea9089f03be755eb4e06830d097cc.
FRUC/dispatcher précédemment qualifiés conservés. Le SDK et son CUDART11
restent externes. Binaires propres + hashes figés, aucune redistribution SDK.

Patchstack de l’installateur appliquée à mpv19c0fcf895 frais : source filtre
exactement identique à celle qualifiée, headers copiés. Packager compilé,
whitelist/hash/overlay mis à jour, dépendance mpv ordered-pipeline1 pour que
l’updater acquière aussi le lecteur compatible. Release3.8.0.72 préparée ;
AH-301 reste In Progress tant que sa publication n’est pas vérifiée.

Limites : Linux CUDA, FRUC Fast SDR8bits, facteurs mixtes entiers, sortie
YUV444P16, SR spatial,≤16étages/facteur≤16. Autres méthodes/API/GPU,
HDR synthèse et présentation physique non qualifiés. Répétabilité exacte SDK
non concluante au lot39. Manager AH-302 séparé ; aucune UI déjà livrée annoncée.
L’interface générale AH-58 reste ouverte pour capacités des autres méthodes.

Clients reproductibles dans tests/inference/pipeline_*.py ; reçus concluants
protégés contre replay. Artefacts privés sous artifacts/performance/lots-20261016/lot-40 :
config-contract.log, common-median-f32/comparison.json, player/summary.json,
player-lifecycle/summary.json, init-cancel/summary.json, async-lifecycle/summary.json,
legacy-player/summary.json, sections/comparison.json, patch-delivery.json,
launch-policy.log, launch-integration-final.log, packager-build.log.
