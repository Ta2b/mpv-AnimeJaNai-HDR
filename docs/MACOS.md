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
