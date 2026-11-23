from pathlib import Path
import numpy as np, cv2, trimesh, json, zipfile
from PIL import Image
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union
from shapely import affinity
import xml.etree.ElementTree as ET
P=Path(__file__).parent
im=Image.open(P/'official-header.png').convert('RGBA').crop((600,715,1320,1055)); im.save(P/'official-title-reference.png')
a=np.array(im);r,g,b=a[:,:,:3].transpose(2,0,1).astype(float)
gold=((r>165)&(g>100)&(r>b*1.15)&(g>b*1.08)&(a[:,:,3]>100)).astype('uint8')
blue=((b>120)&(g>100)&(r<160)&(b>r*1.1)).astype('uint8')
colored=((a[:,:,3]>100)&((r>25)|(g>25)|(b>25))).astype('uint8')
# Use only the set wordmark, with no promotional banner or release-date badge.
scale=84/701

def geom(mask, minarea=.025):
 cs,h=cv2.findContours(mask,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
 ps=[]
 for i,c in enumerate(cs):
  if h[0,i,3]!=-1 or cv2.contourArea(c)*scale*scale<minarea: continue
  shell=c[:,0,:].astype(float);shell[:,1]=340-shell[:,1];shell*=scale
  holes=[];child=h[0,i,2]
  while child!=-1:
   cc=cs[child][:,0,:].astype(float);cc[:,1]=340-cc[:,1];cc*=scale
   if len(cc)>=3 and cv2.contourArea(cs[child])*scale*scale>.045:holes.append(cc)
   child=h[0,child,0]
  if len(shell)>=3:ps.append(Polygon(shell,holes).buffer(0))
 return unary_union(ps).simplify(.035,preserve_topology=True)
upper=gold.copy();upper[108:]=0
lower=gold.copy();lower[:108]=0
# Flatten the printed gold gradient and omit hairline map contours, retaining the actual lettering.
top=geom(upper).buffer(.10,join_style=1)
face=geom(lower).buffer(.025,join_style=1)
lowoutline=gold|blue;lowoutline[:108]=0
outline=face.buffer(.42,join_style=1).simplify(.025,preserve_topology=True)
# Original brown wordmark silhouette plus a robust margin; fill backing counters.
sil=geom(colored)
polys=list(sil.geoms) if sil.geom_type=='MultiPolygon' else [sil]
sil=unary_union([Polygon(p.exterior) for p in polys if p.area>1])
base=sil.buffer(.9,join_style=1)
# Attachment loop: 4.5 mm clear hole, 3 mm radial material, joined to left flank.
cy=16.0;cx=-3.8
base=base.union(box(cx,cy-3.6,4.3,cy+3.6)).union(Point(cx,cy).buffer(5.25,quad_segs=48)).difference(Point(cx,cy).buffer(2.25,quad_segs=48))
# shift entire keychain to positive XY coordinates, common origin for all parts
minx,miny,maxx,maxy=base.bounds
shift=lambda s:affinity.translate(s,-minx,-miny)
base,outline,face,top=map(shift,[base,outline,face,top])

def extrude(g,z,h):
 import manifold3d as mf
 from shapely.geometry.polygon import orient
 ps=list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
 contours=[]
 for p in ps:
  p=orient(p,sign=1)
  contours += [np.array(p.exterior.coords)[:-1]]+[np.array(q.coords)[:-1] for q in p.interiors]
 mm=mf.CrossSection(contours).extrude(h).translate([0,0,z]).to_mesh()
 return trimesh.Trimesh(vertices=np.array(mm.vert_properties)[:,:3],faces=np.array(mm.tri_verts),process=True)
meshes=[extrude(base,0,2),extrude(outline,2,.4),trimesh.util.concatenate([extrude(face,2.4,.6),extrude(top,2,1)])]
names=['01_Cocoa_Brown_backing','02_Ice_Blue_outline','03_Sunflower_Yellow_lettering']
colors=['#633A22','#9BC8DE','#F2C547']
for n,m in zip(names,meshes):m.export(P/(n+'.stl'))
print([(n,m.is_watertight,m.is_volume,len(m.faces),m.volume) for n,m in zip(names,meshes)],flush=True)
solid=trimesh.boolean.union(meshes,engine='manifold');solid.export(P/'Into_the_Inklands_single_colour.stl')
# Standards-compliant multi-part 3MF, dimensions in millimetres; no printer settings or G-code.
ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';ET.register_namespace('',ns)
def tag(x):return '{'+ns+'}'+x
root=ET.Element(tag('model'),{'unit':'millimeter','xml:lang':'en-US'})
ET.SubElement(root,tag('metadata'),{'name':'Title'}).text='Into the Inklands - Set 3 binder keychain'
ET.SubElement(root,tag('metadata'),{'name':'Description'}).text='95 x 40.7 x 3 mm; 4.5 mm loop; 3 named colour parts. Flat back on bed; 0.20 mm layers. Unsliced geometry. Official artwork: https://www.disneylorcana.com/en-US/product-s3'
res=ET.SubElement(root,tag('resources'))
bm=ET.SubElement(res,tag('basematerials'),{'id':'1'})
for n,c in zip(names,colors):ET.SubElement(bm,tag('base'),{'name':n,'displaycolor':c+'FF'})
for i,(m,n) in enumerate(zip(meshes,names)):
 obj=ET.SubElement(res,tag('object'),{'id':str(i+2),'type':'model','name':n,'pid':'1','pindex':str(i)})
 mesh=ET.SubElement(obj,tag('mesh'));v=ET.SubElement(mesh,tag('vertices'));t=ET.SubElement(mesh,tag('triangles'))
 for x,y,z in m.vertices:ET.SubElement(v,tag('vertex'),{'x':f'{x:.5f}','y':f'{y:.5f}','z':f'{z:.5f}'})
 for x,y,z in m.faces:ET.SubElement(t,tag('triangle'),{'v1':str(x),'v2':str(y),'v3':str(z)})
obj=ET.SubElement(res,tag('object'),{'id':'5','type':'model','name':'Into the Inklands - binder keychain'})
comp=ET.SubElement(obj,tag('components'))
for i in range(3):ET.SubElement(comp,tag('component'),{'objectid':str(i+2)})
build=ET.SubElement(root,tag('build'));ET.SubElement(build,tag('item'),{'objectid':'5'})
with zipfile.ZipFile(P/'Into_the_Inklands_3_colour.3mf','w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
 z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
 z.writestr('3D/3dmodel.model',ET.tostring(root,encoding='utf-8',xml_declaration=True))
# Editable self-contained OpenSCAD polygon source.
def scadpoly(g):
 ps=list(g.geoms) if g.geom_type=='MultiPolygon' else [g];out=[]
 for p in ps:
  rings=[p.exterior,*p.interiors];pts=[];paths=[]
  for ring in rings:
   v=list(ring.coords)[:-1];paths.append(list(range(len(pts),len(pts)+len(v))));pts+=v
  out.append('polygon(points='+json.dumps([[round(x,4),round(y,4)] for x,y in pts])+',paths='+json.dumps(paths)+');')
 return 'union(){'+''.join(out)+'}'
s='// Official set title traced from Ravensburger artwork. Units: mm.\n// Choose 0=assembly, 1=backing, 2=outline, 3=lettering.\npart=0;\n'
for i,(g,z,h,col) in enumerate([(base,0,2,colors[0]),(outline,2,.4,colors[1]),(face,2.4,.6,colors[2]),(top,2,1,colors[2])]):
 part=1 if i==0 else 2 if i==1 else 3
 s+=f'if(part==0 || part=={part}) color("{col}") translate([0,0,{z}]) linear_extrude({h}) '+scadpoly(g)+'\n'
(P/'Into_the_Inklands.scad').write_text(s)
# Exact geometry top view plus an oblique mesh render, both derived from printable parts.
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MPath
from shapely.geometry.polygon import orient
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
fig=plt.figure(figsize=(14,9),facecolor='#F3F1EA')
ax=fig.add_axes([.06,.54,.88,.32]);ax.set_aspect('equal');ax.axis('off')
def draw(g,c):
 ps=list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
 for p in ps:
  p=orient(p,sign=1);verts=[];codes=[]
  for ring in [p.exterior,*p.interiors]:
   xy=list(ring.coords);verts+=xy;codes += [MPath.MOVETO]+[MPath.LINETO]*(len(xy)-2)+[MPath.CLOSEPOLY]
  ax.add_patch(PathPatch(MPath(verts,codes),facecolor=c,edgecolor='none'))
for g,c in [(base,colors[0]),(outline,colors[1]),(face,colors[2]),(top,colors[2])]:draw(g,c)
ax.set_xlim(-2,base.bounds[2]+2);ax.set_ylim(-2,base.bounds[3]+2)
from matplotlib.collections import PolyCollection
ax3=fig.add_axes([.06,.13,.88,.32]);ax3.set_aspect('equal');ax3.axis('off')
for i,(m,c) in enumerate(zip(meshes,colors)):
 rgb=np.array([int(c[j:j+2],16) for j in (1,3,5)])/255
 shade=np.clip(.70+.30*m.face_normals[:,2]-.08*m.face_normals[:,1],.40,1.0)
 tri=m.triangles
 projected=np.stack([tri[:,:,0]-.32*tri[:,:,1],.52*tri[:,:,1]+1.5*tri[:,:,2]],axis=2)
 order=np.argsort(tri[:,:,2].mean(axis=1)+.001*tri[:,:,1].mean(axis=1))
 fc=np.c_[shade[:,None]*rgb,np.ones(len(shade))]
 ax3.add_collection(PolyCollection(projected[order],facecolors=fc[order],edgecolors=fc[order],linewidths=.1,antialiased=True))
ax3.autoscale_view();ax3.margins(.025)
fig.text(.06,.94,'INTO THE INKLANDS',fontsize=25,weight='bold',color='#302A24')
fig.text(.06,.90,'SET 03  /  BINDER KEYCHAIN  /  PRINTABLE PROOF OF CONCEPT',fontsize=11,color='#6B6257')
w=base.bounds[2];h=base.bounds[3]
fig.text(.06,.515,f'{w:.1f} × {h:.1f} × 3.0 mm   ·   4.5 mm attachment hole   ·   Flat back',fontsize=12,color='#51493F')
fig.text(.06,.055,'COCOA BROWN  +  ICE BLUE  +  SUNFLOWER YELLOW',fontsize=11,weight='bold',color='#51493F')
fig.text(.06,.025,'Exact model geometry shown. Gold gradients and map hairlines simplified for FDM printing.',fontsize=10,color='#6B6257')
fig.savefig(P/'Into_the_Inklands_preview.png',dpi=160,facecolor=fig.get_facecolor());plt.close(fig)
report={'dimensions_mm':[round(w,2),round(h,2),3], 'loop_hole_mm':4.5,'solid_watertight':bool(solid.is_watertight),'solid_components':len(solid.split()),'solid_volume_mm3':round(solid.volume,1),'parts':[{'name':n,'watertight':bool(m.is_watertight),'volume_mm3':round(m.volume,1)} for n,m in zip(names,meshes)]}
(P/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
