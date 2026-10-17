# Validation des features — essais courts et strict nécessaire

## Instruction actuelle

Précision utilisateur du **17 octobre 2026** : avancer vite sur tous les moteurs, OS et matériels. **Un test ou benchmark n’est plus obligatoire pour chaque optimisation** lorsque la revue du code permet d’établir clairement son effet et l’absence de changement de rendu. Un coût supprimé peut justifier une amélioration attendue sans inventer un gain FPS mesuré.

Adapter le contrôle au doute restant : compilation/revue pour une transformation simple, essai ciblé pour une nouvelle arithmétique, une invalidation délicate, une panne, un résultat ambigu ou une instabilité. Les exemples ci-dessous sont un réservoir de contrôles, pas une batterie à lancer. Ne pas répéter un essai concluant ; ne jamais attendre une compilation ou release avant une tâche indépendante.

Conserver Quality et distinguer **preuve de code / gain attendu / résultat mesuré / qualification matérielle absente**. Ne pas forcer la convergence des implémentations : les moteurs peuvent avoir des formats, précisions, kernels et besoins de mémoire différents. Harmoniser l’expérience et les comportements injustifiés sans pénaliser ces besoins. Les modèles, médias, profils et SDK utilisateur restent préservés.

Pour documentation/UI/packaging sans changement vidéo : contrôles simples adaptés, aucun benchmark vidéo. Une compilation ne constitue pas une mesure de performance ni une preuve de rendu matériel.

## Boucle minimale par changement

1. **Définir la question.** Quel coût disparaît, quel comportement change,
   quelle panne est corrigée ? Choisir une mesure et un cas représentatif
   avant de coder. Pour une option de diagnostic ou un prérequis, établir son
   utilité fonctionnelle et son coût plutôt que promettre des FPS.
2. **Conserver une référence.** SHA, modèle/poids, paramètres, rendu, GPU,
   runtime et artefact initial. Préserver l'installation et les modifications
   utilisateur. Préférer un switch off/on dans le même binaire lorsque pertinent.
3. **Implémenter puis compiler.** Préparer les modèles/artefacts nécessaires
   séparément ; journaliser cette durée sans la confondre avec le temps mesuré.
4. **Si nécessaire, exécuter une comparaison ciblée et courte.** Référence et candidat sur
   mêmes entrées, configuration et conditions GPU ; exécution séquentielle.
   Réutiliser une référence valable déjà acquise. Ne pas répéter un essai
   concluant pour atteindre un quota de répétitions ou de couverture.
5. **Contrôler les points encore incertains.** Réutiliser les sorties de
   cette comparaison quand possible ; compléter seulement par quelques cas
   courts nécessaires au changement, sans relancer toute la matrice des moteurs.
6. **Décider et consigner.** Conserver, corriger, abandonner ou laisser
   expérimental/non concluant. Mettre les résultats et limites dans Jira et
   le relais ; un succès de compilation ne justifie pas un statut « qualifié ».

Un essai concluant peut suffire s'il répond aux questions du changement. Ajouter
des essais seulement si une question importante reste ouverte, si une panne
apparaît ou si le résultat est réellement instable d'un passage à l'autre.
Ne pas lancer une batterie exhaustive ni réactiver globalement les suites CI
par défaut. La durée et l'étendue doivent être justifiées par ce qui reste à établir.

## Choisir les contrôles utiles

| Changement | Contrôle court adapté |
|---|---|
| Cache exact, buffers, ordonnanceur | Même sortie pour les mêmes entrées ; compteurs de calcul/copie, ordre et PTS ; un seek ou une invalidation ciblée si le changement les affecte. |
| Kernel, fusion, layout ou tactique | Erreur sur tenseurs/flow/coordonnées si accessibles et pixels ; bords, précision et un mouvement représentatif ; temps complet en plus du temps du kernel. |
| Nouveau moteur ou raccord GPU | Device effectif, repli CPU, couleur et copies ; même modèle/poids ; courte chaîne avec rendu quand le matériel est disponible. |
| Fast ou autre algorithme | Comparaison visuelle/temporelle sur contours, mouvement/occlusion adaptés au changement ; nommer toute approximation et préserver Quality. |
| Couleur/HDR | Niveaux, gradients, gamut/transfert et état temporel concernés ; un résultat SDR ne certifie pas la sortie HDR physique. |
| Manager, configuration ou packaging | Lecture/sauvegarde/migration ou ouverture ciblée ; présence et version des artefacts ; coût ajouté si pertinent. |

