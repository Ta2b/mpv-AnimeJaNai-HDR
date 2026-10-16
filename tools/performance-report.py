#!/usr/bin/env python3
"""Export identified raw measurements; never infer percentiles from averages or rendering from inference."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import tempfile

SCOPES = {'network_resident', 'chain_offscreen', 'playback_presented'}
IDENTITY = ('media_sha256', 'models_sha256', 'settings_sha256', 'machine_id', 'runtime', 'driver', 'output_contract')
SESSION = ('desktop_load', 'player_state', 'power_mode')

def known_context(value):
    if not value: return False
    if isinstance(value, str): return value.strip().lower() not in ('unknown', 'not_measured', 'unavailable')
    if isinstance(value, dict): return all(known_context(v) for v in value.values())
    if isinstance(value, list): return all(known_context(v) for v in value)
    return True

def number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f'{label}: expected finite number >= {minimum}')
    return value

def distribution(values):
    if not values:
        return {'status': 'not_measured', 'count': 0}
    ordered = sorted(values)
    def percentile(p):
        index = (len(ordered)-1)*p; lo = math.floor(index); hi = math.ceil(index)
        return ordered[lo] + (ordered[hi]-ordered[lo])*(index-lo)
    return dict(status='observed', count=len(values), median=percentile(.5), p95=percentile(.95),
                p99=percentile(.99), maximum=ordered[-1], mean=statistics.fmean(values), unit='ms')

def measured(rows, field):
    values, excluded = [], {'compile': 0, 'warmup': 0, 'incomplete': 0}
    for row in rows:
        phase = row.get('phase')
        if phase not in ('measure', 'compile', 'warmup'):
            raise ValueError('Every sample must declare phase=measure/compile/warmup')
        if phase != 'measure': excluded[phase] += 1; continue
        if not isinstance(row.get('completed'), bool): raise ValueError('Sample completion must be explicit')
        if not row['completed']: excluded['incomplete'] += 1; continue
        values.append(number(row[field], field))
    return values, excluded

def load_trace(path):
    raw = path.read_bytes()
    trace = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON value: '+value)))
    if trace.get('schema') != 'animejanai.measurements.v1' or trace.get('scope') not in SCOPES:
        raise ValueError('Expected measurements.v1 with an explicit measurement scope')
    if trace.get('data_origin') not in ('measurement', 'fixture'): raise ValueError('Declare data_origin=measurement/fixture')
    missing_context = []
    for group, keys in [('identity', IDENTITY), ('session', SESSION)]:
        for key in keys:
            value = trace.setdefault(group, {}).get(key)
            if not known_context(value):
                missing_context.append(group+'.'+key)
    if not trace.get('provenance') or not trace.get('timing_source') or not trace.get('warmup_policy'):
        raise ValueError('Provenance, timing_source and warmup_policy must be explicit')
    wall = number(trace['window']['wall_seconds'], 'wall_seconds')
    media = number(trace['window']['media_seconds'], 'media_seconds')
    if wall == 0: raise ValueError('Measured wall window must be positive')
    if trace['window'].get('excludes_compile_warmup') is not True:
        raise ValueError('Measured wall/media window must explicitly exclude compilation and warmup')
    if not trace.get('sample_unit'): raise ValueError('Sample unit must be explicit')
    durations, excluded = measured(trace['samples'], 'duration_ms')
    if not durations: raise ValueError('No completed measurement samples; compilation/warmup are not measurements')
    pairs, excluded_pairs = measured(trace.get('pairs', []), 'cost_ms')
    resources = {}
    for key in ('allocations_count', 'peak_ram_bytes', 'peak_vram_bytes', 'energy_joules'):
        sample = trace.get('resources', {}).get(key)
        if sample is None: resources[key] = {'status': 'not_measured'}; continue
        if not sample.get('source'): raise ValueError(f'{key}: measurement source required')
        value = number(sample['value'], key)
        if key != 'energy_joules' and not isinstance(value, int): raise ValueError(f'{key}: integer count/bytes required')
        resources[key] = dict(status='observed', value=value, source=sample['source'])
    energy = resources['energy_joules']
    resources['average_watts'] = (dict(status='observed', value=energy['value']/wall, source=energy['source'])
                                  if energy['status']=='observed' else {'status': 'not_measured'})
    temperatures = trace.get('temperatures_celsius', [])
    thermal = {'status': 'not_measured', 'stability': 'not_established'}
    if temperatures:
        times, degrees = [], []
        for sample in temperatures:
            times.append(number(sample['wall_seconds'], 'temperature timestamp'))
            degrees.append(number(sample['value'], 'temperature Celsius', -273.15))
            if not sample.get('source'): raise ValueError('Temperature source required')
        if any(a >= b for a, b in zip(times, times[1:])) or times[-1] > wall:
            raise ValueError('Temperature timestamps must increase within the measured wall window')
        interval = times[-1]-times[0]
        thermal = dict(status='observed', samples=len(times), minimum_celsius=min(degrees), maximum_celsius=max(degrees),
            delta_celsius=degrees[-1]-degrees[0], sampled_seconds=interval,
            slope_celsius_per_second=(degrees[-1]-degrees[0])/interval if interval else None,
            stability='not_established', note='A sampled range/slope is not a certification of sustained thermal stability.')
    report = dict(scope=trace['scope'], data_origin=trace['data_origin'], identity=trace['identity'],
        provenance=trace['provenance'], session=trace['session'], timing_source=trace['timing_source'],
        comparable_context_complete=not missing_context, missing_context=missing_context,
        warmup_policy=trace['warmup_policy'], sample_unit=trace['sample_unit'], latency=distribution(durations),
        pair_cost=distribution(pairs), excluded_samples=excluded, excluded_pairs=excluded_pairs,
        window=trace['window'], media_seconds_per_wall_second=media/wall,
        resources=resources, thermal=thermal, quality_reported=trace.get('quality', {'status': 'not_measured'}),
        evidence=dict(filename=path.name, sha256=hashlib.sha256(raw).hexdigest()),
        limitations=['Throughput uses the explicit measured wall window, never a sum of overlapping durations.',
            'Pair costs are explicit collector measurements; no second multiplication by RIFE factor.',
            'Network/chain timing does not count physical display refreshes; presentation claims require separate evidence.',
            'Context and quality are reported by the input collector, not independently verified by this exporter.',
            'Percentiles use linear interpolation (R7); a short sample set is not a stability certification.'])
    return trace, report

def export(paths):
    loaded = [load_trace(path) for path in paths]
    result = dict(schema='animejanai.performance-report.v1',
        exporter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), runs=[report for _, report in loaded])
    if len(loaded) == 2:
        a, b = [trace for trace, _ in loaded]
        mismatches = []
        mismatches.extend(loaded[0][1]['missing_context']); mismatches.extend(loaded[1][1]['missing_context'])
        for key in ('scope', 'sample_unit', 'timing_source', 'warmup_policy'):
            if a[key] != b[key]: mismatches.append(key)
        for group, keys in [('identity', IDENTITY), ('session', SESSION)]:
            for key in keys:
                if a[group].get(key) != b[group].get(key): mismatches.append(group+'.'+key)
        if a['data_origin'] != b['data_origin']: mismatches.append('data_origin')
        if mismatches: raise ValueError('Incomparable measurements: '+', '.join(mismatches))
        ra, rb = result['runs']; median_before=ra['latency']['median']; median_after=rb['latency']['median']
        result['comparison'] = dict(comparable_context=True, latency_median_change_ms=median_after-median_before,
            latency_median_speed_ratio=median_before/median_after if median_after else None,
            media_throughput_change=rb['media_seconds_per_wall_second']-ra['media_seconds_per_wall_second'],
            gain_established=False, reason='Descriptive comparison only; noise, quality and causality require the recorded qualification decision.')
    return result

def write_new(path, value):
    path = path.absolute(); path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(path): raise FileExistsError('Destination exists; choose a new report filename')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.aji-report-', delete=False) as file:
            temporary = Path(file.name); json.dump(value, file, indent=2, allow_nan=False); file.write('\n')
            file.flush(); os.fsync(file.fileno())
        os.link(temporary, path) # atomic create-only publication; no overwrite of a competing writer
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('traces', type=Path, nargs='+'); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(args.traces) not in (1, 2): parser.error('Supply one trace or a before/after pair')
    try:
        if os.path.lexists(args.output): raise FileExistsError('Destination exists; choose a new report filename')
        write_new(args.output, export(args.traces))
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError) as error:
        parser.exit(1, 'Report not written: '+str(error)+'\n')

if __name__ == '__main__': main()
