# AH-362 — route Linux ABI9 et configuration immuable

Le 17 octobre 2026, sur Linux / RTX 4070 Ti. Correctif de fidélité et de cohérence au lancement, sans modification des calculs d’image. Aucun gain de FPS revendiqué.

## Sources et binaires

- MPV amont `19c0fcf89595e6ab33908299207c555b67e81558`, installateur Linux et huit patches courants, puis le neuvième `vf_animejanai-quality-contract.patch`. Application exacte du dernier patch avec `--fuzz=0` ; vraie source C compilée et liée pour le contrôle local. Ce lien réutilise les objets du cœur MPV ; la CI de release reconstruit le lecteur complet.
- Dispatcher `118c27252240efbb7d980d0e0b8ef358b6d4bc7e`, compilé dans l’image Ubuntu `aji-rtx-build`, cible `aji`, sans RPATH local. SHA256 `592a828989d3fa40228577bd103374568ef05277df89eb6f467ab965175764c3`.
- TensorRT/alias conservés de .92, SHA256 `4c1074ed7cd31361c99e991966e86a45e3092fb13531fe6a773c73cc9cdf302e`. Pipeline et kernels conservés avec leurs sources propres. Aucune recompilation ou qualification numérique répétée.
- Contrôle ancien fournisseur : TensorRT lot62, sans contrat optionnel. Fichiers utilisateur originaux préservés ; configurations et copies privées dans `lot-71-native-legacy-control-20261017`.

## Conclusion avant/après

Avant : la route ABI9 ne vérifiait pas la policy effective du contexte. Un chemin de configuration identique pouvait aussi être réutilisé après modification de son contenu par une sélection directe ; `aji_set_slot` ne relit pas AjiConf. Le rechargement explicite du Manager recréait déjà le filtre : ce n’est pas une panne générale de ce rechargement.

Après : le lancement résout et charge la même copie immuable. Le filtre vérifie une fois après configure, avant traitement des pixels, que le fournisseur annonce la policy demandée et les flags attendus. Quality inconnu ou incohérent est refusé ; Fast ancien reste un choix explicite avec état inconnu. Aucun remplacement automatique de Quality par Fast. `dlsym` ne suffit pas : create/configure/infer_rife/contrat doivent provenir de la même image ELF, y compris à l’intérieur du dispatcher.

## Contrôles ciblés conclus

1. Validateur C réellement utilisé par le lecteur : policies, référence RGB, absence des raccourcis Fast en Quality, flags/version/taille et chaînes bornées. PASS.
2. Vrais DSOs et dispatcher : API présente, absente et trouvée seulement dans une dépendance. Transfert sur innerhandle exact ; null/taille/version incorrects laissent le buffer intact. PASS. Le dernier cas est rejeté comme inconnu.
3. Vrai lanceur Lua avec mock MPV : résolution et contexte consomment le même snapshot malgré une sauvegarde concurrente ; sélection directe au même chemin voit le nouveau contenu ; copie précédente et original conservés ; contenu identique réutilisé ; aliases et policy de règle conservés ; nettoyage des fichiers possédés seulement. PASS. La première fixture observait avant la géométrie demux ; corrigée vers `on_preloaded`, sans changement du produit pour cette erreur de fixture.
4. Vrai MPV, NVDEC 1280×720 H.264, RIFE4.26 ×4 et plans existants, `/bin/false` interdit toute compilation de modèle :
   - dispatcher actuel + Quality : état verified, effective quality, flags1 ; module observé = **inner TensorRT**, distinct du dispatcher ; source déclarée unknown, explicitement distincte du hash de fichier ;
   - ancien fournisseur + Quality : état failed et diagnostic de mise à jour/redémarrage ; zéro inférence RIFE, lecture originale conservée par le repli MPV ;
   - ancien fournisseur + Fast explicite : état unknown, aucune certification Quality, lecture acceptée.

[Reçu natif](native-receipt.json) et trois extraits de logs dans ce dossier. Ces contrôles portent sur l’activation, le refus et GET_META, pas sur un benchmark ou une nouvelle comparaison de pixels. Réutiliser les preuves numériques .86/.90/.92 puisque TRT/pipeline/kernels n’ont pas changé.

## Limites et livraison

Linux historique uniquement. Le pipeline ordonné reste protégé par AH361 ; Windows/macOS, choix/migration des overrides et intégration détaillée dans l’export restent des portées du parent AH330. Aucun profil, modèle, SDK ou composant utilisateur écrasé. Le correctif de c-ares du producteur Windows appartient à AH344 ; il n’active pas encore son lecteur apparié.

Livraison prévue .93 : vérifier les trois CI au SHA exact, le dispatcher livré contre ce hash, les deux lecteurs Linux et leur marqueur `legacy_rife_contract=1`, les programmes Lua modifiés et le manifeste. Ne pas répéter les trois activations concluantes sur les mêmes contenus. Done seulement après vérification de livraison.
