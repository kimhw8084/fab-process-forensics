"""Deterministic synthetic catalog. This is NEVER a real Fab Insight MCP."""
import random

def synthetic_catalog(n=13000, seed=20261122):
    if not 1 <= n <= 100000:
        raise ValueError('n must be 1..100000')
    rng=random.Random(seed)
    areas=('MET','PHOTO','ETCH','DEP','DIFF','IMPL','CMP','WAT','SORT')
    out=[]
    for i in range(n):
        area=areas[i % len(areas)]
        columns=['wafer_id','lot_id','step_instance_id','event_ts','measure_value']
        if i % 13 == 0: columns.append('equipment_id')
        if i % 17 == 0: columns.append('chamber_id')
        out.append({'id':f'SYN_{area}_{i:05d}','area':area,'columns':columns,
             'approved':i % 11 != 0,'relationships':[],
             'timestamp_timezone':rng.choice(['UTC','local_unknown']),
             'source':'SYNTHETIC_ONLY'})
    return out

def approved_join(table_a, table_b, key, catalog, *, time_window=None):
    index={t['id']:t for t in catalog}
    a=index.get(table_a); b=index.get(table_b)
    if not (a and b and a.get('approved') is True and b.get('approved') is True
            and key in a.get('columns',[]) and key in b.get('columns',[])
            and isinstance(time_window,tuple) and len(time_window)==2):
        return False
    from datetime import datetime
    try:
        start=datetime.fromisoformat(time_window[0].replace('Z','+00:00'))
        end=datetime.fromisoformat(time_window[1].replace('Z','+00:00'))
    except (AttributeError,TypeError,ValueError):
        return False
    if start.tzinfo is None or end.tzinfo is None or end<=start:
        return False
    for relation in a.get('relationships',[]):
        if not isinstance(relation,dict) or relation.get('target_id')!=table_b or relation.get('approved') is not True:
            continue
        if key not in relation.get('keys',[]) or not relation.get('cardinality'):
            continue
        try:
            effective_start=datetime.fromisoformat(relation['effective_start'].replace('Z','+00:00'))
            effective_end=datetime.fromisoformat(relation['effective_end'].replace('Z','+00:00'))
        except (KeyError,AttributeError,TypeError,ValueError):
            continue
        if (effective_start.tzinfo is not None and effective_end.tzinfo is not None
                and effective_start<=start and end<=effective_end):
            return True
    return False
