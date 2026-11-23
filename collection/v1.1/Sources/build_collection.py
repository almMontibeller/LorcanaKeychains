from pathlib import Path
import numpy as np, cv2, trimesh, json,zipfile,shutil
from PIL import Image
import manifold3d as mf
from shapely.geometry import Polygon,Point,LineString,box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union,nearest_points
from shapely import affinity,set_precision
import xml.etree.ElementTree as E
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
P=Path(__file__).parent;D=P/'v1.0';D.mkdir(exist_ok=True)
COL={'Cocoa Brown':'#633A22','Ice Blue':'#9BC8DE','Sunflower Yellow':'#F2C547','Purple':'#583B83','Red':'#B93642','Ivory White':'#F5F0DD','Marine Blue':'#193D58','Dark Green':'#24534A','Mistletoe Green':'#639653','Caramel':'#BC773F','Pumpkin Orange':'#E68B31','Charcoal':'#363A3B','Ash Gray':'#A7AAA5'}
SETS={4:("Ursulas_Return","Ursula’s Return",'ursulas-return'),5:('Shimmering_Skies','Shimmering Skies','shimmering-skies'),6:('Azurite_Sea','Azurite Sea','azurite-sea'),7:('Archazias_Island','Archazia’s Island','archazias-island'),8:('Reign_of_Jafar','Reign of Jafar','reign-of-jafar'),9:('Fabled','Fabled','fabled'),10:('Whispers_in_the_Well','Whispers in the Well','whispers'),11:('Winterspell','Winterspell','winterspell'),12:('Wilds_Unknown','Wilds Unknown','wilds-unknown'),13:('Attack_of_the_Vine','Attack of the Vine!','attack-of-the-vine'),14:('Hyperia_City','Hyperia City','hyperia-city')}

def polygons(g):return list(g.geoms) if g.geom_type=='MultiPolygon' else [g] if g.geom_type=='Polygon' else [p for p in getattr(g,'geoms',[]) if p.geom_type=='Polygon']
def maskgeom(m,scale,H,minarea=.06,holes=True):
 cs,hh=cv2.findContours(m.astype('uint8'),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE);ps=[]
 if hh is None:return Polygon()
 for i,c in enumerate(cs):
  if hh[0,i,3]!=-1 or cv2.contourArea(c)*scale**2<minarea or len(c)<3:continue
  sh=c[:,0,:].astype(float);sh[:,1]=H-sh[:,1];sh*=scale
  ins=[];ch=hh[0,i,2]
  while ch!=-1:
   cc=cs[ch][:,0,:].astype(float);cc[:,1]=H-cc[:,1];cc*=scale
   if holes and len(cc)>2 and cv2.contourArea(cs[ch])*scale**2>.28:ins.append(cc)
   ch=hh[0,ch,0]
  ps.append(Polygon(sh,ins).buffer(0))
 return unary_union(ps).simplify(.045,preserve_topology=True)

def mesh(g,z,h):
 g=g.buffer(-.012).buffer(.012);g=set_precision(g,.005).simplify(.02,preserve_topology=True)
 contours=[]
 for p in polygons(g):
  p=orient(p,sign=1);contours += [np.array(p.exterior.coords)[:-1]]+[np.array(q.coords)[:-1] for q in p.interiors]
 mm=mf.CrossSection(contours).extrude(h).translate([0,0,z]).to_mesh()
 return trimesh.Trimesh(vertices=np.array(mm.vert_properties)[:,:3],faces=np.array(mm.tri_verts),process=False)

