#!/usr/bin/env python3
"""Set 08 v10: printable red counters/eyes and hood bands meeting the rim."""
import copy
import json
import math
import xml.etree.ElementTree as ET
import zipfile

import rebuild_set08_v08 as engine
from rebuild_set04 import area, boundary_loops, orient

core = engine.core
ROOT, SET = core.ROOT, core.SET
VERSION = 'v10'
NAME = SET.name+'_'+VERSION
SOURCE = SET/'v09'/(SET.name+'_v09.3mf')
DEST = SET/VERSION
PROJECT = DEST/(NAME+'.3mf')
VECTOR = core.VECTOR.with_name('set08_serpent_detail_v09.svg')
KEYLINE = .35
COUNTER_INSET = .25
EYE_INSET, EYE_ROUNDING = .10, .25
RED_CORNER_RADIUS = .20
RED_FILL_SETTINGS = {'top_surface_line_width': '0.35', 'internal_solid_infill_line_width': '0.35'}
ORANGE_CORNER_RADIUS = .18
RED_FACE_TOP = 3.0


def artwork():
    art = copy.deepcopy(core.artwork())
    # Slightly smaller counters leave enough red on BOTH sides of the bowl
    # junction. The black openings remain substantial and separate.
    for name in ('a_first', 'a_second'):
        outer = [c for c in art['jafar'][name] if area(c) > 0]
        counter = next(c for c in art['jafar'][name] if area(c) < 0)
        inner = core.contours(engine.raster([counter], COUNTER_INSET))
        assert len(inner) == 1
        art['jafar'][name] = orient(outer+inner)
    # Round the eye tips to a printable radius and expand their sides very
    # slightly. This replaces acute red slivers with complete rounded eyes.
    for name, loops in art['accents'].items():
        inner = core.contours(engine.raster(loops, EYE_INSET))
        art['accents'][name] = core.contours(engine.raster(inner, -EYE_ROUNDING))
        assert len(art['accents'][name]) == 1
    art['gold']['frame'] = orient(art['gold']['frame'][:2]
        +[c for loops in art['accents'].values() for c in loops])
    return art


def red_contours(art):
    red = {}
    for name, loops in art['jafar'].items():
        inside = core.contours(engine.raster(loops, KEYLINE+RED_CORNER_RADIUS))
        red[name] = core.contours(engine.raster(inside, -RED_CORNER_RADIUS))
    assert len(red['a_first']) == len(red['a_second']) == 2, 'red bowl must fully surround its counter'
    return red


def detail_artwork():
    root = ET.parse(VECTOR).getroot()
    return {group: {p.get('id'): (core.sample(p.get('d')) if group == 'orange'
                    else engine.open_path(p.get('d')))
                    for p in root.findall(f"s:g[@id='{group}']/s:path", core.SVG)}
            for group in ('orange', 'hood')}


def extend(path):
    """Continue both tangents past the hood; the inner rim clips the ends."""
    def endpoint(a, b):
        length = math.dist(a, b)
        return tuple(a[k]+50*(a[k]-b[k])/length for k in (0, 1))
    return [endpoint(path[0], path[1])]+path+[endpoint(path[-1], path[-2])]


def masks(art):
    details = detail_artwork()
    frame = art['gold']['frame']
    inner = frame[1]
    safe = engine.raster(frame, .30)
    band = engine.stroke([inner+inner[:1]], 1.9)
    gap = engine.stroke([inner+inner[:1]], .7)
    face = engine.raster(details['orange']['serpent_face'])
    orange = bytearray(ok and ((b and not g) or f) for ok, b, g, f in zip(safe, band, gap, face))
    # Remove nozzle-sized cheek slivers left between the enlarged eyes and
    # the rim. Keep the continuous rim/face instead of isolated orange tips.
    inner_orange = core.contours(engine.raster(core.contours(orange), ORANGE_CORNER_RADIUS))
    rounded = engine.raster(inner_orange, -ORANGE_CORNER_RADIUS)
    orange = largest_region(bytearray(a and b for a, b in zip(orange, rounded)))
    field = engine.raster([inner])
    text = [ls for n, ls in art['gold'].items() if n != 'frame']+list(art['jafar'].values())
    keepouts = bytearray(len(field))
    for loops in text:
        region = engine.raster(loops, -.22)
        keepouts = bytearray(a or b for a, b in zip(keepouts, region))
    bands = {}
    for name, path in details['hood'].items():
        line = engine.stroke([extend(path)], engine.GROOVE_WIDTH)
        bands[name] = bytearray(a and b and not c for a, b, c in zip(line, field, keepouts))
    hood = bytearray(any(v) for v in zip(*bands.values()))
    return orange, hood, bands


def largest_region(mask):
    values = bytearray(mask)
    width = core.SIZE[0]
    largest = []
    for index, value in enumerate(values):
        if not value:
            continue
        todo, component = [index], [index]
        values[index] = 0
        while todo:
            p = todo.pop()
            for q in (p-1, p+1, p-width, p+width):
                if 0 <= q < len(values) and values[q]:
                    values[q] = 0
                    todo.append(q)
                    component.append(q)
        if len(component) > len(largest):
            largest = component
    result = bytearray(len(mask))
    for i in largest:
        result[i] = 1
    return result


