# AH-363 — identité du lecteur Linux assemblé

Défaut confirmé le17octobre2026 lors de la vérification .93 : lecteurs complets modifiés et scripts bien livrés, mais `deps.mpvfork` manuel identique à .92. Le vrai `IsOverlaySufficientAsync` pouvait donc sélectionner l’overlay de dossier Linux, qui exclut le lecteur natif. Une mise à jour AppImage remplace déjà tout le fichier et ne prend pas cette décision d’overlay.

## Correction et utilité

`LinuxMpvIdentity.Capture` exige mpv et libmpv.so.2, trie les noms des fichiers du dossier natif, calcule un SHA256 par fichier et un hash agrégé avec un préfixe de version/noms/longueurs cadrés. Le manifeste prend cette identité du bundle assemblé au lieu d’une liste manuelle de capacités. Pas de timestamp, chemin de checkout ou numéro de release dans le hash. Chaque dépendance native et build-info participent ; scripts/profils restent en dehors.

L’assembleur copie aussi `build-info.txt` lorsqu’il est fourni par le build natif, dans `mpv/build-info.txt`. L’identité concerne le bundle natif au stade d’assemblage du dossier/tar ; AppImage peut ensuite réécrire des RPATH en fabriquant ses copies dans usr, ce n’est pas un hash des pages chargées. Les marqueurs sont désormais livrés et la provenance des fichiers reste distincte du contrat effectif GET_META.

Pour une installation en dossier, ancien lecteur ou contenu natif différent → package complet contenant le nouveau lecteur. Même bundle et nouvelle release de scripts → overlay conservé. Les composants gérés par packs gardent leur traitement séparé. La déclaration de capacité Vulkan mentionne maintenant le segment SPAN résident. Aucun changement de moteur, de calcul vidéo ou de règles de préservation.

## Qualification nécessaire conclue

[Contrôle CPU](check.txt), sur le vrai calcul d’identité et la méthode de décision de production copiée sans réécriture de sa logique :

- contenu identique sous autre dossier, ordre de création inversé et autres mtimes → identité identique ;
- modification indépendante de mpv, libmpv, autre bibliothèque ou build-info → identité différente ; lecteur requis absent → refus ;
- manifeste ancien/identifiant natif différent → overlay refusé ; même bundle ou seul pack modèles changé → overlay autorisé.

Aucun téléchargement ni invocation de l’updater réel, aucun fichier d’installation utilisateur modifié. Assembleur compilé .NET10 Release : zéro erreur et zéro avertissement. Tests existants de copie/préservation réutilisés puisque leur code ne change pas ; aucun contrôle vidéo requis.

## Livraison

Prévue .95. Vérifier trois CI/tag, manifeste Linux avec nouvelle identité, build-info effectivement dans le paquet et recalcul de l’identité sur le dossier natif du tar publié. Vérifier les nouveaux lecteurs et dispatcher déjà contrôlés en .93 ; le [reçu .93](../../jira/release-20261017-3.8.0.93.json) valide les payloads frais, sans clore AH362 tant que ce couplage d’upgrade reste ouvert. AH335 (manifeste local invalide) et les autres routes d’AH330 restent distincts.
