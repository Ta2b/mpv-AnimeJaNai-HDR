# macOS (puce Apple)

## Situation actuelle — 3.8.0.29 (14/10/2026 à 20 h 45 (Paris))

La **3.8.0.29 est publiée sur les trois plateformes**, depuis `6fa85bb`.
Les releases Windows/Linux/macOS sont indépendantes et n'ont plus de jobs de
tests. Le code RIFE partagé `30a3e83` est maintenant dépassé et intégré par les
lots suivants : `d639dc1` / `b3f9d5d` ajoutent la chaîne warp et la chronologie
des dessins. La branche NVIDIA CUDA Graph `f4fcd17` reste isolée.

Lire [l'état consolidé courant](ETAT-PROJET.md) et
[le chantier 3.8.0.24–29 / 165 Hz](CHANTIER-RIFE-165HZ.md). Les sections datées
3.8.0.23 ci-dessous restent un historique des preuves de cette session, pas
l'état global actuel. La chaîne warp est livrée dans le moteur partagé ;
**elle ne l'est pas dans NCNN/Vulkan ni dans les binaires Windows amont**.
Les modèles sont conservés, mais cette stratégie et le lissage des dessins
changent le rendu temporel ; l'ancien mode est conservé.

## Historique — moteur partagé avant la nouvelle chaîne 3.8.0.29

## État au 14 octobre 2026

La **[3.8.0.23 est publiée](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/releases/tag/3.8.0.23)** :
application Apple Silicon, SHA-256, notice et paquet autonome de benchmark.
La dernière application a été essayée par l'utilisateur sur son MacBook Pro
M4 Pro, avec un retour qualitatif très favorable à Core ML natif GPU+NPU, suivi
de Metal GPU+NPU. Ce retour ne fournit pas un gain chiffré du nouveau code.

Le benchmark 3.8.0.21 s'est déroulé en partie avec la session verrouillée : ses
classements et longues pauses restent provisoires. Le nouveau programme exclut
l'échauffement, fournit médiane/p95/max et phases RIFE et protège temporairement
contre la veille automatique. Il ne garantit pas l'absence de verrouillage.
`upscale work` et `other` remplacent les anciennes colonnes trompeuses ; `other`
n'est pas un temps de copies. Les durées RIFE sont par intervalle source.

[État du projet](ETAT-PROJET.md) et [relais détaillé](CHANTIER-PERFORMANCE-RELAIS.md).
Mode d'emploi : `installer/macos/LISEZ-MOI.txt` ; notice de mesure :
`native/macos-bench/LISEZ-MOI.txt`. Aucun nouveau test local après la demande d'arrêt.

## Moteurs, modèles et fonctions livrés

- **Upscale :** Core ML natif, Metal et Core ML via ONNX Runtime, avec les cibles
  proposées dans le Manager. Le moteur partagé `libaji_ort.dylib` organise les
  tuiles, la reprise de dessins/zones et le traitement en avance.
- **RIFE :** modèles actuels 4.26, 4.25 et 4.22 lite, avant ou après upscale.
  RIFE est toujours exécuté via ORT/Core ML, même quand l'upscale est natif ou Metal.
  Le meilleur ordre dépend des coûts et du rendu ; aucun changement automatique
  d'ordre n'a été introduit dans les derniers lots.
- **3.8.0.23 :** workers CPU persistants, entrée/timestep RIFE réutilisés et
  buffers de conversion conservés. Modèles et précision conservés dans le code.
- **Application :** mpv/MoltenVK, lanceur fixant `MPV_HOME`, réglages utilisateur
  dans `~/Library/Application Support/AnimeJaNai`, cache de modèles sous
  `~/Library/Caches/AnimeJaNai`. Manager, updater et profils RIFE sont inclus.
- **Signature :** ad hoc, sans notarisation Apple ; la notice explique le retrait
  de l'attribut de quarantaine pour le premier lancement.

## Suite codée, pas encore livrée dans la 3.8.0.23

Commit **`30a3e83`**, `hdr-3.8` : décision dessin/coupe conservée par paire et sortie
RIFE ORT préallouée. Compilation Release Linux et CI Mac/plateforme réussies,
notamment [engine et player](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38481912353).
La suite locale de 516 images par variante n'a pas été répétée pour ce nouveau
lot ; aucune accélération chiffrée ni fidélité sur chaque puce physique annoncée.
Les switches de comparaison et leurs versions sont dans [DEVELOPMENT.md](DEVELOPMENT.md).

RIFE natif Core ML/Metal et chaîne SPAN/RIFE résidente sur GPU restent à écrire.
La branche CUDA Graph du backend NVIDIA ne concerne pas les binaires Mac.

## Compilation et preuves

`.github/workflows/macos.yml` construit le moteur et l'application avec ONNX
Runtime **1.31.0**. Sur `release`, il ajoute les assets Mac à la release ou la
crée si Deploy ne l'a pas encore créée. Deploy publie Windows/Linux séparément.
Le run de livraison [38479416046](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/38479416046)
et Deploy sont réussis ; la release contient maintenant les trois plateformes.

Les contrôles sur le runner Apple Silicon valident compilation, modèle et
intégration synthétique, pas le débit ou l'affichage HDR d'un Mac physique.
Les comparaisons de moteurs sur le vrai Mac nécessitent une mesure déverrouillée
si l'utilisateur souhaite reprendre les essais ; la consigne d'arrêt locale
reste active dans ce chantier.

## Historique du 13 octobre 2026

Les sections suivantes conservent les premiers états et observations. Les
mentions « RIFE/Manager/updater non faits », « jamais ouvert sur un vrai Mac »
et « non publié » concernent ces étapes, pas l'état courant décrit ci-dessus.

## 3.8.0.15 (13 octobre 2026) : premier retour d'un vrai Mac

Premier essai de l'utilisateur sur un MacBook Pro M4 Pro : le lecteur s'ouvre et le profil le plus
léger prend **54 ms par image**, trop pour 24 images par seconde (41 ms). Corrections :

- **Conversions sur plusieurs cœurs.** Le travail côté processeur (octets vers flottants,
  redimensionnement, demi-flottants, retour en octets) tournait sur un seul cœur. Il est réparti sur
  huit au plus, et deux chemins directs évitent l'image flottante intermédiaire : octets vers
  demi-flottants par table à l'entrée, demi-flottants vers octets à la sortie.
- **Détail des temps.** Les statistiques (`Ctrl+j`) donnent le temps du modèle et celui des
  conversions : c'est ce qui dira où chercher ensuite. Gain réel non mesuré sur un vrai Mac.
- **Bogue du cache Core ML.** Le modèle compilé était rangé sans tenir compte de la taille d'image ;
  un changement de profil ou une vidéo d'une autre taille reprenait un modèle incompatible et le
  filtre échouait. Un dossier par taille et par périphérique. Essai ajouté à la compilation.
- **Conversion SDR vers HDR.** Les scripts HDR communs (`gpu-policy.lua`, `hdr-grade.lua`,
  `linux-hdr.lua`) et le shader `anime-hdr-grade` sont livrés ; `gpu-policy.detect` connaît macOS.
  Active avec `linux_hdr_output=pq`. Vérifié seulement : chargement sans erreur Lua.
- **Arborescence.** `~/Library/Application Support/AnimeJaNai` a la forme de l'installation Linux
  (`portable_config`, `animejanai`), avec `ANIMEJANAI_ROOT` et `ANIMEJANAI_DATA_DIR`, pour qu'un
  Manager puisse s'y brancher. L'ancien dossier `mpv/` de la 3.8.0.14 n'est plus lu.

Écran Liquid Retina XDR : la sortie PQ / BT.2020 de mpv passe par l'EDR de macOS. Réglages conseillés,
non vérifiés : `display_peak=1600`, `display_oled=no` (mini-LED). `Ctrl+i` affiche ce que l'écran a
négocié.

## État à la pause du 13 octobre 2026 : à lire pour reprendre

**Dernière release : 3.8.0.15.** La branche `hdr-3.8` est en avance sur elle (correctif ci-dessous,
non publié). Pour le publier : passer `release-version.txt` à 3.8.0.16, pousser `hdr-3.8` puis
`hdr-3.8:release` ; le workflow `macOS` joint seul ses fichiers à la release.

### Mesure sur le MacBook Pro M4 Pro de l'utilisateur (3.8.0.15, profil 1)

- Temps par image 47 à 49 ms, dont **modèle 46 à 48 ms** et conversions 2,5 ms. Il faut moins de
  41 ms pour 24 images par seconde. Résolution de la vidéo et valeur de `device` non précisées
  (probablement 1080p et `ALL`).
- Les conversions ne sont donc plus le problème ; tout se joue dans le modèle.

### Cause trouvée, correctif écrit, non publié, gain non mesuré

- Avec `AJI_ORT_LOG=0`, ONNX Runtime montre que Core ML ne prend pas le graphe en entier : le
  « pixel unshuffle » des modèles (Reshape en rang 6, Transpose, Reshape) est refusé, Core ML
  n'acceptant pas les tenseurs de rang supérieur à 5. Le graphe est coupé en **deux parties Core ML**
  avec ces nœuds sur le processeur entre les deux.
- `native/linux-ort/fuse_unshuffle.py` remplace ces trois nœuds par une convolution 2x2 de pas 2 à
  poids unitaires, strictement équivalente. Le workflow produit des variantes `*.coreml.onnx` ; le
  moteur les préfère quand `backend=CoreML` (`AJI_ORT_ORIGINAL=1` revient au modèle d'origine).
- Vérifié en intégration continue : **une seule partie Core ML**, même pixel de contrôle que le
  fournisseur CPU, application et paquet de mesure contenant les variantes.
- **Non vérifié : le gain.** La machine de test est virtuelle, sans vrai GPU ; ses temps ne disent
  rien (le modèle fusionné y est même un peu plus lent, dans le bruit).

### Suite proposée, dans l'ordre

1. Publier la 3.8.0.16 et demander à l'utilisateur `Model ms` (Ctrl+j) avec `device=ALL`, `GPU` puis
   `ANE`, profil 1, vidéo 1080p. Le paquet `AnimeJaNai-mac-bench.zip` donne les mêmes chiffres sans
   lecteur.
2. Si le modèle reste au-dessus de 35 ms : regarder ce que Core ML fait encore hors GPU (journal
   `AJI_ORT_LOG=0`), puis comparer avec MLX (il faudra réécrire le modèle SPAN, MLX ne lisant pas
   l'ONNX) ou un appel direct à Core ML sans ONNX Runtime.
3. Manager pour macOS : non commencé. Le Manager distingue Windows et Linux à 21 endroits et ne
   connaît pas Core ML ; l'arborescence `~/Library/Application Support/AnimeJaNai` est déjà celle
   de Linux (`ANIMEJANAI_ROOT`, `ANIMEJANAI_DATA_DIR`).
4. RIFE dans le moteur ONNX Runtime, mise à jour automatique sur Mac.

### Jamais vérifié sur le Mac

Conversion SDR vers HDR (`linux_hdr_output=pq`, `display_peak=1600`, `display_oled=no` conseillés
pour l'écran XDR) : aucun retour de l'utilisateur. Ouverture depuis le Finder : aucun retour non plus.

## 3.8.0.18 (13 octobre 2026) : réglages Core ML et deux processeurs à la fois

Écrit sans Mac : compilé et vérifié fonctionnellement ici sous Linux (fournisseur CPU) et en
intégration continue sur la machine Apple virtuelle. **Aucun gain n'est mesuré.**

### Pourquoi 46 ms n'est sans doute pas un défaut de câblage

Ordre de grandeur, à prendre comme une estimation et non une mesure : le modèle Performance fait
environ 18 convolutions 3x3 à 48 canaux sur une image interne de 640x360 pour une entrée 720p,
soit de l'ordre de 170 milliards d'opérations flottantes par image. La RTX 4070 Ti le fait en
4,5 ms (TensorRT). Un GPU de M4 Pro donné pour environ 8 TFLOPS, exploité à moitié par Core ML,
donne 40 à 50 ms : c'est ce qui a été mesuré (46 à 48 ms). Le chemin par ONNX Runtime ajoute des
copies, mais il n'explique pas un facteur 2 : sur le GPU seul, le M4 Pro est proche de sa limite
en 720p. Les leviers sont donc ailleurs.

### Ce qui change

- **Options Core ML** (`aji_ort.cpp`) : `SpecializationStrategy=FastPrediction` et
  `AllowLowPrecisionAccumulationOnGPU=1` (sommes en demi-flottants dans les convolutions du GPU,
  la précision que les modèles utilisent déjà). Retour aux anciens réglages pour comparer :
  `AJI_ORT_COREML="SpecializationStrategy=Default;AllowLowPrecisionAccumulationOnGPU=0"`.
- **Deux processeurs à la fois** : `device=GPU+ANE`. L'image d'entrée du modèle est coupée en
  bandes horizontales, une session par processeur, exécutées en parallèle ; le GPU et le Neural
  Engine sont deux processeurs distincts. Chaque bande voit 48 lignes au-delà de ses bords
  (`AJI_ORT_OVERLAP`), ce que couvrent les convolutions : la sortie est identique à celle de
  l'image entière, vérifié octet pour octet avec le fournisseur CPU sur les deux modèles, en
  640x360, 1280x720 et avec le profil qui ramène le 1080p à 720p. `AJI_ORT_SPLIT` donne la part
  de l'image du premier processeur (50 % par défaut). Limité aux profils à un seul modèle.
- **Statistiques** (`Ctrl+j`) : avec deux processeurs, une ligne `Lanes` donne le temps de chacun,
  pour régler leur part.
- **Paquet de mesure** : une ligne `RESULT` par essai (temps par image hors première image, part
  du modèle, part des conversions) et un classement final. Il compare chaque processeur seul,
  les anciens réglages, puis les bandes GPU+ANE à 50, 60 et 70 %, en 540p, 720p et 1080p, avec
  les deux modèles. `bench.command rapide` se limite à Performance en 720p.

### Ce qu'il faut du vrai Mac

Le fichier `resultats.txt` du paquet de mesure 3.8.0.18. Il dit, en une exécution : ce que valent
le GPU et le Neural Engine séparément, ce qu'apportent les nouveaux réglages, et si les deux
ensemble dépassent le meilleur des deux. Selon le classement, `device` et `AJI_ORT_SPLIT` seront
fixés par défaut dans `animejanai_mac.conf`.

### Pas fait

Modèle Core ML natif sans ONNX Runtime, images gardées dans le GPU (décodage VideoToolbox sans
copie), RIFE, Manager. Le premier n'a d'intérêt que si la mesure montre que le temps part dans
ONNX Runtime et non dans le calcul.

### Réglages par défaut sans Manager (3.8.0.19)

Il n'y a pas de Manager sur Mac : ce qui dépend de la machine se règle seul.

- **Profil.** `animejanai_mac.lua` lit le temps par image du moteur (16 mesures après les 12
  premières images) et le compare au temps entre deux images de la vidéo (85 % de ce temps,
  `auto_budget`). Trop lent : profil plus léger suivant, 1 puis 5 (540p) puis 6 (360p) puis
  désactivé, avec un message, et mémorisation dans `animejanai/auto-profile.txt` (« désactivé »
  n'est pas mémorisé). `Ctrl+r` oublie ce choix ; un profil choisi au clavier suspend le
  mécanisme pour la séance ; `auto_profile=no` le coupe. Les profils 5 et 6 sont lus dans la
  banque de l'application quand celle de l'utilisateur, plus ancienne, ne les a pas.
  Vérifié sous Linux avec le fournisseur CPU dans le mpv du paquet : descente 1, 5, 6, arrêt ;
  profil mémorisé repris au lancement suivant.
- **HDR.** Au premier lancement, `launcher.sh` cherche un écran XDR (`system_profiler`). S'il y
  en a un et que les réglages sont encore ceux d'origine : `linux_hdr_output=pq` et
  `display_peak=1600` (`display_oled=no` est déjà la valeur d'origine). Une seule fois
  (`.display-defaults`). `Ctrl+h` bascule la conversion et réécrit le réglage. Vérifié : la
  logique du lanceur avec une fausse détection, la bascule dans le lecteur. **Jamais vu à
  l'écran : la conversion SDR vers HDR sur macOS reste sans retour de l'utilisateur.**
- **Processeur.** `device=ALL` reste la valeur d'origine tant que le paquet de mesure n'a pas dit
  si `GPU+ANE` fait mieux.

