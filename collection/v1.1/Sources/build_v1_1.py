from pathlib import Path
# Reuse the geometry primitives, not the earlier colour masks.
exec(Path(__file__).with_name('build_collection.py').read_text().split('reports=[]')[0])
D=P/'v1.1';D.mkdir(exist_ok=True)
SETS={1:('The_First_Chapter','The First Chapter',''),2:('Rise_of_the_Floodborn','Rise of the Floodborn','rise-of-the-floodborn'),3:('Into_the_Inklands','Into the Inklands','into-the-inklands'),**SETS}

def clean(mask,scale,closing=.35,opening=.12):
 def kernel(mm):return cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(max(1,round(mm/scale))*2+1,)*2)
 raw=mask.astype('uint8')
 if closing:raw=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,kernel(closing))
 if opening:raw=cv2.morphologyEx(raw,cv2.MORPH_OPEN,kernel(opening))
 return maskgeom(raw,scale,len(raw),minarea=.16).simplify(.04)

reports=[];designs=[]
for n,(slug,title,page) in SETS.items():
 if n==1:im=Image.open(P/'sources/01-header.png').convert('RGBA').crop((630,680,1290,885))
 elif n==2:im=Image.open(P/'sources/02-header.png').convert('RGBA').crop((610,750,1290,1005))
 elif n==3:im=Image.open(P.parent/'inklands/official-header.png').convert('RGBA').crop((600,715,1320,1055))
 else:
  im=Image.open(P/'sources'/f'{n:02d}.png').convert('RGBA')
  if n==4:im=im.crop((625,680,1290,1040))
 if n>3:
  a=np.array(im);yy,xx=np.where(a[:,:,3]>140);im=im.crop((max(0,xx.min()-2),max(0,yy.min()-2),min(im.width,xx.max()+3),min(im.height,yy.max()+3)))
 a=np.array(im);H,W=a.shape[:2];r,g,b=a[:,:,:3].transpose(2,0,1).astype(float);valid=a[:,:,3]>135;scale=min(84/W,40/H);Y,X=np.indices((H,W))
 G=lambda m,c=.35,o=.12:clean(m&valid,scale,c,o)
 if n==1:
  basecol='Purple';face=G((r>220)&(g>220)&(b>220),.16,.05);regions=[('Ivory White',face,.8)]
 elif n==2:
  basecol='Marine Blue';face=G((r>155)&(g>155)&(b>145),.32,.05);regions=[('Ice Blue',face.buffer(.55),.4),('Ivory White',face,.8)]
 elif n==3:
  basecol='Cocoa Brown';gold=(r>165)&(g>100)&(r>b*1.15)&(g>b*1.08)
  full=G(gold,.20,.04); top=unary_union([q for q in polygons(full) if q.centroid.y>scale*(H-105)]); face=unary_union([q for q in polygons(full) if q.centroid.y<=scale*(H-105)])
  regions=[('Ice Blue',face.buffer(.65),.4),('Sunflower Yellow',face.union(top),1.)]
 elif n==4:
  basecol='Purple';regions=[('Sunflower Yellow',G((r>145)&(g>90)&(r>1.15*b)&(r>1.12*g),.55,.13),.8),('Ice Blue',G((b>120)&(g>120)&(r<g*1.15)&(b>r*.95),.45,.12),.8)]
 elif n==5:
  basecol='Purple';regions=[('Red',G((r>105)&(r>g*1.5)&(r>b*1.1),.5,.15),.4),('Ivory White',G((r>185)&(g>130)&(b>70),.25,.06),1.)]
 elif n==6:
  basecol='Marine Blue';regions=[('Ice Blue',G((g>95)&(b>100)&(r<g*.8),.25,.1),.4),('Sunflower Yellow',G((r>140)&(g>80)&(r>b*1.12),.35,.08),.8)]
 elif n==7:
  basecol='Dark Green';regions=[('Caramel',maskgeom(valid,scale,H,minarea=.15,holes=False).buffer(-.25).difference(maskgeom(valid,scale,H,minarea=.15,holes=False).buffer(-.9)),.4),('Ivory White',G((r>210)&(g>170)&(b>115),.25,.07),1.)]
 elif n==8:
  basecol='Charcoal';regions=[('Pumpkin Orange',G((r>140)&(g>75)&(r>b*1.5),.3,.12),.4),('Sunflower Yellow',G((r>220)&(g>180)&(b>110),.35,.12),.8),('Red',G((r>120)&(g<105)&(b<60),.35,.12),.8)]
 elif n==9:
  basecol='Marine Blue';letters=G((b>r*1.12)&(b>g*1.12)&(b<170),.2,.05)
  gold=G((r>95)&(g>70)&(r>b*1.08),.4,.1)
  regions=[('Sunflower Yellow',gold.union(letters.buffer(.55)),.6),('Purple',letters,1.)]
 elif n==10:
  basecol='Charcoal';warm=G((r>100)&(g>55)&(r>g*1.08)&(b<g),.16,.05); warm=unary_union([q for q in polygons(warm) if q.area>.8 and q.centroid.y>H*scale*.58])
  regions=[('Ash Gray',G((r>75)&(g>75)&(b>65)&(r<g*1.35),.14,.04),.8),('Sunflower Yellow',warm,.8)]
 elif n==11:
  basecol='Marine Blue';face=G((r>145)&(g>110)&(r>b*.92),.3,.06)
  regions=[('Ice Blue',G((b>100)&(b>r*1.05)&(g>80),.5,.15).union(face.buffer(.55)),.4),('Ivory White',face,1.)]
 elif n==12:
  basecol='Cocoa Brown';regions=[('Dark Green',G((g>r*1.05)&(g>b*1.2),.3,.12),.6),('Ivory White',G((r>160)&(g>135)&(b>75)&(g>r*.65),.25,.06),1.)]
 elif n==13:
  basecol='Purple';text=G((g>95)&(b<g*.8)&(r>65),.12,.04);split=maskgeom((Y<H*.46-X*.14).astype('uint8'),scale,H,minarea=.1)
  regions=[('Mistletoe Green',text.intersection(split),.8),('Sunflower Yellow',text.difference(split),.8)]
 elif n==14:
  basecol='Cocoa Brown';face=G((r>195)&(g>165)&(b>100),.35,.08)
  regions=[('Caramel',G((r>105)&(g>55)&(b<g*.85)&(r>g*1.15),.45,.12).union(face.buffer(.5)),.4),('Ivory White',face,1.)]
 # Flatten raster texture and build continuous, mechanically sound backing.
 if n<=2:silhouette=unary_union([q for _,q,_ in regions]).buffer(1.1)
 elif n==3:
  colored=G((r>25)|(g>25)|(b>25),.3,0)
  silhouette=unary_union([Polygon(q.exterior) for q in polygons(colored) if q.area>1]).buffer(.9)
 else:silhouette=maskgeom(valid,scale,H,minarea=.15,holes=False).buffer(.8).simplify(.04)
 silhouette=unary_union([q for q in polygons(silhouette) if q.area>.4])
 while len(polygons(silhouette))>1:
  ps=sorted(polygons(silhouette),key=lambda q:q.area,reverse=True);main=ps[0];other=min(ps[1:],key=lambda q:q.distance(main));p1,p2=nearest_points(main,other);silhouette=unary_union([silhouette,LineString([p1,p2]).buffer(1.1)])
 # Ensure outline is fully supported.
 silhouette=silhouette.union(unary_union([q for _,q,_ in regions]).buffer(.25))
 bounds=silhouette.bounds;cy=(bounds[1]+bounds[3])/2;inter=silhouette.intersection(LineString([(bounds[0]-2,cy),(bounds[2]+2,cy)]));anchor=inter.bounds[0];cx=bounds[0]-4.5
 base=silhouette.union(box(cx,cy-3.5,anchor+2.5,cy+3.5)).union(Point(cx,cy).buffer(5.25,quad_segs=40)).difference(Point(cx,cy).buffer(2.25,quad_segs=40))
 # Ordered parts without overlapping volumes; outline rings remain around faces.
 occupied=Polygon();cleaned=[]
 for col,geo,h in reversed(regions):
  gg=geo.difference(occupied).buffer(0);gg=unary_union([q for q in polygons(gg) if q.area>.08]);cleaned.append((col,gg,h));occupied=occupied.union(geo)
 regions=list(reversed(cleaned));x0,y0,_,_=base.bounds;shift=lambda q:affinity.translate(q,-x0,-y0)
 geoms=[shift(base)]+[shift(q) for _,q,_ in regions];cols=[basecol]+[c for c,_,_ in regions];hs=[2.]+[h for _,_,h in regions]
 meshes=[mesh(q,0 if i==0 else 2,h) for i,(q,h) in enumerate(zip(geoms,hs))]
 for m in meshes:assert m.is_volume and m.is_watertight,n
 solid=trimesh.boolean.union(meshes,engine='manifold');assert len(solid.split())==1,(n,'disconnected')
 # Export intermediate geometry for a separate Bambu project writer.
 dest=D/f'Set_{n:02d}_{slug}_v1.1.3mf';write3mf(dest,meshes,cols,[COL[c] for c in cols],title,'https://www.disneylorcana.com/en-US/product/'+page)
 dims=np.round(solid.extents,2).tolist();reports.append(dict(set=n,title=title,filename=dest.name,dimensions_mm=dims,colours=cols,source='https://www.disneylorcana.com/en-US/product/'+page));designs.append((n,title,geoms,cols,dims))
 fig,ax=plt.subplots(figsize=(9,4),facecolor='#F3F1EA');ax.set_aspect('equal');ax.axis('off')
 for q,c in zip(geoms,cols):draw(ax,q,COL[c])
 ax.autoscale_view();ax.margins(.04);fig.tight_layout();fig.savefig(D/f'Set_{n:02d}_{slug}_v1.1_preview.png',dpi=130);plt.close(fig)
 print(n,title,dims,flush=True)
(D/'Validation_v1.1.json').write_text(json.dumps(reports,indent=2))
fig,axs=plt.subplots(5,3,figsize=(15,18),facecolor='#F3F1EA')
for ax in axs.flat:ax.axis('off')
for ax,(n,title,geoms,cols,dims) in zip(axs.flat,designs):
 ax.set_aspect('equal')
 for q,c in zip(geoms,cols):draw(ax,q,COL[c])
 ax.autoscale_view();ax.margins(.04);ax.set_title(f'{n:02d}  {title}',loc='left',fontsize=12,weight='bold');ax.text(0,-.12,f'{dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm | {len(cols)} colours',transform=ax.transAxes,fontsize=9)
fig.suptitle('LORCANA BINDER KEYCHAINS / v1.1',fontsize=23,weight='bold',x=.05,ha='left');fig.tight_layout(rect=[.02,.02,.98,.965],h_pad=3);fig.savefig(D/'Lorcana_Keychains_v1.1_Preview.png',dpi=140);plt.close(fig)
