# Lot 15 — descriptions et provenance des versions

AH-17 / REF-07. Base player `66f4be0b47b046429d0a2c0e91dfedb4bb63a455` / 3.8.0.44 ; source de capacités/CLI `826cb36de916fa62eccb9d144d92cd8536c75c23`. Manager référence `b3a8c1fcfd7b5acc846c0fb6ecba2fea793ef740`, candidat `132dab9525b5eab87e149f3d043b572b5f2d258a`, compilant la source partagée player `826cb36`. GPU libraries pin `9bcc7d476e59f1bf87ed0af6c3c5a65ac420c76f` conservé ; le lot motion/temporal 14 n’est pas inclus.

## Changement

`BackendCapabilities` dans le fichier C# déjà partagé entre lecteur/Manager est la source des notices : ONNX RIFE partagé pour OpenVINO, NCNN/Vulkan d’inférence, TensorRT/CUDA et présentation Vulkan distincts. Le chemin RIFE implémenté ne vaut pas qualification native Intel ; l’expérimentation et les besoins provider/opérateurs/modèles sont explicites. Documentation courante [CAPACITES-ET-VERSIONS](../CAPACITES-ET-VERSIONS.md), rapports datés conservés comme historiques.

CLI à la demande `--capabilities` et `--versions --root DIR [--release-manifest FILE]` : informations de compilation de l’outil, déclaration de compilation GPU-SOURCE, manifeste livré explicite, version/manifeste locaux et SHA réels des bibliothèques sur disque. Une provenance absente reste inconnue ; un hash différent ne prétend pas identifier le code installé. Rien ne prétend identifier une bibliothèque déjà chargée dans un processus. Lecture séquentielle à la demande, pas capture atomique de tous les fichiers.

## Essais courts et ciblés

Même Linux/machine/configurations de fixture. Aucun calcul GPU ni modification du jeu/services utilisateur. Le gain est la correction d’une information trompeuse et une provenance vérifiable ; pas un gain FPS.

- **Manager réel compilé, avant/après** : même probe de ViewModel et mêmes fichiers de présence/configuration. Avant : `Upscaling only, no RIFE yet`. Après : chemin `shared ONNX RIFE`, dépendances explicites. Notices NCNN/Vulkan et TensorRT/CUDA distinguées de la notice d’affichage Vulkan ; binding Avalonia compilé. Ces fichiers de présence sont des fixtures UI, sans qualification d’un provider natif. Deux processus courts, cas conclusifs arrêtés.
- **Versions distinctes** : bibliothèque réellement compilée backend `df489209…` / SHA `9d9e87d5…`, version locale de fixture `3.8.0.40`, manifeste officiel livré `.44` (`package_version`), hash déclaré correspondant : les trois états apparaissent séparément. Version de l’outil local `1.0.0+826cb36…` explicitement distincte.
- **Remplacement d’un fichier** : ajout de bytes dans la seule copie de fixture, `version.txt` inchangé : `matches_compiled_metadata` passe true→false.
- **Métadonnée absente** : paquet de test extrait existant `artifacts/performance/player/squashfs-root`, lu sans modification ; quatre bibliothèques fingerprintées, sources de compilation inconnues, aucune inférence à partir du numéro de version. Ce dossier ne prétend pas être l’application actuellement chargée par l’utilisateur.
- **Catalogue CLI** : décrit les mêmes capacités que les notices, avec qualification matérielle distincte.

Coûts ponctuels des commandes : cas identité 0,1009 s ; fichier remplacé 0,1048 s ; paquet de test extrait 0,1670 s ; capacités 0,0620 s. Aucun benchmark FPS, aucune répétition. Le premier build du probe avait un mauvais mode self-contained ; il a échoué avant toute exécution de test. Seule cette configuration de compilation a été corrigée. Builds locaux avant/après : mêmes 44 avertissements existants, zéro erreur après correction.

Reproduction : `tests/manager-notices/NoticeProbe.csproj` avec `ManagerSource` et `PlatformSource` épinglés, RID linux-x64/self-contained ; `tests/platform/capabilities_versions_check.py SPEC`. Reçus, logs, manifestes publics et commandes dans `artifacts/performance/lots-20261016/lot-15/`. Les shaders, modèles et bibliothèques d’inférence restent ceux de .44 ; aucun changement de calcul/qualité introduit.

## Livraison et décision

Conserver : mentions périmées supprimées, source commune consommée, compilation/livraison/fichiers installés identifiables séparément. Manager workflow **38843001983 success**, release immuable `hdr-132dab9525b5eab87e149f3d043b572b5f2d258a` vérifiée, **4 assets uploaded** Windows/Linux/macOS. Livraison du lecteur **3.8.0.45** à préparer avec ce pin. Les qualifications natives de providers restent dans leurs tickets ; AH-242 reste ouvert, contrôle GPU suspendu pendant le jeu de l’utilisateur, sans publication partielle du lot 14.
