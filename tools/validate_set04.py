#!/usr/bin/env python3
"""Slice the Set 04 revision and inspect actual deposited toolpaths.

Requires Pillow for the independent raster footprint and toolpath checks.
Run with the local Codex Python runtime if the system Python lacks Pillow.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image, ImageChops, ImageDraw

import rebuild_set04 as build
from repair_v1_1 import read_parts
from validate_bambu import bambu_command

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / 'validation' / build.SET.name / build.VERSION


def footprints():
    contours = json.loads((build.DEST/'footprints.json').read_text())
    masks = []
    for loops in contours:
        im = Image.new('1', (4400, 2100))
        for loop in sorted(loops, key=lambda c: abs(build.area(c)), reverse=True):
            ImageDraw.Draw(im).polygon([(x*50, (41-y)*50) for x, y in loop], fill=255 if build.area(loop)>0 else 0)
        masks.append(im)
    unsupported = ImageChops.logical_and(ImageChops.logical_or(masks[1], masks[2]), ImageChops.invert(masks[0]))
    overlap = ImageChops.logical_and(masks[1], masks[2])
    assert unsupported.getbbox() is None, 'letter footprint extends beyond its backing'
    assert overlap.getbbox() is None, 'gold and blue volumes overlap'
    bore = [max(p[k] for p in contours[0][1])-min(p[k] for p in contours[0][1]) for k in range(2)]
    assert all(abs(value-5.5)<1e-7 for value in bore)
    return dict(resolution_mm=.02, unsupported_letter_pixels=0, colour_overlap_pixels=0, hole_extents_mm=bore)


def mesh_checks(project):
    with zipfile.ZipFile(project) as archive:
        assert archive.testzip() is None
        data = {n: archive.read(n) for n in archive.namelist()}
    parts = read_parts(data)
    with zipfile.ZipFile(build.SOURCE) as archive:
        assert data['Metadata/project_settings.config'] == archive.read('Metadata/project_settings.config')
    volumes = []
    for part in parts:
        volume = 0
        for face in part['faces']:
            a, b, c = [part['vertices'][i] for i in face]
            u, v = [b[k]-a[k] for k in range(3)], [c[k]-a[k] for k in range(3)]
            cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            assert sum(x*x for x in cross) > 1e-22, 'degenerate triangle'
            volume += (a[0]*(b[1]*c[2]-b[2]*c[1]) + a[1]*(b[2]*c[0]-b[0]*c[2]) + a[2]*(b[0]*c[1]-b[1]*c[0]))/6
        assert volume > 0
        volumes.append(volume)
    base = parts[0]
    assert max(v[2] for v in base['vertices'] if v[0] <= 10.5) == 1.6
    assert min(v[2] for v in base['vertices']) == 0
    assert max(v[2] for v in base['vertices']) == 2
    assert all(abs(v[2]-2)<1e-7 or abs(v[2]-2.8)<1e-7 for part in parts[1:] for v in part['vertices'])
    return dict(closed_manifold_parts=3, positive_volumes_mm3=volumes, degenerate_triangles=0,
                eyelet_thickness_mm=1.6, full_backing_thickness_mm=2, process_settings_unchanged=True)


def revision_checks(project):
    if build.VERSION != 'v1.4':
        return None
    previous = build.SET/'v1.3/Set_04_Ursulas_Return_v1.3.3mf'
    packages = []
    for path in (previous, project):
        with zipfile.ZipFile(path) as archive:
            packages.append({n: archive.read(n) for n in archive.namelist()})
    old_parts, new_parts = map(read_parts, packages)
    assert old_parts[0] == new_parts[0], 'backing or attachment geometry changed'
    assert old_parts[2] == new_parts[2], 'RETURN geometry changed'
    assert packages[0]['Metadata/project_settings.config'] == packages[1]['Metadata/project_settings.config']
    paths = []
    for name in ('set04_clean_letters.svg', 'set04_clean_letters_v1_4.svg'):
        svg = ET.parse(Path(__file__).with_name(name)).getroot()
        paths.append({p.get('id'): p.get('d') for p in svg.findall('.//{http://www.w3.org/2000/svg}path')})
    assert paths[0].keys() == paths[1].keys()
    changed = [k for k in paths[0] if paths[0][k] != paths[1][k]]
    assert changed == ['ursula-r', 'ursula-a']
    def spans(path, pixel_y):
        y = 2.7+(665-pixel_y)*40/336/2
        loops = build.svg_loops(path)
        x = sorted(a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])
                   for loop in loops for a,b in zip(loop,loop[1:]+loop[:1]) if (a[1]>y)!=(b[1]>y))
        return list(zip(x[::2],x[1::2]))
    r_widths = [spans(paths[1]['ursula-r'], y)[0][1]-spans(paths[1]['ursula-r'], y)[0][0] for y in (340,360,380,400)]
    probe = 14.36+(948.5-67)*40/336/2
    a_widths = [next(right-left for left,right in spans(paths[1]['ursula-a'], y) if left<probe<right) for y in (190,210,230,250,260)]
    assert min(r_widths)>2.6
    assert min(a_widths)>1.3
    return dict(changed_letters=changed, backing_and_attachment_mesh_exactly_unchanged=True,
                return_mesh_exactly_unchanged=True, other_letter_paths_exactly_unchanged=True,
                r_leg_width_mm=round(min(r_widths),4), a_upper_stroke_min_sampled_width_mm=round(min(a_widths),4))


def render_toolpaths(path, output):
    """Composite the last eyelet, backing and letter layers from actual G-code.

    Interpret relative extrusion, absolute XY and I/J arcs. Ignore custom
    machine commands and purge paths outside the object's bounding box.
    """
    scale, margin = 32, 60
    width, height = math.ceil(86.465*scale)+2*margin, 41*scale+2*margin
    im = Image.new('RGB', (width, height), '#404443')
    draw = ImageDraw.Draw(im)
    colors = ('#583B83', '#F2C547', '#9BC8DE')
    x, y, tool, nominal, line_width, feature = 0, 0, 0, 0, .42, 'Custom'
    relative, previous_e = True, 0
    layers = {1.6: [], 2.0: [], 2.8: []}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith('; Z_HEIGHT:'):
            nominal = round(float(line.split(':', 1)[1]), 3)
        elif line.startswith('; LINE_WIDTH:'):
            line_width = float(line.split(':', 1)[1])
        elif line.startswith('; FEATURE:'):
            feature = line.split(':', 1)[1].strip()
        elif re.fullmatch(r'T\d+', line):
            # T1000 is an A1 machine macro, not a filament change.
            if int(line[1:]) in range(3):
                tool = int(line[1:])
        elif line in ('M82', 'M83'):
            relative = line == 'M83'
        command = line.split(';', 1)[0].split()
        if not command:
            continue
        values = {key: float(val) for key, val in re.findall(r'([XYZEFIJP])\s*([-+]?(?:\d*\.\d+|\d+))', ' '.join(command[1:]))}
        if command[0] == 'G92':
            previous_e = values.get('E', previous_e)
        if command[0] not in ('G0', 'G1', 'G2', 'G3'):
            continue
        end = values.get('X', x), values.get('Y', y)
        extrusion = values.get('E', 0) if relative else values.get('E', previous_e)-previous_e
        if not relative:
            previous_e = values.get('E', previous_e)
        if extrusion>0 and ('X' in values or 'Y' in values) and nominal in layers and tool in range(3) and feature not in ('Custom', 'Prime tower'):
            points = [(x, y), end]
            if command[0] in ('G2', 'G3') and ('I' in values or 'J' in values):
                cx, cy = x+values.get('I', 0), y+values.get('J', 0)
                radius = math.hypot(x-cx, y-cy)
                start = math.atan2(y-cy, x-cx)
                stop = math.atan2(end[1]-cy, end[0]-cx)
                sweep = (stop-start) % math.tau if command[0] == 'G3' else -((start-stop) % math.tau)
                steps = max(2, math.ceil(abs(sweep)*radius/.05))
                points = [(cx+radius*math.cos(start+sweep*i/steps), cy+radius*math.sin(start+sweep*i/steps)) for i in range(steps+1)]
            if all(84.6<=px<=171.5 and 107.3<=py<=148.7 for px, py in points):
                layers[nominal].append((points, line_width, tool))
        x, y = end
    for z, paths in layers.items():
        assert paths, f'missing toolpaths at Z={z}'
        for points, line_width, tool in paths:
            projected = [(margin+(x-84.77)*scale, margin+(148.5-y)*scale) for x, y in points]
            stroke = max(1, round(line_width*scale))
            draw.line(projected, fill=colors[tool], width=stroke, joint='curve')
            # Each G-code segment deposits a continuous rounded bead. Pillow
            # otherwise leaves artificial triangular gaps at segment joins.
            radius = stroke/2
            for x, y in (projected[0], projected[-1]):
                draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=colors[tool])
    im = im.resize((1600, round(im.height*1600/im.width)), Image.Resampling.LANCZOS)
    im.save(output)
    return {str(z): len(paths) for z, paths in layers.items()}


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    project = build.project_path()
    report = dict(filename=project.name, sha256=hashlib.sha256(project.read_bytes()).hexdigest(),
                  geometry=mesh_checks(project), footprints=footprints())
    report['revision_scope'] = revision_checks(project)
    command = bambu_command()
    run = subprocess.run(command+['--datadir', '/tmp/lorcana-set04-settings', '--debug', '2', '--info', '--slice', '1', '--outputdir', str(LOGS), str(project)], capture_output=True, text=True, timeout=180)
    log = run.stdout+run.stderr
    (LOGS/'slice.log').write_text(log)
    result = json.loads((LOGS/'result.json').read_text())
    assert run.returncode == result['return_code'] == 0, result
    assert 'manifold = yes' in log
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [p['id'] for p in plate['filaments']] == [1, 2, 3]
    assert all(p['main_used_g']>0 for p in plate['filaments'])
    paths = render_toolpaths(LOGS/'plate_1.gcode', build.DEST/(build.NAME+'_sliced_preview.png'))
    report.update(bambu_version='02.08.02.61', slice_result=result, used_filament_slots=[1,2,3],
                  rendered_toolpath_segments=paths, physical_print_verified=False,
                  environment_notes='CLI uses embedded project settings. Relocated Flatpak executable reports missing /app preset resources; the slice succeeds without plate warnings.')
    (build.DEST/f'Validation_{build.VERSION}.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ('slice_result',)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=['v1.3', 'v1.4'], default='v1.4')
    build.configure(parser.parse_args().version)
    LOGS = ROOT / 'validation' / build.SET.name / build.VERSION
    main()
