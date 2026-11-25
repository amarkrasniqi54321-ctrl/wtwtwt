#!/usr/bin/env python3
"""Reproduce historical Monsoon analysis and conditional six-day model.
Usage: python analyze_energy.py BASELINE.zip OPTIMIZED.zip --out results
Dependencies: numpy pandas scipy matplotlib. No current-hardware measurements.
"""
import argparse, io, zipfile, re, json, hashlib, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.ndimage import median_filter,binary_closing
from scipy.signal import find_peaks
from scipy.optimize import minimize_scalar
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DT=0.0002; BIN=.02; FS=5000; T=144*3600
REF=dict(base_W=262.86/144,base_sensor_J=3.79*3600/259200,base_camera_J=7.03*3600/8640,opt_W=192.86/144,opt_sensor_J=.092838,opt_block_J=55.848094,opt_block_s=34.72,overhead_s=.334625)

def read_csv_bytes(b):
    a=pd.read_csv(io.BytesIO(b)).to_numpy(dtype=float); a[:,1]/=1000
    if not np.isfinite(a).all() or np.any(a[:,1]<0): raise ValueError('Invalid power values')
    tick=np.rint(a[:,0]*FS).astype(np.int64)
    if np.max(np.abs(a[:,0]-tick/FS))>1e-7 or np.any(np.diff(tick)<=0) or np.max(np.diff(tick))>50: raise ValueError('Nonmonotonic timestamp or gap >10 ms')
    return a

def bins(a):
    tick=np.rint(a[:,0]*FS).astype(np.int64); k=tick//100; offset=k[0]; k-=offset
    cnt=np.bincount(k); p=np.bincount(k,weights=a[:,1])/np.maximum(cnt,1)
    t=(np.arange(len(cnt))+offset+.5)*BIN
    if np.any(cnt[1:-1]==0): raise ValueError("Empty interior bin")
    keep=np.ones(len(cnt),bool);keep[0]=cnt[0]==100;keep[-1]=cnt[-1]==100
    return t[keep],p[keep]

def groups(mask):
    x=np.flatnonzero(np.diff(np.r_[False,mask,False]));return list(zip(x[::2],x[1::2]))

def summary(a,name,status):
    t,p=a.T;return dict(trace=name,status=status,samples=len(t),start_s=t[0],end_s=t[-1],duration_s=t[-1]-t[0],missing_nominal_samples=int(round((t[-1]-t[0])*FS))+1-len(t),max_gap_ms=1000*np.diff(t).max(),energy_J=np.trapezoid(p,t),mean_W=np.trapezoid(p,t)/(t[-1]-t[0]),min_W=p.min(),median_W=np.median(p),p95_W=np.quantile(p,.95),max_W=p.max())

def baseline(a,name):
    t,p=bins(a); peakidx=find_peaks(p,height=4,distance=int(20/BIN))[0]; peaks=t[peakidx]
    camera=np.zeros(len(t),bool)
    for q in peaks:camera|=(t>=q-3)&(t<q+3)
    ordinary=(t>=20)&(t<t[-1]-2)&~camera
    tt=t[ordinary]; yy=np.clip((p-median_filter(p,51))[ordinary],0,.6)
    freq=np.linspace(.497,.506,181)
    scores=[abs(np.dot(yy,np.exp(2j*np.pi*f*tt))) for f in freq];j=np.argmax(scores)
    f=minimize_scalar(lambda f:-abs(np.dot(yy,np.exp(2j*np.pi*f*tt))),bounds=(freq[max(0,j-1)],freq[min(len(freq)-1,j+1)]),method='bounded').x
    period=1/f; phase=np.floor((tt*f%1)*100).astype(int)
    profile=np.array([p[ordinary][phase==k].mean() for k in range(100)])
    # Quiescent phase reference: lowest 60% of phase-bin means. This is an inferred decomposition, not isolated component power.
    sens=(profile.mean()-np.sort(profile)[:60].mean())*period
    ordinary_W=p[ordinary].mean(); base_W=ordinary_W-sens/period
    events=[]
    for q in peaks:
        if q>23 and q+3<t[-1]:
            mask=(t>=q-3)&(t<q+3)
            events.append(dict(trace=name,kind='camera-like',center_s=q,start_s=q-3,end_s=q+3,duration_s=mask.sum()*BIN,increment_J=np.sum(p[mask]-ordinary_W)*BIN))
    # sensitivity to event window and phase reference; report as method dependence, not CI
    variants=[]
    for half in [2.5,3,4]:
        cm=np.zeros(len(t),bool)
        for q in peaks:cm|=(t>=q-half)&(t<q+half)
        m=(t>=20)&(t<t[-1]-2)&~cm; ph=np.floor((t[m]*f%1)*100).astype(int)
        pr=np.array([p[m][ph==k].mean() for k in range(100)]);ordW=p[m].mean()
        for pct in [.4,.6,.8]:
            e=(pr.mean()-np.sort(pr)[:int(100*pct)].mean())*period
            es=[np.sum(p[(t>=q-half)&(t<q+half)]-ordW)*BIN for q in peaks if q>20+half and q+half<t[-1]]
            variants.append(dict(trace=name,half_window_s=half,quiet_phase_fraction=pct,base_W=ordW-e/period,sensor_J=e,camera_J=np.mean(es)))
    return dict(trace=name,period_s=period,base_W=base_W,sensor_J=sens,camera_J=np.mean([x['increment_J'] for x in events]),camera_events=len(events),ordinary_W=ordinary_W),events,variants,(t,p,peaks)

