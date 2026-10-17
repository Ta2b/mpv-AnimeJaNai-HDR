# Audit moteurs et pipeline — 17 octobre 2026

Périmètre : lecture du backend livré `463a0c73b6f2e77df09f908a3fef2bf5898cb5a1` (worktree `backend-rife-regression-20261017`) et du lecteur `.82`, commit `0f3f6bfb7e76ca15647d74fc5a91405d3072be69` (worktree `lot-55-rife-regression-20261017`). Aucun code modifié, aucun benchmark GPU supplémentaire exécuté. Les performances citées proviennent uniquement des reçus du lot 55. Les références `backend:` / `player:` désignent ces deux sources précises.

Le lot 55 restaure un chemin Fast ×4 utile et protège la référence Quality. Il ne constitue pas une standardisation complète des moteurs ni une fusion physique de toutes les opérations : le pipeline ordonné est Linux/CUDA/TensorRT, plusieurs contextes demeurent nécessaires, et HDR reste terminal. Les branches GMFSS/préparation (`lot-54-vfi-preparation-20261017`, `manager-vfi-preparation-20261017`) ne sont pas des fonctionnalités livrées par `.82`.

## Priorités et constats

### MP-01 — P1 — Contrat couleur RIFE plus large que son calcul réel

**Preuve de code.** `backend:src/surface_cuda_impl.h:41` accepte les matrices BT.601 à BT.2020 et transmet leur identifiant à `aji_frame` (`:56`). Le pipeline ordonné les accepte aussi (`backend:src/aji_pipeline.cpp:449`). Pourtant RIFE convertit systématiquement avec BT.709 à l’entrée (`backend:src/aji_trt.cpp:3734`) et à la sortie (`:3789`). Les métadonnées originales sont conservées.

**Impact.** Un contenu non-BT.709 accepté peut être donné au réseau dans un espace RGB incorrect. Le retour par la même matrice ne garantit pas l’équivalence à une inférence dans le bon espace, le réseau étant non linéaire. L’incidence visuelle exacte reste à mesurer ; les essais 709 du lot 55 ne couvrent pas ce cas.

**Approche.** Définir explicitement l’espace de travail de chaque modèle. Corriger la matrice d’entrée/sortie et, si nécessaire, effectuer une conversion de primaires documentée ; à court terme, refuser les combinaisons non implémentées au lieu de les annoncer supportées. Conserver l’oracle Quality 709.

**Essai court.** Une paire de mires colorées BT.601 et sa représentation BT.709 du même RGB, comparaison des interpolées après remise dans un espace commun ; un contrôle 709 doit rester exact. Ne pas étendre à une batterie HDR tant que la politique SDR n’est pas définie.

### MP-02 — P1 — Retirer FRUC exige de découpler le build du pipeline

**Preuve.** `backend:CMakeLists.txt:44` ouvre `if(AJI_FRUC_ROOT AND NOT WIN32)` ; les targets `aji_pipeline` et son fatbin sont créés à l’intérieur (`:68–83`). La dépendance de construction à un SDK FRUC existe même pour RIFE/downscale/upscale/HDR. Le module conserve également le chargement FRUC et ses symboles (`backend:src/aji_pipeline.cpp:85`, `:205`, `:392`).

**Impact.** Supprimer le SDK/option FRUC sans réorganisation supprimerait aussi le pipeline ordonné à la compilation. C’est une dépendance technique du retrait demandé, pas une raison de maintenir FRUC dans le produit.

**Approche.** Extraire un target pipeline CUDA indépendant ; rendre l’adaptateur FRUC supprimable sans affecter les autres fournisseurs. Supprimer ensuite les capacités/chemins FRUC selon le ticket existant AH-328, avec migration explicite des profils concernés.

**Essai court.** Configuration CMake sans `AJI_FRUC_ROOT` : target pipeline présent, aucun symbole/asset FRUC requis. Reprendre le contrôle court RIFE→SPAN déjà disponible, sans réévaluer la qualité FRUC.

### MP-03 — P1 — Provenance des bibliothèques réellement chargées non garantie après mise à jour

**Preuve.** `player:installer/linux/AppRun:252–259` privilégie le dossier de composants et ne remplace dans celui-ci que les liens ou les fichiers absents. Un fichier régulier ancien y reste. La route ordonnée choisit `libaji_trt.so` à côté de la bibliothèque sélectionnée (`player:native/linux-cuda/vf_animejanai-pipeline.patch:154`), tandis que les anciennes voies peuvent choisir la variante RTX.

**Impact.** Une release vérifiée peut coexister avec un binaire local ancien et donner des comportements Quality/Fast différents. La préservation de fichiers utilisateur est légitime ; l’absence de provenance visible est le défaut. AH-330 couvre déjà cette famille.

