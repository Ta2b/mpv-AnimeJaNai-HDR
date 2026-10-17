# Guide de travail du dépôt

Lire d’abord [AGENTS.md](AGENTS.md) et [l’état courant](docs/ETAT-COURANT.md). Ils portent les instructions actives, la livraison vérifiée, les branches non livrées et les priorités. Ce fichier décrit l’architecture et les conventions ; les anciens checkpoints sont dans [les archives](docs/ARCHIVES.md).

## Où intervenir

| Zone | Responsabilité |
|---|---|
| `BuildMpvUpscale2xAnimeJaNai/` | Assembleur .NET : versions, téléchargements, composants, manifests et distribution par plateforme. |
| `BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/` | Overlay livré : configuration mpv/AnimeJaNai, scripts Lua, modèles et ressources. |
| `AnimeJaNaiUpdater/` | Mise à jour du lecteur et des composants ; la préservation des données utilisateur est un contrat à vérifier. |
| `native/`, `installer/`, `.github/` | Backends/bridges présents dans ce dépôt, adaptations natives, assemblage et publication. Lire les sources de la plateforme concernée. |
| Dépôts composants | Le fork mpv porte le filtre ; le backend NVIDIA et le Manager ont leurs propres sources et pins. Ne pas déduire leur version des seuls fichiers du dépôt d’assemblage. |
| `docs/qualification/`, `docs/jira/` | Preuves datées, reçus de livraison et liens vers les tickets existants. Les exports ne sont pas un état Jira en temps réel. |

La lecture native relie mpv, le filtre, le backend et les modèles. Le Manager écrit les profils ; les scripts/lanceurs choisissent et préparent les composants. L’ABI, les formats de pixels, les identités des sources, les chemins et les durées de vie des buffers traversent ces frontières. Une préparation vidéo externe et un moteur de lecture temps réel sont deux intégrations distinctes.

## Conventions durables

- Vérifier le checkout, les modifications locales et les pins avant de modifier le code. La source livrée peut être dans un worktree isolé ; ne pas écraser les profils, caches, SDK, modèles ou fichiers utilisateur.
- Tracer séparément version du lecteur, version du Manager, bibliothèque réellement chargée, modèles et paramètres effectifs. Un manifeste récent ne prouve pas que le processus utilise le nouveau moteur.
- Coordonner filtre et moteur lorsqu’un contrat ABI change. Les interfaces de surface et de soumission doivent préciser format, propriétaire, synchronisation et libération.
- Préserver le sens des profils et leurs IDs, l’ordre des étages et les paramètres inactifs. Une migration doit annoncer les changements de résultat ; ne pas convertir silencieusement une option inconnue en Fast.
- Les noms de modèles sont référencés dans les profils et certains presets natifs. Vérifier tous leurs consommateurs avant de renommer ou retirer un modèle.
- Garder les règles communes dans un contrat partagé et les différences de plateforme dans des capacités explicites. Un backend disponible ne rend pas tous les modèles, formats HDR ou étages exécutables.
- Séparer les réglages spatiaux, la politique temporelle et la conversion couleur. Voir [Quality/Fast](docs/CHANTIER-QUALITY-FAST.md), [étages](docs/INTERPOLATION-STAGES.md), [couleur](docs/CONTRAT-COULEUR-PROFONDEUR.md) et [précision](docs/CONTRAT-PRECISION-MOTEURS.md).

## Validation et livraison

Les essais sont autorisés. Pour une modification moteur/flux, choisir le contrôle court nécessaire au fonctionnement, au bénéfice et à la qualité, avec comparaison sur les mêmes entrées. Ne pas répéter une preuve concluante. Pour les autres modifications, appliquer des contrôles adaptés sans benchmark vidéo automatique. Le [protocole](docs/PROTOCOLE-VALIDATION-FEATURES.md) fait foi ; les anciennes interdictions de tests sont périmées.

La compilation, la publication, l’installation, l’exécution et la qualification matérielle sont des étapes distinctes. Conserver la référence Quality ; une approximation Fast doit être explicite. Écrire les résultats et limites dans le ticket concerné avant sa clôture complète.

Lancer les builds sans attente active, poursuivre le travail indépendant puis consulter leur résultat en fin de tâche. Ne pas annoncer une release ou une plateforme validée à partir d’un lancement de workflow.

Procédures : [développement](docs/DEVELOPMENT.md), [release](docs/RELEASE.md), [Linux](docs/LINUX.md). Avant d’exécuter une commande historique, vérifier le script actuel, les pins et les effets sur les fichiers existants. Les fichiers de version et références immuables doivent désigner des composants compatibles ; ne pas fabriquer une référence à partir d’un ancien numéro de release.

L’audit et ses limites sont dans [AUDIT-GLOBAL-2026-10-17.md](docs/AUDIT-GLOBAL-2026-10-17.md). Une recommandation de l’audit n’est pas une correction déjà livrée.