def geometry(old):
    art = artwork()
    orange_mask, hood_mask, _ = masks(art)
    orange, hood = core.contours(orange_mask), core.contours(hood_mask)
    base = engine.recessed(boundary_loops(old[0]), hood, 0., 2., 1.6, old[0])
    base['name'] = 'Charcoal — complete cobra hood bands, backing and loop'
    gold = core.merge([
        engine.recessed(art['gold']['frame'], orange, 2., 2.8, 2.4, old[2]),
        core.relief([ls for n, ls in art['gold'].items() if n != 'frame'], 2., .8, old[2]),
        core.relief(list(art['jafar'].values()), 2., .4, old[2])])
    gold['name'] = 'Sunflower Yellow — rim, lettering and printable red keylines'
    accent = core.relief([orange], 2.4, .4, old[1])
    crimson = core.merge([core.relief(list(red_contours(art).values()), 2.4, RED_FACE_TOP-2.4, old[3]),
                          core.relief(list(art['accents'].values()), 2., .8, old[3])])
    crimson['name'] = 'Red — fuller Jafar faces and rounded cobra eyes'
    return [base, accent, gold, crimson]


def main():
    data = core.package(SOURCE)
    old = core.read_parts(data)
    parts = geometry(old)
    root = ET.fromstring(data['3D/3dmodel.model'])
    config = ET.fromstring(data['Metadata/model_settings.config'])
    obj = config.find('object')
    assembly = root.find(f"m:resources/m:object[@id='{obj.get('id')}']", core.NS)
    resources = {}
    for i, component in enumerate(assembly.find('m:components', core.NS)):
        path = component.get('{'+core.PROD+'}path').lstrip('/')
        if path not in resources:
            resources[path] = ET.fromstring(data[path])
        oid = component.get('objectid')
        core.write_mesh(resources[path].find(f"m:resources/m:object[@id='{oid}']", core.NS), parts[i])
        cfg = obj.find(f"part[@id='{oid}']")
        cfg.find("metadata[@key='name']").set('value', parts[i]['name'])
        cfg.find('mesh_stat').set('face_count', str(len(parts[i]['faces'])))
        if parts[i]['slot'] == 4:
            for key, value in RED_FILL_SETTINGS.items():
                md = cfg.find(f"metadata[@key='{key}']")
                if md is None:
                    md = ET.SubElement(cfg, 'metadata', {'key': key})
                md.set('value', value)
    obj.find("metadata[@key='name']").set('value', NAME)
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    root.find("m:metadata[@name='Description']", core.NS).text = (
        'v10; fuller red Jafar faces with 0.35 mm gold keylines and locally fuller a bowls; '
        'rounded printable red cobra eyes; plain orange face without nose/chevron; '
        'five 0.6 mm wide, 0.4 mm deep hood bands extended to meet the inner rim; '
        'native backing outline, 2 mm eyelet, 6.5 mm bore and plate placement retained; '
        '1.6 mm groove floor; three red face layers to 3 mm; rounded eyes remain at 2.8 mm; '
        'four original filament slots; 3 mm maximum height.')
    for path, resource in resources.items():
        if not any(k.startswith('{'+core.PROD+'}') for e in resource.iter() for k in e.attrib):
            resource.set('xmlns:p', core.PROD)
        data[path] = ET.tostring(resource, encoding='utf-8', xml_declaration=True)
    data['3D/3dmodel.model'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    data['Metadata/model_settings.config'] = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    floor = [f for f in parts[0]['faces'] if all(abs(parts[0]['vertices'][i][2]-1.6) < 1e-7 for i in f)]
    other = [f for f in parts[0]['faces'] if not all(abs(parts[0]['vertices'][i][2]-1.6) < 1e-7 for i in f)]
    lit = [dict(parts[0], faces=other), dict(parts[0], faces=floor, color='#202324')]+parts[1:]
    data['Metadata/plate_1.png'] = core.thumbnail(lit, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = core.thumbnail(lit, 128)
    DEST.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PROJECT, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, raw in data.items():
            archive.writestr(path, raw)
    loaded = core.read_parts(core.package(PROJECT))
    engine.preview(loaded, DEST/(NAME+'_preview.png'))
    engine.preview(loaded, DEST/(NAME+'_isometric.png'), isometric=True)
    engine.head_preview(loaded, DEST/(NAME+'_head_preview.png'))
    engine.comparison(old, loaded, before_label='v09',
        after_label='v10 - fuller red faces and completed hood bands',
        destination=DEST/(NAME+'_comparison.png'))
    print(json.dumps(dict(project=str(PROJECT.relative_to(ROOT)), sha256=core.digest(PROJECT),
        parts=[dict(slot=p['slot'], **core.mesh_stats(p)) for p in loaded]), indent=2))


if __name__ == '__main__':
    main()
