#!/usr/bin/env bash
# Build the pinned mpv/aji ABI with mandatory Wayland support on Ubuntu 24.04.
# Development packages: see docs/LINUX.md. No private build image is required.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(realpath -m "${1:?usage: build-native.sh WORK OUTPUT}")"
OUTPUT="$(realpath -m "${2:?output directory required}")"
PREFIX="$WORK/prefix"
JOBS="${AJ_BUILD_JOBS:-4}"
export PKG_CONFIG_PATH="$PREFIX/share/pkgconfig:$PREFIX/lib/pkgconfig:$PREFIX/lib/x86_64-linux-gnu/pkgconfig:${PKG_CONFIG_PATH:-}"
export LD_LIBRARY_PATH="$PREFIX/lib:$PREFIX/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PATH="$PREFIX/bin:$PATH"
mkdir -p "$WORK" "$OUTPUT"
clone() {
    local repository="$1" directory="$2" revision="$3"
    if [ ! -d "$directory/.git" ]; then git clone --filter=blob:none "$repository" "$directory"; fi
    git -C "$directory" checkout --detach "$revision"
}
build_meson() {
    local directory="$1"; shift
    if [ -d "$directory/build" ]; then meson setup --clearcache --reconfigure "$directory/build" "$directory" "$@"
    else meson setup "$directory/build" "$directory" "$@"; fi
    ninja -C "$directory/build" -j "$JOBS" install
}
clone https://github.com/wayland-mirror/wayland.git "$WORK/wayland" 1.23.1
build_meson "$WORK/wayland" --prefix="$PREFIX" --libdir=lib --buildtype=release \
    -Dtests=false -Ddocumentation=false -Ddtd_validation=false
clone https://github.com/wayland-mirror/wayland-protocols.git "$WORK/wayland-protocols" 1.45
build_meson "$WORK/wayland-protocols" --prefix="$PREFIX" -Dtests=false
clone https://github.com/FFmpeg/nv-codec-headers.git "$WORK/nv-codec-headers" n13.0.19.0
make -C "$WORK/nv-codec-headers" PREFIX="$PREFIX" install
clone https://github.com/FFmpeg/FFmpeg.git "$WORK/ffmpeg" n9.0.2
( cd "$WORK/ffmpeg"
  ./configure --prefix="$PREFIX" --enable-gpl --enable-version3 --enable-shared --disable-static \
    --enable-ffnvcodec --enable-nvdec --enable-cuvid --disable-programs --disable-doc --disable-debug \
    --extra-cflags="-I$PREFIX/include" --extra-ldflags="-L$PREFIX/lib"
  make -j "$JOBS"; make install )
clone https://github.com/haasn/libplacebo.git "$WORK/libplacebo" v7.360.1
git -C "$WORK/libplacebo" submodule update --init --recursive
build_meson "$WORK/libplacebo" --prefix="$PREFIX" --libdir=lib --buildtype=release \
    -Dlibdovi=disabled -Ddemos=false -Dtests=false
clone https://github.com/the-database/libass.git "$WORK/libass" 896614fa263f9f64944f7b8650ff6806d5328c4d
( cd "$WORK/libass"; ./autogen.sh
  ./configure --prefix="$PREFIX" --disable-static --enable-shared
  make -j "$JOBS"; make install )
clone https://github.com/the-database/mpv.git "$WORK/mpv" 19c0fcf895
python3 "$REPO/native/linux-vulkan/install-filter.py" "$WORK/mpv"
build_meson "$WORK/mpv" --prefix="$PREFIX" --libdir=lib --buildtype=release \
    -Dlibmpv=true -Dwayland=enabled -Dvulkan=enabled -Dcuda-hwaccel=enabled -Dlua=enabled
cp -a "$PREFIX/bin/mpv" "$OUTPUT/"
cp -aL "$PREFIX/lib/libmpv.so.2" "$OUTPUT/"
EXCLUDE='^(ld-linux|libc\.|libm\.|libdl\.|libpthread|librt\.|libresolv|libstdc\+\+|libgcc_s|libGL|libEGL|libGLX|libGLdispatch|libOpenGL|libdrm|libgbm|libva\.|libva-|libvulkan|libwayland|libxkbcommon|libX11|libxcb|libexpat|libffi|libcuda\.|libnvidia)'
collect() {
    local binary="$1" library base
    while read -r library; do
        base="$(basename "$library")"
        [[ "$base" =~ $EXCLUDE ]] && continue
        [ -e "$OUTPUT/$base" ] && continue
        cp -aL "$library" "$OUTPUT/$base"
        collect "$library"
    done < <(ldd "$binary" | awk '/=> \// {print $3}')
}
collect "$OUTPUT/mpv"; collect "$OUTPUT/libmpv.so.2"
contexts="$(LD_LIBRARY_PATH="$OUTPUT:$LD_LIBRARY_PATH" "$OUTPUT/mpv" --no-config --gpu-context=help)"
grep -q waylandvk <<< "$contexts"
options="$(LD_LIBRARY_PATH="$OUTPUT:$LD_LIBRARY_PATH" "$OUTPUT/mpv" --no-config --list-options)"
grep -q target-colorspace-hint-strict <<< "$options"
printf 'mpv=19c0fcf895\naji_abi=9\nvulkan_bridge_abi=1\nlibass=896614fa263f9f64944f7b8650ff6806d5328c4d\nwayland=1.23.1\nprotocols=1.45\nffmpeg=n9.0.2\nlibplacebo=v7.360.1\n' > "$OUTPUT/build-info.txt"
