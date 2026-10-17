# Lot 08 — identités de sources ABI 1 (AH-33 / CAC-06)

Base player `212c286` / 3.8.0.38. AH-33 réellement In Progress avant le travail. Sources dans `lot-08-source-ids-20261015`, backend spécialisé/pin et modèles inchangés.

## Contrat et changement

Extension facultative `aji_vk_source_ids(context, generation, previous, current)` : symboles négociés par dlsym/GetProcAddress, ABI 1 conservée. Les jetons non nuls décrivent des **octets RGB24 utiles immuables**, sans identité fondée sur l’adresse. Un jeton est consommé par le prochain process seulement. Sans jeton/symbole, la comparaison des octets reste la référence. Le client doit renouveler la génération à tout changement de stream, couleur/conversion, modèle ou état temporel ; l’engine inclut dimensions et stride dans sa vue.

Le bridge conserve un numéro de source monotone, le transmet dans chaque job asynchrone avec son précédent et une génération, avancée au reset/seek, changement de format/couleur et wrap. Le moteur refuse une génération ancienne et une régression du compteur ; l’époque recyclée reste refusée jusqu’à une génération supérieure. Ces refus retombent sur les octets, sans supprimer de sortie ni changer de PTS.

Les caches de sources ORT/Core ML/Metal/MIGraphX et NCNN/Vulkan reconnaissent ces identités avant leur comparaison de pixels. Les résultats dérivés et les décisions RIFE restent les mêmes. NCNN avec similarité explicitement demandée conserve son comportement et n’emploie pas ce raccourci. Les futurs frames sans IDs (lookahead) conservent aussi la comparaison. Télémétrie : hits ID, comparaisons de sources et appels refusés. `AJI_FRAME_IDS=0` désactive l’extension dans le bridge pour diagnostic/ablation.

## Essais courts et décisions

- Contrat C++ : vues/dimensions/stride, génération, paire répétée, compteur régressé puis tentative de reprise de la même époque, génération supérieure, époque ancienne et absence d’ID : succès.
- Inférence réelle **ORT/CPU RIFE4.26/SPAN Quality**, mêmes inputs/config/poids, 128×72 : 9 interpolations + 5 cas ciblés (adresses recyclées/compteur régressé, époque refusée, nouvelle époque, stride changé, client sans ID). **14 sorties identiques** à la référence .37, 14 hits d’ID et 2 refus de compteur. Processus 0,2958 / 0,2668 s, mesures uniques sans gain FPS revendiqué.
- Même contrat **NCNN/Vulkan RTX4070Ti RIFE4.6/SPAN**, 64×64 : **14 sorties identiques**, 14 hits et 2 refus, 0,8924 / 0,8596 s. Modèles et cache GPU identiques ; candidat lié aux objets NCNN/RIFE épinglés déjà compilés.
- Bridge réel asynchrone, même binaire et input anime lossless 128×72, IDs **off/on** : **13 hashes de sortie et PTS identiques**, EOF atteint. Comparaisons de sources **32 -> 5**, hits ID 0 -> 18, aucun appel refusé. Réduction de travail établie, sans extrapolation FPS. Nouvelle bibliothèque avec ancien client contrôlée par le cas direct sans ID ; nouveau bridge avec ancienne bibliothèque sans symbole : chargement réussi et première sortie identique.
- Seek réel : référence neuve IDs off à 0,0417 s ; candidat IDs on après trois pas puis seek vers 0,0417. **Trois PNG 16 bits et PTS identiques** (0,041708 / 0,052135 / 0,062562), fermeture et sockets nettoyés. Processus 1,3227 / 1,2670 s ; pas de mesure de latence statistique. Présentation locale **OpenGL**, inférence **NCNN/Vulkan**. Diagnostic initial : renderer Vulkan absent de ce build mpv local, refus d’option avant inférence ; essai corrigé conservé seul.
- Builds/links natifs et bridge C réussis, actionlint/bashes/diff vérifiés. Les contrôles d’images concluants n’ont pas été répétés.

Artefacts : `artifacts/performance/lots-20261015/lot-08/` : contrats, commandes/hashes des bibliothèques et entrées, NPZ, framehash, compteurs, PNG16, logs et manifeste. Pilotes sous `tests/observability/source_identity_*`.

Conserver : contrat d’identité utile et 32 -> 5 comparaisons réellement évitées, sans perte d’image sur ces cas. Pas de gain FPS établi. Le contrat exige des octets immuables pour un ID répété ; une mutation mensongère sous le même jeton ne peut être vérifiée sans relire ces octets. Le bridge fourni produit les jetons et générations, les anciens clients restent sur la comparaison de contenu.

## Portée restante

**AH-33 reste In Progress** : clients Windows ABI9 et leurs caches Fast/vues/état temporel rank-5 restent à auditer et intégrer. Cette extension ABI1 est disponible pour les clients Windows du moteur partagé, mais leur intégration n’est pas déclarée livrée. Apple/AMD/Intel : code commun compilé par les builds, pas de qualification matérielle locale. Ni HDR physique ni épisode prolongé certifié. Publication de cet incrément : **3.8.0.39**, assets à suivre. Les références, modèles, Quality et le backend utilisateur d’origine sont conservés.
