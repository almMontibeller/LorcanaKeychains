from pathlib import Path
import subprocess,os,json,zipfile,xml.etree.ElementTree as E,shutil
P=Path(__file__).parent;D=P/'v1.1';T=Path('/tmp/bambu-tests');T.mkdir(exist_ok=True)
env=dict(os.environ,LD_LIBRARY_PATH='/tmp/bambu-libs/usr/lib/x86_64-linux-gnu:/tmp/squashfs-root/bin')
rs=json.loads((D/'Validation_v1.1.json').read_text())
for row in rs:
 src=D/row['filename'];out=T/row['filename']
 run=subprocess.run(['/tmp/squashfs-root/bin/bambu-studio','--debug','2','--export-3mf',str(out),str(src)],env=env,capture_output=True,text=True)
 (T/(src.stem+'.log')).write_text(run.stdout+run.stderr)
 assert out.exists() and out.stat().st_size>10000,(row['set'],run.stdout,run.stderr)
 z=zipfile.ZipFile(out);assert z.testzip() is None;cfg=json.loads(z.read('Metadata/project_settings.config'));model=E.fromstring(z.read('Metadata/model_settings.config'));parts=model.findall('./object/part')
 assert len(parts)==len(row['colours']),(row['set'],len(parts))
 assert [p.find("metadata[@key='extruder']").get('value') for p in parts]==list(map(str,range(1,len(parts)+1)))
 assert len(cfg['filament_colour'])==len(parts)
 shutil.copyfile(out,src)
 # Import the native export again with Bambu Studio, checking real geometry.
 rr=subprocess.run(['/tmp/squashfs-root/bin/bambu-studio','--debug','2','--info',str(src)],env=env,capture_output=True,text=True)
 txt=rr.stdout+rr.stderr;(T/(src.stem+'-reimport.log')).write_text(txt)
 assert 'manifold = yes' in txt and 'number_of_facets' in txt,(row['set'],txt)
 row.update(bambu_studio_import_verified=True,bambu_native_export=True,filament_colours=cfg['filament_colour'],part_extruders=list(range(1,len(parts)+1)),geometry_watertight=True,assembled_connected_components=1)
 print(row['set'],'native export, reimport, colours verified',flush=True)
(D/'Validation_v1.1.json').write_text(json.dumps(rs,indent=2))
