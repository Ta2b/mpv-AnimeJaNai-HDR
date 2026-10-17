# Lot46 — diagnostic qualité FRUC, AH-320 In Progress

L’utilisateur observe une baisse de qualité avec FRUC seul et RIFE→FRUC. Aucun correctif moteur n’est encore établi.

Un couple720p : frame3 originale + médiane RIFE acquise, sans rejouer de plan neural. FRUC natif seul, une paire + EOF : images originales et finale bit-exact avec les entréesYUV16, durée conservée, flags[1,4,1], une prédictionFRUC, zéro copieCPU provider, owners équilibrés. PackRGBA vérifié contre oracleCPU : max0/1code8bits, tolérance fixée1code ; présentationcanaux/alpha cohérente avec l’échantillonNVIDIA.

Les octets réellement packés ont été soumis au clientSDK indépendant. Native/direct diffèrent au-delà de1codeYUV16 sur48composantes/2 764 800, erreurlocale max5306. Un seul contrôle direct complémentaire, justifié par l’ambiguïté : mêmes octets/timestamps directs,281pixelsRGB différents et max17codes8bits. RépétabilitépixelSDK non concluante. Les deux chemins demandent la médiane ; natif arrondit les PTS une fois aux nanosecondes, direct utilise la période rationnelle : limite écrite, aucune parité parfaite revendiquée.

La planche RIFEQuality / FRUCnatif / SDKdirect / contrôle a été inspectée. Défauts localisés de contours/bouche présents également en SDKdirect. Le cas ne montre ni recompressionglobale ni altérationdesoriginaux ; il ne suffit pas à reproduire la sévérité de la lecture utilisateur. Qualification ouverte, aucune correction arbitraire ni équivalenceQuality. FRUC reste opt-in. Ne pas rejouer les contrôles acquis ; cibler le casutilisateur restant lorsqu’il sera identifié.

Artefacts : artifacts/performance/lots-20261016/lot-46/path, source client tests/inference/fruc_quality_path_check.py. SourceRGBA issue de la vidéo locale ; aucune image utilisateur publiée surJira/GitHub. Documentation primaire : https://docs.nvidia.com/video-technologies/optical-flow-sdk/nvfruc-programming-guide/index.html


## Cas utilisateur du faisceau lumineux — 17 octobre

Capture et session retrouvées par IPC en lecture seule, à1052.6985s : FRUC seul×2, source1080p SDR BT.709 limitée, NVDEC ; sortieYUV444P16. Les deux sources à1052.678/1052.719s sont propres. Un faisceau traverse rapidement l’image ; la synthèse contient de larges trous/blocs et stries dans cette zone.

Un seul couple soumis directement au SDK NVIDIA, sans lecteur, shaderHDR ni conversionYUV de sortie : le même type de corruption sévère apparaît en RGBA. Une ablation ciblée sur le format NV12, directement décodé de la source, conserve la corruption. L’API, les pitches et la présentationRGBA suivent l’échantillon fourni par NVIDIA. Le changementNV12 est donc écarté comme correctif de ce défaut ; aucune modification arithmétique du provider n’est conservée. Arrêt des essais dès cette conclusion.

RTX4070Ti, pilote615.78.08, SDK5.0.7 (empreintes du lot45). Chaque client a produit une médiane puis a libéré ses ressources. Appels directs complets : RGBA46.8085ms, NV1263.3469ms ; appels froids isolés, aucune comparaison de FPS exploitable. Intervalle réel de cette paire41ms (timestampsMatroska), clientdirect réglé1/0.041fps pour demander sa médiane ; cadence nominale vidéo24000/1001. Entrées décodées logiciel : pas de revendication de paritépixel avec NVDEC/lecteur, ni de disposition des trous identique entre essais.

Conclusion : cette classe d’artefacts est déjà produite par le SDKFRUC sur ce passage, dans les deux formats supportés. Ce n’est pas une preuve d’une recompression du fichier ni d’un défaut du shaderHDR. Aucun correctif d’intégration établi. FRUC reste opt-in ; l’avertissement du Manager mentionne maintenant les artefacts sévères sur flashes, changements lumineux rapides et occlusions. Le diagnostic est acquis ; sa livraison reste à vérifier avantDone. Les originaux et Quality ne changent pas.

Artefacts locaux : artifacts/performance/lots-20261016/lot-46/beam/{session.json,source-probe.json,extract.log,sdk-direct.json,sdk-nv12.json,summary.json} et captures inspectées. Aucun média utilisateur envoyé sur Jira/GitHub. Le client indépendant tests/inference/fruc_probe.cpp accepte désormais un format explicite rgba|nv12 ; compatibilité des en-têtes CUDA13 corrigée pour cet outil seul. Deux tentatives de compilation invalides avant ce correctif sont exclues des essais.
