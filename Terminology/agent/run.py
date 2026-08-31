#!/usr/bin/env python3
"""
Hybrid Agent for ADNI Terminology Mapping

Usage:
    python -m agent.run                    # Run all fields
    python -m agent.run --field PIB        # Run single field
    python -m agent.run --status           # Show completion status
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from agent.hybrid.runner import (
    run_field,
    run_all_fields,
    get_agent_fields,
    save_outputs,
)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base; nested dicts merge, scalars replace."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config() -> dict:
    base_path = Path(__file__).parent.parent / "config.yaml"
    with open(base_path) as f:
        config = yaml.safe_load(f)
    local_path = base_path.parent / "config.local.yaml"
    if local_path.exists():
        with open(local_path) as f:
            local = yaml.safe_load(f) or {}
        config = _deep_merge(config, local)
    return config


ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts" / "agent"


def run_single_field_cli(field_concept: dict) -> dict:
    """Run the hybrid pipeline for a single field."""
    print(f"\n{'='*60}")
    print(f"Processing: {field_concept['field_name']} ({field_concept.get('semantic_group', '')})")
    print(f"{'='*60}")

    result = run_field(field_concept)

    decision = result.get("decision", "unknown")
    print(f"\nDecision: {decision}")
    print(f"Score: {result.get('score', 0):.2f}")

    candidate = result.get("candidate")
    if decision == "mapped" and candidate:
        print(f"Mapped: {candidate.get('code')} - {candidate.get('display')}")
    if result.get("reason"):
        print(f"Reason: {result['reason']}")

    # Save outputs
    conceptmap_path, audit_path = save_outputs(result, ARTIFACTS_DIR)

    print(f"\nOutputs:")
    print(f"  ConceptMap: {conceptmap_path}")
    print(f"  Audit:      {audit_path}")

    return result


def run_all_fields_cli() -> list[dict]:
    """Run the hybrid pipeline for all agent-path fields."""
    results = run_all_fields(output_dir=ARTIFACTS_DIR)

    # Summary
    success = sum(1 for r in results if r.get("decision") == "mapped")
    human_review = sum(1 for r in results if r.get("decision") == "human_review")
    no_mapping = sum(1 for r in results if r.get("decision") == "no_mapping")
    errors = sum(1 for r in results if r.get("decision") == "error")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total processed: {len(results)}")
    print(f"  Mapped:        {success}")
    print(f"  Human review:  {human_review}")
    print(f"  No mapping:    {no_mapping}")
    print(f"  Errors:        {errors}")

    return results


def show_status():
    """Show fields that have been processed."""
    agent_fields = get_agent_fields()

    if not ARTIFACTS_DIR.exists():
        print(f"\nNo artifacts yet. Run to process {len(agent_fields)} fields.")
        return

    completed = []
    for f in agent_fields:
        conceptmap_path = ARTIFACTS_DIR / f"{f['field_name']}.conceptmap.json"
        if conceptmap_path.exists():
            completed.append(f['field_name'])

    print(f"\nStatus:")
    print(f"  Agent path fields: {len(agent_fields)}")
    print(f"  Completed:         {len(completed)}")
    print(f"  Pending:           {len(agent_fields) - len(completed)}")

    if completed:
        print(f"\nCompleted fields:")
        for field in completed:
            print(f"  - {field}")


def main():
    parser = argparse.ArgumentParser(description="ADNI Terminology Hybrid Agent")
    parser.add_argument("--field", type=str, help="Run single field")
    parser.add_argument("--status", action="store_true", help="Show completion status")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.field:
        fields = get_agent_fields()
        field = next((f for f in fields if f["field_name"] == args.field), None)

        if not field:
            print(f"Error: Field '{args.field}' not found or not agent path")
            sys.exit(1)

        result = run_single_field_cli(field)
        print(f"\nFinal result: {result.get('decision')}")

    else:
        run_all_fields_cli()


if __name__ == "__main__":
    main()
