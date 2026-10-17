# AH-361 — Quality garantie par le moteur chargé du pipeline CUDA

Source backend `9d2c717f756c632c9c2d0acc53479fd8690586cb`. Le pipeline exige désormais un contrat RIFE configuré version1 pour un maillon Quality, seul ou fusionné avec SPAN. Symbole absent ou provenant d'une autre image ELF : refus avant create/configure, avec chemin observé et demande de mise à jour, fichiers locaux conservés. Après configure, policy réelle, version/taille et flags de référence RGB sont vérifiés ; aucun raccourci Fast ne peut être présenté comme Quality. Le contrat est interrogé une fois par activation, jamais par image.

Le CABI optionnel ne modifie ni ABI9 ni Surface1. Il rapporte la policy du contexte configuré, la disponibilité des raccourcis motion/held et le chemin de l'image du symbole (`dladdr`). Une révision source est une déclaration de build facultative, distincte d'un hash des pages mappées. Ici elle reste `unknown` : Git est absent de l'image de build portable. Les sources et SHA du bundle restent vérifiés séparément. Même un fichier récent sur disque ne suffit pas à établir cette sémantique du module chargé.

Point important de la revue : `dlsym(handle)` peut trouver une fonction dans une dépendance du moteur. Le contrat doit appartenir à la même image que create/configure/process. Une fixture CPU charge deux vrais DSOs : moteur complet, puis ancien moteur dépendant du premier et empruntant son symbole. Le second est refusé. La même fonction de garde utilisée par le pipeline prouve le refus avant configure, le maintien Fast explicite sans contrat, les structures/policies/flags/chaînes/révisions invalides et les erreurs. Résultat PASS observé sur les sources committées ; pas de répétition pour générer un autre journal.

Contrôle natif ciblé Linux RTX4070Ti, plans720p existants, aucun build de modèle autorisé (`trtexec=/bin/false`) et **zéro image vidéo traitée**. [Reçu](native-receipt.json).

| Cas | Résultat |
| --- | --- |
| Ancien module .86, Quality RIFE seul | Refus explicite avant create/inférence, module existant conservé. |
| Module actuel, Quality×4 + SPAN fusionnés | Accepté ; diagnostic `effective=quality contract=v1 flags=1`, chemin du module attendu. |
| Module actuel, Fast×4 + SPAN fusionnés | Accepté ; `effective=fast contract=v1 flags=2` (motion prêt). |
| Ancien module, Fast explicite fusionné | Accepté ; `effective=unknown contract=unavailable`, module ancien effectivement observé. |
| CABI null/taille courte/version inconnue/contexte non configuré | Refus et buffer du client inchangé. |

Les modules sur disque restent identiques avant/après ce processus de contrôle privé. Aucun média/profil installé n'est lu en écriture. Le logger TensorRT du premier contexte reste vivant jusqu'à destruction des contextes suivants ; les avertissements de logger partagé sont connus et le contrôle s'est terminé normalement.

Aucun calcul pixel, poids, précision, seuil de coupe ou cache de source exact n'a changé. La section device `.nv_fatbin` TRT est **byte-identique** à .86 (SHA256 `23766330f0d82b1a69660abff608b3f0630ea9089f03be755eb4e06830d097cc`), tout comme le fatbin pipeline Area3:2 de .90. La qualification numérique antérieure est réutilisée : pas de replay des13images, pas de benchmark ni gainFPS revendiqué. Utilité : fidélité des libellés et refus d'une Quality non vérifiable.

Compilation TRT portable : GLIBC2.34 / GLIBCXX3.4.30 ; pipeline GLIBC2.38 / GLIBCXX3.4.30, sans RPATH local, TrueHDR conservé. Multi-SM compilé, seule RTX4070Ti exercée. Windows/dispatcher et les routes ABI9 historiques ne reçoivent pas cette protection par ce ticket ; AH330 reste ouvert pour ces routes et le résolveur/UI. Le backend Windows déclare explicitement cette requête non prise en charge.

Compatibilité : le fallback d'un ancien provider qualifié par AH354 reste une preuve historique .86. À partir de ce nouveau pipeline, Quality exige le contrat version1 même si le provider possède Surface1 ; une ancienne bibliothèque doit être mise à jour et le lecteur redémarré. Fast explicite reste utilisable sans ce contrat et indique honnêtement l'absence de connaissance. Ne pas remplacer automatiquement Quality par Fast ni écraser un override.

Prochaine action : bundle couplé pipeline/TRT/alias, pins et release, puis extraire les modules concernés et vérifier leurs hashes avant Done. [Guide précis](../../reprise/20261017/AH-361.md).
