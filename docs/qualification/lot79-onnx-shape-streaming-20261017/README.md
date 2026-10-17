# AH366 — Lecture des dimensions ONNX sans les poids

Le même algorithme de sélection des inputs et des dimensions utilise un lecteur byte[] conservé comme référence et un lecteur Stream seekable. TemporalFrames ouvre maintenant FileStream ; cache path/mtime/longueur, détection4D/5D et fallback1 inchangés. Aucun moteur, fichier modèle ou calcul vidéo modifié.

[Reçu CPU](receipt.json) : dimensions exactes sur 4Dtemporel,5Dtemporel,symboles,input égalementinitializer,absencegraphe/forme et un vrai modèle SPAN du catalogue. Initializer dont le nom suit un gros raw_data traité correctement. Varints/longueurs/wires/messages tronqués refusés de façon bornée ; fallback1 et invalidation même longueur/mtime changé conservés.

Fixture privée sparse128Mio : avant File.ReadAllBytes→InputDims(byte[]), après InputDims(Stream), même fichier/même forme. Allocation sur thread134219232→5840octets ; lecteur logique90octets, seek de134217728octets. Il s’agit des octets consommés par le lecteur, **pas d’une mesure des pages IO du système**. Pas de gainFPS/durée d’inférence revendiqué, ni réduction du chargement des poids par les moteurs.

Commande : dotnet tests/platform/StreamingShape/bin/Release/net10.0/StreamingShape.dll NOUVEAU_DOSSIER MODELE_SPAN_EXISTANT. Une seule exécution concluante, arrêter sans replay. Le test construit sa fixture dans un dossier neuf, ne modifie pas le modèle réel. Builds helper/test .NET10Release0warning/0error.

Manager et helper doivent compiler cette source commune exacte, puis publication couplée .101 et vérification du paquet avant Done. Les calculs natifs .99/.100 sont inchangés : réutiliser leurs preuves, aucun test vidéo supplémentaire nécessaire.

Producteur Manager39025601275 réussi sur troisOS ; sourceb69968a8a30cedc83b28820ca14d014abcb36928, pin partagé97e325e, tag immuable et4assets vérifiés. .101 épingle ce Manager ; présence dans le paquet à vérifier.
