# macOS (puce Apple) : aperçu

État au 13 octobre 2026 : première version, **compilée et vérifiée sans écran en intégration
continue, jamais ouverte sur un vrai Mac**. Mode d'emploi pour l'utilisateur :
`installer/macos/LISEZ-MOI.txt` (joint à la release sous le nom `LISEZ-MOI-macOS.txt`).

## Ce qui est livré

- `mpv-AnimeJaNai-HDR-v<version>-macos-arm64.zip` : l'application « mpv AnimeJaNai ».
- `AnimeJaNai-mac-bench.zip` : mesure du temps de calcul des modèles avec Core ML, sans lecteur
  (`native/macos-bench`). C'est par elle qu'on sait si un Mac donné tient le temps réel.

## Composition

- **mpv** : le même mpv épinglé que sous Linux (`the-database/mpv`, `19c0fcf895`), avec le filtre à
  pont d'images `animejanai-vulkan` (`native/linux-vulkan/install-filter.py`, étendu à macOS).
  Compilé avec les bibliothèques de Homebrew, sortie Vulkan par MoltenVK (`gpu-context=macvk`),
  empaqueté par `TOOLS/osxbundle.py`. Script : `installer/macos/build-mpv.sh`.
- **Moteur** : `libaji_ort.dylib` (`native/linux-ort`), ONNX Runtime 1.31 standard pour macOS avec
  le fournisseur **Core ML** (`backend=CoreML`). Modèle au format ML Program, demi-flottants, taille
  d'entrée fixe. Périphérique : `ALL`, `GPU`, `ANE` (Neural Engine) ou `CPU`. Modèle compilé gardé
  dans `~/Library/Caches/AnimeJaNai/coreml`.
- **Application** (`installer/macos/package.sh`) : l'exécutable principal est `launcher.sh`. mpv ne
  lit pas ses réglages dans son paquet d'application (constaté : seuls `~/.config/mpv`, `~/.mpv` et
  le dossier de Homebrew sont consultés), donc le lanceur fixe `MPV_HOME` sur
  `~/Library/Application Support/AnimeJaNai/mpv`, y copie le script à chaque lancement et les
  fichiers de réglages s'ils manquent, puis lance mpv. Le script `animejanai_mac.lua` est autonome :
  il ne dépend ni de `gpu-policy.lua` ni de l'assistant `AnimeJaNaiPlatform`.
- **Signature** : ad hoc seulement. Sans compte développeur Apple l'application n'est ni signée ni
  notariée : l'utilisateur doit retirer l'attribut de quarantaine (`xattr -dr com.apple.quarantine`).

## Ce qui est vérifié en intégration continue (machine Apple Silicon virtuelle)

- Core ML accepte les modèles et donne le même pixel de contrôle que le fournisseur CPU, sur les
  quatre périphériques.
- L'application lit un clip de synthèse : script chargé, filtre actif, statistiques
  `Backend: ONNX Runtime/CoreML`, sortie 1280x720 pour une source 640x360.
- Les temps mesurés là (environ 45 ms en 320x180) ne disent rien d'un vrai Mac : la machine est
  virtuelle.

## Ce qui n'est pas fait

- Affichage réel, HDR, ouverture de fichiers depuis le Finder, raccourcis : jamais essayés.
- Conversion SDR vers HDR avec le rendu TrueHDR (shader `anime-hdr-grade`), RIFE, Manager,
  mise à jour automatique, intégration à l'assembleur `Program.cs`.
- MLX : non essayé. À comparer à Core ML seulement si les mesures sur un vrai Mac déçoivent.

## Compilation

Workflow `.github/workflows/macos.yml` : jobs `engine` (moteur, essais, paquet de mesure) et
`player` (mpv, application, essai de lecture). Sur la branche `release`, il attend que la release
existe puis y ajoute les fichiers macOS ; il ne bloque jamais la release Windows et Linux.

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
