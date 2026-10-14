"""Recheck stored evidence without launching Blender. Never executes a report."""
import copy
import hashlib
import math
from fractions import Fraction
from pathlib import Path
from .gate import check_exact
from .io import InputError, load_report, read_input
from .numeric import check
from .reducer import MeshState, collapse, ancestry_check, failure_signature
from .surface import correspondence
from .engine import displaced
from .guard import sub, dot, cross

def require(condition,message):
    if not condition:raise InputError(message)

def geometry(m):
    return {'vertices':m['vertices'],'faces':m['faces']}

def normalize(pair):
    p=copy.deepcopy(pair)
    for m in p:
        for a in m['ancestry']:a['weights']={str(k):v for k,v in a['weights'].items()}
    return p

def validate_mesh(m):
    require(isinstance(m,dict),'invalid mesh record')
    require(len(m.get('vertices',[]))<=2048 and len(m.get('faces',[]))<=2048,'stored geometry exceeds verification bounds')
    q=check_exact(m.get('vertices',[]),m.get('faces',[]))
    require(q['valid'],'stored mesh guard refused: '+','.join(q['reasons']))

def output_integral(m):
    """Recompute the stored triangle-surface integral using exact coordinates.

    Failed outputs may have unused vertices, zero-area faces or intersections;
    their signed integral is not a certified physical solid volume. Do not
    require repaired-surface validity here, and never trust the scalar alone.
    """
    require(isinstance(m,dict),'invalid output mesh record')
    vertices,faces=m.get('vertices'),m.get('faces')
    require(isinstance(vertices,list) and 0<len(vertices)<=2048,'output vertex bounds failed')
    require(isinstance(faces,list) and 0<len(faces)<=2048,'output triangle bounds failed')
    def finite(value):
        try:return type(value) in (int,float) and math.isfinite(value)
        except OverflowError:return False
    require(all(isinstance(p,list) and len(p)==3 and all(finite(x) for x in p) for p in vertices),'output coordinates must be finite triples')
    require(all(isinstance(f,list) and len(f)==3 and all(type(i)==int and 0<=i<len(vertices) for i in f) for f in faces),'output faces must be in-range triangles')
    vv=[tuple(Fraction(x) for x in p) for p in vertices];origin=vv[0]
    value=sum((dot(sub(vv[f[0]],origin),cross(sub(vv[f[1]],origin),sub(vv[f[2]],origin)))/6 for f in faces),Fraction(0))
    try:actual=float(value)
    except OverflowError:raise InputError('output integral exceeds finite numeric range') from None
    declared=m.get('volume')
    require(math.isfinite(actual) and finite(declared),'output volume/integral must be finite')
    # Blender accumulates a floating integral. Permit a narrowly declared
    # relative accumulation difference, with no absolute floor at small scales.
    require(math.isclose(actual,declared,rel_tol=1e-9,abs_tol=0.0),'serialized output volume differs from recomputed surface integral')
    return dict(m,volume=actual)

def bind_signature(stored,inputs,output):
    """Bind mirror fields to replayed inputs and a verified output integral.

    Derived differences retain the native scalar's rounding. Check their
    internal arithmetic exactly, then require the independently recomputed
    integral to reach the same failure verdict.
    """
    actual=failure_signature(inputs,output)
    require(isinstance(stored,dict) and set(actual)<=set(stored),'incomplete stored failure signature')
    declared={k:stored[k] for k in actual}
    volume=declared['output_volume']
    try:finite=type(volume) in (int,float) and math.isfinite(volume)
    except OverflowError:finite=False
    require(finite and type(declared['matches']) is bool,'invalid stored signature volume/verdict')
    require(math.isclose(volume,output['volume'],rel_tol=1e-9,abs_tol=0.0),'stored signature volume differs from verified output integral')
    recorded_inputs=[]
    for field,checked in zip(('input_a_volume','input_b_volume'),inputs):
        recorded=declared[field]
        try:finite=type(recorded) in (int,float) and math.isfinite(recorded)
        except OverflowError:finite=False
        require(finite and math.isclose(recorded,checked['volume'],rel_tol=1e-9,abs_tol=0.0),'stored signature input integral differs from replayed geometry')
        recorded_inputs.append({'volume':recorded})
    # The writer's floating inputs can differ slightly across Python versions.
    # Derived mirror arithmetic must still exactly match those checked values.
    require(declared==failure_signature(recorded_inputs,{'volume':volume}),'stored failure signature fields are inconsistent')
    require(declared['matches']==actual['matches'],'stored failure verdict differs from recomputed geometry')
    return actual

