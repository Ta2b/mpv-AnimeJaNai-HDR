# AH365 — SPAN CoreML résidents

Runtime source9e03e0c559af3b212382a439224a58d3368fa717 ; natifCI39023928908 réussi, macOS15.7.9/24G830 arm64. Deux vrais SPAN Performance normalisés de .88, entrée256→512→1024, CoreMLCPU, mêmes computeUnits/accumulation/hints. Base .98 source18013889f61234facfa53b997d5aeebea2cdc307 et candidate/off/on via vrais dylibs/CABI.

[Reçu](receipt.json) : pixels RGB8 exacts base/off/on, hash3f38af37d506b27fc213ff6aa8fd963e80a4404432898ad0a46175daa1809702. RGB→BGRA983040→196608octets et BGRA→RGB3932160→3145728octets, deux conversions supprimées à la frontière512×512 (1,5Mio RGB par frame). Ces compteurs sont des conversions hôte, pas des transferts GPU ou copies internes CoreML. L’ablation Metal à0 n’affecte pas CoreML.

Trois appels chauds complets, sans étendre l’essai : off149,817/148,095/153,662ms ; on149,217/150,700/154,194ms. Médianes149,817→150,700ms, **aucun gain de temps CPU établi** avec ce petit relevé bruité. Utilité établie = travail de conversion et canvas intermédiaire retirés, rendu exact ; aucun FPS/GPU/ANE physique promis. Ne pas répéter ce timing pour chercher artificiellement un gain.

Resize intermédiaire : ancien repli exact et route résidente exclue. Reconfigure : sortie exacte, segment de nouveau actif. [Probe owner/erreur](owner.log) : sortie précédente retenue non écrasée par un second appel, format résident invalide refusé, reprise exacte au second modèle. La sortie réellement retournée est retenue, même différente du backing proposé ; le backing est renouvelé si une ancienne image est encore détenue. Prédictions synchrones, pas de nouvelle queue ou de thread.

Dylib baseSHA61b30d435acb85659927d3e5686cd7e28288efefbf457e79eb6918f761fff478 ; candidatSHA7816d2a515cee72d8be4236aab946ba20f9117bdb5b887cf92816621d2268a45. [Machine](machine.txt), [log chaîne](chain.log). Deux modules complets compilés par CMake, parserv0.11.1/ORT1.31/deployment13.3 comme la release. Source core également syntax-check sur Linux. Les calculs Metal et autres providers sont inchangés ; pas de replay de leurs mesures.

API primaire vérifiée : [MLFeatureValue pixelBuffer](https://developer.apple.com/documentation/coreml/mlfeaturevalue/init(pixelbuffer:)), formats RGB/BGR en32BGRA ; [outputBackings](https://developer.apple.com/documentation/coreml/mlpredictionoptions/outputbackings), buffers client. Ne pas déduire de ces contrats une absence de copie interne ou une trace du device réellement utilisé.

.99 à publier/vérifier avant Done ; AH119 garde RIFE→SPAN et la sortie vers rendu. Pas de replay des transactions AH364 ou des autres poids/manifestes déjà qualifiés.
