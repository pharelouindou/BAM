#!/usr/bin/env python3
"""
Point d'entrée collecte hebdomadaire — Render Cron Job.

Lance collecte_bam() une fois puis quitte (pas de processus 24/7).
Prefect Cloud non requis : @flow/@task locaux uniquement.

Variables optionnelles :
  BAM_DEPTS=Alibori,Atacora   # sous-ensemble pour test manuel
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bam_pipeline import DEPTS, collecte_bam


def _parse_depts() -> list[str]:
    raw = os.getenv("BAM_DEPTS", "").strip()
    if not raw:
        return DEPTS
    return [d.strip() for d in raw.split(",") if d.strip()]


def main() -> None:
    depts = _parse_depts()
    print(f"BAM · collecte hebdo — {len(depts)} département(s)")
    for d in depts:
        print(f"  - {d}")
    collecte_bam(depts=depts)
    print("BAM · collecte terminée.")


if __name__ == "__main__":
    main()
