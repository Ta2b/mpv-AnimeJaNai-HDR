#!/usr/bin/env python3
"""FP32 independent pixel oracle, same-context size replacement, malformed output refusal."""
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import onnx
from onnx import helper, TensorProto, numpy_helper

names = ['cpu_memory_descriptors', 'tensor_descriptors', 'owned_shape_handles',
         'null_output_requests', 'runs', 'borrowed_shape_queries']

def child(s):
    lib = C.CDLL(s['library']); pointer = C.c_void_p; bytep = C.POINTER(C.c_ubyte)
    class Plan(C.Structure):
        _fields_ = [(n, C.c_int) for n in ['width', 'height', 'numerator', 'denominator', 'active']]
    lib.aji_vk_create.argtypes = [C.c_char_p] * 5 + [C.c_int]; lib.aji_vk_create.restype = pointer
    lib.aji_vk_configure.argtypes = [pointer, C.c_int, C.c_int, C.c_double, C.POINTER(Plan)]
    lib.aji_vk_process.argtypes = [pointer, bytep, C.c_ssize_t, bytep, C.c_ssize_t, C.c_double, bytep, C.c_ssize_t]
    lib.aji_vk_destroy.argtypes = [pointer]
    lib.aji_vk_error.argtypes = [pointer]; lib.aji_vk_error.restype = C.c_char_p
    counter = C.CDLL(None).aji_test_ort_counters; counter.argtypes = [C.POINTER(C.c_uint64)]
    def snapshot():
        v = (C.c_uint64 * 6)(); counter(v); return np.array(list(v), dtype=np.int64)
    out = Path(s['output']); arrays = {}; rows = []
    conf = out / ('bad.conf' if s.get('bad') else 'good.conf')
    ctx = lib.aji_vk_create(os.fsencode(conf), os.fsencode(out / 'models'), os.fsencode(out / 'models'), b'cpu', None, 1)
    assert ctx, lib.aji_vk_error(None)
    try:
        for w, h in ([(64, 32)] if s.get('bad') else [(64, 32), (80, 48)]):
            plan = Plan()
            assert lib.aji_vk_configure(ctx, w, h, 24, C.byref(plan)) == 0, lib.aji_vk_error(ctx)
            assert (plan.width, plan.height, plan.numerator, plan.denominator) == (2*w, 2*h, 1, 1)
            source = np.full((h, 3*w+13), 0xA5, np.uint8)
            y, x, ch = np.indices((h, w, 3))
            source[:, :3*w] = ((x*3+y*7+ch*17) % 256).astype(np.uint8).reshape(h, 3*w)
            expected = np.repeat(np.repeat(source[:, :3*w].reshape(h,w,3), 2, 0), 2, 1).reshape(2*h,6*w)
            result = np.full((2*h, 6*w+11), 0xA5, np.uint8)
            def process():
                return lib.aji_vk_process(ctx, None, 0, source.ctypes.data_as(bytep), source.strides[0],
                    1, result.ctypes.data_as(bytep), result.strides[0])
            status = process()
            if s.get('bad'):
                assert status < 0 and np.all(result == 0xA5)
                error = lib.aji_vk_error(ctx).decode(); assert error
                rows.append(dict(geometry=[w,h], refused=True, destination_untouched=True, error=error))
            else:
                assert status == 0, lib.aji_vk_error(ctx)
                assert np.array_equal(result[:, :6*w], expected) and np.all(result[:, 6*w:] == 0xA5)
                # A distinct next source exercises the hot path rather than source-result reuse.
                source[:, :3*w] = (source[:, :3*w].astype(np.uint16)+19).astype(np.uint8)
                expected = np.repeat(np.repeat(source[:, :3*w].reshape(h,w,3),2,0),2,1).reshape(2*h,6*w)
                before = snapshot(); assert process() == 0, lib.aji_vk_error(ctx)
                calls = dict(zip(names,(snapshot()-before).tolist()))
                assert np.array_equal(result[:, :6*w], expected) and np.all(result[:, 6*w:] == 0xA5)
                arrays[f'{w}x{h}'] = result[:, :6*w].copy()
                rows.append(dict(geometry=[w,h], independent_nearest_2x_oracle=True, stride_padding_untouched=True, ort_api_calls=calls))
    finally:
        lib.aji_vk_destroy(ctx)
    np.savez(out / (s['label']+'.npz'), **arrays)
    (out / (s['label']+'.json')).write_text(json.dumps(dict(passed=True,cases=rows),indent=2)+'\n')

def parent(s):
    out = Path(s['output']); out.mkdir(parents=True,exist_ok=True); (out/'models').mkdir(exist_ok=True)
    receipt = out/'summary.json'
    if receipt.exists():
        assert json.loads(receipt.read_text())['passed']; print('Conclusive receipt exists; no repeat.'); return
    for label, scale in [('good',2),('bad',3)]:
        inp=helper.make_tensor_value_info('input',TensorProto.FLOAT,[1,3,'height','width'])
        result=helper.make_tensor_value_info('output',TensorProto.FLOAT,[1,3,'out_height','out_width'])
        node=helper.make_node('Resize',['input','','scales'],['output'],mode='nearest',coordinate_transformation_mode='asymmetric',nearest_mode='floor')
        graph=helper.make_graph([node],'fp32_geometry',[inp],[result],[numpy_helper.from_array(np.array([1,1,scale,scale],np.float32),'scales')])
        model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',13)]); model.ir_version=10
        onnx.checker.check_model(model); onnx.save(model,out/'models'/(label+'.onnx'))
        (out/(label+'.conf')).write_text('[global]\nbackend=CPU\nengine_reuse=off\nengine_boost=no\n[slot_1]\nchain_1_model_1_name='+label+'\n')
    rows={}
    for case in ['good','bad']:
        for treatment in ['before','after']:
            label=case+'-'+treatment; path=out/(label+'.json')
            if not path.exists():
                spec=dict(s,bad=case=='bad',label=label); spec_path=out/(label+'.spec.json')
                spec_path.write_text(json.dumps(spec,indent=2)+'\n')
                with (out/(label+'.log')).open('w') as log:
                    p=subprocess.run([sys.executable,__file__,str(spec_path),'--child'],
                        env=dict(os.environ,AJI_ORT_PROVIDER='cpu',AJI_ORT_REUSE_BINDINGS='0' if treatment=='before' else '1',
                            AJI_TEST_ORT_LIBRARY=s['ort_runtime'],LD_LIBRARY_PATH=s['runtime'],LD_PRELOAD=s['interposer']),
                        stdout=log,stderr=subprocess.STDOUT,timeout=30)
                assert p.returncode==0,(out/(label+'.log')).read_text()[-3500:]
            rows[label]=json.loads(path.read_text())
    a=np.load(out/'good-before.npz'); b=np.load(out/'good-after.npz')
    assert a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
    for before,after in zip(rows['good-before']['cases'],rows['good-after']['cases']):
        for k in names[:4]: assert before['ort_api_calls'][k]>0 and after['ort_api_calls'][k]==0
        assert after['ort_api_calls']['borrowed_shape_queries']==1
    summary=dict(passed=True,fp32_geometries=2,same_context_reconfigured=True,changed_bytes=0,
        malformed_scale_refused_off_on=True,malformed_destination_untouched=True,results=rows)
    receipt.write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary,indent=2))

if __name__=='__main__':
    spec=json.loads(Path(sys.argv[1]).read_text())
    child(spec) if '--child' in sys.argv else parent(spec)
