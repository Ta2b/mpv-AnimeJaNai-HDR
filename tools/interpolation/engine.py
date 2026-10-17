"""Faithful external GMFSS Fortuna adapter; imports/runtime stay out of the UI."""
import importlib
import sys

class Fortuna:
    def __init__(self, job):
        import torch
        import cupy
        if not torch.cuda.is_available():raise RuntimeError('GMFSS Fortuna preparation requires a CUDA GPU and PyTorch CUDA runtime')
        if cupy.cuda.get_cuda_path() is None:raise RuntimeError('CuPy CUDA toolkit unavailable; no PyTorch splat fallback is substituted')
        torch.set_num_threads(1)
        torch.set_grad_enabled(False)
        torch.backends.cudnn.benchmark=True
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        torch.set_float32_matmul_precision('highest')
        sys.path.insert(0,str(job.model_source))
        module=importlib.import_module('model.GMFSS_infer_b')
        if not module.HAS_CUDA:raise RuntimeError('Official CUDA CuPy softsplat unavailable; inference refused')
        self.torch=torch;self.model=module.Model()
        self.model.load_model(str(job.weights),-1);self.model.eval();self.model.device()
        self.info={'torch':torch.__version__,'cupy':cupy.__version__,'cuda':torch.version.cuda,
                   'device':torch.cuda.get_device_name(),'precision':'FP32, TF32 disabled, scale1',
                   'softsplat':'original CUDA CuPy, no replacement'}
    def source(self,pixels):
        t=self.torch;h,w=pixels.shape[:2]
        value=t.from_numpy(pixels.copy()).permute(2,0,1).unsqueeze(0).cuda().float()/255
        return t.nn.functional.pad(value,(0,(-w)%64,0,(-h)%64))
    def pair(self,left,right):return self.model.reuse(left,right,1.0)
    def predict(self,left,right,pair,phase,width,height):
        value=self.model.inference(left,right,pair,float(phase))
        return value[0,:,:height,:width].permute(1,2,0).float().cpu().numpy()
    @staticmethod
    def pixels(value):
        import numpy as np
        if not np.isfinite(value).all():raise RuntimeError('GMFSS returned nonfinite pixels')
        # Same truncation as the official presentation path and acquired probe.
        return np.clip(value*255,0,255).astype(np.uint8)
