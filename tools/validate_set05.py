#!/usr/bin/env python3
"""Validate Set 05 geometry, star connections and the real Bambu slice.

Requires the same NumPy/Pillow runtime as rebuild_set05.py and local Bambu.
The input project remains unsliced; evidence is saved under validation/.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

import rebuild_set05 as build
from rebuild_set04 import area, boundary_loops
from repair_v1_1 import NS, read_parts
from validate_bambu import bambu_command

LOGS = build.ROOT / 'validation' / build.SET.name / build.VERSION


def mesh_checks():
    data, source_data = map(build.project_data, (build.PROJECT, build.SOURCE))
    parts, original = map(read_parts, (data, source_data))
    unchanged = (0, 2) if build.VERSION == 'v1.3' else (1, 2)
    for i in unchanged:
        assert parts[i] == original[i], f'original mesh {i} changed'
    assert data['Metadata/project_settings.config'] == source_data['Metadata/project_settings.config']
    # Compare untouched XML mesh resources as well as assembled coordinates.
    old_mesh, new_mesh = [ET.fromstring(d['3D/Objects/object_1.model']) for d in (source_data, data)]
    for oid in (str(i+1) for i in unchanged):
        path = f"m:resources/m:object[@id='{oid}']/m:mesh"
        assert ET.tostring(old_mesh.find(path, NS)) == ET.tostring(new_mesh.find(path, NS))
    old_root, new_root = [ET.fromstring(d['3D/3dmodel.model']) for d in (source_data, data)]
    assert ET.tostring(old_root.find('m:build', NS)) == ET.tostring(new_root.find('m:build', NS))
    volumes = []
    for part in parts:
        directed = collections.Counter((f[i], f[(i+1) % 3]) for f in part['faces'] for i in range(3))
        assert all(count == directed[(b, a)] == 1 for (a, b), count in directed.items())
        v, f = np.asarray(part['vertices']), np.asarray(part['faces'])
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        cross = np.cross(b-a, c-a)
        assert np.all(np.sum(cross*cross, axis=1) > 1e-22), 'degenerate triangle'
        volume = np.einsum('ij,ij->', a, np.cross(b, c))/6
        assert volume > 0
        volumes.append(float(volume))
    base, red, ivory = [build.footprint(boundary_loops(p)) for p in parts]
    assert not np.any(red & ivory), 'red and ivory volumes overlap'
    assert not np.any(red & ~base), 'red is unsupported'
    assert not np.any(ivory & ~base), 'ivory is unsupported'
    # The visible red face must reach the left S and the right side of each
    # word; this catches the original threshold split independently of RGB.
    red_loops = boundary_loops(parts[1])
    red_area_by_band = {}
    for label, x0, x1, y0, y1 in [('left_S', 11, 25, 2, 31),
                                  ('shimmering_left', 28, 45, 17, 29),
                                  ('shimmering_right', 60, 83, 20, 33),
                                  ('skies_left', 49, 64, 2, 17),
                                  ('skies_right', 68, 84, 2, 16)]:
        px0, py1 = build.xy_pixel((x0, y0))
        px1, py0 = build.xy_pixel((x1, y1))
        value = float(np.count_nonzero(red[round(py0):round(py1), round(px0):round(px1)]))*build.STEP**2
        assert value > 5, (label, 'missing red background')
        red_area_by_band[label] = round(value, 4)
    geometry = dict(closed_manifold_parts=3, degenerate_triangles=0,
                       positive_volumes_mm3=volumes,
                       original_meshes_exactly_unchanged=[original[i]['name'] for i in unchanged],
                       plate_placement_unchanged=True,
                       filament_and_process_settings_byte_identical=True,
                       unsupported_red_pixels=0, unsupported_ivory_pixels=0,
                       red_ivory_overlap_pixels=0, footprint_resolution_mm=build.STEP,
                       red_area_by_region_mm2=red_area_by_band,
                       red_footprint_area_mm2=round(sum(area(c) for c in build.orient(red_loops)), 4))
    if build.VERSION == 'v1.4':
        geometry['star_connections'] = star_connection_checks(parts[0], original[0])
        old_bore, new_bore = [next(c for c in boundary_loops(p) if 15.7 < abs(area(c)) < 15.9)
                              for p in (original[0], parts[0])]
        assert len(old_bore) == len(new_bore)
        assert all(math.dist(a, b) < 1e-8 for a, b in zip(sorted(old_bore), sorted(new_bore)))
        geometry['keyring_bore_exactly_preserved'] = True
    return parts, geometry


def star_connection_checks(base_part, previous_part):
    """Prove a 3 mm material corridor exists from every star into the body.

    Erode the actual mesh footprint by 1.5 mm and flood-fill from inside the
    wordmark. Every star centre must remain reachable after that erosion.
    Check at 0.05 mm resolution with conservative 2x2 pixel reduction.
    This is a geometric width check, not a physical strength measurement.
    """
    probes = build.STAR_SUPPORTS + [dict(name='integrated_flourish_sparkle', star=(87.2, 17.6))]
    def connected_stars(part):
        mask = build.footprint(boundary_loops(part))
        h, w = mask.shape
        mask = mask[:h//2*2, :w//2*2].reshape(h//2, 2, w//2, 2).all(axis=(1, 3))
        inset = build.erode(mask, 1.5, step=2*build.STEP)
        image = Image.fromarray(inset.astype(np.uint8)*255).copy()
        def pixel(p):
            return tuple(round(n/2) for n in build.xy_pixel(p))
        seed = pixel((55., 24.))
        assert image.getpixel(seed) == 255, 'body seed must survive erosion'
        ImageDraw.floodfill(image, seed, 128)
        return {s['name']: image.getpixel(pixel(s['star'])) == 128 for s in probes}
    before, after = connected_stars(previous_part), connected_stars(base_part)
    assert all(after.values()), ('a star lacks a continuous 3 mm connection', after)
    assert len(boundary_loops(base_part)) == 2, 'only the outer contour and native keyring bore should remain'
    assert all(abs(v[2]) < 1e-8 or abs(v[2]-2) < 1e-8 for v in base_part['vertices'])
    return dict(minimum_verified_corridor_width_mm=3., verification_resolution_mm=.05,
                backing_thickness_mm=2., connections_to_main_body=len(probes),
                newly_reinforced_connections=len(build.STAR_SUPPORTS),
                previous_revision_passed=before, reinforced_revision_passed=after,
                small_star_connection_voids_remaining=0,
                physical_strength_test_performed=False)


def render_toolpaths(path, output, bbox, colors):
    """Composite Z=2 backing, Z=2.4 red and Z=3 ivory from deposited paths."""
    scale, margin = 32, 65
    x0, y0 = bbox['x'], bbox['y']
    x1, y1 = x0+bbox['width'], y0+bbox['depth']
    im = Image.new('RGB', (math.ceil(bbox['width']*scale)+2*margin,
                          math.ceil(bbox['depth']*scale)+2*margin), '#404443')
    draw = ImageDraw.Draw(im)
    x, y, tool, nominal, line_width, feature = 0., 0., 0, 0., .42, 'Custom'
    relative, previous_e = True, 0.
    layers = {2.: [], 2.4: [], 3.: []}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith('; Z_HEIGHT:'):
            nominal = round(float(line.split(':', 1)[1]), 3)
        elif line.startswith('; LINE_WIDTH:'):
            line_width = float(line.split(':', 1)[1])
        elif line.startswith('; FEATURE:'):
            feature = line.split(':', 1)[1].strip()
        elif re.fullmatch(r'T\d+', line):
            if int(line[1:]) < len(colors):
                tool = int(line[1:])
        elif line in ('M82', 'M83'):
            relative = line == 'M83'
        command = line.split(';', 1)[0].split()
        if not command:
            continue
        values = {key: float(val) for key, val in re.findall(
            r'([XYZEFIJP])\s*([-+]?(?:\d*\.\d+|\d+))', ' '.join(command[1:]))}
        if command[0] == 'G92':
            previous_e = values.get('E', previous_e)
        if command[0] not in ('G0', 'G1', 'G2', 'G3'):
            continue
        end = values.get('X', x), values.get('Y', y)
        extrusion = values.get('E', 0) if relative else values.get('E', previous_e)-previous_e
        if not relative:
            previous_e = values.get('E', previous_e)
        if (extrusion > 0 and ('X' in values or 'Y' in values) and nominal in layers
                and feature not in ('Custom', 'Prime tower')):
            points = [(x, y), end]
            if command[0] in ('G2', 'G3') and ('I' in values or 'J' in values):
                cx, cy = x+values.get('I', 0), y+values.get('J', 0)
                radius = math.hypot(x-cx, y-cy)
                start = math.atan2(y-cy, x-cx)
                stop = math.atan2(end[1]-cy, end[0]-cx)
                sweep = (stop-start) % math.tau if command[0] == 'G3' else -((start-stop) % math.tau)
                steps = max(2, math.ceil(abs(sweep)*radius/.05))
                points = [(cx+radius*math.cos(start+sweep*i/steps),
                           cy+radius*math.sin(start+sweep*i/steps)) for i in range(steps+1)]
            if all(x0-.25 <= px <= x1+.25 and y0-.25 <= py <= y1+.25 for px, py in points):
                layers[nominal].append((points, line_width, tool))
        x, y = end
    for z, paths in layers.items():
        assert paths, f'missing deposited paths at Z={z}'
        for points, line_width, tool in paths:
            projected = [(margin+(x-x0)*scale, margin+(y1-y)*scale) for x, y in points]
            stroke = max(1, round(line_width*scale))
            draw.line(projected, fill=colors[tool], width=stroke, joint='curve')
            radius = stroke/2
            for x, y in (projected[0], projected[-1]):
                draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=colors[tool])
    im.resize((1800, round(im.height*1800/im.width)), Image.Resampling.LANCZOS).save(output)
    counts = {str(z): dict(collections.Counter(str(tool+1) for _, _, tool in paths))
              for z, paths in layers.items()}
    assert counts['2.0'].get('1', 0) > 0
    assert counts['2.4'].get('2', 0) > 0
    assert counts['3.0'].get('3', 0) > 0
    return counts


def main():
    parts, geometry = mesh_checks()
    LOGS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lorcana-set05-settings-') as directory:
        run = subprocess.run(bambu_command()+['--datadir', directory, '--debug', '2',
                             '--info', '--slice', '1', '--outputdir', str(LOGS), str(build.PROJECT)],
                             cwd=LOGS, capture_output=True, text=True, timeout=180)
    log = run.stdout+run.stderr
    (LOGS/'slice.log').write_text(log)
    result = json.loads((LOGS/'result.json').read_text())
    assert run.returncode == result['return_code'] == 0, result
    assert 'manifold = yes' in log
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == '', plate['warning_message']
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    colors = json.loads(build.project_data(build.PROJECT)['Metadata/project_settings.config'])['filament_colour']
    counts = render_toolpaths(LOGS/'plate_1.gcode', build.DEST/(build.NAME+'_sliced_preview.png'),
                             plate['objects'][0]['bbox'], colors)
    report = dict(filename=build.PROJECT.name,
                  sha256=hashlib.sha256(build.PROJECT.read_bytes()).hexdigest(),
                  geometry=geometry, bambu_version='02.08.02.61',
                  slice_result=result, used_filament_slots=[1, 2, 3],
                  rendered_toolpath_segments_by_layer_and_slot=counts,
                  physical_print_verified=False,
                  environment_notes='Installed Bambu Flatpak CLI uses embedded project settings; missing /app preset-resource messages do not prevent slicing.')
    (build.DEST/f'Validation_{build.VERSION}.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'slice_result'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=['v1.3', 'v1.4'], default='v1.4')
    build.configure(parser.parse_args().version)
    LOGS = build.ROOT / 'validation' / build.SET.name / build.VERSION
    main()