**Approche.** Séparer les overrides utilisateur explicites des fichiers gérés. Enregistrer et afficher le chemin résolu, SHA/build-id et capacités de chaque module chargé ; avertir d’un décalage de bundle. Ne pas écraser arbitrairement les fichiers réguliers existants.

**Essai court.** Arbre d’installation temporaire avec un lien, un fichier géré obsolète et un override explicite ; vérifier résolution/migration et préservation. Pas de test vidéo lourd requis.

### MP-04 — P1 — Qualification de performances encore insuffisante pour conclure sur la chaîne HDR et l’hybride

**Preuve mesurée.** `lot-55/before-fast/summary.json` : 60.522/58.831 ms ; `after-fast` : 18.298/18.371 ms. En revanche HDR complet : 45.885/45.817 ms avant, 46.240/46.241 ms après ; l’ablation fusion-off mesure 63.116/55.142 ms. Hybride Q2→F2 : 39.576/38.760 ms avant, 55.961/50.724 ms avec le plan final séparé. Le contrôle complémentaire intercalé `before-hybrid-burst` / `after-hybrid-burst` mesure 40.385/38.672 ms avant et 58.263/38.347 ms après : le dernier intervalle converge, tandis que le premier reste instable. Le résultat temporel est non concluant ; aucune régression stable ni restauration générale ne peut être déduite de ces seules observations. Les pixels hybrides finaux sont exacts, ce qui ne prouve pas l’équivalence du temps. Voir rapport de qualification du lot 55.

**Impact.** Le gain sans HDR est établi localement ; aucun retour général aux FPS anciens ni avantage de Q2→F2 n’est démontré. Cette limite doit rester visible dans la clôture des tickets et le discours de release.

**Approche.** Un seul protocole court intercalé off/on, mêmes entrées/plans, journaux de clocks/utilisation GPU et temps par étape ; ne répéter que cette comparaison ambiguë, pas les contrôles Quality déjà exacts. Distinguer l’ancien raccourci Fast appliquant HDR aux endpoints et le HDR terminal actuel, dont la sémantique diffère.

**Essai court.** Une paire après amorçage et un passage off/on intercalé avec HDR ; arrêter si le coût HDR domine ou si la machine reste instable, et noter non concluant. La validation mpv du lot 55 prouve cadence/EOF, pas le débit affiché.

### MP-05 — P1 — Construction/chargement du modèle motion inutilisé en RIFE Fast isolé

**Preuve de code, coût à mesurer.** Le plan final exclut Fast ×2 de la fusion native (`backend:src/pipeline_config.cpp:189–201`). Un bloc RIFE isolé est configuré avant-upscale ; `setup_rife()` appelle `setup_warp()` lorsque Fast est choisi (`backend:src/aji_trt.cpp:1345`), alors que `warp_ready()` exige `active` (`:2573`) et le contexte sans opération spatiale reste inactif (`:2036`).

**Impact probable.** Un moteur motion peut être construit/chargé sans jamais être utilisé. Coût d’installation, de mémoire et de temps de préparation ; ce n’est pas nécessairement une perte de débit à chaud. Le comportement « Fast » isolé reste une prédiction complète.

**Approche.** Calculer l’éligibilité statique du mode warp à partir du plan effectif avant de préparer son moteur. Exposer la stratégie effective dans le diagnostic. Conserver la préférence utilisateur sans téléchargement/construction inutile.

**Essai court.** Configuration RIFE Fast seul avec capture des demandes de construction : aucun plan motion demandé ; un contrôle de pixels identique à la référence, puis vérification qu’un bloc Fast ×4→SPAN continue de demander/activer le moteur motion.

### MP-06 — P2 — Synchronisations par image et copies finales limitent le recouvrement

**Preuve.** Chaque `trt.process` utilise l’API synchrone (`backend:src/surface_cuda_impl.h:258–261`, fence `:247`). Chaque étape de resize et chaque copie finale synchronise son stream (`backend:src/aji_pipeline.cpp:311–318`, `:376–379`). Le lecteur n’a qu’un ticket ordonné en vol (`player:native/linux-cuda/vf_animejanai-pipeline.patch:150`, `:192–206`) et attend la fin de toutes les sorties d’une paire avant de publier la première. Le fournisseur matérialise les vecteurs de points et recopie chaque sortie (`backend:src/aji_pipeline.cpp:423–435`).

**Impact inféré.** Latence de burst et travail CPU/fences supplémentaires, recouvrement limité entre étapes et décodage/inférence. Un thread worker évite de bloquer l’UI mais ne rend pas ces opérations GPU concurrentes. Aucun gain chiffré garanti.

