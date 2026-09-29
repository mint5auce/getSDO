#!/bin/zsh
set -eu
repo_dir=${0:A:h:h}
build_dir="$repo_dir/build"
mkdir -p "$build_dir/Solar Horizon.app/Contents/MacOS" "$build_dir/Solar Horizon.saver/Contents/MacOS"
xcrun swiftc -O -target arm64-apple-macosx14.0 "$repo_dir/macOS/SolarSceneCore.swift" "$repo_dir/macOS/SolarHorizonApp.swift" -o "$build_dir/Solar Horizon.app/Contents/MacOS/SolarHorizon" -framework AppKit -framework MetalKit -framework IOKit
for build_arch in arm64 x86_64; do
    xcrun swiftc -O -emit-library -Xlinker -bundle -module-name SolarHorizonSaver -target "$build_arch-apple-macosx14.0" "$repo_dir/macOS/SolarSceneCore.swift" "$repo_dir/macOS/SolarHorizonSaver.swift" -o "$build_dir/saver-$build_arch" -framework ScreenSaver -framework MetalKit -framework IOKit
done
xcrun lipo -create "$build_dir/saver-arm64" "$build_dir/saver-x86_64" -output "$build_dir/Solar Horizon.saver/Contents/MacOS/SolarHorizonSaver"
mkdir -p "$build_dir/Solar Horizon.saver/Contents/Resources"
cp "$repo_dir/macOS/Resources/thumbnail.png" "$repo_dir/macOS/Resources/thumbnail@2x.png" "$build_dir/Solar Horizon.saver/Contents/Resources/"
/usr/bin/python3 - "$build_dir" <<'PY'
import plistlib,sys
from pathlib import Path
for kind, executable, package in [('app','SolarHorizon','APPL'),('saver','SolarHorizonSaver','BNDL')]:
    data={'CFBundleIdentifier':f'uk.jonh.getSDO.{kind}', 'CFBundleName':'Solar Horizon','CFBundleExecutable':executable,'CFBundlePackageType':package,'CFBundleVersion':'5','CFBundleShortVersionString':'1.4','LSMinimumSystemVersion':'14.0','CFBundleInfoDictionaryVersion':'6.0','CFBundleDevelopmentRegion':'en','NSHighResolutionCapable':True}
    if kind=='app': data['LSUIElement']=True
    else: data['NSPrincipalClass']='SolarHorizonSaver'
    with (Path(sys.argv[1])/f'Solar Horizon.{kind}'/'Contents/Info.plist').open('wb') as f: plistlib.dump(data,f)
PY
codesign --force --sign - "$build_dir/Solar Horizon.app"
codesign --force --sign - "$build_dir/Solar Horizon.saver"
