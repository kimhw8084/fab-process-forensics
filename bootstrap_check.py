"""Verify the supplied ZIP extraction has not been altered, then run seeded tests."""
from pathlib import Path
import hashlib, json, subprocess, sys
ROOT=Path(__file__).resolve().parent

def main():
    manifest=ROOT/'release'/'BOOTSTRAP_MANIFEST.sha256'
    checks=0
    for line in manifest.read_text(encoding='utf8').splitlines():
        if not line.strip(): continue
        expected,rel=line.split('  ',1)
        actual=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
        if actual!=expected:
            raise SystemExit('INTEGRITY FAILED: '+rel)
        checks+=1
    print('SOURCE INTEGRITY PASS:',checks,'files')
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT)
    if tests.returncode: raise SystemExit(tests.returncode)
    state=json.loads((ROOT/'product.json').read_text(encoding='utf8'))['release_state']
    print('P2 TESTS PASS — RELEASE STATE:',state,'— EXTERNAL_TRANSFER_READY NOT CLAIMED')

if __name__=='__main__':main()
