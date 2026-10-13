#!/bin/bash
# Mesure la vitesse des modèles AnimeJaNai sur ce Mac avec les trois moteurs et chaque processeur.
# Une ligne RESULT par essai, puis un classement et le réglage à choisir dans le Manager.
#   bench.command          mesure complète (dix à quinze minutes la première fois)
#   bench.command rapide   Performance en 720p seulement
# Le Manager lance ce même script (Run Benchmarks) depuis l'application ; il fonctionne aussi
# seul, dans le dossier AnimeJaNai-mac-bench.
cd "$(dirname "$0")" || exit 1
mode="${1:-}"
tool="${AJI_BENCH_TOOL:-./animejanai-ort-test}"
models="${AJI_BENCH_MODELS:-models}"
conf="${AJI_BENCH_CONF:-bench.conf}"
out="${AJI_BENCH_OUT:-resultats.txt}"
work="${AJI_BENCH_WORK:-.}"
[ -x "$tool" ] || { echo "Outil de mesure introuvable : $tool"; exit 1; }
[ "$tool" = ./animejanai-ort-test ] && xattr -dr com.apple.quarantine . 2>/dev/null
mkdir -p "$work" && cd_work="$work"
tool="$(cd "$(dirname "$tool")" && pwd)/$(basename "$tool")"
models="$(cd "$models" && pwd)"
conf="$(cd "$(dirname "$conf")" && pwd)/$(basename "$conf")"
# Les modèles RIFE : dans l'application, ou avec les autres modèles dans le dossier de mesure.
rife="${AJI_BENCH_RIFE:-$models}"
[ -d "$rife" ] && export AJI_TEST_RIFE_DIR="$(cd "$rife" && pwd)"
case "$out" in /*) ;; *) out="$(pwd)/$out" ;; esac
cd "$cd_work" || exit 1
{
    echo "AnimeJaNai - mesure des moteurs - $(date)"
    echo "Application : ${AJI_BENCH_VERSION:-paquet de mesure seul}"
    sw_vers 2>/dev/null
    sysctl -n machdep.cpu.brand_string 2>/dev/null
    system_profiler SPHardwareDataType 2>/dev/null | grep -E 'Model Name|Chip|Memory|Cores'
    echo "Aucune image n'est réutilisée ici (engine_reuse=off) : c'est le coût d'une image entièrement nouvelle."
} | tee "$out"

frames=30
[ "$mode" = essai ] && frames=3
# essai MOTEUR CIBLE PROFIL LARGEUR HAUTEUR [VARIABLE=VALEUR...]
#   MOTEUR : coreml (Core ML par ONNX Runtime), coremlnative (Core ML natif), metal
#   PROFIL : 1 Performance, 2 Balanced, 3 Performance + RIFE x2 avant l'upscale, 4 le même après
#   Variables d'essai : AJI_TILES=2x2 (découpe en tuiles), AJI_METAL_LAYOUT=nchw, AJI_METAL_OPT=1,
#   AJI_RIFE_DEVICE=gpu|npu|cpu (processeur de RIFE ; sans elle, Core ML choisit)
essai() {
    local engine="$1" device="$2" slot="$3" w="$4" h="$5" n="$frames"
    shift 5
    [ "$device" = CPU ] && n=4
    local extra="${*:+ $*}"
    echo | tee -a "$out"
    echo "== $engine | $device | profil $slot | ${w}x${h}$extra" | tee -a "$out"
    env AJI_ORT_PROVIDER="$engine" AJI_REUSE=off "$@" "$tool" "$conf" "$models" "$slot" "$w" "$h" "$n" "$device" 2>&1 \
        | grep -E '^RESULT|^Tiles|^Devices|^Placement|^RIFE|failed|rror' \
        | sed "s/^RESULT/RESULT | moteur=$engine cible=$device profil=$slot$extra/" | cut -c1-420 | tee -a "$out"
}

if [ "$mode" = essai ]; then
    # Passage court de l'intégration continue : chaque moteur une fois, petite image.
    essai coreml ALL 1 640 360; essai coremlnative GPU 1 640 360; essai metal GPU 1 640 360
    essai metal GPU 1 640 360 AJI_METAL_LAYOUT=nchw; essai coremlnative NPU 1 640 360 AJI_TILES=2x2
    essai coremlnative GPU 3 640 360
else
    # 1. Chaque moteur sur chaque processeur seul, Performance en 720p.
    for device in ALL GPU ANE; do essai coreml "$device" 1 1280 720; done
    for device in AUTO GPU NPU; do essai coremlnative "$device" 1 1280 720; done
    essai metal GPU 1 1280 720
    # 2. Deux processeurs sur la même image : quatre tuiles, chacun prend la suivante dès qu'il est libre.
    essai coremlnative GPU+NPU 1 1280 720
    essai metal GPU+NPU 1 1280 720
    essai coreml GPU+ANE 1 1280 720
    # Trois processeurs : le CPU (et son unité matricielle) prend aussi des tuiles. Chaque moteur,
    # puis la même image en davantage de tuiles (le plus lent en prend alors une plus petite part).
    essai coremlnative GPU+NPU+CPU 1 1280 720
    essai metal GPU+NPU+CPU 1 1280 720
    essai coreml GPU+ANE+CPU 1 1280 720
    essai coremlnative GPU+NPU+CPU 1 1280 720 AJI_TILES=4x3
    essai metal GPU+NPU+CPU 1 1280 720 AJI_TILES=4x3
    # 3. Le Neural Engine préfère les petites images : la même image en 4, 6 puis 12 tuiles.
    for grid in 2x2 3x2 4x3; do essai coremlnative NPU 1 1280 720 "AJI_TILES=$grid"; done
    essai coremlnative GPU+NPU 1 1280 720 AJI_TILES=4x3
    essai metal GPU+NPU 1 1280 720 AJI_TILES=4x3
    # 4. Variantes du moteur Metal : disposition des données, placement par le graphe.
    essai metal GPU 1 1280 720 AJI_METAL_LAYOUT=nchw
    essai metal GPU 1 1280 720 AJI_METAL_OPT=1
    # 5. Interpolation RIFE x2 : le temps est celui d'une image source, soit deux images affichées.
    #    Avant l'upscale (profil 3) puis après (profil 4), et RIFE sur chaque processeur.
    essai coremlnative GPU+NPU 3 1280 720
    essai coremlnative GPU+NPU 3 1280 720 AJI_RIFE_DEVICE=gpu
    essai coremlnative GPU+NPU 3 1280 720 AJI_RIFE_DEVICE=npu
    essai coremlnative GPU 3 1280 720 AJI_RIFE_DEVICE=npu
    essai coremlnative GPU 3 1280 720 AJI_RIFE_DEVICE=npu AJI_RIFE_PARALLEL=0
    essai metal GPU 3 1280 720 AJI_RIFE_DEVICE=npu
    essai coremlnative GPU+NPU 4 1280 720
    essai coremlnative GPU+NPU+CPU 3 1280 720
    essai coremlnative GPU+NPU+CPU 3 1280 720 AJI_RIFE_DEVICE=cpu
    essai metal GPU+NPU+CPU 3 1280 720
    essai coremlnative GPU+NPU 3 960 540
    essai coremlnative GPU+NPU+CPU 3 960 540
    if [ "$mode" != rapide ]; then
        # 6. Autres tailles, puis le modèle Balanced (profil 2).
        for size in "960 540" "1920 1080"; do
            set -- $size
            essai coremlnative GPU 1 "$1" "$2"; essai coremlnative GPU+NPU 1 "$1" "$2"; essai coremlnative GPU+NPU+CPU 1 "$1" "$2"
            essai metal GPU 1 "$1" "$2"; essai metal GPU+NPU 1 "$1" "$2"; essai metal GPU+NPU+CPU 1 "$1" "$2"; essai coreml ALL 1 "$1" "$2"
        done
        essai coremlnative GPU 2 1280 720; essai coremlnative GPU+NPU 2 1280 720; essai coremlnative GPU+NPU+CPU 2 1280 720
        essai metal GPU 2 1280 720; essai metal GPU+NPU 2 1280 720; essai metal GPU+NPU+CPU 2 1280 720; essai coreml ALL 2 1280 720
        essai coremlnative CPU 1 1280 720
    fi
fi

rank() { # rank TITRE MOTIF
    echo
    echo "== $1 (temps par image, du plus rapide au plus lent ; 41,7 ms = 24 images/s)"
    grep '^RESULT' "$out" | grep -- "$2" | awk -F'|' '{ t=$5; sub(/.*frame /,"",t); sub(/ ms.*/,"",t); print t "\t" $2 "|" $5 }' \
        | sort -n | awk -F'\t' '{ printf "%8.1f ms  %s\n", $1, $2 }' | cut -c1-200
}
{
    if [ "$mode" = essai ]; then rank "Classement" "640x360 ->"
    else
        rank "Performance, 1280x720 vers 2560x1440" "profil=1 .*1280x720 ->"
        rank "Performance + RIFE x2, 1280x720 vers 2560x1440 (temps par image source : il en faut moins de 41,7 ms)" "profil=[34] .*1280x720 ->"
        if [ "$mode" != rapide ]; then
            rank "Performance, 1920x1080 vers 3840x2160" "profil=1 .*1920x1080 ->"
            rank "Performance, 960x540 vers 1920x1080" "profil=1 .*960x540 ->"
            rank "Balanced, 1280x720 vers 2560x1440" "profil=2 .*1280x720 ->"
        fi
        best="$(grep '^RESULT' "$out" | grep -- 'profil=1 .*1280x720 ->' | awk -F'|' '{ t=$5; sub(/.*frame /,"",t); sub(/ ms.*/,"",t); print t "\t" $2 }' | sort -n | head -1 | cut -f2)"
        echo
        echo "== Réglage le plus rapide en 720p :$best"
        echo "   Manager > Global Settings : moteur coreml = « Core ML (ONNX Runtime) », coremlnative ="
        echo "   « Core ML (native) », metal = « Metal » ; cible = Compute target. Une variable AJI_TILES se"
        echo "   règle par engine_tiles=... dans la section [global] de animejanai.conf."
        # Deux et trois processeurs côte à côte, pour chaque moteur : ce que le CPU ajoute ou retire.
        echo
        echo "== Le CPU en plus du GPU et du Neural Engine (Performance 720p, ms par image)"
        for engine in coremlnative metal coreml; do
            two="$(grep '^RESULT' "$out" | grep -E "moteur=$engine cible=GPU\+(NPU|ANE) profil=1 \|.*1280x720 ->" | head -1 | awk -F'|' '{ t=$5; sub(/.*frame /,"",t); sub(/ ms.*/,"",t); print t }')"
            three="$(grep '^RESULT' "$out" | grep -E "moteur=$engine cible=GPU\+(NPU|ANE)\+CPU profil=1 \|.*1280x720 ->" | head -1 | awk -F'|' '{ t=$5; sub(/.*frame /,"",t); sub(/ ms.*/,"",t); print t }')"
            printf '   %-13s GPU + NPU : %8s      GPU + NPU + CPU : %8s\n' "$engine" "${two:-absent}" "${three:-absent}"
        done
    fi
} | tee -a "$out"
echo | tee -a "$out"
echo "Terminé. Résultats : $out"
