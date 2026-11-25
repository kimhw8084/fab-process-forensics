"""Frozen P1-P4 shared evidence contract; no remote dependencies."""
from __future__ import annotations
import hashlib, json
from typing import Any

CONTRACT_VERSION='1.0.0'
PRODUCT_IDS=frozenset({'p1','p2','p3','p4'})
MODES=frozenset({'SYNTHETIC_DEMO','INTERNAL_AUTHORIZED'})
STATUSES=frozenset({'VALID','PARTIAL','INCONCLUSIVE','REFUSED','ERROR'})
CATEGORIES=frozenset({'DESCRIPTIVE','ASSOCIATION','PREDICTION','CAUSAL_ESTIMATE','INTERVENTION_VALIDATED'})

class ContractError(ValueError): pass

def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def envelope(product_id, raw_input, status, claims, limitations=(), *, mode='SYNTHETIC_DEMO', assumptions=(), sources=None):
    if product_id not in PRODUCT_IDS: raise ContractError('unknown product')
    if mode not in MODES: raise ContractError('invalid mode')
    if status not in STATUSES: raise ContractError('invalid status')
    if mode=='INTERNAL_AUTHORIZED': raise ContractError('bootstrap is never an authorized internal connector')
    input_hash=digest(raw_input)
    ev={'schema_version':CONTRACT_VERSION,'investigation_id':f'SYN-{product_id}-{input_hash[:12]}',
        'product_id':product_id,'mode':mode,'status':status,'claims':list(claims),'sources':sources or [],
        'assumptions':list(assumptions),'limitations':list(limitations),
        'provenance':{'engine_version':'0.1.0-bootstrap','input_sha256':input_hash,'semantic_catalog_version':'SYNTHETIC-1'}}
    validate_envelope(ev)
    return ev

def validate_envelope(ev):
    required=('schema_version','investigation_id','product_id','mode','status','claims','sources','assumptions','limitations','provenance')
    allowed=set(required)|{'claim_category','populations','transformations','units','counterevidence','uncertainty','artifacts'}
    if not isinstance(ev,dict): raise ContractError('evidence envelope must be an object')
    for key in required:
        if key not in ev: raise ContractError('missing '+key)
    if set(ev)-allowed: raise ContractError('unknown evidence envelope field: '+sorted(set(ev)-allowed)[0])
    if ev['schema_version'] != CONTRACT_VERSION or ev['product_id'] not in PRODUCT_IDS or ev['mode'] not in MODES or ev['status'] not in STATUSES:
        raise ContractError('bad enumerated field')
    if not isinstance(ev['investigation_id'],str) or not isinstance(ev['claims'],list) or not isinstance(ev['sources'],list):
        raise ContractError('bad evidence envelope type')
    if ev['mode']=='SYNTHETIC_DEMO' and ev['investigation_id'][:4]!='SYN-': raise ContractError('synthetic case not labeled')
    if not isinstance(ev['assumptions'],list) or not isinstance(ev['limitations'],list) or not isinstance(ev['provenance'],dict):
        raise ContractError('bad assumptions, limitations, or provenance type')
    if any(not isinstance(item,str) for item in ev['assumptions']+ev['limitations']):
        raise ContractError('assumptions and limitations must be strings')
    if 'claim_category' in ev and ev['claim_category'] not in CATEGORIES|{'NONE'}:
        raise ContractError('invalid top-level claim_category')
    if 'engine_version' not in ev['provenance'] or 'input_sha256' not in ev['provenance']:
        raise ContractError('provenance missing engine_version or input_sha256')
    if not isinstance(ev['provenance']['engine_version'],str) or not isinstance(ev['provenance']['input_sha256'],str):
        raise ContractError('invalid provenance type')
    for claim in ev['claims']:
        if not isinstance(claim,dict): raise ContractError('claim must be an object')
        if set(claim)-{'statement','category','source_ids','method','certainty'}:
            raise ContractError('unknown claim field')
        for field in ('statement','category','source_ids','method','certainty'):
            if field not in claim: raise ContractError('incomplete claim')
        if not isinstance(claim['statement'],str) or not isinstance(claim['method'],str) or not isinstance(claim['source_ids'],list):
            raise ContractError('bad claim type')
        if any(not isinstance(source_id,str) for source_id in claim['source_ids']):
            raise ContractError('claim source IDs must be strings')
        if not isinstance(claim['category'],str) or claim['category'] not in CATEGORIES: raise ContractError('invalid claim category')
        if not isinstance(claim['certainty'],str) or claim['certainty'] not in ('SUPPORTED','CONDITIONAL','INCONCLUSIVE'): raise ContractError('invalid certainty')
    for source in ev['sources']:
        if not isinstance(source,dict) or any(not isinstance(source.get(field),str) for field in ('id','approved_semantic_version','grain','source_hash')):
            raise ContractError('invalid evidence source')
        if set(source)-{'id','approved_semantic_version','grain','source_hash','permissions_ref','observed_at'}:
            raise ContractError('unknown evidence source field')
        if any(key in source and not isinstance(source[key],str) for key in ('permissions_ref','observed_at')):
            raise ContractError('invalid optional evidence source field')
    for field in ('populations','transformations','counterevidence','artifacts'):
        if field in ev and not isinstance(ev[field],list): raise ContractError(field+' must be a list')
    if 'units' in ev and not isinstance(ev['units'],dict): raise ContractError('units must be an object')
    if 'uncertainty' in ev and not isinstance(ev['uncertainty'],dict): raise ContractError('uncertainty must be an object')
    if ev['status'] in ('INCONCLUSIVE','REFUSED') and not ev['limitations']:
        raise ContractError('an inconclusive/refused result requires a reason')
    return True

def claim(statement,category='DESCRIPTIVE',method='deterministic_baseline',source_ids=None,certainty='SUPPORTED'):
    return {'statement':statement,'category':category,'source_ids':source_ids or [],'method':method,'certainty':certainty}