def optimized(a,name):
    t,p=bins(a); low=np.median(p[p<1.4]); long=binary_closing(p>1.6,structure=np.ones(26)); all_blocks=[(a,b) for a,b in groups(long) if (b-a)*BIN>3]
    exc=np.zeros(len(p),bool);events=[];sensors=[];bl=[]
    for a,b in all_blocks:
        exc[max(0,a-50):min(len(p),b+50)]=True
        # Exclude truncated and partial edge blocks; require quiet before and after.
        if a<50 or b+50>=len(p) or np.median(p[a-50:a-10])>1.4 or np.median(p[b+10:b+50])>1.4:continue
        # extend .36s on each side to capture transition tails; signed excess
        aa=a-18;bb=b+18; e=np.sum(p[aa:bb]-low)*BIN
        row=dict(trace=name,kind='Pi-like block',center_s=(t[aa]+t[bb-1])/2,start_s=t[aa]-BIN/2,end_s=t[bb-1]+BIN/2,duration_s=(bb-aa)*BIN,increment_J=e)
        events.append(row);bl.append(row)
    for a,b in groups(binary_closing((p>1.42)&~exc,structure=np.ones(4))):
        if .20<=(b-a)*BIN<=.9 and a>=8 and b+8<len(p) and not exc[a-5:b+5].any():
            aa=a-4;bb=b+4;e=np.sum(p[aa:bb]-low)*BIN
            row=dict(trace=name,kind='sensor-like',center_s=t[a],start_s=t[aa]-BIN/2,end_s=t[bb-1]+BIN/2,duration_s=(bb-aa)*BIN,increment_J=e)
            events.append(row);sensors.append(row)
    gaps=np.diff([x['center_s'] for x in sensors]);gaps=gaps[(gaps>9)&(gaps<12)]
    return dict(trace=name,low_W=low,sensor_J=np.mean([x['increment_J'] for x in sensors]),sensor_sd_J=np.std([x['increment_J'] for x in sensors],ddof=1),sensor_events=len(sensors),block_J=np.mean([x['increment_J'] for x in bl]),block_sd_J=np.std([x['increment_J'] for x in bl],ddof=1),block_s=np.mean([x['duration_s'] for x in bl]),blocks=len(bl),sensor_period_s=np.median(gaps),overhead_s=np.median(gaps)-10),events,(t,p,bl,sensors)

