"""Export a strictly offline, withdrawn-Tk widget inventory and intended-layout preview.

This never maps/captures a window. Descendant allocation while withdrawn may be
1x1: SVGs are explicitly intended-layout representations, not GUI screenshots or
proof of actual pixel allocation/clipping. ROOT/cache/progress live in a tempdir.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import gc
import html
import json
from pathlib import Path
import socket
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def denied(*args, **kwargs):
    raise AssertionError('Offline preview forbids native acquisition, input and marker processes')

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

def set_cell(function, name, value):
    for key, cell in zip(function.__code__.co_freevars, function.__closure__ or ()):
        if key == name:
            cell.cell_contents = value
            return True
    return False

def widget_inventory(window):
    import tkinter as tk
    from tkinter import ttk
    style = ttk.Style(window)
    def item(widget):
        options = {}
        for key in ('text', 'style', 'state', 'width', 'height', 'padding', 'wraplength', 'font', 'background', 'foreground'):
            try:
                options[key] = str(widget.cget(key))
            except tk.TclError:
                pass
        if 'textvariable' in widget.keys():
            try:
                options['text'] = str(widget.getvar(widget.cget('textvariable')))
            except tk.TclError:
                pass
        name = options.get('style') or widget.winfo_class()
        resolved = {key: str(style.lookup(name, key)) for key in ('font','foreground','background','padding')}
        value = dict(path=str(widget), widgetClass=widget.winfo_class(), options=options,
                     resolvedStyle=resolved, requested=[widget.winfo_reqwidth(),widget.winfo_reqheight()],
                     allocated=[widget.winfo_x(),widget.winfo_y(),widget.winfo_width(),widget.winfo_height()],
                     mapped=bool(widget.winfo_ismapped()), manager=widget.winfo_manager())
        if isinstance(widget, ttk.Treeview):
            value['rows'] = [dict(id=k,values=list(widget.item(k,'values')),tags=list(widget.item(k,'tags'))) for k in widget.get_children()]
            value['selection'] = list(widget.selection())
        if isinstance(widget, tk.Canvas):
            value['primitives'] = [dict(type=widget.type(k), coordinates=widget.coords(k),
                options={key:str(v[-1]) for key,v in widget.itemconfigure(k).items()}) for k in widget.find_all()]
        if isinstance(widget, tk.Text):
            value['content'] = widget.get('1.0','end-1c')
        value['children'] = [item(child) for child in widget.winfo_children()]
        return value
    return item(window)

def preview_svg(local, width, height, tab, scenario):
    """Small explicit intended-layout composition; deliberately no Tk layout emulator."""
    import tkinter as tk
    from tkinter import ttk
    window=local['window']; style=ttk.Style(window)
    bg=style.lookup('TFrame','background') or '#101923'
    fg=style.lookup('TLabel','foreground') or '#e4eaf2'
    card=style.lookup('Card.TFrame','background') or '#172533'
    gold=style.lookup('Gold.TLabel','foreground') or '#edc477'
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           f'<rect width="100%" height="100%" fill="{bg}"/>',
           '<style>text{font-family:Segoe UI,Arial,sans-serif} .muted{fill:#9fb0c1}</style>']
    def rect(x,y,w,h,fill=card,stroke='#304252',radius=10):
        parts.append(f'<rect x="{x}" y="{y}" width="{max(0,w)}" height="{max(0,h)}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>')
    def text(x,y,value,size=12,color=fg,weight='normal'):
        parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}">{html.escape(str(value))}</text>')
    def button(x,y,label,w=None,disabled=None,widget=None):
        if widget is None:
            widget=next((v for v in descendants(window) if isinstance(v,ttk.Button) and str(v.cget('text'))==label),None)
        states=widget.state() if widget is not None else ()
        disabled=('disabled' in states) if disabled is None else disabled
        states=('disabled',) if disabled else tuple(v for v in states if v!='disabled')
        name=(str(widget.cget('style')) if widget is not None else '') or 'TButton'
        fill=style.lookup(name,'background',states) or '#1a3040'
        ink=style.lookup(name,'foreground',states) or fg
        border=style.lookup(name,'bordercolor',states) or '#415a6b'
        w=w or max(66,len(label)*7+26)
        rect(x,y,w,30,fill,border,6)
        text(x+10,y+20,label,11,ink)
        return w
    text(26,29,'RIFT / READER 2',10,gold,'600');text(26,61,'Waypoints',28,fg,'600')
    text(160,29,'AMD-DESKTOP / OFFLINE FIXTURE',10,'#a3b5c4')
    button(width-250,24,'Refresh',90);button(width-148,24,'STOP / F8',122)
    live=bool(local['live_pose'].get())
    rect(width-250,66,12,12,style.lookup('TCheckbutton','indicatorbackground',('selected',) if live else ()) or '#102131','#4b6578',2)
    if live:text(width-248,76,'v',9,bg,'bold')
    text(width-230,77,'Live pose (2 s)',11,style.lookup('TCheckbutton','foreground') or fg)
    text(width-148,76,'Always available',9,'#a3b5c4')
    status=local['state'].get();rect(24,85,width-48,32)
    text(38,106,status[:int((width-80)/6.1)],12,gold)
    text(26,140,local['pose_text'].get(),12,fg)
    text(26,163,local['summary'].get()[:int((width-54)/6.1)],11,'#9fb0c1')
    top=180;bottom=height-237;wh=bottom-top;leftw=(width-60)*.56;rightx=36+leftw
    rect(24,top,leftw,wh);rect(rightx,top,width-rightx-24,wh)
    text(38,top+25,'YOUR ROUTE',10,gold,'600');text(143,top+25,local['route_status'].get(),11,fg)
    toolbar=local.get('file_toolbar');x=38
    if toolbar:
        for child in toolbar.winfo_children():
            try: label=str(child.cget('text'))
            except tk.TclError:continue
            if label:x+=button(x,top+40,label,max(55,len(label)*6.1+20))+5
    recent=local.get('recent_dropdown')
    combo_text=recent.get() if recent is not None else ''
    combo_x,combo_y,combo_w=122,top+78,max(130,leftw-229)
    text(38,combo_y+19,'Recent routes',10,'#a3b5c4')
    rect(combo_x,combo_y,combo_w,29,style.lookup('TCombobox','fieldbackground',('readonly',)) or '#102131',style.lookup('TCombobox','bordercolor',('readonly',)) or '#4b6578',4)
    text(combo_x+9,combo_y+19,combo_text[-int((combo_w-30)/6):],10,fg)
    text(combo_x+combo_w-17,combo_y+19,'v',10,'#a3b5c4')
    button(combo_x+combo_w+7,combo_y,'Load recent',97)
    table=local['table'];ty=top+116;rowh=25
    rect(38,ty,leftw-28,max(28,wh-132),'#0f1b27','#304252',4)
    text(48,ty+20,'Waypoint',11,'#a8b9ca');text(38+leftw*.66,ty+20,'X',11,'#a8b9ca');text(38+leftw*.83,ty+20,'Z',11,'#a8b9ca')
    for n,key in enumerate(table.get_children()):
        y=ty+29+n*rowh
        if y+rowh>bottom-9:break
        if key in table.selection():rect(40,y,leftw-32,rowh,'#2b465b','#2b465b',3)
        vals=table.item(key,'values');tags=table.item(key,'tags');color='#69d1e9' if 'next' in tags else '#78b99a' if 'completed' in tags else fg
        text(48,y+17,vals[0],11,color);text(38+leftw*.66,y+17,f'{float(vals[1]):.2f}',10,color);text(38+leftw*.83,y+17,f'{float(vals[2]):.2f}',10,color)
    text(rightx+14,top+25,'LOCAL PREVIEW',10,gold,'600')
    canvas=local['canvas'];cw=max(100,width-rightx-52);ch=max(100,wh-83)
    # Redraw real Canvas primitives at the intended Canvas size without mapping.
    oldw,oldh=canvas.winfo_width,canvas.winfo_height
    canvas.winfo_width=lambda:int(cw);canvas.winfo_height=lambda:int(ch)
    try:local['redraw']()
    finally:canvas.winfo_width,canvas.winfo_height=oldw,oldh
    parts.append(f'<svg x="{rightx+14}" y="{top+40}" width="{cw}" height="{ch}" viewBox="0 0 {cw} {ch}">')
    parts.append(f'<rect width="100%" height="100%" fill="{canvas.cget("background")}"/>')
    for key in canvas.find_all():
        kind=canvas.type(key);c=canvas.coords(key);opt=lambda k:canvas.itemcget(key,k)
        fill=opt('fill') or 'none';stroke=opt('outline') if kind in ('oval','rectangle','polygon') else fill
        if kind=='oval':parts.append(f'<ellipse cx="{(c[0]+c[2])/2}" cy="{(c[1]+c[3])/2}" rx="{(c[2]-c[0])/2}" ry="{(c[3]-c[1])/2}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{opt("width") or 1}"/>')
        elif kind in ('line','polygon'):
            coords=' '.join(f'{c[i]},{c[i+1]}' for i in range(0,len(c),2));tag='polyline' if kind=='line' else 'polygon'
            parts.append(f'<{tag} points="{coords}" fill="{"none" if kind=="line" else fill}" stroke="{stroke or "none"}" stroke-width="{opt("width") or 1}"/>')
        elif kind=='text':
            anchor=opt('anchor');align='start' if 'w' in anchor else 'end' if 'e' in anchor else 'middle'
            parts.append(f'<text x="{c[0]}" y="{c[1]}" fill="{fill}" text-anchor="{align}" dominant-baseline="middle" font-size="11">{html.escape(opt("text"))}</text>')
    parts.append('</svg>');text(rightx+14,bottom-14,'Click to add     +      -      Fit       10 units',10,'#9fb0c1')
    tabs=local['workflow'];taby=height-221;x=24
    for item in tabs.tabs():
        title=tabs.tab(item,'text');bw=len(title)*7+28
        rect(x,taby,bw,31,'#253b4c' if title==tab else bg,'#304252',6);text(x+14,taby+21,title,11,gold if title==tab else '#9fb0c1');x+=bw+3
    rect(24,taby+36,width-48,143)
    selected=window.nametowidget(tabs.select());lines=[]
    for widget in descendants(selected):
        if isinstance(widget,(ttk.Button,ttk.Checkbutton,ttk.Label)):
            try:
                value=str(widget.cget('text'))
                if 'textvariable' in widget.keys() and widget.cget('textvariable'):value=str(widget.getvar(widget.cget('textvariable')))
            except tk.TclError:continue
            if value:lines.append((widget,value))
    x,y=40,taby+51
    if tab=='Replay':
        groups=[v for v in selected.winfo_children() if isinstance(v,ttk.LabelFrame)]
        gap=10;gx=38;gw=(width-76-2*gap)/3
        for group in groups:
            rect(gx,taby+49,gw,100,style.lookup('Card.TLabelframe','background') or card,'#304252',5)
            text(gx+10,taby+64,group.cget('text'),9,style.lookup('Card.TLabelframe.Label','foreground') or fg,'600')
            buttons=[v for v in group.winfo_children() if isinstance(v,ttk.Button)]
            for control in buttons:
                info=control.grid_info();row=int(info.get('row',0));col=int(info.get('column',0));span=int(info.get('columnspan',1))
                columns=3 if group.cget('text')=='DIRECT MOVEMENT' else 2
                cell=(gw-20-5*(columns-1))/columns
                button(gx+10+col*(cell+5),taby+71+row*36,str(control.cget('text')),cell*min(span,columns)+5*(min(span,columns)-1),widget=control)
            for control in group.winfo_children():
                if isinstance(control,ttk.Checkbutton):
                    checked=bool(window.getvar(control.cget('variable')))
                    rect(gx+11,taby+113,11,11,'#7fe3c3' if checked else '#102131','#4b6578',2)
                    text(gx+28,taby+123,control.cget('text'),10,'#a3b5c4')
            gx+=gw+gap
        text(40,taby+170,local['progress_text'].get()[:int((width-90)/6)],10,'#a3b5c4')
        lines=[]
    if tab=='Edit waypoint':
        # These three fields and two action rows mirror the explicit source groups.
        entries=local['point_entries'];ex=40
        for label,control,fieldw in zip(('Name','X','Z'),entries,(240,174,174)):
            text(ex,taby+69,label,11,fg);ex+=42 if label=='Name' else 20
            states=control.state();fill=style.lookup('TEntry','fieldbackground',states) or '#0a1722'
            border=style.lookup('TEntry','bordercolor',states) or '#4b6578'
            rect(ex,taby+49,fieldw,29,fill,border,4)
            text(ex+8,taby+69,control.get(),11,style.lookup('TEntry','foreground',states) or fg)
            ex+=fieldw+18
        for parent,by in ((local['buttons'],taby+91),(local['buttons_second'],taby+130)):
            bx=40
            for control in parent.winfo_children():
                if isinstance(control,ttk.Button):
                    label=str(control.cget('text'));bw=max(58,len(label)*6.5+24)
                    bx+=button(bx,by,label,bw,widget=control)+6
        lines=[]
    if tab=='Scene & beacons':
        groups=[v for v in selected.winfo_children() if isinstance(v,ttk.LabelFrame)]
        gx=38;gw=(width-90)/2
        for group in groups:
            rect(gx,taby+49,gw,116,style.lookup('Card.TLabelframe','background') or card,'#304252',5)
            text(gx+11,taby+65,group.cget('text'),9,style.lookup('Card.TLabelframe.Label','foreground') or fg,'600')
            bx=gx+11
            for control in descendants(group):
                if isinstance(control,ttk.Button):
                    label=str(control.cget('text'));bw=max(66,len(label)*6.5+24)
                    bx+=button(bx,taby+73,label,bw,widget=control)+6
            checks=[v for v in group.winfo_children() if isinstance(v,ttk.Checkbutton)]
            for n,control in enumerate(checks):
                cy=taby+116+n*25;states=control.state();checked=bool(window.getvar(control.cget('variable')))
                rect(gx+12,cy-10,11,11,style.lookup('TCheckbutton','indicatorbackground',('selected',) if checked else ()) or '#0a1722','#4b6578',2)
                if checked:text(gx+13,cy,'v',9,bg)
                text(gx+30,cy,str(control.cget('text')),11,style.lookup('TCheckbutton','foreground',states) or fg)
            gx+=gw+14
        lines=[]
    if tab=='Activity':
        lines=[]
        text(40,taby+65,local['state'].get()[:int((width-90)/6)],11,gold)
        rect(39,taby+76,width-78,88,local['log'].cget('background'),'#4b6578',3)
    for widget,value in lines:
        if isinstance(widget,(ttk.Button,ttk.Checkbutton)):
            bw=max(66,len(value)*6.5+25)
            if x+bw>width-38:x,y=40,y+40
            if y+30<height-34:x+=button(x,y,value,bw,str(widget.cget('state'))=='disabled')+7
        else:
            if x>40:x,y=40,y+39
            if y+15<height-34:text(x,y+14,value[:int((width-90)/6)],11,'#a9b9c9');y+=23
    if tab=='Activity':
        content=local['log'].get('1.0','end-1c').strip().splitlines()[-4:]
        for n,line in enumerate(content):text(49,taby+94+n*19,line[:int((width-90)/6)],11,'#b2c3d2')
    text(25,height-12,'OFFLINE WIDGET-LAYOUT PREVIEW  -  intended placement; withdrawn allocation is not a screenshot',9,'#7e90a2')
    parts.append('</svg>');return '\n'.join(parts)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'output/playwright/waypoint-ui')
    args=parser.parse_args(argv)
    if socket.gethostname().upper()!='AMD-DESKTOP':raise SystemExit('Host mismatch: AMD-DESKTOP required')
    import tkinter as tk
    from tkinter import ttk
    from scripts import physical_waypoints as app
    args.output.mkdir(parents=True,exist_ok=True)
    actual_tk=tk.Tk; roots=[];threads=[];local={};errors=[]
    route=json.loads((ROOT/'docs/validation/gui-taught-route-2026-11-12.json').read_text())
    identity=route['recording']['identity']
    position=route['waypoints'][0];pose=app.Snapshot(app.Position(position[1],route['heights'][0],position[2]),62,time.monotonic(),'offline-fixture')
    adapter=SimpleNamespace(pid=123,binding=identity,read=lambda **kw:pose,identity=denied,pulse=denied,reserve=denied)
    def root_factory(*a,**kw):
        r=actual_tk(*a,**kw);r.withdraw();r.report_callback_exception=lambda *e:errors.append(str(e[1]));roots.append(r);return r
    class InlineThread:
        def __init__(self,target,args=(),kwargs=None,**kw):self.target=target;self.args=args;self.kwargs=kwargs or {};threads.append(self)
        def start(self):self.target(*self.args,**self.kwargs)
        def is_alive(self):return False
        def join(self,*a,**kw):pass
    def capture_loop(self,*a,**kw):local.update(sys._getframe(1).f_locals)
    was_gc=gc.isenabled();gc.collect();gc.disable()
    try:
      with tempfile.TemporaryDirectory(prefix='rr2-offline-ui-') as temp,ExitStack() as stack:
        sandbox=Path(temp);(sandbox/'artifacts').mkdir();path=sandbox/'seven-point-demo.json';path.write_text(json.dumps(route))
        for obj,name,value in ((app,'ROOT',sandbox),(tk,'Tk',root_factory),(actual_tk,'mainloop',capture_loop),
                (app.threading,'Thread',InlineThread),(app,'ForegroundStop',denied),(app,'PhysicalAdapter',denied),
                (app.physical_rift,'select_physical',denied),(app.physical_rift,'read_native',denied)):
            stack.enter_context(patch.object(obj,name,value))
        app.launch_window(SimpleNamespace(expected_host='AMD-DESKTOP',physical_pid=123,initial_adapter=adapter,
            basis=Path('offline-unused'),face_waypoints=True,route=path,auto_reconnect=False,initial_reason=None))
        window=roots[0]
        for _ in range(3):window.update();time.sleep(.09)
        if window.state()!='withdrawn' or window.winfo_ismapped():raise AssertionError('Preview must remain withdrawn')
        table=local['table'];table.selection_set(table.get_children()[2]);local['select_point'](None)
        local['live_pose'].set(False)
        previews=[]
        scenarios=[('idle-start',0,False),('idle-corner',2,False),('busy-next',4,True)]
        for scenario,index,busy in scenarios:
            point=route['waypoints'][index]
            for function in (local['redraw'],local['poll']):
                set_cell(function,'last_pose',(point[1],point[2],62));set_cell(function,'last_y',route['heights'][index])
                set_cell(function,'busy',busy);set_cell(function,'playback_view',dict(direction='forward',nextIndex=index))
            local['state'].set('Walking to Recorded 5  -  synthetic busy fixture; STOP remains available' if busy else 'Ready  -  offline seven-point route loaded')
            local['pose_text'].set(f'X {point[1]:.6f}    Y {route["heights"][index]:.6f}    Z {point[2]:.6f}    Facing 62.00 -    -   OFFLINE')
            local['progress_text'].set(f'{index} / 7 confirmed  -  next Recorded {index+1}  -  synthetic fixture')
            for widget in local.get('editable',[]):widget.configure(state='disabled' if busy else 'normal')
            for widget in descendants(window):
                if isinstance(widget,ttk.Button):
                    label=str(widget.cget('text'))
                    if label in ('Play Forward','Play Reverse','Resume','Walk + Record','Record','Run Route','Go Selected','Face Selected','Save current position','Save Current'):
                        widget.configure(state='disabled' if busy else 'normal')
            local['log'].configure(state='normal');local['log'].delete('1.0','end')
            local['log'].insert('end', 'OFFLINE FIXTURE  -  no native process connected.\n'
                'Loaded seven actual retained recorded points; original provenance unchanged.\n'
                + (f'Synthetic playback: {index}/7 confirmed; next Recorded {index+1}.\n' if busy else 'Ready: choose a waypoint or playback direction.\n')
                + 'This preview made no gameplay input or captures.\n')
            local['log'].configure(state='disabled')
            for width,height in ((1120,850),(980,740)):
                window.geometry(f'{width}x{height}');window.update_idletasks()
                for item in local['workflow'].tabs():
                    local['workflow'].select(item);window.update_idletasks();tab=local['workflow'].tab(item,'text')
                    slug=f'{width}x{height}-{scenario}-{tab.split()[0].lower()}'
                    svg=preview_svg(local,width,height,tab,scenario);(args.output/(slug+'.svg')).write_text(svg,encoding='utf-8')
                    (args.output/(slug+'.json')).write_text(json.dumps(widget_inventory(window),indent=2),encoding='utf-8')
                    previews.append(dict(file=slug+'.svg',width=width,height=height,scenario=scenario,tab=tab))
        manifest=dict(kind='offline-widget-layout-preview',host='AMD-DESKTOP',mapped=False,
            limitation='Real Tk requested sizes/styles/widget tree/Canvas primitives. Intended placement only; withdrawn descendant allocation is not on-screen geometry or screenshot proof.',
            scenarios=scenarios,previews=previews,callbackErrors=errors)
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        cards=''.join(f'<section data-size="{v["width"]}" data-scenario="{v["scenario"]}"><h2>{html.escape(v["tab"])} <small>{v["scenario"]}  -  {v["width"]} - {v["height"]}</small></h2><a href="{v["file"]}"><img src="{v["file"]}" width="{v["width"]}" height="{v["height"]}"></a></section>' for v in previews)
        page='''<!doctype html><meta charset="utf-8"><title>RR2  -  Offline waypoint layout review</title><style>body{margin:0;background:#090f17;color:#dce8f1;font:15px Segoe UI,Arial}header,main{padding:28px 4vw}header{border-bottom:1px solid #293846;background:#111c29}h1{font-size:32px;margin:8px 0;color:#f0c97e}p{max-width:1050px;line-height:1.6;color:#a8b9ca}button{background:#1d3042;border:1px solid #405c72;color:#dce8f1;padding:10px 17px;border-radius:7px;margin:4px;cursor:pointer}section{margin:15px 0 42px}h2{font-size:20px}small{font-weight:400;color:#879caf;margin-left:15px}img{max-width:100%;height:auto;box-shadow:0 14px 50px #0008;border:1px solid #304355;border-radius:10px}a{color:#8ed8ef}</style><header><span>RIFT / READER 2  -  DESIGN REVIEW</span><h1>Waypoint workspace  -  offline layout preview</h1><p>Actual current Tk widget tree, text, requested sizes, styles and real Canvas primitives, assembled into an intended-layout representation. All Tk roots remained withdrawn. This is <b>not a GUI screenshot</b> or proof of on-screen allocation, exact clipping, keyboard focus or interaction. Three synthetic pose/progress states; no game or native connection.</p><div><button onclick="filter(1120)">1120  -  850</button><button onclick="filter(980)">980  -  740</button><button onclick="filter(0)">All sizes</button></div><a href="manifest.json">Evidence manifest</a></header><main>'''+cards+'''</main><script>function filter(n){document.querySelectorAll('section').forEach(x=>x.hidden=n&&+x.dataset.size!==n)}filter(1120)</script>'''
        (args.output/'index.html').write_text(page,encoding='utf-8')
        print(json.dumps(dict(output=str(args.output/'index.html'),previews=len(previews),mapped=False,callbackErrors=errors)))
        if errors:raise RuntimeError('Offline callback errors: '+str(errors))
    finally:
        for thread in threads:thread.join()
        for window in roots:
            try:
                for cb in window.tk.call('after','info'):window.after_cancel(cb)
                window.destroy()
            except tk.TclError:pass
        local.clear();roots.clear();gc.collect()
        if was_gc:gc.enable()
    return 0

if __name__=='__main__':raise SystemExit(main())
