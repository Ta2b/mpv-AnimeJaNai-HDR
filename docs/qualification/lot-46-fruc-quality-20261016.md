# Lot46 — diagnostic qualité FRUC, AH-320 In Progress

L’utilisateur observe une baisse de qualité avec FRUC seul et RIFE→FRUC. Aucun correctif moteur n’est encore établi.

Un couple720p : frame3 originale + médiane RIFE acquise, sans rejouer de plan neural. FRUC natif seul, une paire + EOF : images originales et finale bit-exact avec les entréesYUV16, durée conservée, flags[1,4,1], une prédictionFRUC, zéro copieCPU provider, owners équilibrés. PackRGBA vérifié contre oracleCPU : max0/1code8bits, tolérance fixée1code ; présentationcanaux/alpha cohérente avec l’échantillonNVIDIA.

Les octets réellement packés ont été soumis au clientSDK indépendant. Native/direct diffèrent au-delà de1codeYUV16 sur48composantes/2 764 800, erreurlocale max5306. Un seul contrôle direct complémentaire, justifié par l’ambiguïté : mêmes octets/timestamps directs,281pixelsRGB différents et max17codes8bits. RépétabilitépixelSDK non concluante. Les deux chemins demandent la médiane ; natif arrondit les PTS une fois aux nanosecondes, direct utilise la période rationnelle : limite écrite, aucune parité parfaite revendiquée.

La planche RIFEQuality / FRUCnatif / SDKdirect / contrôle a été inspectée. Défauts localisés de contours/bouche présents également en SDKdirect. Le cas ne montre ni recompressionglobale ni altérationdesoriginaux ; il ne suffit pas à reproduire la sévérité de la lecture utilisateur. Qualification ouverte, aucune correction arbitraire ni équivalenceQuality. FRUC reste opt-in. Ne pas rejouer les contrôles acquis ; cibler le casutilisateur restant lorsqu’il sera identifié.

Artefacts : artifacts/performance/lots-20261016/lot-46/path, source client tests/inference/fruc_quality_path_check.py. SourceRGBA issue de la vidéo locale ; aucune image utilisateur publiée surJira/GitHub. Documentation primaire : https://docs.nvidia.com/video-technologies/optical-flow-sdk/nvfruc-programming-guide/index.html