def simulate(n,period,kind):
    since=stable=0;prev=0;requested=False; times=[]; reasons=[]
    # Explicit deterministic synthetic environment: 2 x 2h persistent threshold episodes per day.
    for i in range(n):
        sec=i*period; tod=sec%86400
        alarm=1 if kind=='normal' or (kind=='dynamic' and (8*3600<=tod<10*3600 or 18*3600<=tod<20*3600)) else 0
        # 'normal' control: nonstable without alarm edges, forcing scheduled 30-min operation.
        valid=(kind!='normal'); mask=0 if kind=='normal' else alarm
        since+=1;stable=min(360,stable+1) if valid and mask==0 else 0
        interval=360 if requested and stable>=90 else 90
        reason='alarm_new' if mask&~prev else ('scheduled_120m' if interval==360 else 'scheduled_30m') if since>=interval else None
        if reason:times.append(sec);reasons.append(reason);since=0;requested=True
        prev=mask
    return np.array(times),reasons

def net_block_j(c):
    # Remove estimated sensing already embedded at the historical 10 s sleep cadence.
    return c['opt_block_J']-c['opt_block_s']/(10+c['overhead_s'])*c['opt_sensor_J']

def project(c,kind):
    period=20+c['overhead_s']; ns=math.ceil(T/period); times,reasons=simulate(ns,period,kind)
    # Include one initial manually booted Pi block at t=0 for each optimized scenario.
    n=len(times)+1
    B=c['base_W']*144; S=25920*c['base_sensor_J']/3600; C=288*c['base_camera_J']/3600
    ob=c['opt_W']*144; os=ns*c['opt_sensor_J']/3600; oc=n*net_block_j(c)/3600
    return dict(scenario=kind,baseline_bg_Wh=B,baseline_sensor_Wh=S,baseline_camera_Wh=C,baseline_Wh=B+S+C,opt_bg_Wh=ob,opt_sensor_Wh=os,opt_block_Wh=oc,opt_Wh=ob+os+oc,savings_Wh=B+S+C-ob-os-oc,savings_pct=100*(1-(ob+os+oc)/(B+S+C)),baseline_samples=25920,opt_samples=ns,baseline_camera_events=288,opt_requests=len(times),opt_activity_blocks=n,scheduled_30m=reasons.count('scheduled_30m'),scheduled_120m=reasons.count('scheduled_120m'),alarm_new=reasons.count('alarm_new'),period_s=period),times,reasons

