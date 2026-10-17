# Lot59 — Quality exact, copies et mémoire

Les 13 images, horodatages rationnels, durées, flags, dimensions et couleurs sont identiques avec copie YUV de référence, copie supprimée et rafale expérimentale. Le reset est exact. Voir [le reçu](receipt.json). Les médias et profils restent privés.

AH-347 économise 11,25 Mio de pads YUV à1280×768 tant que le fallback ne les demande pas. AH-355 retire trois copies de plans, soit5 529 600octets par image720p synthétisée (16 588 800octets par paire Quality×4). Les conversions et la quantification Quality restent présentes. Ces économies sont établies par le code ; aucun gainFPS n'est revendiqué.

AH-354 soumet les sorties avant leur consommation, avec conservation des owners ;15contrôles CPU préexistants, pixels/PTS/reset acquis. Les temps ne permettent pas d'établir un gain : même les étapes Area/HDR inchangées varient et les fréquences observées sont1200/2385/2730MHz selon le passage. Arrêt des mesures après ce contrôle d'ambiguïté. La rafale est désactivée par défaut ; activation d'étude seulement avec `AJI_PIPELINE_QUALITY_BURST=1`. Le ticket reste ouvert pour sa conclusion de performance.

Modules Linux portables avec TrueHDR conservé ; compilation Windows NVIDIA/AMD réussie sur8ff36e8, seuls dispatcher/TRT/DML repris (ancien MIGraphX conservé avec sa provenance). Pipeline final8c67670 ne change que la garde du réglage expérimental. Bundle préparé0f43e8e, pas encore une release.

Reprise AH-354 : profiler d'abord les attentes/reaper (`src/surface_cuda_async.h`, sondage événement1ms) et le coût des soumissions sur une fréquence observée comparable ; ne pas recommencer les tests pixels concluants sans modification affectant le rendu/ownership. Si aucun gain n'est établi, conserver le chemin synchrone. Ne jamais présenter la simple suppression d'attentes hôte comme une accélération GPU mesurée.
