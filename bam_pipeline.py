# prefect_pipeline.py
from prefect import flow, task
import subprocess
import os
import sys

DEPTS = ["Alibori", "Atacora", "Atlantique", "Borgou", "Collines", 
         "Couffo", "Donga", "Littoral", "Mono", "Oueme", "Plateau", "Zou"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _run_python(script_relpath: str, args: list[str]) -> None:
    """
    Lance un script python et stream stdout/stderr dans les logs Prefect.
    """
    script_path = os.path.join(BASE_DIR, script_relpath)
    cmd = [sys.executable, "-u", script_path] + args

    print(f"[subprocess] {cmd}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    combined: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        combined.append(line)
        print(line, end="")

    rc = proc.wait()
    if rc != 0:
        tail = "".join(combined[-200:])  # éviter de spammer si énorme
        raise RuntimeError(
            f"Subprocess failed (exit_code={rc}): {script_relpath}\n"
            f"--- last output ---\n{tail}"
        )


@task(name="Enrichir communes", retries=2)
def enrichir_communes(dept: str):
    print(f"=== Communes: {dept} ===")
    _run_python("process/enrichir_communes_geojson.py", ["--dept", dept])

@task(name="Enrichir grille", retries=2)
def enrichir_grille(dept: str):
    print(f"=== Relief / sol / météo / TWI: {dept} ===")
    _run_python("process/enrichir_grille.py", ["--dept", dept])

@task(name="Analyser grille satellite", retries=2)
def analyser_grille(dept: str):
    print(f"=== Satellite GEE + historique: {dept} ===")
    _run_python(
        "process/analyser_grille.py",
        ["--dept", dept, "--force"],
    )

@flow(name="BAM - Collecte par département")
def collecte_bam(depts: list[str] = DEPTS):
    for dept in depts:
        enrichir_communes(dept)
        enrichir_grille(dept)
        analyser_grille(dept)

if __name__ == "__main__":
    # Local uniquement : scheduler embarqué Prefect (pas de Cloud requis).
    # En prod Render → scripts/run_collecte_hebdo.py via Cron Job.
    collecte_bam.serve(
        name="bam-collecte-hebdo",
        cron="5 7 * * 1"  # Lundi 07h05 UTC = 08h05 Bénin (UTC+1)
    )