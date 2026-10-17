# Lot 07 — log atomique au configure CUDA (AH-22)

Base player `a0622c7` / 3.8.0.37. Suite du même ticket, toujours réellement In Progress. La partie native par sortie a été qualifiée et livrée dans le lot 06 ; cet incrément vise seulement l’écriture immédiate du log par le filtre CUDA au configure.

## Changement

Patch `native/linux-cuda/vf_animejanai-stats.patch`, appliqué par le build Linux après les patchs dessins et Quality/Fast. Le filtre utilise `mp_save_to_file`, l’utilitaire mpv existant : fichier exclusif unique dans le même répertoire, écriture/fermeture contrôlée, puis remplacement atomique. Un échec conserve l’ancien fichier et émet un diagnostic. Le helper amont laissait son temporaire après un rename échoué ; le patch le nettoie. Aucun calcul, modèle, réglage ni pin backend changé. Le manifeste Linux déclare `stats_atomic=1` et sa provenance identifie le nouveau patch.

## Essais courts

- `configure_snapshot_check.c` lié aux **vrais objets C mpv avant/après** du helper : la séquence exacte ancien fopen(w) révèle un fichier vide à un lecteur intervenant ; publication atomique conserve l’ancien fichier ouvert complet et rend le nouveau complet. Échec de rename volontaire : ancien état préservé dans les deux cas, temporaire résiduel **1 -> 0**. Allocateur/randomness de fixture, véritables opérations fichier/rename/unlink. Cas déterministes, aucune boucle de stress répétée.
- Build/link mpv local : seul le module du filtre et le helper sont substitués ; objets restants et dépendances identiques. La baseline locale a été reconstruite depuis les mêmes patchs de 3.8.0.37 avec la nouvelle écriture désactivée. L’ancien build local contenait moins de changements RIFE : il n’est pas utilisé comme baseline d’image.
- Lecteur réel, même clip anime lossless 128×72, mêmes config/modèle/plan TensorRT Quality, trtexec=/bin/false : NVDEC réellement actif, SPAN appliqué, **trois sorties et PTS strictement identiques** via framehash. Texte complet des logs de configuration identique à l’octet. Inode de stats : inchangé avant, remplacé après. Durées uniques 0,51450 / 0,51442 s : aucun gain FPS, utilité cohérence des lecteurs.
- Build .NET assembleur et bash -n : succès. Diagnostic de préparation : `--no-restore` sur le worktree neuf sans assets NuGet, corrigé par build normal ; baseline C déplacée manquait `refqueue.h`, chemin d’inclusion ajouté. Ces diagnostics ne sont pas des échecs du moteur et n’ont produit aucune comparaison retenue.

Commandes, objets, binaires, données, logs, hashes et rapports sous `artifacts/performance/lots-20261015/lot-07/`, manifeste local. Aucun essai concluant rejoué ; référence/candidat exécutés une fois chacun, builds adaptés en réponse aux erreurs de préparation.

## Décision

Conserver pour publication cohérente et nettoyage d’échec, sans gain FPS annoncé ni perte de pixels observée. Linux qualifié sur ce cas ; pas de HDR physique, de performance prolongée ou d’inférence Windows revendiquée. Le code de helper mpv a une implémentation Windows de rename remplaçant, mais **le mpv Windows précompilé actuellement épinglé n’a pas été reconstruit avec ce patch**. **AH-22 reste In Progress pour la livraison/qualification Windows**. Les autres lecteurs natifs et macOS bénéficient du lot 06 ; le log CUDA n’était déjà écrit qu’au configure, sans coût par sortie. Publication de cet incrément : 3.8.0.38, assets à suivre.