**Approche.** Étudier une soumission par burst avec dépendances d’événements et une seule fence de fin, puis une écriture directe dans les sorties quand la durée de vie le permet. Garder les références d’owners et bornes de queue. Préserver un chemin simple de secours. Éviter de multiplier d’abord les streams sans plan de ressources.

**Essai court.** Le même burst factor4 : pixels/PTS/descripteurs/owners exacts et mesure nombre de fences + temps complet. Un seek ou une annulation pendant un burst valide la durée de vie, sans test prolongé.

### MP-07 — P2 — TrueHDR force le stream par défaut et une synchronisation du contexte entier

**Preuve.** `backend:src/pipeline_hdr.c:41` ignore le stream fourni et `:69–71` sélectionne `NULL` pour reproduire la référence SDK. Le pipeline synchronise le producteur, puis `cuCtxSynchronize`, puis l’unpack (`backend:src/aji_pipeline.cpp:357–367`).

**Impact inféré.** L’attente peut englober du travail indépendant dans le même contexte CUDA. Le coût restant du HDR peut masquer les gains de fusion. La référence actuelle étant qualifiée, enlever ces fences sans contrat SDK serait risqué.

**Approche.** Qualifier le stream explicite documenté par le SDK installé ; transférer les dépendances par événements et conserver la synchronisation globale uniquement si nécessaire. Ne pas déplacer le HDR dans la chaîne pour contourner ces attentes.

**Essai court.** Une paire SDR, ablation stream par défaut/stream fourni : sortie HDR exacte, capture d’erreurs différées et événement de fin correct. Si le SDK rejette ce mode, documenter cette limite et arrêter.

### MP-08 — P2 — Le budget actuel borne seulement le pool interne, pas la VRAM totale

**Preuve.** `backend:include/pipeline.h:27` précise « provider-owned pixel pool only ». Le défaut est 512 MiB (`backend:src/aji_pipeline.cpp:538`), les images internes coûtent six octets/pixel (`:166–174`) et les vecteurs gardent les sorties d’étape jusqu’à la suivante (`:320`, `:423`). Le lecteur alloue en plus toutes les sorties du burst (`player:native/linux-cuda/vf_animejanai-pipeline.patch:226–234`) sans donner de `pixel_budget`. Les moteurs TensorRT et le workspace SDK n’entrent pas dans ce compteur.

**Impact.** Le facteur cumulé autorisé jusqu’à16 (`backend:src/pipeline_config.cpp:126`) peut dépasser le pool par simple géométrie. Par exemple, 17 surfaces 3840×2160 YUV444P16 représentent 846013440 octets avant les autres tampons : ce calcul n’est pas un benchmark. Une configuration acceptée peut échouer tard ou saturer la VRAM réelle malgré le respect du compteur.

**Approche.** Estimer le pic vivant du graphe avant allocation ; afficher budget pixels, workspace moteurs et marge GPU séparément. Réduire la rétention des points/émettre progressivement avant d’augmenter aveuglément le défaut. Ne pas changer automatiquement qualité/facteur en silence.

**Essai court.** Planification CPU de deux géométries/facteurs autour de la limite, rejet précoce explicite ; un petit burst avec quota contraint valide l’erreur et la libération, sans provoquer une vraie OOM de la machine.

### MP-09 — P2 — La profondeur16 bits du pipeline ne signifie pas conservation10/16 bits par TrueHDR

**Preuve.** Le pack HDR réduit le YUV16 en RGBA8 (`backend:src/pipeline_kernels.cu:36–49`) ; l’adaptateur déclare `NVCV_U8` en entrée et RGB10A2 en sortie (`backend:src/pipeline_hdr.c:78–81`). L’unpack remet cette sortie dans un conteneur YUV16 (`backend:src/pipeline_kernels.cu:51–60`).

**Impact.** Une source SDR10 bits subit une quantification8 bits à l’entrée du SDK. La sortie16 bits ne restitue pas l’information perdue. C’est une limitation explicite de la voie actuelle, pas une preuve de défaut FRUC ni une erreur cachée du format16 bits.

**Approche.** Vérifier les formats réellement acceptés par la version du SDK installée avant de proposer un chemin plus profond. Si U8 est obligatoire, déclarer ce compromis et évaluer un dithering déterministe seulement s’il améliore une mire sans dégrader le contenu ; conserver la référence existante.

**Essai court.** Dégradé SDR10 bits avec quelques niveaux voisins, inspection histogramme/banding avant-après et un contrôle SDR8. Arrêter si aucune entrée SDK plus profonde n’est disponible et consigner la limite.

