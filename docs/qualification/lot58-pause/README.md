# Lot58 et Quality — checkpoint de pause du17octobre2026

Pause explicitement demandée par l’utilisateur après la fin des agents. Aucun ticket partiel marqué Done, aucune release85 publiée. La dernière release vérifiée reste **3.8.0.84**.

## Livraison préparée, pas encore dans une release

- PLAYER producteur Windows : `3ff8782d70f70dc0292c4365e0bf59535192b9bf` sur `hdr-3.8`, source isolée `/home/ta2b/.animejanai-tools/work/lot-58-engines-20261017`. Build assembleur local succès (0erreur/avertissement), collecte des archives avec sous-dossiers corrigée et fixture ciblée concluante.
- Backend AH344/345/346 intégré : `61ba62753d0bbaa85734b19e7992be946ba92434`. Correctif des exports Windows : `fac3b8afd5cffdb9f449b28d533791fb1d50cba9`, publié sur `perf-specialized-lot58-engines-20261017`. Premier build61ba échoué MSVC C2375; les12déclarations d’API ont été corrigées, fixture COFF et clients dynamiques valides. NVIDIA du nouveau run39006960500 réussi ; AMD était encore en cours lors du relevé.
- Bundle préparé : `5433c70` sur `binaries/lot-58-engines-20261017`. Sources Linux61ba par module (TRT/alias e5216ed…, pipeline4e6574d…), Windowsfac3 par module (dispatcher/TRT/DML), MIGraphXWindows préservé652fbc6. Aucun pin PLAYER vers ce bundle tant que le producteur mpvWindows apparié n’est pas vérifié.
- Producteur mpvWindows : run `39006425781`, SHA3ff8782, encore au build lors du checkpoint. Ne pas le relancer en double. À la reprise, relever une fois son statut ; succès attendu avant `windows-mpv-source-ref.txt`. Tag producteur `windows-mpv-3ff8782d70f70dc0292c4365e0bf59535192b9bf`. Vérifier mpv.exe/mpv.com/libmpv-2.dll et provenance avant livraison AH344.
- Windows modules téléchargés durablement dans `/home/ta2b/.animejanai-tools/work/lot-58-windows-built-20261017`. Binaires Linux candidats et preuves de réutilisation acquis ; aucun nouvel essai concluant répété.

## Diagnostic réel Quality×4

Processus utilisateur .84 observé en lecture seule et laissé enpause. Profils/bibliothèques mappées conformes .84 ; pas de vieux module chargé dans cette instance. Source NVDEC1080p, Area720 puis RIFEQuality4 puis Sharp1PerformanceSPAN2x puis TrueHDR1440. La cadence PTS≈95,69 n’est pas une mesure de débit enpause. Ancien currentanimejanai.log périméprofil1 : ne pas l’utiliser comme trace actuelle.

Un contrôle natif court reproduit le dépassement : deux paires chaudes59,31/55,81ms face au budget41,71ms/source23,976fps. Bloc RIFE+SPAN49,51/46,31ms ; HDR7,89/7,91ms ; Area0,88/0,79ms. Fusion active, une préparation de paire puis promotionB→A. Chiffres d’un cas court, pas mesure d’affichage ni stabilité prolongée. `quality-baseline-summary.json` conserve hashes/timeline/compteurs ; médias et captures détaillées restent privés dans `artifacts/performance/lots-20261017/quality-live-20261017/`.

## Candidats à qualifier à la reprise

- AH347 : pads d’entrée paresseux, commit `fc6b1f6e62840061481ca0f28cfaba882f522af7`, build portable Linux réussi, revue indépendante sans blocage. Source temporaire `/tmp/lot-59-rife-lazy-pads-20261017`; patch/reçu ici, binaires durables `/home/ta2b/.animejanai-tools/work/lot-59-engine-handoff-20261017/`. Pas livré. Économie brute44411,25Mio à1280×768, pas gainFPS mesuré.
- AH354 : burst Surface par bloc Quality+upscale, commit `b367479977202e971c3bdf803f24294967b2787e`, clone durable `/home/ta2b/.animejanai-tools/work/quality-pipeline-burst-20261017`, preuves et binaire `/home/ta2b/.animejanai-tools/work/quality-pipeline-burst-artifacts-20261017/`. Build TrueHDR réussi +15contrôles CPU. **Pas encore d’essai GPU ni gain établi.** Guide `AH-354/HANDOFF-AH354.md`, ablation `AJI_PIPELINE_QUALITY_BURST=0/1`. Cache maintenu : drain seulement erreurs/reset. Polling existant jusqu’à1ms peut rogner le gain.
- AH355 : commit `e523a5c77486441c8fb50975f83c935fda787a1d`, clone durable `/home/ta2b/.animejanai-tools/work/quality-rife-yuv-copy-20261017`, guide/patch sous `AH-355/`, binaires durables `/home/ta2b/.animejanai-tools/work/quality-rife-yuv-copy-artifacts-20261017/`. Build Linux portable réussi, alias SHAcae89d88…472d. Réduction middle→stage_in en réutilisant le buffer YUV interne stable ; RGB→YUV→RGB, crop/padding/quantification conservés. Ablation `AJI_RIFE_YUV_STAGING=0`. Revue indépendante demandée mais non achevée au moment de la pause ; aucun GPU/gainFPS ni livraison. Basefc6b1f6 contient347, ajouter fac3b8a pour Windows.
- AH73 : audit de l’encodeur indépendant de t terminé (`rife-quality-subgraph-audit.md`). Cache paire pourrait enlever9,10% des MACs Conv/ConvTranspose des3prédictions, coût15Mio ; aucun gaintemps mesuré, modèles intacts. Rafraîchir les étapes Jira avant implémentation. Cette piste n’est pas incluse dans les binaires candidats.

## Ordre exact à la reprise

1. Lire ETAT-COURANT et Jira AH329/344/345/346/347/354/355 ; vérifier statut/HEAD/remotes. Ne pas réimporter le backlog, ne pas appliquer deux fois les patches.
2. Consulter les CI déjà lancées par headSha ; ne pas attendre en boucle. Corriger uniquement les éventuels échecs réels, garder les preuves acquises.
3. Assembler dans un backend isolé les commits Quality retenus + correctif Windowsfac3 ; ne pas perdre les pads347 ni les changements345/346. Pipeline354 et TRT355 touchent des fichiers distincts. Garder les provenances de chaque binaire.
4. Si vidéo utilisateur encore enlecture, aucune mesureGPU concurrente. Une courte ablation même candidat0/1 avec mêmes sources/modèles suffit pour le nouveau burst/copie ; comparer les13hashes/PTS/flags, compteurs et lifetimes. La baseline et ses médias isolés existent : ne pas les écraser. L'amorçage est séparé des paires chaudes. Arrêter dès conclusion suffisante ; si gain bruité ou pixels différents, conserver le fallback et corriger plutôt que proclamer un gain.
5. Après décision, backend/modules→bundle depuispin courant→pins PLAYER réels→release suivante non existante→vérifier assets extraits→commentaires Jira→Done des tickets entièrement terminés seulement. Le parent AH329 reste ouvert tant que son périmètre reste partiel.

Les compilations déjà lancées peuvent finir pendant la pause. Aucun service, SDK, modèle, profil ou lecture utilisateur n’a été arrêté/reconfiguré. Les prochaines actions attendent la reprise demandée par l’utilisateur.
