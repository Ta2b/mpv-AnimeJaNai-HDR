#!/usr/bin/env python3
"""Preparation job v1: bounded media preflight, identities and exact CFR timeline.
No inference libraries are imported here. Execution/Manager are separate parts
of AH-313; a successful preflight is not an available interpolation provider.
"""
from dataclasses import dataclass,asdict
from fractions import Fraction
import hashlib,json
from pathlib import Path
import subprocess

class PreparationError(ValueError):pass

def require(value,message):
    if not value:raise PreparationError(message)

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(2*1024*1024):h.update(b)
    return h.hexdigest()

@dataclass(frozen=True)
class Job:
    source:Path
    destination:Path
    model_source:Path
    weights:Path
    factor:int
    ffmpeg:str
    ffprobe:str
    audio:str
    output_codec:str
    @classmethod
    def read(cls,values):
        require(values.get('version')==1,'Unsupported preparation job version')
        require(values.get('method')=='gmfss-fortuna','Preparation method not implemented')
        known={'version','method','source','destination','model_source','weights','factor','ffmpeg','ffprobe','audio','output_codec'}
        require(not set(values)-known,'Unknown preparation job options')
        factor=values.get('factor',2)
        require(type(factor) is int and 2<=factor<=8,'GMFSS factor must be integer2..8')
        paths={k:Path(values[k]).expanduser().resolve(strict=k!='destination') for k in ['source','destination','model_source','weights']}
        require(paths['source'].is_file(),'Source must be an existing local video')
        require(paths['destination']!=paths['source'],'Destination cannot replace the input')
        require(not paths['destination'].exists(),'Destination exists; choose a new output')
        require(paths['destination'].suffix.lower() in ['.nut','.mkv'],'Prepared output requires .mkv or .nut')
        require(paths['destination'].parent.is_dir(),'Destination folder does not exist')
        require(paths['model_source'].is_dir() and paths['weights'].is_dir(),'Model source/weights folders missing')
        audio=values.get('audio','copy');require(audio in ['copy','drop'],'Audio requires explicit copy/drop')
        codec=values.get('output_codec','lossless-rgb');require(codec in ['lossless-rgb','hevc44410-sdr'],'Unknown prepared output codec')
        require(codec!='lossless-rgb' or paths['destination'].suffix.lower()=='.mkv','Lossless RGB requires Matroska to preserve SDR color metadata')
        return cls(**paths,factor=factor,ffmpeg=str(values.get('ffmpeg','ffmpeg')),ffprobe=str(values.get('ffprobe','ffprobe')),audio=audio,output_codec=codec)
    def identity(self):
        manifest=json.loads(Path(__file__).with_name('gmfss-fortuna.json').read_text())
        found={}
        for key,expected in manifest['sha256'].items():
            prefix,relative=key.split('/',1);root=self.model_source if prefix=='source' else self.weights
            path=root/relative;require(path.is_file(),'Missing pinned model file: '+key)
            value=digest(path);require(value==expected,'Pinned model file differs: '+key);found[key]=value
        return dict(method='gmfss-fortuna',revision=manifest['revision'],files=found,
                    precision='FP32, TF32 disabled, scale1; original CuPy softsplat',
                    input='decoded RGB8/full, float32 divided by255; right/bottom pad64',
                    output='official clamped RGB8 truncation; SDR preparation, not RIFE Quality equivalence',
                    source_fingerprint=digest(self.source))

@dataclass(frozen=True)
class Media:
    width:int
    height:int
    fps:Fraction
    timebase:Fraction
    first_pts:Fraction
    source_frames:int
    duration:Fraction
    audio_streams:int
    matrix:str
    transfer:str
    primaries:str
    color_range:str
    video_index:int=0
    def json(self):
        return {k:str(v) if isinstance(v,Fraction) else v for k,v in asdict(self).items()}