def write3mf(path,meshes,names,colors,title,source):
 ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';E.register_namespace('',ns);t=lambda x:'{'+ns+'}'+x
 root=E.Element(t('model'),{'unit':'millimeter','xml:lang':'en-US'})
 for k,v in [('Title',title),('Description','v1.0; flat backing down; 4.5 mm loop; 0.20 mm layers; unsliced geometry, assign named parts to AMS filaments.'),('Copyright','Disney / Ravensburger original title art; personal binder labels.'),('Source',source)]:E.SubElement(root,t('metadata'),{'name':k}).text=v
 res=E.SubElement(root,t('resources'));bm=E.SubElement(res,t('basematerials'),{'id':'1'})
 for n,c in zip(names,colors):E.SubElement(bm,t('base'),{'name':n,'displaycolor':c+'FF'})
 for i,(m,n) in enumerate(zip(meshes,names)):
  obj=E.SubElement(res,t('object'),{'id':str(i+2),'type':'model','name':n,'pid':'1','pindex':str(i)});me=E.SubElement(obj,t('mesh'));vs=E.SubElement(me,t('vertices'));ts=E.SubElement(me,t('triangles'))
  for x,y,z in m.vertices:E.SubElement(vs,t('vertex'),{'x':f'{x:.5f}','y':f'{y:.5f}','z':f'{z:.5f}'})
  for x,y,z in m.faces:E.SubElement(ts,t('triangle'),{'v1':str(x),'v2':str(y),'v3':str(z)})
 oid=len(meshes)+2;obj=E.SubElement(res,t('object'),{'id':str(oid),'type':'model','name':title});co=E.SubElement(obj,t('components'))
 for i in range(len(meshes)):E.SubElement(co,t('component'),{'objectid':str(i+2)})
 bu=E.SubElement(root,t('build'));E.SubElement(bu,t('item'),{'objectid':str(oid)})
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
  z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
  z.writestr('3D/3dmodel.model',E.tostring(root,encoding='utf-8',xml_declaration=True))

def draw(ax,g,c):
 for p in polygons(g):
  p=orient(p,sign=1);vv=[];codes=[]
  for q in [p.exterior,*p.interiors]:
   xy=list(q.coords);vv+=xy;codes += [MPath.MOVETO]+[MPath.LINETO]*(len(xy)-2)+[MPath.CLOSEPOLY]
  ax.add_patch(PathPatch(MPath(vv,codes),facecolor=c,edgecolor='none'))

