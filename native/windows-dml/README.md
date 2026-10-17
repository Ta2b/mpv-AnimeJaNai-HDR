# Windows DirectML — préparations RIFE exactes (AH-344)

Le cache partage les conversions des deux images sources et la décision de coupe
entre les instants d’une même paire. Le réseau RGB complet reste exécuté à chaque
instant, avec le modèle, le timestep, les conversions et le seuil de coupe
existants. À ×4, les préparations et lectures SCD passent de 3 à 1 ; les trois
prédictions et leurs attentes de fin restent présentes. Ce comptage vient du
code. Aucun gain de FPS ni résultat GPU Windows n’est annoncé comme mesuré.

Le backend conserve une seule paire explicitement annoncée, avec identifiants
non nuls, vues complètes et références COM. Le filtre retient les `mp_image`
pendant la boucle : ces références protègent les cases du pool, contrairement à
un simple `AddRef` sur la texture. Nouvelle paire, seek, configuration, modèle,
échec ou alias avec la tranche source invalident la réutilisation. Les anciens
filtres restent compatibles, sans cache. `AJI_RIFE_PAIR_CACHE=0` désactive le
cache pour une éventuelle ablation. La branche MIGraphX garde son chemin propre.

## Livrer les deux exécutables

Modifier uniquement `aji_dml.dll` ne suffit pas : les anciens `mpv.exe` et
`libmpv-2.dll` Windows n’appellent pas `aji_rife_begin_pair`. Le producteur
`.github/workflows/build-windows-mpv.yml` compile les deux avec le même patch,
sans avoir besoin d’écrire dans les dépôts tiers.

Sources verrouillées :

| Composant | Commit |
|---|---|
| mpv | `19c0fcf89595e6ab33908299207c555b67e81558` |
| pilote winbuild | `597bab33931cbd2ec29abe9d44a29e6363da7499` |
| recette CMake | `1f8d2e76255abc48f0456d9be99b4cab9c6566e6` |
| libass | `896614fa263f9f64944f7b8650ff6806d5328c4d` |
| libplacebo | `0d043c7f6f79cd3687c023454bdacbe615e4d96f` |

La recette conserve les corrections Windows du pilote, notamment présentation
Vulkan et verrouillage RTX HDR. Le patch ANGLE est déjà présent dans cette
recette ; l’ancien rebase du patch Vulkan n’est plus utilisé par sa cible.
Les autres dépendances et l’image de compilation suivent cette recette : ceci
n’est pas une affirmation de reproductibilité binaire bit pour bit.

1. Introduire le workflow et ses sources dans PLAYER sans changer la release
   active ni créer de pin prématuré. Déclencher **Build paired Windows mpv** sur
   le commit producteur choisi (`gh workflow run build-windows-mpv.yml --ref …`).
   Le workflow doit être disponible sur la branche par défaut pour le dispatch.
2. Poursuivre les autres tâches pendant le build. À sa réussite, le tag
   `windows-mpv-<SHA PLAYER complet>` contient `mpv-windows-x64.7z` et sa
   provenance. Un retry ne remplace pas un producteur déjà publié.
3. Écrire ce SHA dans `windows-mpv-source-ref.txt` du lot de livraison et le
   committer avec le pin du backend contenant AH-344. Ne pas épingler une
   compilation inachevée. Le workflow de release stage le bundle ; l’assembleur
   vérifie source, patch, postimage du filtre et SHA-256 des trois binaires.
4. Publier le lot habituel. Le manifeste change `deps.mpvfork` pour forcer
   l’installation cohérente des nouveaux exécutables. Conserver le ticket en
   cours tant que cette livraison n’a pas été constatée.

Un pin présent sans bundle, une provenance manquante ou un binaire différent
fait échouer l’assemblage. Sans fichier de pin, l’ancien chemin de livraison
reste utilisable pour la release précédente. Le contenu de `MPV_WINDOWS_LOCAL`
est validé par le même contrat ; ce réglage sert à la construction du package,
pas à l’utilisateur du lecteur.

## Contrôles déjà réalisés en développement

- Fixture CPU utilisant la vraie structure de cache : identifiants absents,
  désactivation, les 12 champs de chaque vue, nouvelle paire, coupe, erreur,
  reset ; fixture complémentaire alias texture/tranche.
- Patch appliqué et postimage vérifiée sur le vrai commit mpv ci-dessus.
- Graphe CMake minimal exécuté : patch avant configure, provenance copiée dans
  les deux répertoires avant leur renommage.
- Préparation de la vraie recette figée ; collecte de deux archives factices PE
  x64 ; contrat assembleur avec bundle valide, pin sans staging et binaire
  modifié ; compilation de l’assembleur : zéro avertissement, zéro erreur.
- Aucun essai DirectML/Windows local. La compilation Windows et la publication
  doivent être enregistrées par leurs reçus CI ; les fixtures ne les remplacent
  pas. Un essai court cache off/on est utile seulement si un doute réel subsiste
  sur cette plateforme.
