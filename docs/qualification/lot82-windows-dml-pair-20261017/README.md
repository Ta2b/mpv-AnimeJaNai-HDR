# AH344 — livraison du lecteur Windows apparié

Producteur natif réussi : [39019317771](https://github.com/Ta2b/mpv-AnimeJaNai-HDR/actions/runs/39019317771), source `32464bc13260918381537dbb73a5a2e7523c2477`.
Tag immuable `windows-mpv-32464bc13260918381537dbb73a5a2e7523c2477` : archive69 159 040octets, SHA256 `62d5039e072bc307cd55f1c29ea21617530e5a4e6173493b064565ffb93dcf8c` ; provenance séparée byte-identique à celle archivée, digest GitHub conforme.

Le contrôle unique du vrai producteur vérifie troisPE x64, leurs SHA256, source mpv, patch, postimage du filtre, ABI9 et contrat exact-pair1 contre les constantes du vrai assembleur. Les deux archives sources sont compilées ensemble et le producteur refuse leur divergence. Le dispatcher livré exporte `aji_rife_begin_pair` ; dispatcher/DML correspondent aux empreintes du bundle déjà publié. Les fixtures CPU de cache/assembleur déjà concluantes ne sont pas rejouées.

Le nouveau bundle `dc53e6c…` ne change que la provenance Windows : aucune DLL ni fichier Linux modifié. Backend DML `d5b34469a3aa1cc30f107ba3122699d713de1dca`, CI spécialisée39009958899. Les référencesCOM, IDs et fences restent présentes ; même réseau RGB complet à chaque instant. Préparations/SCD3→1 à×4 est un comptage du code, pas un gainFPS mesuré.

Release .103 : vérifier encore le paquet Windows réellement publié, son manifeste et sa provenance avant Done de l’implémentation AH344. **Qualification GPU Windows non faite**, portée explicitement par AH367 ; AH93 reste ouvert. Aucun résultat matériel extrapolé de la compilation. [Contrôle du producteur](producer-check.json).
