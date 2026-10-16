# Capacités et versions : source courante

Les capacités partagées du lecteur et du Manager sont définies dans [`BackendCapabilities`](../AnimeJaNaiPlatform/PlatformServices.cs). Le Manager compile ce même fichier depuis le commit player épinglé par son `player-source-ref.txt` ; le lecteur épingle séparément le Manager par `manager-source-ref.txt`. `AnimeJaNaiPlatform --capabilities` expose ces descriptions. Il s’agit de chemins implémentés, pas d’une certification de chaque API/GPU.

Sur Linux, `AnimeJaNaiPlatform --device-capabilities --root DIR [--cuda-device ORDINAL]`
charge les modules présents et consomme leurs sondes optionnelles : conversion
CPU réellement exécutée et kernel CUDA du module livré, périphérique/SM et versions.
Un module ancien sans sonde reste inconnu ; un fichier présent mais non chargeable
échoue explicitement. Cela ne qualifie ni les modèles ni leurs opérateurs.
Voir [la portée et les preuves du lot28](qualification/lot-28-device-caps-20261016.md).

| Choix | Calcul d’inférence | Modèles / limites |
|---|---|---|
| TensorRT | CUDA / TensorRT, NVIDIA | ONNX spatial + ONNX RIFE ; précision/profils propres aux graphes |
| Vulkan (moteur Linux) | NCNN / Vulkan | SPAN et RIFE4.6 NCNN, SDR et dimensions paires |
| OpenVINO | Engine partagé ONNX Runtime, provider OpenVINO Intel | Spatial ONNX et chemin RIFE partagé ; provider/opérateurs/modèles compatibles requis. Qualification native Intel distincte de la preuve CPU |
| Vulkan (affichage mpv) | Présentation des images terminées | Choix d’affichage indépendant du moteur d’inférence ; les effets RTX ont leurs conditions NVIDIA |

La mention « OpenVINO: no RIFE yet » est périmée : le chemin partagé RIFE existe. Cela ne transforme pas les essais CPU de la transformation en validation native du provider Intel. Les notices gardent cette distinction.

## Identifier séparément compilation, livraison et installation

```
AnimeJaNaiPlatform --versions --root /chemin/du/paquet --release-manifest /chemin/manifest-livraison.json
AnimeJaNaiPlatform --capabilities
```

- **Compilation** : les champs `backend_source`, `player_source`, `player_qualification_source`, `windows_build` et `sha256` dans `GPU-SOURCE.json` décrivent la provenance déclarée de la bibliothèque compilée. Une compilation/link réussie ne prouve pas une inférence matérielle réussie. Le rapport sépare aussi la version/information de compilation de son propre outil.
- **Livraison** : le manifeste fourni explicitement et le tag de release immuable décrivent ce qui a été publié. Ils ne sont pas déduits d’un dossier installé. La source du tag, les statuts des workflows et les SHA des assets sont conservés dans les reçus de livraison.
- **Installation** : le rapport lit la version/manifeste locaux et calcule les SHA des vraies bibliothèques sur disque. `matches_compiled_metadata` indique si le fichier correspond à la déclaration de compilation, ou reste inconnu si elle manque. Une bibliothèque remplacée est détectée même si `version.txt` garde l’ancienne valeur.

Les trois états peuvent être différents. Un champ absent reste inconnu ; les hashes sur disque ne prétendent pas identifier une bibliothèque déjà chargée dans un processus. L’export de référence IPC existant complète ce rapport avec les chemins/configurations réellement observés, ses limites restant explicites.

## Historiques et qualification

Un rapport daté et son commit de référence décrivent cet état passé. Les rapports des lots dans `docs/qualification/` conservent sources, conditions, mesures et limites de leur propre lot ; ils ne décrivent pas automatiquement l’installation courante. Les points courants de REPRISE / TODO / QUALIFICATION et Jira désignent les dernières livraisons vérifiées. Ne pas assimiler code compilé, paquet publié, fichier installé et calcul réellement observé.

Les contrôles de ce changement portent sur les notices et la traçabilité des fichiers. Aucun shader, modèle, réglage de rendu ou algorithme d’inférence n’est modifié ; aucun gain FPS n’est revendiqué.