def verify(path):
    path=Path(path);r=load_report(path)
    require(r.get('status') in ('repaired','witness','no_failure'),'report is not a successful completed analysis')
    sources=r.get('sources',[])
    require(len(sources)==2,'expected exactly two preserved sources')
    originals=[]
    for i,source in enumerate(sources):
        name=('A.obj','B.obj')[i];allowed='originals/'+name
        require(source.get('stored_path')==allowed,'source path is not an allowed preserved operand')
        target=path.parent/allowed
        directory=path.parent/'originals'
        require(not directory.is_symlink() and not target.is_symlink(),'preserved source symlinks refused')
        require(directory.resolve().parent==path.parent.resolve() and target.resolve().parent==directory.resolve(),'source escaped output directory')
        data,mesh,metadata=read_input(target)
        require(len(data)==source['bytes'] and hashlib.sha256(data).hexdigest()==source['sha256'],'original source bytes/hash mismatch')
        require(metadata['conversion']==source['conversion'],'source conversion metadata mismatch')
        mesh['name']=name;originals.append(mesh);validate_mesh(mesh)
    b=r['baseline']
    require(list(b['inputs'])==['A.obj','B.obj'],'baseline operand identity/order mismatch')
    require(all(geometry(x)==geometry(y) for x,y in zip(originals,b['inputs'].values())),'baseline does not match preserved sources')
    validate_mesh(b['outputs']['MANIFOLD']);output_integral(b['outputs']['MANIFOLD'])
    original_metrics=[check(m['vertices'],m['faces']) for m in originals]
    baseline_output=output_integral(b['outputs']['FLOAT'])
    initial=bind_signature(b['failure_signature'],original_metrics,baseline_output)
    if r['status']=='no_failure':
        require(not initial['matches'],'no_failure report contains scoped failure')
        return {'valid':True,'status':r['status'],'scope':'Stored source and comparator guards; no fresh native execution.'}
    require(initial['matches'],'witness lost original failure family')
    d=r.get('reduction')
    require(isinstance(d,dict),'witness report has no completed reduction')
    bind_signature(d['initial_failure_signature'],original_metrics,baseline_output)
    states=[MeshState.original(m['name'],m) for m in originals]
    require(normalize([s.geometry() for s in states])==normalize(d['original_operands']),'reduction predecessor does not match sources')
    require(len(d['accepted_steps'])<=512,'too many stored reduction steps')
    for step in d['accepted_steps']:
        side=step['operand'];require(type(side)==int and side in (0,1),'invalid reduction side')
        old=states[side];edge=step['edge']
        require(step['source_edge']==[old.ancestry[i]['cluster'] for i in edge],'reduction source edge mismatch')
        new,_=collapse(old,edge,step['choice'])
        validate_mesh(new.geometry());ancestry_check(new,len(originals[side]['vertices']))
        require(step['vertex_after']==new.vertices[min(edge)],'reduction vertex replay mismatch')
        states[side]=new
        actual_metrics=[check(x.vertices,x.faces) for x in states]
        require(len(step['input_metrics'])==2,'stored per-step input metrics missing')
        recorded_metrics=[x['volume'] for x in step['input_metrics']]
        require(recorded_metrics==[step['failure_signature']['input_a_volume'],step['failure_signature']['input_b_volume']],'per-step metric/signature volumes disagree')
        sig=bind_signature(step['failure_signature'],actual_metrics,{'volume':step['failure_signature']['output_volume']})
        require(sig['matches'],'stored per-step failure family inconsistent')
    # JSON keys of affine weight dictionaries are strings. Normalize on both
    # sides rather than pretending JSON preserves integer map keys.
    require(normalize([s.geometry() for s in states])==normalize(d['operands']),'final reduced geometry/ancestry replay mismatch')
    reduced=d['operands']
    validate_mesh(d['final_outputs']['MANIFOLD']);output_integral(d['final_outputs']['MANIFOLD'])
    final=bind_signature(d['final_failure_signature'],[check(m['vertices'],m['faces']) for m in reduced],output_integral(d['final_outputs']['FLOAT']))
    require(final['matches'],'stored final witness lost failure family')
    if r['status']=='repaired':
        a=r['repair']['accepted'];trial=a['intervention'];side=trial['side'];ids=trial['vertices'];delta=trial['delta']
        # Schema1 predecessor mirrors do not retain their own output geometry.
        # Bind them to the checked exports for the same original/witness pairs.
        for key,pair,export in [('original_signature',d['original_operands'],b['outputs']['FLOAT']),('witness_signature',reduced,d['final_outputs']['FLOAT'])]:
            mirrored=bind_signature(a[key],[check(m['vertices'],m['faces']) for m in pair],output_integral(export))
            require(mirrored['matches'],'repair predecessor lost recorded failure family')
        require(side in (0,1),'invalid repair side')
        cluster=sorted({x for vi in ids for x in reduced[side]['ancestry'][vi]['cluster']})
        require(cluster==a['cluster']==[x['vertex'] for x in a['patch']],'repair ancestry lift mismatch')
        expected=copy.deepcopy(d['original_operands']);witness=copy.deepcopy(reduced)
        expected[side]=displaced(expected[side],cluster,delta);witness[side]=displaced(witness[side],ids,delta)
        require(expected==a['full_repaired'] and witness==a['witness_repaired'],'repair coordinates do not match stored intervention')
        restored=copy.deepcopy(expected)
        for patch in a['patch']:
            i=patch['vertex'];require(restored[side]['vertices'][i]==patch['after'],'undo after precondition mismatch')
            require(patch['before']==d['original_operands'][side]['vertices'][i],'undo before differs from original')
            restored[side]['vertices'][i]=list(patch['before'])
        require(restored==a['undo_inputs']==d['original_operands'],'stored undo fails exact geometry identity')
        for key,pair in [('witness_check',witness),('full_check',expected)]:
            for m in pair:validate_mesh(m)
            q=a[key];f=q['output_geometry'];reference=q['reference_geometry']
            validate_mesh(f);validate_mesh(reference)
            output_integral(f);output_integral(reference)
            span=max(max(v[k] for m in pair for v in m['vertices'])-min(v[k] for m in pair for v in m['vertices']) for k in range(3))
            # Acceptance tolerance derives from original/reduced coordinates,
            # before intervention; recompute that same scale below.
            base=reduced if key=='witness_check' else d['original_operands']
            span=max(max(v[k] for m in base for v in m['vertices'])-min(v[k] for m in base for v in m['vertices']) for k in range(3))
            c=correspondence(f,reference,span*1e-6)
            require(c['bijection'] and c['within_tolerance'],'repair surface correspondence failed')
            require(c==q['surface_correspondence'],'stored correspondence/bound differs from recomputation')
            fm,rm=check(f['vertices'],f['faces']),check(reference['vertices'],reference['faces'])
            require(abs(fm['volume']-rm['volume'])<=max(abs(rm['volume']),1)*1e-5,'repair volumes disagree')
        undo=bind_signature(a['undo_signature'],[check(m['vertices'],m['faces']) for m in restored],output_integral(a['undo_signature']['geometry']))
        require(undo['matches'],'stored undo output lost failure family')
    return {'valid':True,'status':r['status'],'replayed_steps':len(d['accepted_steps']),
            'scope':'Stored bytes, valid operands, replayed reductions, lifted patch, undo and paired-surface bounds. Does not rerun Blender, authenticate provenance, or prove true union correctness.'}
