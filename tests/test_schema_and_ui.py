import unittest,json
from pathlib import Path
class SourceContractTests(unittest.TestCase):
 def test_schema_files_identify_version(self):
  root=Path(__file__).resolve().parent.parent
  for name in ('evidence.v1.schema.json','product-manifest.v1.schema.json'):
   doc=json.loads((root/'contracts'/name).read_text())
   self.assertIn('1.0.0',doc['$id'])
 def test_manifest_declares_candidate_not_external_release(self):
  root=Path(__file__).resolve().parent.parent
  manifest=json.loads((root/'product.json').read_text())
  self.assertEqual(manifest['release_state'],'CANDIDATE')
  self.assertEqual(manifest['contract_version'],'1.0.0')
  self.assertIn('headless_panels',manifest['entrypoints'])
  self.assertEqual(manifest['entrypoints']['panel_models'],'ui/p2-panels.js:buildP2PanelModels')
  self.assertIn('mcp_adapter',manifest['entrypoints'])
  self.assertIn('B01',manifest['capabilities'])
  contribution=json.loads((root/'ui'/'contribution.manifest.json').read_text())
  self.assertEqual(contribution['product_id'],manifest['product_id'])
  self.assertEqual(contribution['analysis_entrypoint'],manifest['entrypoints']['analysis'])
 def test_p1_host_proposal_tracks_the_versioned_react_contribution(self):
  root=Path(__file__).resolve().parent.parent
  manifest=json.loads((root/'ui'/'contribution.manifest.json').read_text())
  proposal=(root/'ui'/'P1_HOST_INTEGRATION_PROPOSAL.md').read_text()
  module=json.loads((root/'ui'/'p2-react'/'package.json').read_text())
  for value in (manifest['product_id'],manifest['route'],manifest['panel_entrypoint'],manifest['integration_mode']):
   self.assertIn(value,proposal)
  self.assertEqual(manifest['panel_module_version'],module['version'])
  self.assertEqual(module['version'],'1.0.0')
  self.assertIn('react',module['peerDependencies'])
  self.assertEqual(manifest['legacy_dom_panel_entrypoint'],'ui/p2-panels.js:renderP2Contribution')
  self.assertIn('P2ProcessForensicsPanels',proposal)
  self.assertIn('onCancel',proposal)
  self.assertIn('onExportEvidence',proposal)
  for panel in ('journey','exposure','route','counterevidence','evidence'):
   self.assertIn(f'`{panel}`',proposal)
  self.assertTrue((root/'ui'/'p2-react'/'dist'/'index.js').is_file())
  self.assertTrue((root/'ui'/'p2-react'/'dist'/'index.d.ts').is_file())
 def test_no_remote_frontend_assets(self):
  root=Path(__file__).resolve().parent.parent
  assets='\n'.join((root/'ui'/name).read_text() for name in ('index.html','app.js','styles.css'))
  for forbidden in ('src="http://','src="https://','href="http://','href="https://','@import url(http','fetch("http','fetch(\'http'):
   self.assertNotIn(forbidden,assets)
 def test_file_picker_and_review_status_are_keyboard_and_screen_reader_exposed(self):
  root=Path(__file__).resolve().parent.parent
  html=(root/'ui'/'index.html').read_text()
  app=(root/'ui'/'app.js').read_text()
  self.assertIn('<details id="snapshot-editor">',html)
  self.assertIn('<summary id="snapshot-summary">Inspect or edit the bounded evidence snapshot (JSON)</summary>',html)
  self.assertIn('Snapshot JSON is being edited · review to refresh its size and row counts',app)
  self.assertIn('snapshotDetails.open=false',app)
  self.assertIn('<details id="affected-wafer-details">',html)
  self.assertIn('id="affected-wafer-summary">Review or edit selected abnormal wafer IDs</summary>',html)
  self.assertIn('updateAffectedWaferSummary',app)
  self.assertIn('<button id="open-file" type="button">Open JSON file</button>',html)
  self.assertIn('id="file-input" type="file" accept="application/json,.json" hidden',html)
  self.assertIn("document.getElementById('open-file').addEventListener('click',()=>fileInput.click())",app)
  self.assertIn('id="snapshot-review-announcement" class="sr-only" role="status" aria-live="polite"',html)
  self.assertIn('id="summary" class="empty" role="region" aria-labelledby="summary-title" tabindex="-1"',html)
  for target in ('journey-title','exposure-title','counter-title','sources-title'):
   self.assertIn(f'id="{target}" tabindex="-1"',html)
  panels=(root/'ui'/'p2-panels.js').read_text()
  self.assertIn("sectionNav.setAttribute('aria-label', 'Investigation section navigation')",panels)
  self.assertIn("['Counterevidence', 'counter-title']",panels)
  app=(root/'ui'/'app.js').read_text()
  self.assertIn("Inspect full declared analysis scope",app)
  self.assertIn("scope.target_wafer_ids.length",app)
  self.assertIn("scope.population.length",app)
 def test_dynamic_data_tables_have_named_column_headers(self):
  root=Path(__file__).resolve().parent.parent
  app=(root/'ui'/'app.js').read_text()
  panels=(root/'ui'/'p2-panels.js').read_text()
  for source in (app,panels):
   self.assertIn("'caption'",source)
   self.assertIn("'thead'",source)
   self.assertIn("'tbody'",source)
   self.assertRegex(source,r"setAttribute\('scope',\s*'col'\)")