### MP-10 — P2 — La standardisation matérielle demande un contrat de capacités, pas seulement les mêmes choix d’interface

**Preuve.** Le pipeline accepte RIFE TensorRT, ONNX TensorRT, Area CUDA et TrueHDR CUDA (`backend:src/pipeline_config.cpp:115–144`) ; le lecteur rejette D3D11 (`player:native/linux-cuda/vf_animejanai-pipeline.patch:124`). Le backend surface CUDA est limité à Linux x86_64 (`backend:src/surface_cuda_impl.h:7`). Fractionnaires et modèles temporels restent exclus du chemin mixte (`backend:src/pipeline_config.cpp:116`, `:143`). Les anciennes voies peuvent les exécuter autrement.

**Impact.** « Même profil » ne garantit ni le même moteur, ni la même qualité, ni la même cadence sur NVIDIA Windows, AMD, Intel ou Apple. Les gains .82 sont Linux NVIDIA ; la release multiplateforme n’est pas une qualification multiplateforme du moteur.

**Approche.** Une description de capacités par fournisseur : mémoire/device, formats/couleur, temporalité, facteurs, qualité, coût et compatibilité des frontières. Un planificateur choisit des blocs compatibles et explique les absences. Prioriser les ports demandés/utilisés ; ne pas annoncer toutes les méthodes partout avant un prototype utile.

**Essai court.** Tests CPU de négociation de trois profils représentatifs sur capacités simulées, puis un seul clip par matériel réellement disponible. Matériel absent : qualification partielle explicite.

### MP-11 — P2 — La politique Fast contient un compromis temporel fort à grand facteur

**Preuve.** Pour un facteur supérieur à 3, `backend:src/aji_trt.cpp:4056–4060` réutilise le mouvement médian même au-delà du seuil de mouvement. Quality n’emprunte pas ce raccourci. Le lot55 confirme des sorties Fast différentes de Quality.

**Impact.** Le gain ×4 provient aussi de cette approximation ; une optimisation d’ordonnancement ne suffit pas à le présenter comme sans perte. Les scènes rapides/occlusions peuvent nécessiter un meilleur compromis, à démontrer.

**Approche.** Garder Quality comme référence ; étudier une variante Fast qui décide par risque d’occlusion/cohérence du mouvement, avec plafond de coût explicite. Ne pas multiplier les noms de politiques sans différence mesurable.

**Essai court.** Une paire rapide/occlusion qui met en défaut le raccourci et une paire ordinaire ; comparer aux sorties Quality existantes et au temps. Rejeter la variante si elle n’améliore pas le compromis utile.

### MP-12 — P3 — Optimisation Area possible, à subordonner au profilage

**Preuve.** `backend:src/pipeline_kernels.cu:14–32` effectue une intégration de surface en double précision, trois plans et boucles par pixel. La qualité de la réduction est claire, mais le coût de FP64 et des lectures répétées peut compter sur certains GPU.

**Approche.** N’ouvrir l’optimisation que si une trace courte montre une part significative. Pour les rapports fréquents, tester un noyau spécialisé/separable avec résultat exact ou une limite d’erreur déclarée ; garder le calcul de référence comme oracle. Ne pas remplacer Area par un algorithme moins fidèle au seul motif des FPS.

**Essai court.** Une réduction 1080→720 avec mire+image anime, off/on sur le même plan ; vérifier pixels, bords et coût. Si le coût est négligeable, fermer l’exploration sans développement supplémentaire.

## Ordre conseillé

1. Résoudre la cohérence des binaires réellement chargés (AH-330), le contrat couleur (MP-01) et le découplage indispensable au retrait FRUC (AH-328/MP-02).
2. Qualifier les ambiguïtés de débit restantes, puis supprimer le moteur motion inutilisé (MP-04/05). Cela évite d’optimiser un chemin différent de celui réellement exécuté.
3. Unifier planification/capacités et estimation mémoire ; optimiser le burst et les fences sur la trace qui domine réellement (MP-06/07/08/10).
4. Étudier la profondeur SDK et les variantes Fast/Area seulement avec un défaut ou un coût établi. Conserver AH-333 comme exploration HDR avant interpolation distincte : ce déplacement demande une politique couleur et qualité, pas seulement une permission d’UI.

Les futures méthodes d’interpolation doivent entrer comme fournisseurs qualifiés par ce contrat. Les modèles lents restent des choix à proposer dans la préparation Manager ; la rentabilité d’un port temps réel est une décision séparée, qui ne justifie pas leur suppression. GMFSS et autres branches non livrées ne doivent pas être comptées comme intégrations terminées ; leur décision rentable/non rentable doit distinguer lecture temps réel, préparation hors ligne, qualité et matériel.