Pour une transformation sans changement arithmétique, viser la même sortie
sur le même backend. Pour une transformation numérique, définir une tolérance
justifiée avant comparaison ; ne pas élargir après coup les seuils pour faire
passer le candidat. PSNR/SSIM ou erreur moyenne seuls ne prouvent pas l'absence
de régression temporelle. En Quality, une régression observée doit être corrigée
ou l'optimisation retirée de ce mode. L'acceptabilité d'une variante Fast doit
rester explicite, pas être présentée comme une équivalence Quality.

## Interpréter un essai court

Mesurer le poste visé et, lorsque le raccord est concerné, la chaîne complète :
temps par paire/source, copies, synchronisations, mémoire, sorties prévues et
présentées, abandons et répétitions. Séparer compilation, démarrage et régime
chaud. Rapporter le nombre d'échantillons ; ne pas donner à un P99 sur quelques
images ou à un écart dans le bruit une portée qu'il n'a pas.

Une mesure supérieure sur quelques images ne démontre pas la stabilité sur
un épisode, la chauffe prolongée ou la couverture de tout le parc. Ces limites
doivent être écrites ; elles n'imposent pas de campagne longue. Si les résultats
sont insuffisants, bruités ou variables, cibler seulement les essais nécessaires
pour trancher, ou laisser une qualification partielle si le matériel manque.

## Mesurer une performance (depuis le lot B, 18 octobre 2026)

- **Temps GPU réel** : `AJI_PIPELINE_TIMING=1` (ou `AJI_PIPELINE_TRACE=1`) fait écrire au pipeline, pour chaque job, `aji_pipeline_timing: ticket=… total_gpu_ms=… <étage>=…` à partir d'événements CUDA sur son stream : attentes et bulles comprises, aucune synchronisation ajoutée. Les `ms=` de la trace sont du temps CPU de soumission et ne mesurent plus rien en stream partagé.
- **Comparer des variantes** : `tools/bench/pipeline_bench.py --spec <sonde.json> --variant nom=VAR=val,... --runs N --output reçu.json` alterne les variantes en tourniquet, ignore les paires de chauffe, donne min et médiane (GPU et mur) et refuse ou signale un GPU occupé par d'autres processus (`--idle-threshold`, `--idle-patience`). Un gain se lit sur le **min** de plusieurs séries alternées, jamais sur une exécution.
- **Plans TensorRT manquants** : la sonde courte tue le constructeur (`trtexec` meurt avec son parent) ; lancer d'abord `tests/inference/pipeline_build_wait.py <sonde.json>` autant de fois qu'il y a de plans à construire (un par cycle), puis mesurer.
- **GPU partagé** : la machine de référence sert aussi au bureau et au jeu ; vérifier `nvidia-smi` (utilisation et mémoire) avant toute série. Un plan optionnel qui ne trouve pas sa mémoire est ignoré proprement (repli B1), mais ses chiffres n'ont alors aucun sens.
- **Équivalence** : chaque variante qui change un programme TensorRT passe `tests/inference/quality_equivalence.py` (règle v2 : pixels, comptes, chronologie, drapeaux, coupures) contre la référence FP32 sans TF32.

## Compte rendu Jira obligatoire

Dans le ticket existant, enregistrer : référence/candidat et SHA, machine,
modèle/paramètres, commandes et durées réelles de chaque essai, nombre de sorties,
mesure avant/après, qualité observée, cas fonctionnel contrôlé, logs/artefacts,
limites et décision. Distinguer « codé », « compilé », « testé sur cette cible »
et « qualifié ». Si une validation visuelle humaine ou un appareil manque,
le dire ; aucune conclusion universelle ni faux succès.

La prochaine session doit lire le ticket AH et ses dépendances avec le plugin
Atlassian ; le journal et l'index locaux fournissent les clés si la connexion
doit être rétablie. Ne pas créer de ticket en doublon pour enregistrer un essai.
