import { renderP2Contribution } from './p2-panels.js';
const input = document.getElementById('input-json');
    const snapshotDetails = document.getElementById('snapshot-editor');
    const snapshotSummary = document.getElementById('snapshot-summary');
    const statusBox = document.getElementById('request-status');
    const downloadButton = document.getElementById('download');
    const preflightButton = document.getElementById('preflight');
    const runButton = document.getElementById('run');
    const reviewBox = document.getElementById('snapshot-review');
    const reviewAnnouncement = document.getElementById('snapshot-review-announcement');
    const startMode = document.getElementById('starting-point');
    const affectedWafer = document.getElementById('affected-wafer');
    const affectedWaferDetails = document.getElementById('affected-wafer-details');
    const affectedWaferSummary = document.getElementById('affected-wafer-summary');
    const affectedLot = document.getElementById('affected-lot');
    const exposureConditionType = document.getElementById('exposure-condition-type');
    const exposureScopeType = document.getElementById('exposure-scope-type');
    const exposureChamber = document.getElementById('exposure-chamber');
    const exposureTool = document.getElementById('exposure-tool');
    const exposureStart = document.getElementById('exposure-start');
    const exposureEnd = document.getElementById('exposure-end');
    const localToken = document.querySelector('meta[name="fabintel-local-token"]').content;
    let lastResult = null;
    let reviewedInput = null;
    let activeAnalysisId = null;
    const el = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
    function setStatus(message, kind='') { statusBox.textContent = message; statusBox.dataset.kind = kind; }
    function setSnapshotSummary(byteCount, eventCount, outcomeCount) {
      snapshotSummary.textContent = `Inspect or edit snapshot JSON · ${(byteCount / (1024 * 1024)).toFixed(2)} MiB · ${eventCount} events · ${outcomeCount} outcomes`;
    }
    function updateSnapshotSummary() {
      try {
        const payload = JSON.parse(input.value);
        const compactBytes = new TextEncoder().encode(JSON.stringify(payload)).length;
        setSnapshotSummary(compactBytes, Array.isArray(payload.events) ? payload.events.length : 0,
          Array.isArray(payload.outcomes) ? payload.outcomes.length : 0);
      } catch {
        snapshotSummary.textContent = 'Snapshot JSON is being edited · review to refresh its size and row counts';
      }
    }
    function appendJson(target, value) { target.append(el('pre', JSON.stringify(value, null, 2))); }
    function appendTable(parent, captionText, headings, rows) {
      const view=el('table');
      view.append(el('caption',captionText));
      const head=el('thead'); const header=el('tr');
      for (const label of headings) { const cell=el('th',label); cell.setAttribute('scope','col'); header.append(cell); }
      head.append(header); view.append(head);
      const body=el('tbody');
      for (const values of rows) { const row=el('tr'); for (const value of values) row.append(el('td',value)); body.append(row); }
      view.append(body);
      const wrapper=el('div',undefined,'scroll'); wrapper.append(view); parent.append(wrapper);
    }
    function requestCancellationQuietly(requestId) {
      fetch('/api/cancel',{method:'POST',headers:{'Content-Type':'application/json','X-Fabintel-Token':localToken},body:JSON.stringify({request_id:requestId})}).catch(()=>{});
    }
    async function cancelRunningAnalysis() {
      const requestId=activeAnalysisId;
      if (!requestId) return;
      runButton.disabled=true; runButton.textContent='Stopping analysis…';
      setStatus('Cancellation requested. Waiting for the local analysis to stop…');
      try {
        const response=await fetch('/api/cancel',{method:'POST',headers:{'Content-Type':'application/json','X-Fabintel-Token':localToken},body:JSON.stringify({request_id:requestId})});
        const result=await response.json();
        if (!response.ok && result.status!=='NOT_ACTIVE') throw new Error(result.error||'Cancellation request failed.');
        if (result.status==='NOT_ACTIVE') setStatus('Analysis is finishing. Waiting for its final status…');
      } catch (error) {
        if (activeAnalysisId===requestId) {
          runButton.disabled=false; runButton.textContent='Cancel analysis';
          setStatus('Could not request cancellation: '+error.message,'error');
        }
      }
    }
    function clearResults() {
      const defaults = {
        summary: 'No analysis has been run.',
        journeys: 'Journey details appear here.',
        populations: 'Exposure details appear here when an equipment window is supplied.',
        counterevidence: 'Outcome comparisons appear here when outcomes are supplied.',
        evidence: 'Source links and limitations appear here.',
      };
      for (const [id, message] of Object.entries(defaults)) {
        const panel = document.getElementById(id);
        panel.replaceChildren(el('p', message));
        panel.classList.add('empty');
      }
    }
    function clearReview(message='Input changed. Review source relationships and limits again before analysis.') {
      if (activeAnalysisId) requestCancellationQuietly(activeAnalysisId);
      reviewedInput=null; runButton.disabled=true; downloadButton.disabled=true; lastResult=null;
      clearResults();
      reviewBox.replaceChildren(el('p',message));
      reviewAnnouncement.textContent=message;
    }
    function toggleScopeFields() {
      const exposureMode = startMode.value === 'suspected-exposure';
      const lotMode = startMode.value === 'affected-lot';
      document.getElementById('affected-wafer-fields').hidden = exposureMode || lotMode;
      document.getElementById('affected-lot-fields').hidden = !lotMode;
      document.getElementById('suspected-exposure-fields').hidden = !exposureMode;
      document.getElementById('exposure-chamber-fields').hidden = exposureScopeType.value === 'tool';
      document.getElementById('exposure-tool-fields').hidden = exposureScopeType.value !== 'tool';
    }
    function updateAffectedWaferSummary() {
      const ids = [...new Set(affectedWafer.value.split(/[\n,]+/).map(value => value.trim()).filter(Boolean))];
      const label = ids.length === 1 ? 'wafer ID' : 'wafer IDs';
      affectedWaferSummary.textContent = `${ids.length} selected abnormal ${label} · review or edit`;
    }
    function populateScopeInputs() {
      let payload;
      try { payload = JSON.parse(input.value); } catch (error) { return; }
      const abnormalIds = Array.isArray(payload.outcomes) ? [...new Set(payload.outcomes.filter(item => item && item.label === 'ABNORMAL' && typeof item.wafer_id === 'string').map(item => item.wafer_id))] : [];
      affectedWafer.value = abnormalIds.join(', ');
      updateAffectedWaferSummary();
      affectedWaferDetails.open = false;
      affectedLot.value = typeof payload.target_lot_id === 'string' ? payload.target_lot_id : '';
      const spec = payload.suspected_exposure && typeof payload.suspected_exposure === 'object' ? payload.suspected_exposure : {};
      startMode.value = typeof payload.target_lot_id === 'string' ? 'affected-lot' : (Object.keys(spec).length ? 'suspected-exposure' : 'affected-wafer');
      exposureConditionType.value = ['PROCESS', 'MAINTENANCE', 'CHANGE'].includes(spec.condition_type) ? spec.condition_type : 'PROCESS';
      exposureScopeType.value = typeof spec.chamber_id === 'string' ? 'chamber' : (typeof spec.tool_id === 'string' ? 'tool' : 'chamber');
      exposureChamber.value = typeof spec.chamber_id === 'string' ? spec.chamber_id : '';
      exposureTool.value = typeof spec.tool_id === 'string' ? spec.tool_id : '';
      exposureStart.value = typeof spec.start === 'string' ? spec.start : '';
      exposureEnd.value = typeof spec.end === 'string' ? spec.end : '';
      toggleScopeFields();
    }
    function applyStartScope() {
      let payload;
      try {
        payload = JSON.parse(input.value);
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('Snapshot JSON must be an object.');
        if (startMode.value === 'affected-wafer') {
          const waferIds = [...new Set(affectedWafer.value.split(/[\n,]+/).map(value => value.trim()).filter(Boolean))];
          const abnormalIds = new Set(Array.isArray(payload.outcomes) ? payload.outcomes.filter(item => item && item.label === 'ABNORMAL').map(item => item.wafer_id) : []);
          if (!waferIds.length || waferIds.some(waferId => !abnormalIds.has(waferId))) throw new Error('Choose only wafer IDs with caller-supplied ABNORMAL outcomes.');
          delete payload.target_lot_id;
          payload.target_wafer_ids = waferIds;
          payload.wafer_id = waferIds[0];
          const cohort = Array.isArray(payload.cohort) ? payload.cohort : [];
          payload.cohort = [...new Set([...cohort, ...waferIds])];
        } else if (startMode.value === 'affected-lot') {
          const lotId = affectedLot.value.trim();
          if (!lotId) throw new Error('Enter a lot ID from caller-supplied outcome rows.');
          const lotOutcomes = Array.isArray(payload.outcomes) ? payload.outcomes.filter(item => item && item.lot_id === lotId) : [];
          if (!lotOutcomes.length) throw new Error('No caller-supplied outcome rows declare that lot ID.');
          const relationships = Array.isArray(payload.relationships) ? payload.relationships : [];
          const waferIds = [];
          let abnormalPresent = false;
          for (const outcome of lotOutcomes) {
            if (outcome.label !== 'ABNORMAL' && outcome.label !== 'NORMAL') throw new Error('Every selected lot outcome must be labeled ABNORMAL or NORMAL.');
            abnormalPresent ||= outcome.label === 'ABNORMAL';
            const relationship = relationships.find(item => item && item.id === outcome.relationship_id);
            const keys = relationship?.keys;
            if (relationship?.approved !== true || !Array.isArray(keys) || !keys.includes('wafer_id') || !keys.includes('lot_id') || !Array.isArray(relationship.source_ids) || !relationship.source_ids.includes(outcome.source_id)) {
              throw new Error('Each lot outcome needs a caller-declared approved relationship to its source, lot_id, and wafer_id.');
            }
            if (typeof outcome.wafer_id !== 'string' || !outcome.wafer_id.trim()) throw new Error('Each selected lot outcome needs a wafer_id.');
            waferIds.push(outcome.wafer_id);
          }
          if (!abnormalPresent) throw new Error('The selected lot has no caller-supplied ABNORMAL outcome.');
          if (new Set(waferIds).size !== waferIds.length) throw new Error('The selected lot has repeated outcome rows for a wafer.');
          waferIds.sort();
          payload.target_lot_id = lotId;
          payload.target_wafer_ids = waferIds;
          payload.wafer_id = waferIds[0];
          const cohort = Array.isArray(payload.cohort) ? payload.cohort : [];
          payload.cohort = [...new Set([...cohort, ...waferIds])];
        } else {
          const scopeType = exposureScopeType.value === 'tool' ? 'tool' : 'chamber';
          const scopeId = scopeType === 'tool' ? exposureTool.value.trim() : exposureChamber.value.trim();
          const start = exposureStart.value.trim();
          const end = exposureEnd.value.trim();
          if (!scopeId || !start || !end) throw new Error('Enter the exact equipment ID and timezone-aware start and end timestamps.');
          const prior = payload.suspected_exposure;
          if (prior != null && (typeof prior !== 'object' || Array.isArray(prior))) throw new Error('Existing suspected_exposure must be a JSON object.');
          payload.suspected_exposure = { ...(prior || {}), condition_type: exposureConditionType.value, start, end };
          if (scopeType === 'tool') {
            delete payload.suspected_exposure.chamber_id;
            payload.suspected_exposure.tool_id = scopeId;
          } else {
            payload.suspected_exposure.chamber_id = scopeId;
          }
        }
        input.value = JSON.stringify(payload, null, 2);
        updateSnapshotSummary();
        updateAffectedWaferSummary();
        affectedWaferDetails.open = false;
        clearReview('Start scope applied. Review source relationships and limits before analysis.');
        setStatus('Start scope applied to the local snapshot. No source query was issued.', 'ok');
      } catch (error) {
        setStatus(error.message, 'error');
      }
    }
    function renderPreflight(result) {
      reviewBox.replaceChildren();
      reviewBox.append(el('p',result.status==='READY_FOR_LOCAL_ANALYSIS'?'Snapshot structure is ready for local analysis.':'Snapshot was refused: '+result.reason));
      if (result.status!=='READY_FOR_LOCAL_ANALYSIS') { reviewAnnouncement.textContent='Snapshot review refused: '+result.reason; return; }
      reviewAnnouncement.textContent='Snapshot structure is ready for local analysis. Caller-declared source and relationship details are displayed below; no source query was issued.';
      const limits=result.limits;
      reviewBox.append(el('p','Limits · '+limits.payload_bytes+' of '+limits.max_payload_bytes+' bytes · '+limits.event_rows+' of '+limits.max_event_rows+' event rows · '+limits.outcome_rows+' of '+limits.max_outcome_rows+' outcome rows'));
      reviewBox.append(el('h3','Caller-declared sources (synthetic)'));
      appendTable(reviewBox,'Caller-declared source records and permission references', ['Source ID','Semantic version','Grain','Permission reference'],
        result.source_records.map(source=>[source.id,source.approved_semantic_version,source.grain,source.permissions_ref||'Not supplied']));
      reviewBox.append(el('h3','Caller-declared relationships and row use'));
      appendTable(reviewBox,'Caller-declared relationships, effective dates, and event/outcome row use', ['Relationship ID','Sources','Keys','Cardinality / grain','Effective UTC','Rows'],
        result.relationships.map(relation=>[relation.id,relation.source_ids.join(', '),relation.keys.join(', '),relation.cardinality+' / '+relation.grain,relation.effective_start_utc+' → '+relation.effective_end_utc,'events '+relation.event_rows+' · outcomes '+relation.outcome_rows]));
      reviewBox.append(el('h3','Declared analysis scope'));
      const scope = result.scope || {};
      const scopeSummary = [];
      if (Array.isArray(scope.target_wafer_ids)) scopeSummary.push(`${scope.target_wafer_ids.length} target wafer(s)`);
      if (Array.isArray(scope.population)) scopeSummary.push(`${scope.population.length} population member(s)`);
      if (typeof scope.target_lot_id === 'string' && scope.target_lot_id) scopeSummary.push(`lot ${scope.target_lot_id}`);
      const scopeDetails=el('details');
      scopeDetails.append(el('summary',`Inspect full declared analysis scope${scopeSummary.length?' · '+scopeSummary.join(' · '):''}`));
      appendJson(scopeDetails,scope);
      reviewBox.append(scopeDetails);
      const list=el('ul'); for (const limitation of result.limitations) list.append(el('li',limitation)); reviewBox.append(list);
    }
    async function loadDemo() {
      clearReview('Loading the bundled synthetic example…'); setStatus('Loading the bundled synthetic example…');
      try { const response = await fetch('/api/demo'); if (!response.ok) throw new Error('Could not load the local example.'); input.value = JSON.stringify(await response.json(), null, 2); updateSnapshotSummary(); populateScopeInputs(); clearReview('Synthetic example loaded. Review source relationships and limits before analysis.'); setStatus('Synthetic example loaded. Review it, then check its source relationships and limits.', 'ok'); }
      catch (error) { setStatus(error.message, 'error'); }
    }
    async function reviewSnapshot() {
      const snapshotText=input.value;
      let payload; try { payload=JSON.parse(snapshotText); } catch (error) { clearReview(''); setStatus('Invalid JSON: '+error.message,'error'); return; }
      const body=JSON.stringify(payload); const byteLength=new TextEncoder().encode(body).length;
      if (byteLength > 25*1024*1024) { clearReview(''); setStatus('Request exceeds the 25 MB limit.','error'); return; }
      preflightButton.disabled=true; runButton.disabled=true; reviewedInput=null; reviewBox.replaceChildren(el('p','Checking declared source relationships, time ranges, population, and local limits…'));
      reviewAnnouncement.textContent='Checking declared source relationships, time ranges, population, and local limits.';
      try {
        const response=await fetch('/api/preflight',{method:'POST',headers:{'Content-Type':'application/json','X-Fabintel-Token':localToken},body});
        const result=await response.json(); if (!response.ok) throw new Error(result.error||'Snapshot preflight failed.');
        renderPreflight(result);
        if (input.value!==snapshotText) { clearReview(); setStatus('Input changed during review. Run the review again.','error'); }
        else if (result.status==='READY_FOR_LOCAL_ANALYSIS') { reviewedInput=snapshotText; runButton.disabled=false; setStatus('Snapshot review complete · caller-declared metadata only · no query was issued.','ok'); }
        else { setStatus('Snapshot review refused · correct the provenance fields before analysis.','error'); }
      } catch (error) { clearReview(error.message); setStatus(error.message,'error'); }
      finally {
        preflightButton.disabled=false;
        if (reviewedInput===snapshotText && !runButton.disabled) runButton.focus();
        else preflightButton.focus();
      }
    }
    function render(result) {
      renderP2Contribution({
        summary: document.getElementById('summary'),
        journey: document.getElementById('journeys'),
        exposure: document.getElementById('populations'),
        counterevidence: document.getElementById('counterevidence'),
        evidence: document.getElementById('evidence'),
      }, result);
    }
    const fileInput=document.getElementById('file-input');
    document.getElementById('open-file').addEventListener('click',()=>fileInput.click());
    fileInput.addEventListener('change', async event => {
      const file=event.target.files[0]; if (!file) return;
      try {
        if (file.size > 25*1024*1024) { clearReview(''); setStatus('Selected file exceeds 25 MB.','error'); return; }
        input.value=await file.text(); JSON.parse(input.value); updateSnapshotSummary(); populateScopeInputs(); clearReview(); setStatus('Local file loaded. Review its sources and limits before analysis.','ok');
      } catch (error) { clearReview(''); setStatus('File is not valid JSON: '+error.message,'error'); }
      finally { event.target.value=''; }
    });
    input.addEventListener('input',()=>{snapshotSummary.textContent='Snapshot JSON is being edited · review to refresh its size and row counts';clearReview();setStatus('Snapshot changed. Review its source relationships and limits before analysis.');});
    input.addEventListener('change',updateSnapshotSummary);
    document.getElementById('load-demo').addEventListener('click',loadDemo);
    startMode.addEventListener('change',toggleScopeFields);
    affectedWafer.addEventListener('input',updateAffectedWaferSummary);
    exposureScopeType.addEventListener('change',toggleScopeFields);
    document.getElementById('apply-scope').addEventListener('click',applyStartScope);
    preflightButton.addEventListener('click',reviewSnapshot);
    runButton.addEventListener('click',async () => {
      if (activeAnalysisId) { await cancelRunningAnalysis(); return; }
      let payload; try { payload=JSON.parse(input.value); } catch (error) { setStatus('Invalid JSON: '+error.message,'error'); return; }
      if (reviewedInput!==input.value) { clearReview(); setStatus('Review the current snapshot before analysis.','error'); return; }
      if (new TextEncoder().encode(input.value).length > 25*1024*1024) { setStatus('Request exceeds the 25 MB limit.','error'); return; }
      const analyzedText=input.value;
      const requestId=crypto.randomUUID();
      activeAnalysisId=requestId; preflightButton.disabled=true; downloadButton.disabled=true; lastResult=null; clearResults();
      runButton.disabled=false; runButton.textContent='Cancel analysis'; setStatus('Running deterministic analysis on this computer. Activate Cancel analysis to stop without returning partial findings…');
      try {
        const response=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json','X-Fabintel-Token':localToken,'X-Fabintel-Request-ID':requestId},body:JSON.stringify(payload)});
        const result=await response.json();
        if (result.status==='CANCELLED') { setStatus(input.value===analyzedText?'Analysis cancelled. No partial findings or export were returned; review and run again to retry.':'Snapshot changed; analysis cancelled and prior findings were cleared. Review the current input before retrying.'); return; }
        if (!response.ok) throw new Error(result.error || 'Analysis request failed.');
        if (input.value!==analyzedText || reviewedInput!==analyzedText) { clearReview(); setStatus('Input changed during analysis. Review it again before displaying a result.','error'); return; }
        lastResult=result; render(result); snapshotDetails.open=false; downloadButton.disabled=false; setStatus('Analysis finished · '+result.status+' · no external service was contacted.','ok'); document.getElementById('summary').focus();
      } catch (error) {
        if (input.value!==analyzedText || reviewedInput!==analyzedText) setStatus('Input changed during analysis. Review the current snapshot before retrying.','error');
        else setStatus(error.message,'error');
      } finally {
        activeAnalysisId=null; preflightButton.disabled=false; runButton.textContent='Run deterministic analysis'; runButton.disabled=reviewedInput!==input.value;
      }
    });
    downloadButton.addEventListener('click',() => { if (!lastResult) return; const fileName=lastResult.investigation_id+'.json'; const blob=new Blob([JSON.stringify(lastResult,null,2)+'\n'],{type:'application/json'}); const objectUrl=URL.createObjectURL(blob); const link=document.createElement('a'); link.href=objectUrl; link.download=fileName; link.style.position='fixed'; link.style.left='-10000px'; document.body.append(link); link.click(); window.setTimeout(()=>{ link.remove(); URL.revokeObjectURL(objectUrl); },1000); setStatus('Evidence JSON download started · '+fileName,'ok'); });
    toggleScopeFields();
    loadDemo();
