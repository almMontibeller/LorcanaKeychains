from pathlib import Path
import json,zipfile,xml.etree.ElementTree as E,copy
P=Path(__file__).parent;D=P/'v1.1';ROOT=Path('/tmp/squashfs-root/resources/profiles/BBL')
profiles={p.stem:p for p in ROOT.rglob('*.json')}
SKIP={'type','name','inherits','from','setting_id','instantiation','include','description','filament_id'}
def resolve(name,seen=()):
 if name in seen:raise ValueError(name)
 j=json.loads(profiles[name].read_text());out={}
 if j.get('inherits'):out.update(resolve(j['inherits'],seen+(name,)))
 for inc in j.get('include',[]):out.update(resolve(inc,seen+(name,)))
 out.update({k:v for k,v in j.items() if k not in SKIP});return out
machine=resolve('Bambu Lab A1 0.4 nozzle');process=resolve('0.20mm Standard @BBL A1')
ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';t=lambda x:'{'+ns+'}'+x;E.register_namespace('',ns)
rs=json.loads((D/'Validation_v1.1.json').read_text())
for row in rs:
 p=D/row['filename'];z=zipfile.ZipFile(p);data={n:z.read(n) for n in z.namelist()};root=E.fromstring(data['3D/3dmodel.model'])
 E.SubElement(root,t('metadata'),{'name':'BambuStudio:3mfVersion'}).text='1';E.SubElement(root,t('metadata'),{'name':'Application'}).text='BambuStudio-02.08.02.61'
 root.set('xmlns:BambuStudio','http://schemas.bambulab.com/package/2021')
 res=root.find(t('resources'));objs=res.findall(t('object'));assy=objs[-1];aid=assy.get('id');build=root.find(t('build'))[0]
 dims=row['dimensions_mm'];dx=128-dims[0]/2;dy=128-dims[1]/2;transform=f'1 0 0 0 1 0 0 0 1 {dx:.5f} {dy:.5f} 0';build.set('transform',transform);build.set('printable','1')
 cfg=E.Element('config');obj=E.SubElement(cfg,'object',{'id':aid});E.SubElement(obj,'metadata',{'key':'name','value':row['title']+' v1.1'});E.SubElement(obj,'metadata',{'key':'extruder','value':'1'})
 colours=[];filaments=[]
 bases=res.find(t('basematerials')).findall(t('base'))
 for i,partobj in enumerate(objs[:-1]):
  col=row['colours'][i];part=E.SubElement(obj,'part',{'id':partobj.get('id'),'subtype':'normal_part'})
  E.SubElement(part,'metadata',{'key':'name','value':col});E.SubElement(part,'metadata',{'key':'extruder','value':str(i+1)})
  E.SubElement(part,'metadata',{'key':'matrix','value':'1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1'})
  E.SubElement(part,'mesh_stat',{'face_count':str(len(partobj.find(t('mesh')).find(t('triangles')))),'edges_fixed':'0','degenerate_facets':'0','facets_removed':'0','facets_reversed':'0','backwards_edges':'0'})
  colours.append(bases[i].get('displaycolor')[:7]);filaments.append('Bambu PLA Matte @BBL A1' if col in ['Ivory White','Ice Blue','Marine Blue','Dark Green','Caramel','Charcoal','Ash Gray'] else 'Bambu PLA Basic @BBL A1')
 plate=E.SubElement(cfg,'plate')
 for k,v in [('plater_id','1'),('plater_name',row['title']),('locked','false')]:E.SubElement(plate,'metadata',{'key':k,'value':v})
 inst=E.SubElement(plate,'model_instance')
 for k,v in [('object_id',aid),('instance_id','0'),('identify_id','1')]:E.SubElement(inst,'metadata',{'key':k,'value':v})
 assemble=E.SubElement(cfg,'assemble');E.SubElement(assemble,'assemble_item',{'object_id':aid,'instance_id':'0','transform':transform,'offset':'0 0 0'})
 settings={**machine,**process};fp=[resolve(f) for f in filaments]
 for k in set().union(*(f.keys() for f in fp)):
  vals=[f.get(k) for f in fp]
  if all(isinstance(v,list) for v in vals):settings[k]=[v[0] if v else '' for v in vals]
  elif all(isinstance(v,str) for v in vals):settings[k]=vals[0]
 settings.update({'printer_settings_id':'Bambu Lab A1 0.4 nozzle','print_settings_id':'0.20mm Standard @BBL A1','filament_settings_id':filaments,'filament_colour':colours,'filament_type':['PLA']*len(colours),'filament_vendor':['Bambu Lab']*len(colours),'filament_ids':['GFA01' if 'Matte' in f else 'GFA00' for f in filaments],'curr_bed_type':'Textured PEI Plate','enable_support':'0','wall_generator':'arachne','wall_loops':'3','bottom_shell_layers':'5','top_shell_layers':'5','sparse_infill_density':'15%','brim_type':'no_brim','version':'02.08.02.61'})
 data['3D/3dmodel.model']=E.tostring(root,encoding='utf-8',xml_declaration=True);data['Metadata/model_settings.config']=E.tostring(cfg,encoding='utf-8',xml_declaration=True);data['Metadata/project_settings.config']=json.dumps(settings).encode()
 # Native Bambu models use application metadata and per-part extruder assignments.
 with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as out:
  for name,raw in data.items():out.writestr(name,raw)
 print(row['set'],len(colours),p.name,flush=True)
