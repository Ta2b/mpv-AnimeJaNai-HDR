# Export de référence observée — AH-11 / REF-01

Disponible à partir de 3.8.0.33. À la demande, le lecteur exporte un JSON qui rassemble les propriétés mpv observées, les paramètres réels du filtre, le fichier de configuration pointé par ce filtre, le runtime et les empreintes SHA-256 des fichiers des répertoires de modèles/exports. Aucun preset ne sert à deviner ces informations.

Dans la console mpv :

```text
script-message animejanai-export-reference
```

Ou ajouter dans votre `input.conf` la touche de votre choix :

```text
Ctrl+Shift+r script-binding animejanai_reference/export-reference
```

Le rapport est créé dans `animejanai/diagnostics/reference-DATE-PID-N.json` de vos données utilisateur. Il contient des chemins de média et de fichiers locaux. Vous pouvez le lire avant de le partager. Il n’est pas transmis automatiquement. Aucun raccourci existant n’est remplacé.

La CLI fonctionne aussi :

```sh
./AnimeJaNaiPlatform --export-reference --mpv-ipc /chemin/du/socket/mpv.sock --output reference.json
```

Sous Windows, l’endpoint de la configuration livrée est `mpvpipe` ; sous macOS, l’exécutable se trouve dans `mpv AnimeJaNai.app/Contents/Resources`. `ANIMEJANAI_IPC_PATH` peut fournir l’endpoint. `--root` désigne le dossier du programme pour identifier sa version/son manifest. Un rapport existant n’est jamais écrasé. Sans vidéo chargée ou sans IPC accessible, la commande échoue au lieu d’inventer une référence.

L’export ne change aucun réglage et ne met pas la vidéo en pause. Pour une mesure de performance séparée, terminer l’export avant de mesurer : il lit les modèles et leurs caches sur disque et consomme des ressources pendant cette lecture. Aucun coût périodique n’est ajouté à la lecture normale.

## Lire les limites du rapport

`qualification: partial` est volontaire. `observed_properties` décrit ce que mpv renvoie, `unavailable_properties` garde les erreurs, et `artifacts` décrit les octets sur disque. Les répertoires de modèles incluent leurs fichiers de poids externes et leurs exports : il s’agit d’un **inventaire**, pas d’une preuve que tous ces fichiers ont été exécutés. Un modèle remplacé après son chargement peut différer des poids encore en mémoire. Le chemin média est conservé, sans lire entièrement une vidéo longue pour l’empreinter.

`consistent_observed_state` compare l’état de chaîne avant/après l’export et les métadonnées des fichiers lus. Ce contrôle n’est pas une capture atomique : un changement aller-retour peut lui échapper. Les stats sont conservées comme échantillon dont la fraîcheur n’est pas prouvée. La précision par opérateur, le placement effectif et les dimensions de chaque étage requièrent encore la télémétrie des moteurs. Les valeurs configurées (ensemble, précision, coupe, ordre, facteur) restent dans le texte de configuration capturé, sans être confondues avec un constat d’exécution. Ne pas clore REF-01 sur ce seul incrément.
