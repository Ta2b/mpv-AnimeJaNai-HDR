#!/usr/bin/env python3
"""Local, cancellable GMFSS preparation. No model downloads/media uploads.
One frame pair and its original prepared features live on GPU. Input and output
video are streamed. Destination is published only after complete validation.
"""
import argparse
from contextlib import ExitStack
from fractions import Fraction
import json
import os
import queue
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contract import Job,PreparationError,require,digest,probe

class Cancelled(Exception):pass
cancelled=threading.Event()
children=[]

def progress(state,**fields):
    print(json.dumps({'protocol':1,'state':state,**fields},ensure_ascii=False),flush=True)

def check_cancel():
    if cancelled.is_set():raise Cancelled('Preparation cancelled; original source and destination preserved')

def stop_children():
    for child in children:
        if child.poll() is None:
            try:child.terminate()
            except ProcessLookupError:pass
    deadline=time.monotonic()+2
    for child in children:
        try:child.wait(timeout=max(.01,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:child.kill();child.wait()

def launch(args,**kwargs):
    check_cancel();p=subprocess.Popen(args,**kwargs);children.append(p);check_cancel();return p

def rational(value):return f'{value.numerator}/{value.denominator}'

def read_frame(pipe,size):
    pieces=[];remaining=size
    while remaining:
        check_cancel();part=pipe.read(remaining)
        if not part:
            if remaining==size:return None
            raise PreparationError('Decoder returned a partial RGB frame')
        pieces.append(part);remaining-=len(part)
    return b''.join(pieces)

def decoder_args(job,media):
    # ffmpeg decodes source timing without frame duplication. Its explicit
    # input matrix/range is used; RGB is full-range for the neural reference.
    matrix={'gbr':'bt709','bt470bg':'bt601','smpte170m':'bt601','bt709':'bt709'}[media.matrix]
    scale=f'scale=in_color_matrix={matrix}:in_range={"full" if media.color_range=="pc" else "limited"}:out_range=full:flags=bilinear,format=rgb24'
    return [job.ffmpeg,'-v','error','-nostdin','-noautorotate','-i',str(job.source),'-map',f'0:{media.video_index}','-an','-sn','-dn','-fps_mode','passthrough','-vf',scale,'-f','rawvideo','-pix_fmt','rgb24','pipe:1']

def encoder_args(job,media,output):
    fps=media.fps*job.factor
    args=[job.ffmpeg,'-v','error','-nostdin','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{media.width}x{media.height}','-framerate',rational(fps),'-color_range','pc','-colorspace','0','-color_primaries',media.primaries,'-color_trc',media.transfer,'-i','pipe:0']
    if job.audio=='copy' and media.audio_streams:
        # Video is normalized to zero. Apply the identical offset to copied
        # source audio, keeping its original relation to the first video PTS.
        args+=['-copyts','-itsoffset',f'{-float(media.first_pts):.12f}','-i',str(job.source),'-map','0:v:0','-map','1:a?','-c:a','copy']
    else:args+=['-map','0:v:0','-an']
    args+=['-fps_mode','passthrough','-enc_time_base',rational(1/fps),'-color_primaries',media.primaries,'-color_trc',media.transfer]
    if job.output_codec=='lossless-rgb':
        args+=['-c:v','ffv1','-level','3','-pix_fmt','bgr0','-colorspace','0','-color_range','pc']
    else:
        matrix={'bt470bg':'bt601','smpte170m':'bt601'}.get(media.matrix,'bt709')
        args+=['-vf',f'scale=in_range=full:out_range=limited:out_color_matrix={matrix}:flags=bilinear,format=yuv444p10le',
               '-c:v','libx265','-preset','medium','-profile:v','main444-10','-x265-params','lossless=1:repeat-headers=1:log-level=error:pools=2:frame-threads=1',
               '-pix_fmt','yuv444p10le','-colorspace',media.matrix if media.matrix!='gbr' else 'bt709','-color_range','tv']
    args+=['-avoid_negative_ts','disabled','-f','nut' if job.destination.suffix.lower()=='.nut' else 'matroska','-y',str(output)]
    return args

def checked_output(args):
    """Cancellable metadata query; this short query never decodes the whole film."""
    child=launch(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    deadline=time.monotonic()+120
    while True:
        check_cancel()
        require(time.monotonic()<deadline,"Output metadata probe did not finish within120seconds")
        try:
            output,error=child.communicate(timeout=.2)
            require(child.returncode==0,'Output probe failed: '+error.decode(errors='replace')[-4096:])
            return output
        except subprocess.TimeoutExpired:
            continue

def count_output_frames(job,output):
    # Streaming frame metadata gives real progress on a long file. The timeout
    # bounds inactivity, not total film length; cancellation owns this child too.
    args=[job.ffprobe,'-v','error','-select_streams','v:0','-show_frames',
          '-show_entries','frame=media_type','-of','compact=p=0:nk=0',str(output)]
    child=launch(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    lines=queue.Queue(maxsize=64)
    def drain():
        try:
            for line in child.stdout:
                while child.poll() is None or not cancelled.is_set():
                    try:lines.put(line,timeout=.2);break
                    except queue.Full:
                        if cancelled.is_set():return
        finally:
            while not cancelled.is_set():
                try:lines.put(None,timeout=.2);break
                except queue.Full:pass
    threading.Thread(target=drain,daemon=True).start()
    count=0;last=time.monotonic()
    while True:
        check_cancel()
        try:line=lines.get(timeout=.2)
        except queue.Empty:
            require(time.monotonic()-last<120,'Output verification stopped making progress for120seconds')
            continue
        if line is None:break
        last=time.monotonic()
        if line.startswith("media_type=video"):
            count+=1
            if count%256==0:progress('validating',message=f'Checking prepared video: {count} frames verified')
    require(child.wait()==0,'Could not verify prepared video frames')
    return count

def check_publication(parent):
    # Refuse unsupported filesystems before loading a GPU model or encoding.
    # Final publication still uses exclusive hard-link creation and never
    # replaces a destination that appeared while the job was running.
    with tempfile.TemporaryDirectory(prefix='.animejanai-publication-',dir=parent) as directory:
        source=Path(directory)/'probe';source.write_bytes(b'')
        try:os.link(source,Path(directory)/'linked')
        except OSError as e:raise PreparationError('Choose a destination filesystem supporting atomic publication (for example NTFS or ext4): '+str(e)) from e

def validate_output(job,media,output):
    progress('validating',message='Verifying prepared video before publication')
    data=json.loads(checked_output([job.ffprobe,'-v','error','-show_streams','-of','json',str(output)]))
    videos=[s for s in data['streams'] if s['codec_type']=='video'];require(len(videos)==1,'Prepared output has unexpected streams')
    s=videos[0];require(count_output_frames(job,output)==media.source_frames*job.factor,'Prepared output frame count differs from exact schedule')
    require((int(s['width']),int(s['height']))==(media.width,media.height),'Prepared output geometry changed')
    require(Fraction(s['avg_frame_rate'])==media.fps*job.factor,'Prepared output cadence changed')
    require(s.get('color_transfer')==media.transfer and s.get('color_primaries')==media.primaries,'Prepared output lost SDR color metadata')
    expected_audio=media.audio_streams if job.audio=='copy' else 0
    require(len([s for s in data['streams'] if s['codec_type']=='audio'])==expected_audio,'Prepared audio stream count differs from requested policy')
    return {'output_frames':media.source_frames*job.factor,'fps':rational(media.fps*job.factor),'streams':data['streams'],
            'timestamp_policy':'Source CFR rational grid normalized to first video PTS; container timestamp quantization declared',
            'end_policy':'Final source held for its full original duration; no extrapolated future predictions'}

def prepare(job,job_id="standalone"):
    check_cancel();check_publication(job.destination.parent);progress('checking',message='Checking pinned source, weights and source timing')
    info=job.source.stat();source_view=(info.st_size,info.st_mtime_ns)
    identity=job.identity();media=probe(job,spawn=launch,check=check_cancel,metadata=checked_output);check_cancel()
    info=job.source.stat();require((info.st_size,info.st_mtime_ns)==source_view,'Source changed during preflight')
    from engine import Fortuna
    import numpy as np
    progress('initializing',source_frames=media.source_frames,factor=job.factor,message='Loading original FP32 GMFSS and CUDA CuPy softsplat')
    model=Fortuna(job);check_cancel()
    # Private same-filesystem staging keeps existing destination/source intact.
    with tempfile.TemporaryDirectory(prefix='.animejanai-prepare-'+job_id+'-',dir=job.destination.parent) as directory:
        temporary=Path(directory);video=temporary/('video'+job.destination.suffix)
        (temporary/'job-owner').write_text(job_id)
        progress('staging',staging=str(temporary))
        with ExitStack() as stack:
            decode_log=stack.enter_context((temporary/'decode.log').open('w+b'));encode_log=stack.enter_context((temporary/'encode.log').open('w+b'))
            decode=launch(decoder_args(job,media),stdout=subprocess.PIPE,stderr=decode_log)
            encode=launch(encoder_args(job,media,video),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=encode_log)
            size=media.width*media.height*3
            left_bytes=read_frame(decode.stdout,size);require(left_bytes is not None,'Decoder returned no frames')
            left=np.frombuffer(left_bytes,np.uint8).reshape(media.height,media.width,3);left_gpu=model.source(left)
            count=0;predictions=0
            try:
                for i in range(media.source_frames):
                    check_cancel();right_bytes=read_frame(decode.stdout,size) if i+1<media.source_frames else None
                    require(i+1==media.source_frames or right_bytes is not None,'Decoder ended before validated source timing')
                    right=np.frombuffer(right_bytes,np.uint8).reshape(media.height,media.width,3) if right_bytes is not None else None
                    right_gpu=model.source(right) if right is not None else None
                    pair=model.pair(left_gpu,right_gpu) if right is not None else None
                    for phase in range(job.factor):
                        check_cancel()
                        if phase==0 or right is None:pixels=left
                        else:
                            value=model.predict(left_gpu,right_gpu,pair,Fraction(phase,job.factor),media.width,media.height)
                            pixels=model.pixels(value);predictions+=1
                        try:encode.stdin.write(pixels.tobytes())
                        except BrokenPipeError:
                            encode_log.flush();encode_log.seek(0);raise PreparationError('Encoder failed: '+encode_log.read()[-8192:].decode(errors='replace'))
                        count+=1
                    progress('running',source_completed=i+1,source_total=media.source_frames,output_frames=count,predictions=predictions)
                    del pair
                    if right is not None:left,left_gpu=right,right_gpu
                require(read_frame(decode.stdout,size) is None,'Decoder returned more frames than preflight')
                decode.stdout.close();require(decode.wait()==0,'Video decoder failed')
                encode.stdin.close();require(encode.wait()==0,'Video encoder failed')
            finally:
                stop_children()
            check_cancel();stat=job.source.stat();require((stat.st_size,stat.st_mtime_ns)==source_view,'Source changed during preparation; output not published')
            result=validate_output(job,media,video)
            result.update(identity=identity,runtime=model.info,source_media=media.json(),output_codec=job.output_codec,
                          output_conversion='RGB8 presentation preserved losslessly' if job.output_codec=='lossless-rgb' else 'RGB8 to YUV44410 SDR, lossless HEVC after conversion; conversion quantization is explicit',
                          audio_policy=job.audio,predictions=predictions,output_sha256=digest(video),passed=True)
            check_cancel()
            # Atomic non-overwriting publication. A different file appearing
            # during the job is preserved; no destructive rename fallback.
            try:os.link(video,job.destination)
            except FileExistsError:raise PreparationError('Destination appeared during preparation; existing file preserved')
            except OSError as e:raise PreparationError('Cannot publish atomically on destination filesystem: '+str(e)) from e
            progress('complete',destination=str(job.destination),result=result)
            return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('spec');parser.add_argument('--inspect',action='store_true');parser.add_argument('--cancel-file');parser.add_argument('--job-id',default='standalone');args=parser.parse_args()
    require(args.job_id.isalnum() and len(args.job_id)<=64,'Invalid job identity')
    if args.cancel_file:
        def monitor():
            while not cancelled.wait(.1):
                if Path(args.cancel_file).exists():cancelled.set();stop_children();return
        threading.Thread(target=monitor,daemon=True).start()
    values=json.loads(Path(args.spec).read_text());job=Job.read(values)
    if args.inspect:
        check_publication(job.destination.parent)
        progress('inspected',identity=job.identity(),media=probe(job,spawn=launch,check=check_cancel,metadata=checked_output).json(),note='No inference or hardware availability validation');return 0
    prepare(job,args.job_id);return 0

if __name__=='__main__':
    def terminate(signum,frame):
        cancelled.set();raise Cancelled('Preparation cancelled')
    for name in ['SIGTERM','SIGINT']:
        if hasattr(signal,name):signal.signal(getattr(signal,name),terminate)
    try:sys.exit(main())
    except Cancelled as e:progress('cancelled',message=str(e));sys.exit(130)
    except Exception as e:progress('cancelled' if cancelled.is_set() else 'failed',message=str(e));sys.exit(130 if cancelled.is_set() else 1)
    finally:stop_children()
