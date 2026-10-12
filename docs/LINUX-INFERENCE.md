# AnimeJaNai et RIFE sous Linux : journal d'implémentation

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
