# Lot 21 — buffers et descripteurs ORT réutilisables

AH-264 sous AH-63 ; intégration/qualification native restante AH-265. Base .52 `94161dfce0348ceb20fdd5ef0b58f2e7edf2dfe4`, source moteur qualifiée `3534b1eadb252d4a6bb7e85d12be325f1ab4ecce`. Worktree isolé, backend utilisateur d’origine intact. Ablation `AJI_ORT_REUSE_BINDINGS=0/1` dans le **même binaire**, ORT CPU1.24.1, mêmes entrées/poids/options/machine par comparaison. Aucun essai concluant précédent rejoué pour ce lot.

## Changement et utilité

L’exécuteur spatial prépare son MemoryInfo, ses tenseurs d’entrée/sortie et leurs buffers à taille fixe une fois par instance. RIFE conserve déjà entrée et image de sortie ; ses sorties flow/mask sont désormais préallouées, chacune selon son propre type FP16/FP32. Les valeurs intermédiaires, modèles, conversions et arrondis ne changent pas. Le scratch de conversion spatial FP16 reste sur les threads pixels persistants ; FP32 n’en a pas besoin.

Avec ORT API24+, la forme et le type sont lus par référence empruntée à l’OrtValue vivant : validation de la forme conservée après chaque inférence, sans handle de métadonnées possédé ni vecteur de forme. Le résultat reste vivant pendant la conversion synchrone et les jobs pixels ; aucun pointeur de forme conservé entre inférences. Les SDK plus anciens gardent la lecture possédée : pas de promesse de zéro création de métadonnées sur ces versions non exercées.

**Bénéfice établi : suppression des créations répétées de descripteurs applicatifs, handles de forme et demandes de sorties non préallouées dans les fenêtres exercées.** Réutilisation et gestion de ressources prévisible, sans gain FPS établi. Les allocations internes ORT/EP, son arena, les buffers des opérateurs et les vecteurs de jobs de `parallel()` ne sont pas mesurés ni déclarés nuls.

## Inventaire et bornes applicatives

- Par instance spatiale : un MemoryInfo, deux OrtValue, un buffer d’entrée de `3wh` éléments et un buffer de sortie de `12wh` éléments. Taille de chaque élément selon son type propre, 2 ou 4 octets ; aucune modification de géométrie dans cette instance, donc aucun déplacement de ces buffers après binding.
- RIFE : entrée et image de sortie déjà persistantes ; nouveaux flow/mask de `4PH×PW` et `PH×PW` éléments, deux OrtValue, types indépendants. Les vecteurs flow/mask du caller conservent leur capacité après warm-up pour une géométrie donnée.
- Scratch spatial FP16 : au plus `3×largeur_de_crop_max_observée` floats par thread utilisé ; rétention de la plus grande largeur jusqu’à destruction du thread, y compris après un redimensionnement plus petit. Il s’agit d’un compromis de mémoire conservée, pas d’une baisse RAM prouvée.
- Le nombre d’instances/exécuteurs/threads reste celui des modèles, tuiles et pools existants. La reconfiguration remplace les anciennes instances et leurs buffers ensemble. L’ABI conserve ses appels sériels ; aucun nouveau droit d’appel concurrent sur une instance.

La préallocation ajoute une résidence explicite des sorties ; aucun gain de mémoire totale ou borne des allocations internes du runtime n’est revendiqué.

## Essais courts nécessaires

Build local Release via CMake installé, compilateur identique à .52, AVX/F16C. Interposition C API test seule `ort_api_probe.c`, compilée contre l’en-tête/runtime1.24.1 : elle compte les appels réussis de création MemoryInfo/tenseurs/handles de forme, les slots de sortie nuls demandés à Run et les lectures de forme empruntée. Les compteurs sont relevés après warm-up, hors configure/reconfigure. Ce ne sont **pas** des compteurs de malloc internes ORT.

`ort_buffers_check.py SPEC`, avec `ort_buffers_probe.py` : premier intervalle exclu, deux nouvelles paires seulement. Sources RGB24 générées avec strides/padding, huit sorties par branche dont endpoints, warm-up et source après reconfiguration. Comparaison byte à byte.

