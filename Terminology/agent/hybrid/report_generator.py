import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load_fields() -> list[dict]:
    fields_path = Path(__file__).parent.parent.parent / "fields.json"
    with open(fields_path) as f:
        data = json.load(f)
    return data.get("fields", [])


def get_all_field_definitions() -> dict[str, dict]:
    """Get all 62 fields as a lookup dict by field_name."""
    fields = load_fields()
    return {f["field_name"]: f for f in fields}


def generate_adni_codesystem(unmapped_fields: list[dict]) -> dict:
    """Generate FHIR CodeSystem for ADNI custom codes."""
    concepts = []
    
    for field in unmapped_fields:
        field_name = field.get("field_name", "")
        description = field.get("description", "")
        meaning = field.get("meaning", "")
        
        display = meaning if meaning else description
        if not display:
            display = field_name
        
        concepts.append({
            "code": field_name,
            "display": display
        })
    
    return {
        "resourceType": "CodeSystem",
        "id": "adni-terms",
        "meta": {
            "source": "ADNI",
            "date": datetime.utcnow().isoformat() + "Z"
        },
        "url": "http://adni.example.org/fhir/CodeSystem/adni-terms",
        "version": "1.0.0",
        "name": "ADNI_Terms",
        "title": "ADNI Terminology Codes",
        "status": "active",
        "content": "complete",
        "concept": concepts
    }


def generate_mapping_markdown(
    mapped_fields: list[dict],
    unmapped_fields: list[dict]
) -> str:
    """Generate markdown mapping report."""
    
    lines = [
        "# ADNI Terminology Mapping",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
        "This document contains the complete terminology mapping for ADNI schema columns to standard LOINC/SNOMED codes and ADNI custom codes.",
        "",
        "---",
        "",
        "## Fields with Standard LOINC/SNOMED Codes",
        "",
        "| Column | Description | System | Code | Display |",
        "|--------|-------------|--------|------|---------|",
    ]
    
    for field in mapped_fields:
        field_name = field.get("field_name", "")
        field_def = field.get("field_concept", {})
        candidate = field.get("candidate", {})
        
        description = field_def.get("description", "")
        code = candidate.get("code", "")
        display = candidate.get("display", "")
        system = candidate.get("system", "")
        
        if not display:
            display = field_def.get("meaning", "")
        
        if code and system:
            system_short = "LOINC" if "loinc.org" in system else ("SNOMED" if "snomed" in system else "Other")
            lines.append(f"| **{field_name}** | {description} | {system_short} | {code} | {display} |")
    
    lines.extend([
        "",
        "---",
        "",
        "## Fields with ADNI Custom Codes",
        "",
        "| Column | Description | ADNI Code | Display |",
        "|--------|-------------|-----------|---------|",
    ])
    
    for field in unmapped_fields:
        field_name = field.get("field_name", "")
        field_def = field.get("field_concept", {})
        
        description = field_def.get("description", "")
        meaning = field_def.get("meaning", "")
        
        display = meaning if meaning else description
        if not display:
            display = field_name
        
        lines.append(f"| **{field_name}** | {description} | {field_name} | {display} |")
    
    lines.extend([
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Category | Count |",
        "|----------|-------|",
        f"| Standard LOINC/SNOMED codes | {len(mapped_fields)} |",
        f"| ADNI custom codes | {len(unmapped_fields)} |",
    ])
    
    return "\n".join(lines)


def generate_mapping_report(results: list[dict]) -> dict:
    """Generate complete mapping report and CodeSystem."""
    
    all_fields = get_all_field_definitions()
    processed_fields = {r["field_name"]: r for r in results}
    
    mapped_fields = []
    unmapped_field_names = set()
    
    for field_name, result in processed_fields.items():
        decision = result.get("decision", "")
        if decision == "mapped":
            mapped_fields.append(result)
        else:
            unmapped_field_names.add(field_name)
    
    for field_name in all_fields:
        if field_name not in processed_fields:
            unmapped_field_names.add(field_name)
    
    unmapped_fields = [
        {**all_fields[name], "field_name": name, "field_concept": all_fields[name]}
        for name in unmapped_field_names
        if name in all_fields
    ]
    
    unmapped_fields.sort(key=lambda x: x.get("field_name", ""))
    mapped_fields.sort(key=lambda x: x.get("field_name", ""))
    
    codesystem = generate_adni_codesystem(unmapped_fields)
    markdown = generate_mapping_markdown(mapped_fields, unmapped_fields)
    
    return {
        "mapped_count": len(mapped_fields),
        "unmapped_count": len(unmapped_fields),
        "codesystem": codesystem,
        "markdown": markdown,
        "mapped_fields": mapped_fields,
        "unmapped_fields": unmapped_fields,
    }


def save_mapping_report(results: list[dict], output_dir: Path) -> tuple[Path, Path]:
    """Generate and save mapping report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report = generate_mapping_report(results)
    
    codesystem_path = output_dir / "adni-codesystem.json"
    with open(codesystem_path, "w") as f:
        json.dump(report["codesystem"], f, indent=2)
    
    markdown_path = output_dir / "mapping-report.md"
    with open(markdown_path, "w") as f:
        f.write(report["markdown"])
    
    return codesystem_path, markdown_path
