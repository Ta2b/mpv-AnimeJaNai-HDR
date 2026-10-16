# Lot 36 — Budget de la réserve de résultats CUDA

[AH-287](https://tatoub.atlassian.net/browse/AH-287), sous [AH-39](https://tatoub.atlassian.net/browse/AH-39). Jobs/sources indépendants AH-288, ports/API restants AH-289. Base3.8.0.67 `3f09cd036a218d600fd285c74924d9e8a069d530`, mpv19c0fcf, backend .65 `7e9c87137e77046e5c521e635634bfdef751a277`. Aucun modèle ni arithmétique Quality/Fast modifié.

## Changement et limites du budget

Le prototype de réserve limitait uniquement le nombre d'images (1à64), avec `max_bytes=INT64_MAX`. L'option `prefetch-bytes` ajoute un budget de résultats :256MiB par défaut lorsque la réserve opt-in est utilisée ;0 désactive seulement le quota d'octets. La limite d'images reste active. Le filtre reste sans réserve par défaut (`prefetch=0`).

La FIFO native reçoit une politique facultative de coût par frame et expose son compteur d'octets. Les autres utilisateurs mpv gardent la politique existante avec callback NULL. Pour le raccord, le coût conservateur est le maximum entre tailles d'allocations AVBuffer référencées et payload calculé avec les pitches réels/hauteurs de plans, plus l'objet image. Arithmétique64bits saturée ; les signaux EOF coûtent zéro. Les références partagées peuvent être comptées plusieurs fois. Le callback ne lance aucune opération CUDA, lecture de pixels ni copie ; il lit les descripteurs détenus.

**Le quota n'est pas strict au dernier octet.** La FIFO termine/admet une image complète avant de constater le quota : dépassement borné à une image, puis arrêt des demandes amont. Même un budget inférieur au coût d'une image peut donc garder une image. C'est un budget de charge des références détenues par la réserve, **pas une mesure ou un plafond de VRAM totale** : pools de l'allocateur, modèle, sources/jobs, images des pins/consommateur et autres services sont hors de ce compteur. Aucun gain de mémoire résidente globale n'est revendiqué.

Métadonnées ajoutées : budget nominal, octets comptabilisés de réserve, coût de la dernière image et maximum depuis le reset. La configuration/modification de politique recalcule les coûts existants ; reset purge octets et coûts observés. Partage/ownership de frames et compteur d'images du prototype conservés. Patch appliqué après le prototype ; dépendance mpv/cache CI/build-info versionnés.

## Essais courts suffisants

Même RTX4070Ti12Go/pilote615.78.08, NVDEC CUDA, entrée/plan/configuration SPAN Quality du lot34 :12images H264/NV12 BT709128×72→256×144. SHA modèle `72246eded3aab52f8d1a71613c0a1d900734b358d1820b62eb36f1ed376e1cf4`, plan `9d99b61a93dd78ad4faa477fb64225f85096f8dcc3af95a79e747bdb31c8bf04`. Aucun rebuild de modèle.

| Réserve `prefetch=8` | Sans quota d'octets | Budget65536octets |
|---|---:|---:|
| Images CUDA prêtes | 8 | 1 |
| Charge de réserve | 889088octets | 111136octets |
| Coût par image observé | 111136octets | 111136octets |
| Compteur produit au snapshot | 10 | 3 |
| Pause/position | true/0 | true/0 |

La charge ne se réduit pas aux55296octets de pixels visibles : pitches/allocations sont pris en compte. Le dépassement111136−65536=45600octets respecte la borne d'une image. Baisse de sept références prêtes et arrêt plus tôt des demandes établis ; aucun essai plus long ni mesure FPS ajouté.

Seek0.3s dans le même processus à budget réduit : epoch0→1, pause conservée, nouvelle charge111136octets dans la borne ; image cible exacte au témoin off déjà acquis du lot34 (PNG SHA256 `8bdf4589e8da4054512266e8632b1abd3ea6cac0d8f10f11970f90a6d640ca7b`). Aucun nouveau témoin de seek exécuté.

Consommation avec budget réduit :12images/PTS exacts au témoin off du lot34 réutilisé, EOF/exit0 ;663552octets NV12 SHA256 `9c8453e811384d9765657ed765fda9bd2f9f5ce0aa9aa88bfd025d9cc88a1c1d`. Capture/contrôle0.638s, descriptif et sans conclusion FPS. Aucun essai concluant répété.

Build Release headless réussi ; le patch recrée exactement les trois sources compilées (filtre, queueC/H), syntaxe shell et en-têtes compilés contrôlés. Binaire local SHA256 `93b743ce455d6cc828e757fac4880c5b2ddbb54ab34e463db94f27cb627e00b7`. Wayland/Vulkan local et autres API/formats/matériels non exercés ne sont pas déclarés qualifiés.

## Décision et reproduction

**Conserver le budget sur la réserve opt-in** : protection fonctionnelle de stockage établie sans perte observée de pixels/PTS. La marge d'une image et le périmètre de comptabilité sont explicites. Aucune promesse de FPS, de VRAM physique économisée ou de séparation jobs/sources déjà réalisée. Parent AH-39/AH-288/AH-289 restent ouverts.

[Client ciblé](../../tests/player/prefetch_budget_check.py), `python3 tests/player/prefetch_budget_check.py SPEC.json budget|sequence`. Spec `mpv,input,conf,models,lib,out,reference_dir` ; référence valide du lot34 et bibliothèques CUDA/TensorRT dans LD_LIBRARY_PATH. `budget` réalise seulement les deux quotas et le seek du candidat ; `sequence` compare uniquement le nouveau candidat aux12sorties acquises. Receipts concluants réutilisés. Artefacts `artifacts/performance/lots-20261016/lot-36/` : `budget-{0,65536}.json`, `budget-seek.json`, `sequence-summary.json`, sorties/captures, journaux et sources avant patch.

**3.8.0.68 publiée**, source `ea24deaf24f9091afcb27b44c7718da9f04f943e` ; trois workflows success,15assets uploaded, versions/archive/digest et option/compteurs dans le mpv livré vérifiés. AH-287 **Done**, clôture10127 ; parent AH-39 et compléments ouverts.
