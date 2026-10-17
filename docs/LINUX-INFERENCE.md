# AnimeJaNai et RIFE sous Linux : journal d'implémentation

## Situation actuelle — 3.8.0.29 (14/10/2026 à 20 h 45 (Paris))

La **3.8.0.29 est publiée sur les trois plateformes**, depuis `6fa85bb`.
Les releases Windows/Linux/macOS sont indépendantes et n'ont plus de jobs de
tests. Le code RIFE partagé `30a3e83` est maintenant dépassé et intégré par les
lots suivants : `d639dc1` / `b3f9d5d` ajoutent la chaîne warp et la chronologie
des dessins. La branche NVIDIA CUDA Graph `f4fcd17` reste isolée.

Lire [l'état consolidé courant](archive/2026-10-17/chantiers/ETAT-PROJET.md) et
[le chantier 3.8.0.24–29 / 165 Hz](archive/2026-10-17/chantiers/CHANTIER-RIFE-165HZ.md). Les sections datées
3.8.0.23 ci-dessous restent un historique des preuves de cette session, pas
l'état global actuel. La chaîne warp est livrée dans le moteur partagé ;
**elle ne l'est pas dans NCNN/Vulkan ni dans les binaires Windows amont**.
Les modèles sont conservés, mais cette stratégie et le lissage des dessins
changent le rendu temporel ; l'ancien mode est conservé.

## État courant au 14 octobre 2026

La **3.8.0.23 Linux est publiée**, portable, AppImage et overlay, avec Windows
et macOS dans la même release. NCNN/Vulkan comprend la reprise exacte par défaut
et les caches validés du chantier ; similarité opt-in et limites documentées.
Le moteur partagé gère désormais RIFE via ORT : les mentions « RIFE non géré »
dans les étapes du 12 octobre ci-dessous sont historiques. ORT Linux est compilé
contre **1.24.1** pour le fournisseur OpenVINO livré ; cela ne démontre pas la
vitesse ou la fidélité sur chaque GPU/NPU OpenVINO/MIGraphX physique.

Suite non encore livrée : `30a3e83` (décision par paire et sortie RIFE préallouée,
CI réussie) et `f4fcd17` (CUDA Graph RIFE dans un worktree NVIDIA isolé, compilation
C++ seulement confirmée). La dépendance amont du paquet n'est pas remplacée.
[État consolidé](archive/2026-10-17/chantiers/ETAT-PROJET.md) / [relais et preuves](archive/2026-10-17/chantiers/CHANTIER-PERFORMANCE-RELAIS.md).
Les essais HDR physiques et RTX 4050 restent distincts des contrôles logiciels.

## Objectif

Rendre l'upscaling AnimeJaNai et l'interpolation RIFE utilisables dans le lecteur
Linux sur AMD et NVIDIA, en conservant les fonctions Windows. Les documents sont
actualisés au fil de l'implémentation ; les résultats expérimentaux sont séparés
des fonctions réellement vérifiées.

## État du portage et évolution des réglages

Le paquet précédent `3.8.0.8-linux-test.1` reste un lecteur SDR sans inference.
Le nouveau backend Vulkan a exécuté AnimeJaNai et RIFE dans mpv sur la RX 6500,
avec fermeture propre et comparaison numérique du modèle Performance Sharp.
Le portable et l'AppImage `3.8.0.8-linux-test.2` incluent ce backend,
les poids, les profils et le Manager et passent les essais Wayland locaux. La RTX 4050 n'est pas
accessible ici : sa validation physique reste à effectuer.

Le paquet `3.8.0.8-linux-test.3` ajoute la page Global Settings simplifiée, une
seule description d’écran, les valeurs Auto et le démarrage Performance sans
RIFE. Les installations personnalisées sont conservées. Voir [SETTINGS.md](SETTINGS.md)
pour ces choix, les tests de migration et la validation portable/AppImage.

## Conditions des essais : aucune référence de performance

L'utilisateur précise que cette RX 6500 est modeste et qu'un stream Twitch
1080p tourne en arrière-plan. La charge n'est pas contrôlée. Les latences,
images perdues et relevés mémoire ci-dessous documentent uniquement le
fonctionnement dans cette session ; **ils ne constituent pas un benchmark**,
ni une limite intrinsèque du moteur ou du GPU, ni une comparaison Windows/Linux.
Le profil 5 sans perte observée ne prouve pas non plus un débit garanti.

La fidélité numérique, les horodatages, les changements de profil, les
sauvegardes et la fermeture propre restent des résultats de validation utiles.
Des mesures de performance exigent une session isolée sur chaque PC, sans
lecture concurrente, avec conditions comparables. Aucun essai isolé n'a eu lieu.

## Avancées du 12 octobre 2026

### Inspection du filtre et des moteurs

- Le filtre `vf_animejanai` du commit mpv `19c0fcf895` ne négocie que les
  surfaces CUDA et D3D11. Ajouter une bibliothèque Linux AMD ne suffit donc pas.
- L'ABI `aji` version 9 et le chemin TensorRT existant seront conservés pour
  NVIDIA. Le projet d'inférence `v0.11.1` compile DirectML seulement sur Windows.
- RIFE NCNN/Vulkan fournit une implémentation native et des modèles convertis.
  Il faut vérifier la version effectivement utilisée, sans la présenter comme
  identique aux modèles ONNX RIFE 4.26 du chemin TensorRT.
- La voie AMD étudiée est un filtre logiciel mpv relié à une bibliothèque
  NCNN/Vulkan. Elle effectue l'inférence sur le GPU mais implique initialement
  des transferts CPU/GPU. Le débit devra être mesuré, sans promesse de temps réel.
- Le premier prototype Vulkan vise les sources SDR. La conservation des
  formats HDR et de leur précision exige une validation distincte.

À cette étape, les sources des moteurs étaient en cours de récupération. La suite était la
conversion du modèle AnimeJaNai Performance puis une inférence réelle sur AMD,
avant l'intégration des profils et du Manager.

### Première implémentation du backend Vulkan

- Ajout d'une bibliothèque native `aji_vulkan` et d'un test d'inférence autonome.
  Le pont d'images RGB24 utilise une ABI dédiée version 1 ; il ne modifie pas
  l'ABI 9 TensorRT ni les bibliothèques Windows.
- Chargement des modèles NCNN, choix explicite du GPU Vulkan, profils, chaînes
  spatiales 2×, RIFE 4.6, facteurs rationnels et détection de changement de scène.
- Les modèles temporels et les versions RIFE non converties sont refusés avec
  un message explicite. Aucun modèle différent n'est substitué silencieusement.
- Le convertisseur pnnx testé a planté sur le graphe dynamique SPAN, également
  après conversion FP32. Un convertisseur limité aux opérateurs exacts du SPAN
  fourni est ajouté ; sa fidélité doit être comparée à ONNX Runtime.
- La compilation native est lancée sur Ubuntu 24.04 dans un conteneur rootless.
  À ce stade, compilation et inférence ne sont pas encore validées.

### Pont mpv et conversion directe SPAN

- Le filtre `animejanai-vulkan` est ajouté uniquement au build Linux. Il
  négocie RGB24, charge le backend dynamiquement et produit les images RIFE
  avec leurs horodatages, y compris les facteurs fractionnaires.
- Le filtre refuse explicitement les sources PQ/HLG ; la lecture sans
  inférence reste le chemin à utiliser pour ces sources à ce stade.
- Le convertisseur direct conserve les poids ONNX et traduit convolution,
  ReLU, Tanh, additions, multiplications, concaténation et réorganisation des
  pixels. Les graphes non reconnus sont refusés. Le premier modèle Performance
  Sharp a été converti en 63 couches ; aucune validation numérique n'est encore
  acquise.
- Le build mpv a rencontré un `wayland-scanner` système trop ancien ; la
  reconstruction utilise maintenant le scanner du préfixe natif existant.

### Première exécution GPU

- mpv avec le filtre `animejanai-vulkan` et la bibliothèque NCNN ont compilé.
- Une interpolation RIFE 4.6 sur deux images synthétiques 64×64 a produit une
  image non constante sur la RX 6500, avec un facteur configuré 2×. Il reste à
  vérifier la cadence et les horodatages dans le lecteur.
- Le chargement du modèle SPAN a révélé la casse exacte du nom de couche NCNN
  (`TanH`). Le convertisseur a été corrigé ; l'upscaling est retesté avant toute
  déclaration de réussite.

### Fidélité AnimeJaNai et intégration au lecteur

- Le modèle Performance Sharp original FP16 a été comparé à ONNX Runtime CPU
  sur une image synthétique 64×64. Sortie 128×128 : erreur RGB8 absolue moyenne
  0,503 et maximale 1,540, incluant la quantification du pont RGB24.
  Rapport : `artifacts/vulkan-model-parity.json`.
- Le lecteur a produit des images 960×720 à partir du clip 480×360, avec
  AnimeJaNai seul et avec RIFE. Un défaut de destruction de la file mpv a été
  identifié à la fermeture et corrigé ; le nettoyage est retesté.
- Les sources de dimensions impaires sont refusées explicitement dans ce
  premier backend spatial ; les profils et le Manager seront adaptés ensuite.

### Nettoyage validé dans mpv

- Après correction de la durée de vie de la file de conversion, les trois
  essais mpv se terminent avec le code 0 : AnimeJaNai seul, RIFE seul, puis
  AnimeJaNai + RIFE. Chaque essai produit 12 images sur la RX 6500.
- Sorties vérifiées : 960×720, 480×360 à cadence doublée, puis 960×720 à
  cadence doublée. Journaux : `artifacts/vulkan-mpv-fixed-{1,2,3}.log`.
- Prochaine étape : intégrer ces moteurs aux banques Linux, au Manager et au
  paquet, puis tester les changements de profil et les horodatages.

### Intégration des profils et du Manager

- Les banques Linux neuves utilisent `backend=Vulkan` sur AMD et NVIDIA.
  Le profil 1 traite en 360p et produit du 720p ; le profil 2 ajoute RIFE ×2,
  le profil 3 interpole seul, le profil 4 produit du 1440p depuis 720p.
  L'inférence reste désactivée au démarrage (`default_slot=0`).
- Le lecteur distingue explicitement Vulkan et TensorRT ; les changements
  de slot Vulkan recréent le filtre, sans envoyer les commandes de l'ABI CUDA.
  Le pont Vulkan utilise le décodage logiciel puis le calcul GPU.
- Le Manager reçoit une sélection Vulkan Linux, les listes de modèles
  convertis et RIFE 4.6, et un enregistrement du backend. DirectML reste réservé
  à Windows. La compilation et les tests de cette intégration sont en cours.
- `build-inference.sh` épingle NCNN et RIFE, convertit les modèles SPAN et
  prépare les bibliothèques, les poids et les notices. Le paquet Vulkan peut
  fonctionner hors ligne sans TensorRT ; TensorRT reste un choix NVIDIA distinct.
- L'AppImage actualise les modèles Vulkan et ses liens vers les bibliothèques,
  et ne télécharge plus les composants TensorRT pour une banque Vulkan.

### Compilation et tests de l'intégration

- Les quatre modèles SPAN fournis ont été convertis (Performance et Balanced,
  Standard et Sharp). Les modèles non convertis sont exclus de la liste Vulkan.
- Les 9 cas Manager passent, dont le choix Vulkan, le filtrage des modèles,
  la sauvegarde/relecture de RIFE 4.6 et le socket Unix.
- LuaJIT : 214 assertions passent, dont les 161 originales et 53 Linux.
  Les nouveaux cas vérifient AMD/NVIDIA Vulkan sans TensorRT, le GPU explicite,
  le décodage, les changements de slot et la désactivation.
- Le paquet portable `3.8.0.8-linux-test.2` a été construit avec bibliothèques
  Vulkan, poids SPAN, RIFE et Manager. Ses essais matériels intégrés suivent.
- La documentation de compilation décrit `VULKAN_LOCAL` et `--vulkan-only` ;
  le workflow Linux compile aussi les composants depuis leurs commits épinglés.

### Essai intégré Wayland sur la RX 6500

- Le paquet portable ouvre le Manager et lit les cinq clips SDR. Les profils
  Vulkan 1, 2 et 3 fonctionnent, ainsi que changement de profil, recherche,
  chargement d'une autre résolution, désactivation et nettoyage IPC.
  Rapport : `artifacts/linux-vulkan-runtime.json`.
- Première mesure sur le clip 1280×720, sortie 720p : upscaling seul environ
  45 ms/image ; combiné RIFE environ 54 ms/image ; RIFE seul environ 35 ms/image
  en moyenne. Des images sont perdues sous cette charge concurrente ; cela ne permet pas
  de conclure sur le débit en session isolée.
  Il s'agit de fenêtres de cinq secondes, pas d'une validation d'épisode complet.
- Une optimisation d'arithmétique FP16 est testée. Elle ne sera conservée
  qu'après comparaison des quatre modèles aux sorties ONNX originales.

### Cadence et choix de profils légers

- Les huit comparaisons GPU/ONNX (quatre modèles, images 64×64 et 96×96)
  passent en arithmétique FP16. Les absences de modèle/GPU et les dimensions
  impaires sont également refusées. Rapport : `artifacts/vulkan-model-parity-all.json`.
- Une observation sans rendu, sous charge concurrente, relève environ
  44 ms/image pour l'upscaling 360p vers 720p. Ces essais ne permettent pas
  de comparer les performances FP16 et FP32 dans des conditions contrôlées.
- Sur un fichier de 12 images, RIFE produit 23 images avec cadence
  48000/1001 et horodatages croissants ; la dernière interpolation est drainée
  avant la fin du fichier. La précision milliseconde du conteneur est prise en compte.
- Deux profils plus légers sont ajoutés : Ctrl+5 (240p vers 480p sans RIFE),
  Ctrl+6 (180p vers 360p avec RIFE ×2). Mesure initiale sans rendu : combiné
  240p environ 31 ms/image ; combiné 180p environ 21 ms/image. Ces profils
  réduisent la résolution traitée ; les essais Wayland et la mémoire suivent.

### Raccourcis et publication incrémentale

- Le test des touches physiques a révélé que la section personnelle héritée
  désactivait Ctrl+5/Ctrl+6. L'assembleur les active uniquement pour Linux,
  en laissant les touches Windows inchangées.
- La publication incrémentale du Manager après une compilation Windows a
  omis les bibliothèques natives Linux. La reconstruction et le parcours
  de publication sont corrigés avant les derniers essais du paquet. La commande
  de publication désactive les serveurs de compilation persistants ; une
  publication fraîche contient à nouveau SkiaSharp et HarfBuzz et le binaire actuel.
- Les tests d'exécution attendent aussi la confirmation asynchrone du slot,
  afin de ne pas confondre l'ancien filtre avec le nouveau profil.
- La documentation Linux du Manager est ajoutée dans son propre dépôt et
  dans le patch livré avec le lecteur. Les notices et résultats restent
  accessibles dans les deux projets.

### Validation portable et AppImage

- Les deux formats passent les six transitions de profils (1, 2, 3, 5, 6, 1),
  les recherches, le rechargement à une autre résolution et la désactivation.
  Le test utilise les raccourcis réels Ctrl+1/2/3/5/6.
- Le Manager ouvre et sauvegarde/recharge SDR/PQ via le socket Unix, en
  conservant commentaires et options inconnues. Le socket est nettoyé.
- Le profil 5 n'a perdu aucune image durant les fenêtres de cinq secondes.
  Les autres profils perdent des images. Les latences d'inférence sont de
  l'ordre de 20–21 ms pour le profil 5 et 18–19 ms pour le profil 6 ; le coût
  total avec rendu reste supérieur et ces observations sous Twitch ne caractérisent pas le débit intrinsèque de RIFE.
- Pic de mémoire observé sur tout le GPU : environ 0,9–1,1 Gio. Il ne s'agit
  pas d'une mesure par processus. Rapports : `artifacts/linux-vulkan-runtime.json`
  et `artifacts/linux-vulkan-appimage-runtime.json`.
- Le script complet de compilation a aussi été exécuté dans Ubuntu 24.04 :
  bibliothèque, outil de test, quatre conversions et notices sont produits.
  Journal : `artifacts/vulkan-reproducible-build.log`.
- CI : ajout d'un job de compilation NCNN et de comparaison des modèles par
  Vulkan logiciel. Il ne remplace jamais la validation physique AMD/NVIDIA.
- Les guides Linux et ce journal sont inclus dans les paquets et leurs overlays.
  Les builds Windows et Linux du Manager restent distincts ; Windows conserve
  son backend DirectML/TensorRT et les noms de ses assets.

### Essai prolongé du moteur

- AnimeJaNai + RIFE (profil 6) a traité 60 secondes du clip 1280×720, soit
  2 879 images de sortie, en 57 secondes de calcul sans affichage.
- La mémoire GPU totale atteint environ 113 Mio et reste à ce niveau dans
  les dix derniers relevés. Aucun plantage ni croissance continue observée.
  Rapport : `artifacts/vulkan-soak.json`.
- Cet essai vérifie la stabilité du moteur, sans certifier le temps réel avec
  rendu Wayland en session isolée ; Twitch tourne en fond. Un épisode complet sur
  la RTX 4050 reste à tester sur la machine NVIDIA.

### Préparation finale des paquets

- Le backend et ses dépendances sont alignés exactement sur la compilation
  Ubuntu 24.04 ; les huit comparaisons et les cadences RIFE sont retestées.
- Le contrôleur évite de réécrire `hwdec` quand son choix ne change pas,
  pour ne pas demander un redémarrage inutile du décodeur lors d'un changement
  entre profils Vulkan. Les essais d'exécution sont relancés après cet ajustement.

### Correction durable de la publication native du Manager

- Une seconde publication incrémentale reproduisait l'omission des `.so`,
  même sans serveur de build : le build single-file perdait sa liste des
  bibliothèques exclues lorsque la génération du bundle était sautée.
- Le projet Manager copie désormais `NativeCopyLocalItems` après `Publish`
  pour Linux et refuse une sortie sans SkiaSharp/HarfBuzz. Cette correction
  s'applique aussi à ses releases ; elle ne dépend plus d'un dossier neuf.

### Précision sur la charge concurrente

- L'utilisateur signale un stream Twitch 1080p en arrière-plan et demande
  explicitement de ne pas prendre cette configuration comme référence de débit.
- Les rapports runtime et de stabilité portent désormais `performance_reference=false`,
  `background_twitch_1080p=true` et `load_controlled=false`.
- Les chiffres historiques restent conservés pour la traçabilité, avec leurs
  conditions. Ils ne justifient ni une comparaison Windows/Linux, ni une
  conclusion sur la RTX 4050 ou sur les performances propres de la RX 6500.

### Livraison des paquets de test

- Les derniers essais portable et AppImage passent après les corrections de
  publication native du Manager et de changement de décodeur. Les profils
  1, 2, 3, 5 et 6 sont exercés via les raccourcis, avec recherche, changement
  de résolution et désactivation ; le profil 4 produit aussi du 1920×1440
  dans un essai sans affichage terminé proprement.
- Les guides corrigés sont intégrés aux deux paquets `3.8.0.8-linux-test.2`.
  Le réassemblage final porte uniquement sur la documentation ; les binaires
  et scripts restent ceux des derniers essais matériels réussis.
- Les sommes SHA-256 et `artifacts/linux-vulkan-validation.json` accompagnent
  les paquets. Windows reste publié comme auparavant. Aucune release Linux
  publique n'est activée par ces essais ; RTX 4050 et HDR physique restent
  à valider sur les équipements correspondants.

## Sources techniques


- [Filtre mpv](https://github.com/the-database/mpv/blob/19c0fcf895/video/filter/vf_animejanai.c)
- [ABI et moteurs aji](https://github.com/the-database/animejanai-inference/tree/v0.11.1)
- [RIFE NCNN/Vulkan](https://github.com/nihui/rife-ncnn-vulkan)
- [NCNN et conversion des modèles](https://github.com/Tencent/ncnn)

## Plafond du moteur NCNN/Vulkan, mesuré le 12 octobre 2026

Question posée : une réécriture sans copie du backend Vulkan (images gardées dans le GPU) pourrait-elle
rivaliser avec DirectML, et vaut-elle un portage sous Windows ? Mesure faite pour y répondre :
`native/vulkan-bench/bench.cpp` charge un modèle SPAN converti, envoie l'entrée **une seule fois** dans
le GPU, puis exécute l'inférence sans jamais rapatrier la sortie. C'est le plafond de n'importe quel
backend NCNN/Vulkan : un pont d'images ne peut qu'ajouter du temps.

Sur RTX 4070 Ti, pilote 617.42, NCNN `d8227bb`, FP16, compilé avec MSVC :

| Modèle | 720p → 1440p | 1080p → 2160p |
|---|---|---|
| Performance | 28,3 ms (35 i/s) | 57,5 ms (17 i/s) |
| Balanced | 38,8 ms (26 i/s) | 101,5 ms (10 i/s) |

Références publiées dans `data/benchmarks` (chaîne complète, décodage compris) :

| Carte et backend | Performance 720p | Performance 1080p | Balanced 720p | Balanced 1080p |
|---|---|---|---|---|
| RTX 4070 Ti, TensorRT | 224 à 226 i/s | 86 à 92 i/s | 123 à 126 i/s | 55 à 61 i/s |
| RX 9070 XT, DirectML | 245 à 284 i/s | 81 à 99 i/s | 116 à 137 i/s | 43 à 53 i/s |

**Conclusion.** Sur la même carte, le calcul NCNN/Vulkan seul est environ 6 fois plus lent que la chaîne
TensorRT complète, et du même ordre face à DirectML sur une carte de classe comparable. Le frein est le
calcul lui-même (shaders de convolution génériques), pas les copies : une réécriture sans copie ne
comblerait pas l'écart. TensorRT et DirectML s'appuient sur des noyaux de convolution écrits par les
fabricants de GPU, auxquels un backend Vulkan générique n'a pas accès. **Le portage sous Windows et la
réécriture sans copie ne sont donc pas entrepris.** Le backend Vulkan garde son rôle : faire tourner
AnimeJaNai sous Linux là où ni TensorRT ni DirectML n'existent.

Limite de cette mesure : elle est faite sur le pilote Vulkan de NVIDIA. Pour la refaire sur une carte AMD,
compiler `native/vulkan-bench` (NCNN en sous-dossier `ncnn`, voir son `CMakeLists.txt`) et lancer
`bench <modèle sans extension> 1280 720`.

## Moteur ONNX Runtime pour MIGraphX (AMD) et OpenVINO (Intel) : première étape, 12 octobre 2026

But : remplacer NCNN/Vulkan, six fois trop lent, par les moteurs des fabricants là où ils existent.
`native/linux-ort/aji_ort.cpp` implémente la même interface que le moteur Vulkan (pont RGB24 de
`aji_vulkan.h`) avec ONNX Runtime : le filtre du lecteur peut charger l'une ou l'autre bibliothèque
sans modification, par son option `lib=`. Les modèles ONNX d'origine sont utilisés tels quels,
sans conversion. Le fournisseur vient de `backend=` dans la banque : `MIGraphX`, `OpenVINO` ou `CPU`.

**Ce qui est fait et vérifié**

- Lecture des profils (mêmes règles de choix de chaîne que le moteur Vulkan), redimensionnement
  avant le modèle, modèles FP16 ou FP32, enchaînement de plusieurs modèles, fichier de statistiques.
- Compilé sous Windows (MSVC) et exécuté sur le fournisseur **CPU** avec une banque réelle :
  profil « 2K Performance », 1280x720 → 2560x1440, image de sortie valide. Sur CPU : 625 ms par
  image, ce qui n'a aucune valeur de performance.
- Sans le fournisseur demandé, la configuration échoue avec le message d'ONNX Runtime
  (bibliothèque du fournisseur introuvable) : aucun repli silencieux.
- Job CI `ort-backend` : compilation sous Linux et passage d'un profil sur CPU. Il n'est pas
  bloquant tant que le moteur n'est pas empaqueté.

**Ce qui n'est pas fait**

- **Aucun essai sur MIGraphX ni sur OpenVINO.** Aucune carte AMD sous Linux ni carte Intel n'était
  disponible. Les appels aux deux fournisseurs sont écrits d'après les en-têtes d'ONNX Runtime 1.31
  et n'ont jamais tourné. Premier essai à faire sur matériel réel : `animejanai-ort-test` avec
  `AJI_ORT_PROVIDER=migraphx` ou `openvino`, modèle Performance en 1280x720 ; objectif sous 20 ms.
- **RIFE** : non géré par ce moteur. Un profil qui le demande est mis à l'échelle sans
  interpolation, et le fichier de statistiques le signale.
- **Intégration au lecteur** : pas de choix de la bibliothèque dans `linux-playback.lua`, pas de
  banque dédiée, pas de réglage dans le Manager, pas d'empaquetage. Les fournisseurs demandent une
  compilation d'ONNX Runtime qui les contient (paquets d'AMD pour ROCm, paquets d'Intel), à
  installer sur la machine : ils ne tiennent pas dans l'AppImage.
- **Windows** : sans objet pour l'instant. Sous Windows, DirectML couvre déjà AMD et Intel avec
  les noyaux des fabricants (245 à 284 i/s sur RX 9070 XT en Performance 720p). MIGraphX repose
  sur ROCm, dont la cible est Linux ; OpenVINO sous Windows ne se justifierait que s'il battait
  DirectML sur Intel, ce qui reste à mesurer.
- Le pont RGB24 copie chaque image par la mémoire vive. Avec un moteur à quelques millisecondes,
  ce coût deviendra visible ; il se mesurera en même temps que le moteur.

**Le moteur Vulkan reste nécessaire.** ROCm ne couvre que les RX 9070, 9060 XT et 7900 : une
RX 7800 XT, une RX 7600 ou toute la série RX 6000 n'ont que NCNN/Vulkan sous Linux. Ce ne sont pas
des cartes anciennes.

### Branchement dans le lecteur et le Manager (12 octobre 2026, fin de nuit)

- **Lecteur.** `linux-playback.lua` reconnaît `backend=MIGraphX` et `backend=OpenVINO` : même filtre
  à pont d'images que Vulkan, bibliothèque `libaji_ort.so`, décodage logiciel. La variable
  `ANIMEJANAI_ORT_DEVICE` force le périphérique (`GPU`, `GPU.1`, numéro HIP). Le moteur est proposé dès
  que `libaji_ort.so` est présent ; l'absence du fournisseur se voit à la lecture, par le message du moteur.
- **Manager.** *Global Settings* > *Inference engine* affiche **MIGraphX** et **OpenVINO** sous Linux,
  actifs quand `libaji_ort.so` est installé.
- **Paquet.** Le job `ort-backend` produit `libaji_ort.so`, `animejanai-ort-test` et l'ONNX Runtime
  standard ; Deploy les ajoute à `animejanai/inference` quand ce job a réussi, sans jamais bloquer.

**Pour essayer sur une machine réelle** : remplacer dans `animejanai/inference` les fichiers
`libonnxruntime.so*` par ceux d'une compilation d'ONNX Runtime qui contient le fournisseur voulu, avec
ses bibliothèques `libonnxruntime_providers_*.so` (paquet `onnxruntime-migraphx` d'AMD pour ROCm, paquet
`onnxruntime-openvino` d'Intel). Mesure directe, sans le lecteur :
`AJI_ORT_PROVIDER=migraphx ./animejanai-ort-test <banque.conf> <dossier onnx> <profil> 1280 720 20`.
Risque connu, non levé : le moteur est compilé contre ONNX Runtime 1.31 ; une compilation de fabricant
plus ancienne peut le refuser au chargement. Dans ce cas, recompiler `native/linux-ort` contre les
en-têtes de cette version.

**RIFE avec tous les moteurs : non fait.** Vulkan a RIFE 4.6 (NCNN), TensorRT a les modèles RIFE ONNX.
Le moteur ONNX Runtime n'a pas encore l'interpolation : il faut y reproduire la préparation des entrées
du chemin TensorRT (entrée à 11 canaux, grilles et remplissage au multiple de 64, `setup_rife` et
`aji_infer_rife` dans `animejanai-inference/src/aji_trt.cpp`). À faire une fois le moteur validé sur
matériel réel, sinon le travail porterait sur un moteur dont la vitesse n'est pas connue.

**TrueHDR sous Linux : possible par le SDK NVIDIA Maxine Video Effects (constat du 12 octobre 2026, non intégré).**
Le SDK RTX Video 1.1.0 reste limité à Windows, mais NVIDIA distribue le même filtre TrueHDR pour Linux
dans un autre SDK, Maxine Video Effects (exemple `apps/TrueHDREffectApp` du dépôt
`NVIDIA-Maxine/VFX-SDK-Samples`, documentation `docs.nvidia.com/maxine/vfx/latest/Filters/TrueHDR.html`).

- **Interface.** `NvVFX_CreateEffect(NVVFX_FX_TRUE_HDR)`, entrée tampon GPU RGBA 8 bits entrelacé, sortie
  tampon GPU `NVCV_RGB10A2` (PQ, BT.2020), flux CUDA fourni par l'appelant (`NvVFX_SetCudaStream`), même
  taille en sortie. Réglages `NVVFXTRUEHDR_CONTRAST` 0-200, `_SATURATION` 0-200, `_MIDDLE_GRAY` 10-100,
  `_LUMINANCE` 400-2000 nits, `_DEBANDING_OFF`. Ce sont les réglages de `animejanai-rtx.conf`
  (`rtx_contrast`, `rtx_saturation`, `rtx_middle_gray`, pic de l'écran).
- **Prérequis.** Pilote NVIDIA 570.26 ou plus récent ; Ubuntu 20.04 à 24.04, Debian 11-12, RHEL ou
  Rocky 8-9 ; GPU Turing ou plus récent.
- **Distribution.** Le coeur du SDK (en-têtes `nvVideoEffects.h`, `nvVFXTrueHDR.h`, `libVideoFX.so`) et
  la fonction `nvVFXTrueHDR` se téléchargent sur NGC avec une clé d'API personnelle
  (`install_feature.sh --feature nvvfxtruehdr --gpu <modèle>`). Les en-têtes ne sont pas dans le dépôt
  d'exemples. Le script n'énumère que des GPU de serveur, classés par capacité de calcul CUDA : `t4` 7.5,
  `a100` 8.0, `a10` 8.6, `l4` 8.9, `b40` 12.0. Une carte grand public prendrait le paquet de même
  capacité (RTX 40 : `l4`), **ce qui n'a pas été essayé**.
- **Réserves.** NVIDIA écrit que ce SDK est conçu pour le déploiement sur serveur et qu'il ne prend pas
  en charge l'intégration dans une application cliente ni le déploiement local : cela peut marcher sans
  être garanti. La licence du SDK sur NGC n'a pas été lue ; ne pas redistribuer ses fichiers dans une
  release avant de l'avoir fait. Le dépôt d'exemples, lui, est sous licence MIT.
- **Ce que demanderait l'intégration.** Une variante Linux de `aji_rtx` (aujourd'hui NGX, Windows) qui
  appelle `NvVFX` sur le flux CUDA du moteur TensorRT, plus le moteur modifié compilé pour Linux
  (`libaji_trt.so`, branche locale `rtx-video-cuda`, jamais publiée), le SDK étant installé par
  l'utilisateur avec sa clé NGC. Le même SDK contient aussi la super-résolution (`nvvfxvideosuperres`).
  En attendant, la conversion SDR vers HDR sous Linux passe par mpv avec la courbe mesurée sur TrueHDR
  (`mpv_truehdr_look`), qui suit les mêmes réglages.

**TrueHDR sous Linux : étage écrit et branché, jamais exécuté (12 octobre 2026, nuit).**
Le cœur du SDK Maxine 1.3.0.0 a été examiné (en-têtes `nvVideoEffects.h`, `nvCVImage.h`,
`libVideoFX.so`, runtime NGX). La fonction TrueHDR (`nvvfxtruehdr`, avec `nvVFXTrueHDR.h` et les
modèles) n'y est pas : elle se télécharge par `install_feature.sh` avec une clé NGC, qui choisit les
modèles d'après la capacité CUDA de la carte (`nvidia-smi`) ; une carte grand public convient donc en
principe.

- **Bibliothèque de liaison** `libaji_rtx.so` : mêmes fonctions que `aji_rtx.dll`
  (`aji_rtx_create`, `aji_rtx_eval`, `aji_rtx_shutdown`), plus `aji_rtx_input_bits` qui renvoie 8, car
  le filtre Maxine prend du RGBA 8 bits. Elle appelle `NvVFX` sur les tampons CUDA du moteur. À
  compiler sur la machine Linux (g++, quelques secondes) une fois la fonction installée. Pas de
  Super Resolution.
- **Moteur** `libaji_trt_rtx.so` : le moteur TensorRT avec l'étage final, compilé pour Linux
  (TensorRT 11.3.0.99, CUDA 13.4, Ubuntu 22.04). Il charge `libaji_rtx.so` placé à côté de lui.
- **Sources et binaire** : dépôt privé `Ta2b/animejanai-inference-rtx`, branche `rtx-video-cuda`
  (dossier `aji-rtx-linux`, mode d'emploi dans son `README.md`), release `linux-truehdr-1`.
- **Lecteur** : quand les deux bibliothèques sont dans `animejanai/inference`, avec un GPU NVIDIA, le
  moteur TensorRT, `linux_hdr_output=pq` et `hdr_backend` différent de `mpv`,
  `linux-playback.lua` charge `libaji_trt_rtx.so`, écrit `animejanai-rtx.conf` (`rtx_contrast`,
  `rtx_saturation`, `rtx_middle_gray`, pic de l'écran) et marque les images PQ / BT.2020 ;
  `linux-hdr.lua` cesse alors de convertir. Si le moteur n'annonce pas `Applied RTX Video: TrueHDR`
  dans son journal après 3 s, le marquage est retiré et mpv convertit. Le lanceur ajoute les
  dossiers du SDK à `LD_LIBRARY_PATH` seulement quand `libaji_rtx.so` est installé. Sans ces deux
  fichiers, rien ne change.
- **À lever au premier essai** : chargement des bibliothèques de la fonction par `libVideoFX`,
  cohabitation du TensorRT du SDK avec celui du moteur dans le même processus, et le réglage
  `linux_hdr_output=auto` qui ne déclenche pas l'étage (il faut `pq`).

**OpenVINO fourni dans le paquet Linux (3.8.0.13, 12 octobre 2026, nuit).**
Premier essai réel (Fedora, CPU et GPU Intel Arc, release 3.8.0.11) : `backend=OpenVINO` échouait,
faute de `libonnxruntime_providers_openvino.so`. Deux causes, corrigées :

- **Bibliothèques.** L'ONNX Runtime standard n'a pas ce fournisseur, et la compilation d'Intel
  (paquet PyPI `onnxruntime-openvino`, dernière version 1.24.1) est plus ancienne que les en-têtes 1.31
  utilisés jusque-là : elle aurait été refusée au chargement. Le moteur est maintenant compilé contre
  la 1.24.1 et livré avec les bibliothèques d'Intel (ONNX Runtime, fournisseur OpenVINO, OpenVINO
  2025.4.1 avec ses greffons CPU, GPU et NPU ; 153 Mo non compressés dans `animejanai/inference`).
- **Modèles.** Le fournisseur OpenVINO refusait le graphe à dimensions dynamiques (« the graph is not
  acyclic »). Le moteur fixe désormais la taille d'entrée de chaque modèle à la création de la session
  (`AddFreeDimensionOverrideByName`), l'optimisation d'ONNX Runtime restant active. Diagnostic :
  branche `diag` du dépôt privé `Ta2b/animejanai-inference-rtx`.

Vérifié en intégration continue : un profil passe par le fournisseur OpenVINO sur le périphérique CPU
et donne le même pixel de contrôle que le fournisseur CPU. **Non vérifié : le périphérique GPU**, qui
demande le pilote OpenCL d'Intel sur la machine (`intel-compute-runtime` sous Fedora, `intel-opencl-icd`
sous Ubuntu). Essais : `ANIMEJANAI_ORT_DEVICE=CPU` force le processeur ; `AJI_ORT_OPENVINO="clé=valeur;…"`
ajoute des options du fournisseur ; `AJI_ORT_OPT=0..3` change le niveau d'optimisation.
MIGraphX : remplacer `libonnxruntime.so.1` par la compilation d'AMD, version 1.24 ou plus récente.

## Premier essai réel sur NVIDIA sous Linux (3.8.0.16, 13 octobre 2026)

Machine : CachyOS, KDE Wayland avec HDR activé, RTX 4070 Ti, pilote 615.78, AppImage 3.8.0.15.

**TensorRT et RIFE : fonctionnent.** Constructions mesurées dans les journaux de `trtexec` :
AnimeJaNai Performance 640x360 en 53 s, 1920x1080 en 64 s, RIFE 4.26 en 1920x1088 en 22 s.

- **Cause du « model not found: rife_v4.6.onnx ».** La banque `linux-nvidia` livrée est celle du
  moteur Vulkan (`rife_model=46`, RIFE 4.6 au format NCNN). En passant le moteur sur TensorRT dans
  le Manager, ce code restait, alors que le pack RIFE de TensorRT va de 4.7 à 4.26. Le Manager
  (`20473e7`) remplace désormais, sous Linux, un modèle RIFE que le nouveau moteur ne peut pas
  charger : 4.26 sur TensorRT, 4.6 sur Vulkan.
- **Compteur de construction sans fin.** Après cet échec, le filtre était désactivé sans réécrire
  son fichier de statistiques ; `animejanai_engine_monitor.lua` y lisait toujours « Building
  TensorRT engine », gardait la lecture en pause et comptait indéfiniment. Il s'arrête maintenant
  sur l'erreur du filtre, reprend la lecture et affiche la cause.

**TrueHDR (Maxine) : première exécution réussie.** Avec le SDK 1.3.0.0, la fonction
`nvvfxtruehdr`, `libaji_trt_rtx.so` et `libaji_rtx.so` installés : profil RIFE x4 en 720p puis
AnimeJaNai vers 2560x1440, sortie du filtre mesurée à 95,9 images/s en PQ / BT.2020, journal
`Applied RTX Video: TrueHDR (peak 1000 nits)`. Vérifié par les propriétés de mpv, en lecture hors
écran et dans le lecteur ; la qualité de l'image HDR n'a pas été jugée à l'écran par un contrôle
indépendant.

- **Bogue de la bibliothèque de liaison, corrigé dans le dépôt privé (non commité à cette date).**
  `aji_rtx_vfx.cpp` passait à `NvVFX_SetImage` des descripteurs `NvCVImage` locaux ; le SDK en
  garde le pointeur. `NvVFX_Run` échouait à la première image (« invalid parameter value »), le
  filtre entier était désactivé : ni RIFE ni mise à l'échelle, image 1080p à 24 i/s étiquetée PQ.
  Les descripteurs sont maintenant statiques.
- **Les deux incertitudes notées plus haut sont levées** sur cette machine : `libVideoFX` charge
  la fonction, et le TensorRT du SDK cohabite avec celui du moteur dans le même processus.
- **Pic lumineux.** Avec `display_peak=auto`, l'étage recevait 1000 nits fixes alors que mpv
  visait le pic négocié (794 nits ici). Il reçoit maintenant le pic négocié, comme sous Windows,
  quand il est connu au moment de la configuration.
- **Reste ouvert.** Les images TrueHDR sont étiquetées PQ sans pic propre (`sig-peak` de 10 000
  nits) : mpv peut comprimer les hautes lumières vers le pic de l'écran. Non mesuré. Si l'étage
  échoue en cours de lecture, le lecteur garde l'étiquette PQ sur une image restée SDR : à corriger.
- **Diagnostic `Ctrl+Alt+h`.** La version Linux affichait un texte figé (« conversion : mpv ») et
  aucune cadence. Elle donne maintenant la résolution et la cadence après filtres, la cadence
  source, la fréquence de l'écran, l'état réel du filtre et la conversion réellement active.

**Ce qui n'est pas dans la release.** Le SDK NVIDIA ne peut pas être redistribué (clé NGC par
utilisateur, « déploiement serveur » selon NVIDIA) ; `libaji_trt_rtx.so` et le source de la
bibliothèque de liaison sont dans le dépôt privé `Ta2b/animejanai-inference-rtx` et n'ont pas été
copiés dans ce dépôt public. L'installation reste donc celle décrite plus haut. Piste pour la
réduire : les en-têtes `nvCVImage.h`, `nvCVStatus.h` et `nvVideoEffects.h` du SDK sont sous licence
MIT ; une bibliothèque de liaison qui ouvre `libVideoFX.so` à l'exécution (`dlopen`) se compile
sans le SDK et pourrait être livrée précompilée, avec le moteur. L'utilisateur n'aurait plus qu'à
installer le SDK et la fonction avec sa clé.

**Manager.** *RTX Video HDR* n'est plus grisé sous Linux avec un GPU NVIDIA. Les options propres à
un fabricant sont grisées quand la machine n'a pas de GPU de ce fabricant : MIGraphX (AMD),
OpenVINO (Intel), RTX VSR et AMD VideoSR / AMF (Windows). Une machine hybride garde les options
de chacun de ses GPU. Sous Windows, le Manager ne distingue que NVIDIA du reste : AMD VideoSR et
AMF y restent proposés sur Intel.

## NVIDIA Smooth Motion sous Linux (3.8.0.17, 13 octobre 2026)

Le pilote NVIDIA Linux fournit Smooth Motion comme couche Vulkan (`libnvidia-present.so`), activée
par la variable `NVPRESENT_ENABLE_SMOOTH_MOTION=1` (constaté dans
`/usr/share/vulkan/implicit_layer.d/nvidia_layers.json`, pilote 615.78). Elle génère une image
entre deux images affichées, sur toute la fenêtre.

- **Réglage.** `smooth_motion=yes` dans `animejanai_hdr_auto.conf` ; case *NVIDIA Smooth Motion*
  du Manager (`37ee789`), *Global Settings* > *Playback and rendering*, visible sous Linux et
  grisée sans GPU NVIDIA ou si le pilote n'annonce pas la fonction dans son manifeste.
- **Lanceur.** `launch-linux.sh` lit la clé et pose la variable avant de démarrer mpv ; une valeur
  déjà présente dans l'environnement l'emporte. Le lecteur doit être redémarré après un changement.
- **Diagnostic.** `Ctrl+Alt+h` indique si la fonction a été demandée au lancement. Son effet réel
  n'est pas observable depuis mpv : la couche agit après lui.
- **Pas de placement après RIFE.** Smooth Motion ne voit que l'image finale de la fenêtre
  (sous-titres compris, résolution de sortie) ; il ne peut pas s'insérer dans la chaîne de filtres
  pour travailler avant la mise à l'échelle. Dans cette chaîne, c'est RIFE qui tient ce rôle.
- **AMD et Intel.** Pas d'équivalent sous Linux : AMD Fluid Motion Frames n'existe que dans le
  pilote Windows, Intel n'a pas de génération d'images au niveau du pilote. Sous Windows, Smooth
  Motion et Fluid Motion Frames se règlent dans l'application du fabricant, et AMD AMF x2 reste
  le réglage du Manager.
- **Constats sur RTX 4070 Ti, écran 4K 165 Hz VRR, sortie 1440p à 71,93 i/s avec TrueHDR.**
  Charge GPU moyenne 59 % avec Smooth Motion contre 43 % sans (30 s, images tenues réutilisées).
  L'utilisateur voit des artefacts sur les sous-titres et une fréquence d'écran qui oscille entre
  100 et 165 Hz ; cause non établie (VRR « Always » de KDE et cadence non régulière suspectés).
  Sans réutilisation des images tenues, le même profil tourne à 82 % de GPU et perd des images
  par rafales quand une autre application sollicite le GPU (130 en 100 s sur un passage, 0 au
  passage suivant).