def validate_cfr(frames,fps,timebase,width,height):
    require(fps>0 and timebase>0,'Known positive source cadence/timebase required')
    first=None;count=0;period=1/fps;tolerance=timebase/2
    for frame in frames:
        require(int(frame.get('width',width))==width and int(frame.get('height',height))==height,'Mid-stream size changes unavailable')
        raw=frame.get('best_effort_timestamp')
        require(raw not in (None,'N/A'),'Frame PTS missing')
        pts=int(raw)*timebase
        if first is None:first=pts
        require(abs(pts-(first+count*period))<=tolerance,'VFR/discontinuous timestamps unavailable; input remains unchanged')
        # Container packet durations may be truncated to one timestamp tick,
        # while the PTS grid above remains bounded to half a tick.
        duration=frame.get('duration',frame.get('pkt_duration'))
        require(duration not in (None,'N/A','0') and abs(int(duration)*timebase-period)<=timebase,'Frame duration differs from declared CFR')
        count+=1
    require(count>0,'No decoded frames')
    return first,count,count*period

def probe(job,spawn=None,check=lambda:None,metadata=None):
    check()
    query=[job.ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(job.source)]
    data=json.loads(metadata(query) if metadata else subprocess.check_output(query,timeout=30))
    check()
    videos=[s for s in data['streams'] if s['codec_type']=='video' and not s.get('disposition',{}).get('attached_pic')]
    require(len(videos)==1,'Choose a file with one ordinary video stream')
    s=videos[0];width=int(s['width']);height=int(s['height']);require(width>0 and height>0,'Invalid geometry')
    require(s.get('pix_fmt') in ['yuv420p','yuv422p','yuv444p','nv12','rgb24','bgr24','gbrp','bgr0','rgb0','rgba','bgra'],'Preparation currently accepts only SDR8bit input; no hidden precision reduction')
    require(s.get('color_transfer') in ['bt709','bt470bg','smpte170m','bt2020-10','iec61966-2-1','gamma22','gamma28'],'Known SDR transfer required; PQ/HLG/unknown refused')
    require(s.get('color_space') in ['bt709','bt470bg','smpte170m','gbr'],'Known601/709/RGB matrix required')
    require(s.get('color_primaries') in ['bt709','bt470bg','smpte170m','bt470m'],'Known SDR primaries required')
    require(s.get('color_range') in ['tv','pc'],'Known full/limited source range required')
    require(s.get('tags',{}).get('rotate','0') in ['0','0.0'] and not any(float(x.get('rotation',0)) for x in s.get('side_data_list',[])),'Rotated sources unavailable')
    require(s.get('sample_aspect_ratio','1:1') in ['1:1','0:1','N/A'],'Non-square pixels currently unavailable')
    try:fps=Fraction(s['avg_frame_rate']);tb=Fraction(s['time_base'])
    except (KeyError,ValueError,ZeroDivisionError) as e:raise PreparationError('Missing exact source cadence/timebase') from e
    args=[job.ffprobe,'-v','error','-select_streams',str(s['index']),'-show_frames','-show_entries','frame=best_effort_timestamp,duration,pkt_duration,width,height','-of','compact=p=0:nk=0',str(job.source)]
    # Metadata is streamed one frame at a time. Never retain a movie-size frame
    # array merely to establish its cadence. stderr is bounded to ffprobe errors.
    with (spawn or subprocess.Popen)(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True) as process:
        def frames():
            for line in process.stdout:
                check()
                fields=dict(part.split('=',1) for part in line.strip().split('|') if '=' in part)
                if 'best_effort_timestamp' in fields:yield fields
        try:first,count,duration=validate_cfr(frames(),fps,tb,width,height)
        except BaseException:
            process.terminate();process.wait();raise
        check()
        require(process.wait()==0,'Could not read source frame timing')
    audio=[x for x in data['streams'] if x['codec_type']=='audio']
    return Media(width,height,fps,tb,first,count,duration,len(audio),s['color_space'],s['color_transfer'],s['color_primaries'],s['color_range'],int(s['index']))

def timeline(media,factor):
    """Exact output schedule. Final holds preserve the last source duration.
    The final repeated frames are holds, never invented future predictions.
    """
    period=1/media.fps
    for i in range(media.source_frames):
        for phase in range(factor):
            yield {'source':i,'next':i+1 if i+1<media.source_frames else None,
                   'phase':Fraction(phase,factor), 'pts':media.first_pts+i*period+phase*period/factor,
                   'duration':period/factor,'kind':'original' if phase==0 else 'hold' if i==media.source_frames-1 else 'synthesized'}