def main():
    ap=argparse.ArgumentParser();ap.add_argument('baseline_zip');ap.add_argument('optimized_zip');ap.add_argument('--out',default='results');args=ap.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    stats=[]; br=[]; ore=[]; event=[]; variants=[]; bplots={};oplots={}; manifest=[]
    for path,mode in [(args.baseline_zip,'baseline'),(args.optimized_zip,'optimized')]:
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            for name in sorted(z.namelist()):
                if not name.endswith('.csv'):continue
                b=z.read(name);trace=mode+'/'+Path(name).name;manifest.append(dict(trace=trace,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
                if mode=='optimized' and Path(name).stem=='meritev1':
                    # Strictly delimit known localized corruption by invalid lines and validate both clean tails independently.
                    lines=b.split(b'\n');pat=re.compile(rb'[0-9]+\.[0-9]{4},[0-9]+(?:\.[0-9]+)?\r?'); bad=[i for i,l in enumerate(lines[1:],1) if l and not pat.fullmatch(l)]
                    if not bad:raise ValueError('Expected known corrupt trace; reassess')
                    # Exclude 0.2 s guard either side (1000 samples) and all intervening rows. No reconstruction or interpolation.
                    pre=read_csv_bytes(b'\n'.join([lines[0]]+lines[1:min(bad)-1000]));post=read_csv_bytes(b'\n'.join([lines[0]]+lines[max(bad)+1001:]))
                    stats.append(dict(trace=trace,status=f'full trace excluded: {len(bad)} invalid-format rows; additional numeric corruption possible; two contiguous tails used only as sensitivity'))
                    for suffix,a in [('prefix',pre),('suffix',post)]:
                        n=trace+':'+suffix;stats.append(summary(a,n,'partial corroboration only'));r,e,plot=optimized(a,n);ore.append(r);event+=e;oplots[n]=plot
                    continue
                a=read_csv_bytes(b);stats.append(summary(a,trace,'complete valid CSV'))
                if mode=='baseline':r,e,v,plot=baseline(a,trace);br.append(r);event+=e;variants+=v;bplots[trace]=plot
                else:r,e,plot=optimized(a,trace);ore.append(r);event+=e;oplots[trace]=plot
    for name,rows in [('input_manifest',manifest),('trace_quality',stats),('baseline_coefficients',br),('optimized_coefficients',ore),('identified_events',event),('baseline_method_sensitivity',variants)]:pd.DataFrame(rows).to_csv(out/(name+'.csv'),index=False)
    bdf=pd.DataFrame(br); odf=pd.DataFrame(ore);o=odf[odf.trace=='optimized/meritev2.csv'].iloc[0]
    # Primary independent estimate: equal weight per baseline run, complete optimized run only. Corrupt tails are validation/sensitivity.
    c=dict(base_W=bdf.base_W.mean(),base_sensor_J=bdf.sensor_J.mean(),base_camera_J=bdf.camera_J.mean(),opt_W=o.low_W,opt_sensor_J=o.sensor_J,opt_block_J=o.block_J,opt_block_s=o.block_s,overhead_s=o.overhead_s)
    pd.DataFrame([dict(method='independent',**c),dict(method='historical_reference',**REF)]).to_csv(out/'model_coefficients.csv',index=False)
    rows=[]; timelines={}
    for method,coeff in [('independent',c),('historical_reference',REF)]:
        for kind in ['stable','normal','dynamic']:
            r,ts,reasons=project(coeff,kind);rows.append(dict(method=method,**r));
            if method=='independent':timelines[kind]=ts;pd.DataFrame({'time_s':ts,'reason':reasons}).to_csv(out/f'wake_requests_{kind}.csv',index=False)
    pd.DataFrame(rows).to_csv(out/'projections.csv',index=False)
    sens=[]
    for k in range(0,601):
        ns=math.ceil(T/(20+c['overhead_s']));e=144*c['opt_W']+(ns*c['opt_sensor_J']+k*net_block_j(c))/3600; B=rows[0]['baseline_Wh'];sens.append(dict(blocks=k,optimized_Wh=e,savings_pct=100*(1-e/B)))
    sd=pd.DataFrame(sens);sd.to_csv(out/'activation_sensitivity.csv',index=False)
    # Deterministic empirical/model sensitivity envelope, not statistical confidence interval.
    vdf=pd.DataFrame(variants); scenarios=[]
    for (half,q),v in vdf.groupby(['half_window_s','quiet_phase_fraction']):
        for _,x in odf.iterrows():
            cf=dict(base_W=v.base_W.mean(),base_sensor_J=v.sensor_J.mean(),base_camera_J=v.camera_J.mean(),opt_W=x.low_W,opt_sensor_J=x.sensor_J,opt_block_J=x.block_J,opt_block_s=x.block_s,overhead_s=x.overhead_s)
            for kind in ['stable','normal','dynamic']:
                p,_,_=project(cf,kind);scenarios.append(dict(half_window_s=half,quiet_phase_fraction=q,opt_source=x.trace,**p))
    pd.DataFrame(scenarios).to_csv(out/'method_sensitivity.csv',index=False)
    # Publication-ready figures; seconds and watts, actual binned measured data distinct from projections.
    plt.rcParams.update({'font.size':10,'axes.labelsize':10,'axes.titlesize':11,'figure.dpi':160,'axes.spines.top':False,'axes.spines.right':False})
    def save(fig,name):
        fig.tight_layout();fig.savefig(out/(name+'.png'),dpi=300,bbox_inches='tight');fig.savefig(out/(name+'.svg'),bbox_inches='tight');plt.close(fig)
    t,p,peaks=bplots['baseline/meritev2.csv'];fig,ax=plt.subplots(figsize=(7,2.75));m=(t>=20)&(t<=170);ax.plot(t[m],p[m],lw=.7,color='#26476e',label='Measured, 20 ms means');
    for j,q in enumerate(peaks[(peaks>=20)&(peaks<=170)]):ax.axvspan(q-3,q+3,color='#e69f00',alpha=.22,label='Camera-like window' if j==0 else None)
    ax.set(xlabel='Time (s)',ylabel='System power (W)',title='Historical BASELINE: periodic image-processing events');ax.legend(loc='upper left',fontsize=8);ax.grid(alpha=.2);save(fig,'fig1_baseline_trace')
    t,p,bl,se=oplots['optimized/meritev2.csv'];fig,ax=plt.subplots(figsize=(7,2.75));m=(t>=15)&(t<=165);ax.plot(t[m],p[m],lw=.7,color='#26476e',label='Measured, 20 ms means');
    for j,x in enumerate([x for x in bl if x['start_s']<165 and x['end_s']>15]):ax.axvspan(x['start_s'],x['end_s'],color='#e69f00',alpha=.22,label='Pi-like activity block' if j==0 else None)
    for j,x in enumerate([x for x in se if 15<x['center_s']<165]):ax.axvline(x['center_s'],color='#00856a',alpha=.5,lw=.8,label='Sensor-like event' if j==0 else None)
    ax.axhline(c['opt_W'],color='black',ls='--',lw=.9,label='Low-activity reference');ax.set(xlabel='Time (s)',ylabel='System power (W)',title='Historical OPTIMIZED: sleep, sensing and Pi activity');ax.legend(loc='upper left',fontsize=7,ncol=2);ax.grid(alpha=.2);save(fig,'fig2_optimized_trace')
    rr=rows[:3]; labels=['Baseline','Optimized\nstable','Optimized\nnormal','Optimized\ndynamic'];vals=[[rr[0]['baseline_bg_Wh'],rr[0]['baseline_sensor_Wh'],rr[0]['baseline_camera_Wh']]]+[[r['opt_bg_Wh'],r['opt_sensor_Wh'],r['opt_block_Wh']] for r in rr];v=np.array(vals);fig,ax=plt.subplots(figsize=(6.8,3.4));bottom=np.zeros(4)
    for j,(label,col) in enumerate([('Background','#7f9ab5'),('Sensing','#009e73'),('Camera/net Pi increment','#e69f00')]):ax.bar(labels,v[:,j],bottom=bottom,label=label,color=col,width=.63);bottom+=v[:,j]
    for i,y in enumerate(bottom):ax.text(i,y+3,f'{y:.2f}',ha='center',fontsize=9)
    ax.set(ylabel='Projected energy (Wh / 144 h)',title='Six-day energy model (not a new measurement)',ylim=(0,max(bottom)*1.14));ax.legend(fontsize=8,loc='lower left');ax.grid(axis='y',alpha=.2);save(fig,'fig3_projected_energy')
    fig,ax=plt.subplots(figsize=(6.8,3));h=np.linspace(0,144,145);ax.plot(h,rr[0]['baseline_Wh']*h/144,label='Baseline',lw=2,color='#26476e');
    for r,style,col in zip(rr,['--',':','-.'],['#00856a','#d55e00','#9467bd']):
        ts=timelines[r['scenario']];k=np.searchsorted(ts,h*3600,side='right')+(h>0);period=r['period_s'];ns=np.ceil(h*3600/period);e=h*c['opt_W']+(ns*c['opt_sensor_J']+k*net_block_j(c))/3600;ax.plot(h,e,ls=style,color=col,label='Optimized '+r['scenario'],lw=1.6)
    ax.set(xlabel='Time (h)',ylabel='Projected cumulative energy (Wh)',title='Modelled cumulative energy over six days');ax.legend(fontsize=8);ax.grid(alpha=.2);save(fig,'fig4_cumulative')
    fig,ax=plt.subplots(figsize=(6.6,3));ax.plot(sd.blocks,sd.savings_pct,lw=1.8,color='#26476e');
    for r,marker in zip(rr,['o','s','^']):ax.scatter(r['opt_activity_blocks'],r['savings_pct'],label=r['scenario'],marker=marker,s=36,zorder=3)
    ax.set(xlabel='Pi-equivalent activity blocks in 144 h',ylabel='Projected saving (%)',title='Sensitivity to Raspberry Pi activity count');ax.legend(fontsize=8);ax.grid(alpha=.2);save(fig,'fig5_sensitivity')
    print(json.dumps({'coefficients':c,'projections':rows,'optimized':ore,'baseline':br},indent=2))

if __name__=='__main__':main()
