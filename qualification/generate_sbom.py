"""Create a local SPDX 2.3 source inventory; ownership remains unasserted."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "release" / "SBOM.spdx.json"
sys.path.insert(0, str(ROOT))
from release.build_bundle import files_to_package


def main():
    files = []
    for relative, content in files_to_package():
        if relative == "release/SBOM.spdx.json":
            continue
        relative_path = Path(relative)
        files.append({
            "fileName": "./" + relative_path.as_posix(),
            "SPDXID": "SPDXRef-File-" + hashlib.sha256(relative.encode()).hexdigest()[:16],
            "checksums": [{"algorithm": "SHA256", "checksumValue": hashlib.sha256(content).hexdigest()}],
            "licenseConcluded": "NOASSERTION", "licenseInfoInFiles": ["NOASSERTION"],
            "copyrightText": "NOASSERTION",
        })
    inventory_path = ROOT / "vendor" / "mcp-sdk-2.3.0" / "macos-arm64-cp311" / "license-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf8"))
    vendor_packages = []
    npm_audit_path = ROOT / "qualification" / "evidence" / "p2-react-dependency-audit.json"
    npm_audit = json.loads(npm_audit_path.read_text(encoding="utf8"))
    npm_runtime_packages = []
    npm_runtime_relations = []
    host_spdx_id = "SPDXRef-Package-P2-Reference-Host"
    for item in npm_audit.get("bundled_reference_host_runtime", []):
        package_id = "SPDXRef-NPM-" + hashlib.sha256(f"{item['name']}@{item['version']}".encode()).hexdigest()[:16]
        npm_runtime_packages.append({
            "name": item["name"], "SPDXID": package_id,
            "versionInfo": item["version"], "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False, "packageFileName": f"npm:{item['name']}@{item['version']}",
            "licenseConcluded": "NOASSERTION", "licenseDeclared": item["license"],
            "copyrightText": "NOASSERTION",
            "externalRefs": [{
                "referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                "referenceLocator": f"pkg:npm/{item['name']}@{item['version']}",
            }],
        })
        npm_runtime_relations.append({
            "spdxElementId": package_id, "relationshipType": "DEPENDENCY_OF",
            "relatedSpdxElement": host_spdx_id,
        })
    mcp_spdx_id = None
    for item in inventory["packages"]:
        package_id = "SPDXRef-Vendor-" + hashlib.sha256(
            f"{item['normalized_name']}@{item['version']}".encode()
        ).hexdigest()[:16]
        if item["normalized_name"] == "mcp":
            mcp_spdx_id = package_id
        expression = item.get("license_expression") or "NOASSERTION"
        vendor_packages.append({
            "name": item["name"], "SPDXID": package_id,
            "versionInfo": item["version"], "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "packageFileName": item["wheel"],
            "checksums": [{"algorithm": "SHA256", "checksumValue": item["wheel_sha256"]}],
            "licenseConcluded": "NOASSERTION", "licenseDeclared": expression,
            "copyrightText": "NOASSERTION",
            "externalRefs": [{
                "referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                "referenceLocator": f"pkg:pypi/{item['normalized_name']}@{item['version']}",
            }],
        })
    if mcp_spdx_id is None:
        raise SystemExit("The pinned MCP SDK package is missing from the wheel license inventory.")
    doc = {
        "spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
        "name": "FAB Process Forensics P2 candidate source inventory",
        "documentNamespace": "https://spdx.org/spdxdocs/fab-process-forensics-p2-candidate-2026-11-23",
        "creationInfo": {"creators": ["Tool: qualification/generate_sbom.py"], "created": "2026-11-23T00:00:00Z"},
        "packages": [{
            "name": "FAB Process Forensics P2 source bundle", "SPDXID": "SPDXRef-Package-P2",
            "downloadLocation": "NOASSERTION", "filesAnalyzed": True,
            "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "externalRefs": [],
        }, *vendor_packages, {
            "name": "P2 product-neutral browser reference host", "SPDXID": host_spdx_id,
            "versionInfo": "1.0.0", "downloadLocation": "NOASSERTION", "filesAnalyzed": True,
            "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
        }, *npm_runtime_packages, {
            "name": "Python Standard Library", "SPDXID": "SPDXRef-Package-Python-Stdlib",
            "versionInfo": "3.10 or newer (bundled runtime not supplied)",
            "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
        }],
        "files": files,
        "relationships": [
            {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-Package-P2"},
            {"spdxElementId": mcp_spdx_id, "relationshipType": "OPTIONAL_DEPENDENCY_OF", "relatedSpdxElement": "SPDXRef-Package-P2"},
            {"spdxElementId": "SPDXRef-Package-P2", "relationshipType": "CONTAINS", "relatedSpdxElement": host_spdx_id},
            *npm_runtime_relations,
        ],
        "annotations": [{
            "annotationType": "OTHER", "annotator": "Tool: qualification/generate_sbom.py",
            "annotationDate": "2026-11-23T00:00:00Z",
            "comment": "Core engine runtime uses the Python standard library. The optional MCP SDK wheel closure is inventoried with hashes and wheel-metadata license expressions. React, React DOM, and Scheduler are embedded browser runtime components of the local reference host and are listed with npm lock versions and license metadata. Source ownership and company transfer or OSS approval remain unverified; NOASSERTION is not an approval.",
        }],
    }
    TARGET.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(f"Wrote {TARGET.relative_to(ROOT)}: {len(files)} locally inventoried files, no source ownership assertion.")


if __name__ == "__main__":
    main()
