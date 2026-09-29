#!/bin/zsh
set -eu
repo_dir=${0:A:h:h}
"$repo_dir/scripts/build-macos.sh"
xcrun swiftc -O -module-name SolarHorizonValidation "$repo_dir/macOS/SolarSceneCore.swift" "$repo_dir/macOS/Validate.swift" -o "$repo_dir/build/validate" -framework ScreenSaver -framework MetalKit -framework IOKit
"$repo_dir/build/validate" "$repo_dir/build/validation" "$repo_dir/build/Solar Horizon.saver"
"$repo_dir/.venv/bin/python" - "$repo_dir/build/validation" <<'PY'
from pathlib import Path
import json
import sys
from PIL import Image
import numpy as np
folder=Path(sys.argv[1])
for a,b in [('metal-0.png','metal-1200.png'),('saver-0.png','saver-1200.png'),('saver-600.png','retina-bounds.png'),('saver-600.png','retina-bounds-size.png'),('saver-600.png','retina-frame.png')]:
    first=np.asarray(Image.open(folder/a))
    second=np.asarray(Image.open(folder/b))
    assert np.array_equal(first,second), f'{a} != {b}'
    print(f'Identical loop pixels: {a}, {b}')
for phase in (0,300,600,900):
    first=np.asarray(Image.open(folder/f'metal-{phase}.png').convert('RGB'),dtype=float)
    second=np.asarray(Image.open(folder/f'saver-{phase}.png').convert('RGB'),dtype=float)
    delta=np.abs(first-second)
    assert delta.mean()<0.2 and np.percentile(delta,99)<=2 and delta.max()<=12, (phase,delta.mean(),delta.max())
    print(f'Metal and AppKit geometry agree at phase {phase}, allowing colour interpolation rounding')
frames=[np.asarray(Image.open(folder/f'crossfade-{second}.png')) for second in (100,105,110)]
red,mixed,blue=[frame[frame.shape[0]*3//4,frame.shape[1]//2,:3] for frame in frames]
assert red[0]>250 and red[2]<2,red
assert blue[2]>250 and blue[0]<2,blue
assert 180<=mixed[0]<=195 and 180<=mixed[2]<=195 and mixed[1]<2,mixed
print('Ten-second crossfade verified in linear light, including exact endpoints')
preview=np.asarray(Image.open(folder/'layer-preview.png').convert('RGB'))
assert (preview.max(axis=2)>40).sum()>1000, 'Small preview is black'
assert preview[:preview.shape[0]//5].max()<5, 'Preview lost its quiet upper sky'
for cycle in range(5):
    assert np.array_equal(preview,np.asarray(Image.open(folder/f'restart-{cycle}.png').convert('RGB'))), cycle
print('Small AppKit preview survives five detach/start/stop cycles')
for renderer in ('metal','saver'):
    first=np.asarray(Image.open(folder/f'surface-{renderer}-0.png'))
    last=np.asarray(Image.open(folder/f'surface-{renderer}-1200.png'))
    assert np.array_equal(first,last), f'Surface Scroll loop moved in {renderer}'
assert np.array_equal(np.asarray(Image.open(folder/'surface-saver-600.png')),
                      np.asarray(Image.open(folder/'surface-retina-bounds.png')))
metadata=json.loads((folder/'surface-crops.json').read_text())
source=Image.open(metadata['texture']).convert('RGB')
for origin in metadata['origins']:
    phase=int(origin['time'])
    metal=Image.open(folder/f'surface-metal-{phase}.png').convert('RGB')
    saver=Image.open(folder/f'surface-saver-{phase}.png').convert('RGB')
    assert metal.size==saver.size, (metal.size,saver.size)
    expected=source.transform(metal.size,Image.Transform.AFFINE,
                              (1,0,origin['x'],0,1,origin['y']),Image.Resampling.BILINEAR)
    actual=np.asarray(metal,dtype=float)
    reference=np.asarray(expected,dtype=float)
    delta=np.abs(actual-reference)
    assert delta.mean()<0.5 and np.percentile(delta,99)<=2, (phase,delta.mean(),delta.max())
    delta=np.abs(actual-np.asarray(saver,dtype=float))
    assert delta.mean()<0.5 and np.percentile(delta,99)<=2, (phase,delta.mean(),delta.max())
    print(f'Surface Scroll at phase {phase}: native 1:1 source crop and screensaver geometry verified')
    preview=np.asarray(Image.open(folder/f'surface-preview-{phase}.png').convert('RGB'))
    assert (preview.max(axis=2)>40).mean()>0.1, f'Surface Scroll preview is empty at {phase}'
print('Surface Scroll has identical loop endpoints and survives Retina bounds changes')
metadata=json.loads((folder/'peek-geometry.json').read_text())
source=Image.open(metadata['texture']).convert('RGB')
center_x,center_y=metadata['center_x'],metadata['center_y']
for phase in (0,300,600,900):
    metal=Image.open(folder/f'peek-metal-{phase}.png').convert('RGB')
    saver=Image.open(folder/f'peek-saver-{phase}.png').convert('RGB')
    angle=phase/1200*2*np.pi
    c,t=np.cos(angle),np.sin(angle)
    # Inverse rotation only, with unit-length axes and no source enlargement.
    expected=source.transform(metal.size,Image.Transform.AFFINE,
                              (c,t,source.width/2-c*center_x-t*center_y,
                               -t,c,source.height/2+t*center_x-c*center_y),Image.Resampling.BILINEAR)
    actual=np.asarray(metal,dtype=float)
    delta=np.abs(actual-np.asarray(expected,dtype=float))
    assert delta.mean()<0.5 and np.percentile(delta,99)<=2, (phase,delta.mean(),delta.max())
    delta=np.abs(actual-np.asarray(saver,dtype=float))
    assert delta.mean()<0.5 and np.percentile(delta,99)<=2, (phase,delta.mean(),delta.max())
    assert actual[:,:metal.width//10].max()<5, 'Solar Peek lost its quiet left sky'
    preview=np.asarray(Image.open(folder/f'peek-preview-{phase}.png').convert('RGB'))
    assert (preview.max(axis=2)>40).mean()>0.1, f'Solar Peek preview is empty at {phase}'
    print(f'Solar Peek at phase {phase}: fixed reference framing, native scale and screensaver geometry verified')
assert center_x>metal.width*0.7 and center_y>metal.height/2
for renderer in ('metal','saver'):
    first=np.asarray(Image.open(folder/f'peek-{renderer}-0.png'))
    last=np.asarray(Image.open(folder/f'peek-{renderer}-1200.png'))
    assert np.array_equal(first,last), f'Solar Peek loop moved in {renderer}'
    quarter=np.asarray(Image.open(folder/f'peek-{renderer}-300.png'))
    assert np.abs(first.astype(float)-quarter).mean()>5, f'Solar Peek did not rotate in {renderer}'
assert np.array_equal(np.asarray(Image.open(folder/'peek-saver-600.png')),
                      np.asarray(Image.open(folder/'peek-retina-bounds.png')))
preview=np.asarray(Image.open(folder/'peek-preview-600.png'))
for cycle in range(3):
    restarted=np.asarray(Image.open(folder/f'peek-restart-{cycle}.png'))
    delta=np.abs(preview.astype(float)-restarted)
    # AppKit may round isolated colour values on preview reattachment.
    assert delta.max()<=1 and delta.mean()<0.0001, (cycle,delta.mean(),delta.max())
print('Solar Peek loops seamlessly, rotates at native scale and survives preview restarts')
PY
