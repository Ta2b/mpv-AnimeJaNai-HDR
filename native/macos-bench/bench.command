#!/bin/bash
# Mesure la vitesse des modèles AnimeJaNai avec Core ML sur ce Mac.
# Résultat dans resultats.txt, à côté de ce script : une ligne RESULT par essai, puis un classement.
#   ./bench.command          mesure complète (une dizaine de minutes la première fois)
#   ./bench.command rapide   Performance en 720p seulement
cd "$(dirname "$0")" || exit 1
xattr -dr com.apple.quarantine . 2>/dev/null
out=resultats.txt
quick="${1:-}"
{
    echo "AnimeJaNai - mesure Core ML - $(date)"
    sw_vers 2>/dev/null
    sysctl -n machdep.cpu.brand_string 2>/dev/null
    system_profiler SPHardwareDataType 2>/dev/null | grep -E 'Model Name|Chip|Memory|Cores'
} | tee "$out"

# essai NOM PROFIL LARGEUR HAUTEUR DEVICE [VARIABLES...]
essai() {
    local name="$1" slot="$2" w="$3" h="$4" device="$5"; shift 5
    local frames=40
    [ "$device" = CPU ] && frames=6
    echo | tee -a "$out"
    echo "== $name | profil $slot | ${w}x${h} | $device $*" | tee -a "$out"
    env AJI_ORT_PROVIDER=coreml "$@" ./animejanai-ort-test bench.conf models "$slot" "$w" "$h" "$frames" "$device" 2>&1 \
        | grep -E 'RESULT|Lanes|failed|error' | sed "s/^RESULT/RESULT | $name | profil $slot/" | cut -c1-400 | tee -a "$out"
}
ancien="AJI_ORT_COREML=SpecializationStrategy=Default;AllowLowPrecisionAccumulationOnGPU=0"

# 1. Chaque processeur seul, réglages actuels. Profil 1 : Performance. Profil 2 : Balanced.
#    ALL : Core ML choisit. GPU : carte graphique. ANE : Neural Engine.
for device in ALL GPU ANE; do essai "seul" 1 1280 720 "$device"; done
# 2. Les réglages d'avant la 3.8.0.18, pour chiffrer ce qu'apportent les nouveaux.
for device in ALL GPU; do essai "ancien" 1 1280 720 "$device" "$ancien"; done
# 3. Image coupée en deux bandes traitées en même temps, une par processeur.
#    AJI_ORT_SPLIT : part de l'image donnée au premier (en %).
for share in 50 60 70; do essai "bandes" 1 1280 720 "GPU+ANE" "AJI_ORT_SPLIT=$share"; done
essai "bandes" 1 1280 720 "ANE+ANE"
essai "bandes" 1 1280 720 "GPU+GPU"

if [ "$quick" != rapide ]; then
    # 4. Autres tailles et modèle Balanced.
    for size in "960 540" "1920 1080"; do
        set -- $size
        for device in ALL GPU ANE "GPU+ANE"; do essai "taille" 1 "$1" "$2" "$device"; done
    done
    for device in ALL GPU ANE "GPU+ANE"; do essai "balanced" 2 1280 720 "$device"; done
    essai "processeur" 1 1280 720 CPU
fi

{
    echo
    echo "== Classement (temps par image, du plus rapide au plus lent ; 41,7 ms = 24 images/s)"
    grep '^RESULT' "$out" | awk -F'|' '{ t=$6; sub(/.*frame /,"",t); sub(/ ms.*/,"",t); print t "\t" $0 }' \
        | sort -n | cut -f2- | cut -c1-260
} | tee -a "$out"
echo | tee -a "$out"
echo "Terminé. Envoyer le fichier : $(pwd)/$out"
