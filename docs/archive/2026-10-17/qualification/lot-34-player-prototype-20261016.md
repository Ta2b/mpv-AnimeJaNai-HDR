# Lot 34 — Choix du raccord mpv par prototype

[AH-38](https://tatoub.atlassian.net/browse/AH-38), PLY-03. Référence player3.8.0.65 `ba85db40e6b6869803c0537ad152b5d746633f0b`, mpv `19c0fcf89595e6ab33908299207c555b67e81558`. Le critère est de choisir un raccord permettant une avance sans frontière CPU supplémentaire. La production complète et ses politiques restent dans AH-36/37/39/40/41/42.

## Choix et intégration

**Conserver le même processus.** Une enveloppe du filtre animejanai relie le backend inchangé, un tap observant ses sorties, une FIFO native `mp_async_queue` et son lecteur. `prefetch=N`, option CLI expérimentale désactivée par défaut (`0`), active une réserve de1à64images ; `resume_reading` demande des sources futures sans demandes individuelles du consommateur. Les références `mp_frame`/`mp_image` CUDA sont transférées telles quelles ; aucun téléchargement, sérialisation, import de texture ou copie de pixels n'est ajouté à la réserve.

Source mpv : `player/playloop.c` continue à exécuter le graphe de filtres pendant la pause ; `player/video.c` arrête alors la consommation pour présentation. Le filtre initial dépendait des demandes aval. `filters/f_async_queue.c/.h` fournit déjà demande autonome, quotas, transfert de références et reset. L'option off observe les seules images demandées, sans demande autonome ; elle constitue l'ablation dans le même binaire.

Les surfaces CUDA/contextes/événements de l'ABI sont locaux au processus. Un producteur externe demanderait un contrat d'IPC/import/lifetime supplémentaire, sans valeur démontrée sur ce problème. Aucun prototype externe ni gain comparatif IPC n'est revendiqué. Un worker GPU utilisant Submit/Complete dans le même processus reste compatible avec ce choix ; le prototype actuel garde les attentes du filtre sur le thread du graphe. La réactivité UI pendant une longue inférence n'est donc pas démontrée.

Annulation : le reset de mpv vide pins/enfants, puis l'enveloppe purge les références de réserve et incrémente son epoch. La reprise de production est différée au prochain passage du graphe après le reset complet. Le backend conserve son drainage existant ; une image émise par `pop_ring` a déjà passé `aji_wait`. Détruire l'enveloppe purge la réserve. Un changement dynamique de slot est refusé lorsque la réserve est active, en attendant la politique média/génération AH-42 ; le chemin off transmet les commandes existantes.

Métadonnées `vf-metadata/aji` : capacité, images prêtes, compteur produit, epoch et format natif. `get_samples` exclut les signaux EOF dans le mpv épinglé. Le format est conservé sous forme d'identifiant entier, jamais comme adresse d'un nom temporaire. L'installateur applique le patch après drawings/Quality-Fast/stats ; l'identité du pack mpv et le cache CI incluent ce changement.

## Essais strictement ciblés

RTX4070Ti12Go, pilote615.78.08, Linux, FFmpeg système9.x/TensorRT du paquet. Entrée H.264/NV12 BT709 limité128×72,12images/24fps ; sortie SPAN256×144. Même plan et configuration Quality, RIFE désactivé : le changement porte sur le raccord, pas sur l'arithmétique du modèle. Modèle `2x_AnimeJaNai_HD_V3.1Sharp1_Performance_SPANF3_b5f48_unshuffle_fp16`, SHA256 `72246eded3aab52f8d1a71613c0a1d900734b358d1820b62eb36f1ed376e1cf4`, plan `9d99b61a93dd78ad4faa477fb64225f85096f8dcc3af95a79e747bdb31c8bf04`. Backend .65 `7e9c87137e77046e5c521e635634bfdef751a277`.

- **Avance en pause**, ablation0/3 : pause=true et position0 inchangées ; réserve0→3images CUDA réellement terminées, produit2→5 au snapshot acquis. Le lecteur a aussi sa propre anticipation : le compteur total produit peut varier d'une image selon l'instant du snapshot, sans changer la capacité de la réserve. NVDEC/TensorRT effectifs, sortie256×144. Les journaux bornent le démarrage/qualification à moins d'une seconde par processus ; aucun gain FPS mesuré ni promis.
- **Consommation/EOF** :12sorties, PTS et chaque pixel NV12 exacts off/on ; EOF drainé avec exit0. SHA256 des663552octets `9c8453e811384d9765657ed765fda9bd2f9f5ce0aa9aa88bfd025d9cc88a1c1d`. Capture+contrôle0.647s/0.639s, dominés par le démarrage et les outils : **non concluant en FPS**, sans prolongation. Le téléchargement nécessaire à la capture/null est après la réserve, extérieur à son transport CUDA.
- **Seek avec réserve pleine** : seek exact0.3s en pause, epoch0→1, image cible différente de l'initiale et exacte au témoin off ; PNG cible SHA256 `8bdf4589e8da4054512266e8632b1abd3ea6cac0d8f10f11970f90a6d640ca7b`. Pause utilisateur conservée. La réserve se remplit avec les nouvelles images ; près d'EOF elle peut contenir moins que sa capacité. Commande slot refusée, nettoyage sans blocage.

Trois diagnostics invalides/exclus : sélecteur `cuda` sélectionnant CUVID avec échec de création de frames sur FFmpeg local (corrigé en `nvdec`) ; nom temporaire du format conservé trop longtemps (corrigé avant ablation concluante) ; attente de trois images après seek près d'EOF alors que certaines sont déjà consommées ou absentes (assertion corrigée, référence off déjà acquise réutilisée, seul candidat seek repris). Aucun essai concluant répété pour atteindre un quota.

Build local Release réussi ; chaîne de patchs recréant exactement le filtre compilé vérifiée. Binaire local SHA256 `42472584cd49ea5d7b4d7cbc78ce2cf62a5ab3b64a6f441c409b77ac15dc845d`. Wayland désactivé pour ce contrôle headless, Vulkan local indisponible ; la CI Linux conserve leur configuration normale. Strata localhost8080 indisponible : aucune délégation aboutie revendiquée.

## Décision et limites

Conserver ce prototype opt-in : utilité d'avance réelle établie, ordre/pixels préservés sur ce cas. Le choix architectural de AH-38 est établi ; ce résultat ne termine pas les tickets de production et ne justifie aucune activation par défaut. Les budgets sources/jobs/résultats, mémoire VRAM/RAM, état média A/V/sous-titres, worker dédié, changements de slot/config et autres API/OS restent à implémenter et qualifier dans leurs tickets. Aucun nouvel algorithme ni changement Quality/Fast.

Preuves : `artifacts/performance/lots-20261016/lot-34/`, `paused-{0,3}.json`, `sequence-summary.json`, `sequence-{0,3}.json`, `seek-{0,3}-result.json`, images/captures, journaux et builds. [Client ciblé](../../tests/player/prefetch_prototype_check.py) : `python3 tests/player/prefetch_prototype_check.py SPEC.json paused|sequence|seek` ; spec `mpv,input,conf,models,lib,out`, runtime CUDA/TensorRT dans LD_LIBRARY_PATH. Receipts concluants réutilisés ; cas12images128×72→256×144.

**3.8.0.66 publiée**, source `ac407bca07771db0bf9da0b4e37ce245fea895cd` ; trois workflows success,15assets uploaded, archive/digest et prototype dans le mpv livré vérifiés. AH-38 **Done**, clôture10122.
