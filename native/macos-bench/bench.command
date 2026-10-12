#!/bin/bash
# Mesure la vitesse des modèles AnimeJaNai avec Core ML sur ce Mac.
# Résultat dans resultats.txt, à côté de ce script.
cd "$(dirname "$0")" || exit 1
xattr -dr com.apple.quarantine . 2>/dev/null
out=resultats.txt
{
    echo "AnimeJaNai - mesure Core ML - $(date)"
    sw_vers 2>/dev/null
    sysctl -n machdep.cpu.brand_string 2>/dev/null
    system_profiler SPHardwareDataType 2>/dev/null | grep -E 'Model Name|Chip|Memory|Cores'
} | tee "$out"

# Profil 1 : Performance (le plus léger). Profil 2 : Balanced.
# ALL : Core ML choisit. GPU : carte graphique. ANE : Neural Engine. CPU : processeur seul.
for slot in 1 2; do
    for size in "1280 720" "1920 1080"; do
        for device in ALL GPU ANE CPU; do
            frames=40
            [ "$device" = CPU ] && frames=6
            echo | tee -a "$out"
            echo "== profil $slot | ${size/ /x} | $device" | tee -a "$out"
            # shellcheck disable=SC2086
            AJI_ORT_PROVIDER=coreml ./animejanai-ort-test bench.conf models "$slot" $size "$frames" "$device" 2>&1 \
                | grep -v -E 'device_discovery|^$' | tail -6 | tee -a "$out"
        done
    done
done
echo | tee -a "$out"
echo "Terminé. Envoyer le fichier : $(pwd)/$out"