reports=[];designs=[]
# Include the accepted proof of concept unchanged.
src=P.parent/'inklands'/'Into_the_Inklands_3_colour.3mf';dest=D/'Set_03_Into_the_Inklands_v1.0.3mf';shutil.copyfile(src,dest)
r=json.loads((P.parent/'inklands'/'validation.json').read_text());r.update(set=3,title='Into the Inklands',filename=dest.name,colours=['Cocoa Brown','Ice Blue','Sunflower Yellow'],source='https://www.disneylorcana.com/en-US/product-s3');reports.append(r)
for n,(slug,title,page) in SETS.items():
 im=Image.open(P/'sources'/f'{n:02d}.png').convert('RGBA')
 if n==4:im=im.crop((625,680,1290,1040))
 # Trim transparent padding without including diffuse glows.
 a=np.array(im);alpha=a[:,:,3];yy,xx=np.where(alpha>140);im=im.crop((max(0,xx.min()-2),max(0,yy.min()-2),min(im.width,xx.max()+3),min(im.height,yy.max()+3)))
 a=np.array(im);H,W=a.shape[:2];r,g,b=a[:,:,:3].transpose(2,0,1).astype(float);valid=a[:,:,3]>135;scale=min(84/W,40/H)
 # Ordered low-to-high relief: bold background forms, then readable letter faces.
 if n==4:
  basecol='Purple';groups=[('Sunflower Yellow',(r>145)&(g>90)&(r>1.15*b)&(r>1.12*g),.8),('Ice Blue',(b>120)&(g>120)&(r<g*1.15)&(b>r*.95),.8)]
 elif n==5:
  basecol='Purple';groups=[('Red',(r>105)&(r>g*1.5)&(r>b*1.1),.4),('Sunflower Yellow',(r>190)&(g>140)&(g>b*1.1),.8),('Ivory White',(r>220)&(g>205)&(b>140),1.)]
 elif n==6:
  basecol='Marine Blue';groups=[('Ice Blue',(g>95)&(b>100)&(r<g*.8),.4),('Sunflower Yellow',(r>140)&(g>80)&(r>b*1.12),.8),('Ivory White',(r>250)&(g>245)&(b>240)&(b>r),1.)]
 elif n==7:
  basecol='Dark Green';groups=[('Mistletoe Green',(g>95)&(r<g*.75),.4),('Caramel',(r>105)&(g>65)&(r>g*1.15)&(b<g*.95),.6),('Ivory White',(r>215)&(g>185)&(b>140),1.)]
 elif n==8:
  basecol='Charcoal';groups=[('Pumpkin Orange',(r>140)&(g>75)&(r>b*1.5),.6),('Sunflower Yellow',(r>220)&(g>180)&(b>110),.8),('Red',(r>120)&(g<105)&(b<60),1.)]
 elif n==9:
  basecol='Marine Blue';groups=[('Sunflower Yellow',(r>95)&(g>70)&(r>b*1.08),.6),('Ivory White',(r>210)&(g>200)&(b>150),.8)]
 elif n==10:
  basecol='Charcoal';groups=[('Ash Gray',(r>75)&(g>75)&(b>65)&(r<g*1.22),.6),('Sunflower Yellow',(r>100)&(g>55)&(r>g*1.12)&(b<g*.95),.8)]
 elif n==11:
  basecol='Marine Blue';groups=[('Ice Blue',(b>100)&(b>r*1.12)&(g>80),.4),('Sunflower Yellow',(r>130)&(g>95)&(b<r*.9),.8),('Ivory White',(r>205)&(g>195)&(b>155),1.)]
 elif n==12:
  basecol='Cocoa Brown';groups=[('Dark Green',(g>r*1.05)&(g>b*1.2),.6),('Caramel',(r>110)&(r>g*1.35)&(g>b*1.15),.6),('Ivory White',(r>160)&(g>150)&(b>105),1.)]
 elif n==13:
  basecol='Purple';Y,X=np.indices((H,W));textmask=(g>95)&(b<g*.8)&(r>65);split=Y<H*.46-X*.14;groups=[('Mistletoe Green',textmask&split,.8),('Sunflower Yellow',textmask&~split,1.)]
 elif n==14:
  basecol='Cocoa Brown';groups=[('Caramel',(r>105)&(g>55)&(b<g*.85)&(r>g*1.15),.6),('Ice Blue',(g>r*1.2)&(b>r*1.2)&(g>100),.6),('Ivory White',(r>215)&(g>200)&(b>135),1.)]
 silhouette=maskgeom(valid,scale,H,minarea=.15,holes=False).buffer(.8).simplify(.04)
 # Connect decorative islands with narrow, rounded structural bridges.
 while len(polygons(silhouette))>1:
  ps=sorted(polygons(silhouette),key=lambda q:q.area,reverse=True);main=ps[0];other=min(ps[1:],key=lambda q:q.distance(main));p1,p2=nearest_points(main,other)
  silhouette=unary_union([silhouette,LineString([p1,p2]).buffer(1.15)]).buffer(0)
 # Attachment follows the leftmost edge at mid-height, rather than extending into a weak serif.
 bounds=silhouette.bounds;cy=(bounds[1]+bounds[3])*.5
 intercept=silhouette.intersection(LineString([(bounds[0]-2,cy),(bounds[2]+2,cy)]));anchor=intercept.bounds[0]
 cx=bounds[0]-4.5
 base=silhouette.union(box(cx,cy-3.5,anchor+2.5,cy+3.5)).union(Point(cx,cy).buffer(5.25,quad_segs=40)).difference(Point(cx,cy).buffer(2.25,quad_segs=40))
 # Clean each colour region; flatten raster textures into printable continuous shapes.
 relief=[]
 for col,mask,height in groups:
  raw=(mask&valid).astype('uint8')
  k=max(3,int((1.0 if n==4 else .35)/scale)//2*2+1);raw=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,np.ones((k,k),np.uint8))
  geo=maskgeom(raw,scale,H,minarea=.10).buffer(.06).buffer(-.025).simplify(.045,preserve_topology=True).intersection(silhouette)
  relief.append([col,geo,height])
 # Avoid overlapping colour volumes: higher relief regions take priority.
 occupied=Polygon()
 for row in reversed(relief):
  col,geo,height=row;row[1]=geo.difference(occupied).buffer(0);occupied=occupied.union(geo)
 x0,y0,_,_=base.bounds;shift=lambda q:affinity.translate(q,-x0,-y0)
 geoms=[shift(base)];cols=[basecol];heights=[2.]
 for col,geo,h in relief:
  geo=unary_union([p for p in polygons(geo) if p.area>.04])
  if geo.is_empty:continue
  geoms.append(shift(geo));cols.append(col);heights.append(h)
 meshes=[mesh(gg,0 if i==0 else 2,hh) for i,(gg,hh) in enumerate(zip(geoms,heights))]
 for m in meshes:assert m.is_watertight and m.is_volume,(n,'bad mesh')
 combined=trimesh.boolean.union(meshes,engine='manifold');components=[q for q in combined.split() if abs(q.volume)>.001];assert combined.is_watertight and len(components)==1,(n,'disconnected')
 name=f'Set_{n:02d}_{slug}_v1.0.3mf';path=D/name
 write3mf(path,meshes,[f'{i+1:02d} {c}' for i,c in enumerate(cols)],[COL[c] for c in cols],f'Set {n:02d} - {title} - v1.0','https://www.disneylorcana.com/en-US/product/'+page)
 loaded=trimesh.load(path,process=False);assert len(loaded.geometry)==len(meshes) and all(m.is_watertight for m in loaded.geometry.values()),(n,'round trip')
 dims=np.round(loaded.extents,2).tolist()
 rep={'set':n,'title':title,'filename':name,'dimensions_mm':dims,'loop_hole_mm':4.5,'colours':cols,'solid_watertight':True,'solid_components':1,'source':'https://www.disneylorcana.com/en-US/product/'+page}
 reports.append(rep);designs.append((n,title,geoms,cols,dims));print(n,title,dims,len(cols),'colours',flush=True)
 # One exact top view per design; retained for the consolidated preview.
 fig,ax=plt.subplots(figsize=(8,4),facecolor='#F3F1EA');ax.set_aspect('equal');ax.axis('off')
 for gg,c in zip(geoms,cols):draw(ax,gg,COL[c])
 ax.autoscale_view();ax.margins(.04);fig.tight_layout();fig.savefig(D/f'Set_{n:02d}_{slug}_v1.0_preview.png',dpi=150,facecolor=fig.get_facecolor());plt.close(fig)
(P/'validation_v1.0.json').write_text(json.dumps(reports,indent=2))
fig,axs=plt.subplots(4,3,figsize=(15,15),facecolor='#F3F1EA');axs=axs.flatten()
# Accepted set 3 shown from the already-validated top-view portion of its preview.
im3=Image.open(P.parent/'inklands'/'Into_the_Inklands_preview.png').crop((500,180,1680,590))
axs[0].imshow(im3);axs[0].axis('off');axs[0].set_title('03  Into the Inklands',loc='left',fontsize=12,weight='bold')
for ax,(n,title,geoms,cols,dims) in zip(axs[1:],designs):
 ax.set_aspect('equal');ax.axis('off')
 for gg,c in zip(geoms,cols):draw(ax,gg,COL[c])
 ax.autoscale_view();ax.margins(.03);ax.set_title(f'{n:02d}  {title}',loc='left',fontsize=12,weight='bold')
 ax.text(.0,-.12,f'{dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm  |  {len(cols)} colours',transform=ax.transAxes,fontsize=9,color='#675E53')
fig.suptitle('LORCANA BINDER KEYCHAINS  /  v1.0',fontsize=23,weight='bold',x=.05,ha='left',y=.985)
fig.text(.05,.01,'Official English title art • Simplified relief for FDM • 4.5 mm attachment holes • Model geometry previews',fontsize=11,color='#675E53')
fig.tight_layout(rect=[.025,.035,.985,.965],h_pad=3,w_pad=2);fig.savefig(D/'Lorcana_Keychains_v1.0_Preview.png',dpi=170,facecolor=fig.get_facecolor());plt.close(fig)