| Cas nécessaire | MemoryInfo avant→après | Tenseurs avant→après | Handles de forme avant→après | Sorties non préallouées avant→après | Parité |
|---|---:|---:|---:|---:|---|
| Quality, RIFE4.26 + SPAN FP16, 128×72 | 4→0 | 4→0 | 6→0 | 4→0 | 8 sorties, 0 octet différent |
| Fast motion FP16 + deux exécuteurs/tuiles SPAN, 256×72 | 4→0 | 4→0 | 8→0 | 8→0 | 8 sorties, 0 octet différent |
| Fast motion FP32 + mêmes exécuteurs SPAN FP16 | 4→0 | 4→0 | 8→0 | 8→0 | 8 sorties, 0 octet différent |

Six Run restent nécessaires dans chaque fenêtre, sans suppression de calcul neuronal. Les lectures de forme empruntée sont respectivement6/8/8, remplaçant les handles possédés. Les stats attestent le chemin motion et deux exécuteurs/tuiles pour Fast.

Poids livrés inchangés : SPAN SHA256 `72246eded3aab52f8d1a71613c0a1d900734b358d1820b62eb36f1ed376e1cf4`, RIFE `fd6b06538898c9a94d20f0fe55febceadbcde5ad64952240733b7275ef4c9d59`. La troisième comparaison utilise une **fixture temporaire FP32** construite par `ort_fp32_fixture.py` : valeurs des poids FP16 promues exactement en FP32, types/Cast promus pour exercer les nouveaux buffers float. Off/on prennent cette même fixture ; aucune équivalence de ses pixels avec le modèle FP16, aucune amélioration de qualité/algorithme et aucun remplacement du modèle installé revendiqués.

`ort_buffers_geometry_check.py SPEC` : modèle ONNX FP32 Resize nearest×2, oracle indépendant par duplication des pixels. Même contexte reconfiguré64×32→80×48 ; sorties exactes face à l’oracle, padding de stride intact, sorties chaudes off/on identiques. Par source chaude, MemoryInfo/tenseur/handle de forme/slot nul passent chacun1→0, un Run et une validation de forme empruntée restent. Une fixture malformée×3 est refusée off/on, avec message d’erreur explicite et destination sentinelle entièrement intacte ; aucun succès apparent ni écriture hors contrat×2.

Observations murales uniques des deux paires : Quality61,38→56,03ms ; Fast FP16152,08→140,85ms ; Fast motion FP32166,69→127,99ms. **Gain temporel/FPS non concluant**, séries courtes et état bureau/alimentation non contrôlés. Aucun prolongement automatique, aucune stabilité thermique/énergie/RAM annoncée. Les conclusions suffisantes sont la parité, les compteurs applicatifs et la gestion de géométrie/erreur ; arrêt des essais à ce point.

Artefacts locaux : `artifacts/performance/lots-20261016/lot-21/` : configure/build, interposeur, specs exactes, logs, statistiques, NPZ et reçus `summary.json` pour les trois cas neuronaux et les deux géométries/erreur. Commandes principales : `python tests/inference/ort_buffers_check.py quality.spec.json`, `fast.spec.json`, `fast-fp32.spec.json` ; `python tests/inference/ort_buffers_geometry_check.py geometry.spec.json`. Les specs contiennent les chemins et le SHA256 du binaire dans les traces de provenance. `git diff --check` et compilation syntaxique Python réussis ; aucun modèle rejoué pour ces contrôles de source.

## Décision et livraison

Conserver pour le bénéfice applicatif établi, activé par défaut pour **provider CPU**. Les autres providers gardent leur voie existante ; `AJI_ORT_REUSE_BINDINGS=1` permet seulement un essai natif explicite, `=0` l’ablation. Le passage à d’autres tailles/providers ne modifie ni précision ni choix de modèles. Quality reste exacte sur les cas exercés.

Release **3.8.0.53** : moteur partagé Linux/macOS compilé depuis cette source, pin GPU spécialisé inchangé. Compilation macOS/Windows ≠ qualification native. AH-265 conserve l’intégration et la qualification des providers/OS natifs restants, ainsi que l’inventaire des allocations internes du runtime si nécessaire. Parent AH-63 ouvert ; AH-264 ne sera Done qu’après publication vérifiée.

Précision utilisateur applicable aux lots futurs : si un lot ne touche ni au moteur ni au flux vidéo, vérifications simples adaptées uniquement, sans tests vidéo ni mesures compliquées. Ce lot change les buffers du moteur ; les comparaisons ci-dessus sont donc nécessaires.
