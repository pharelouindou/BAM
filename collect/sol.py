"""
BAM · ISRIC SoilGrids — gratuit, sans compte.
ATTENTION : API renvoie valeurs x10 — on divise par 10.
"""
import time
import requests

ISRIC_URL   = "https://rest.isric.org/soilgrids/v2.0/properties/query"
MAX_RETRIES = 3
TIMEOUT     = 45   # ISRIC peut être lent → 45s


def get_sol(lat: float, lon: float) -> dict:
    """
    Retourne ph_sol, carbone_g_kg, argile_pct.
    Réessaie jusqu'à 3 fois si timeout (serveur ISRIC parfois lent).
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(
                ISRIC_URL,
                params={
                    "lon":      lon,
                    "lat":      lat,
                    "property": ["phh2o", "soc", "clay"],
                    "depth":    ["0-5cm"],
                    "value":    "mean",
                },
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            p = r.json()["properties"]

            def val(name: str) -> float:
                try:
                    return p[name]["layers"][0]["values"]["mean"] or 0
                except (KeyError, IndexError, TypeError):
                    return 0

            return {
                "ph_sol":       round(val("phh2o") / 10, 2),
                "carbone_g_kg": round(val("soc")   / 10, 2),
                "argile_pct":   round(val("clay")  / 10, 1),
            }

        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                wait = attempt * 5
                print(f"  ISRIC timeout (tentative {attempt}/{MAX_RETRIES}) — attente {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ✗ ISRIC : timeout après {MAX_RETRIES} tentatives")
                return {}
        except Exception as e:
            print(f"  ✗ ISRIC : {e}")
            return {}
    return {}

if __name__ == "__main__":
    print("Test ISRIC → Savalou (peut prendre 10-15s)")
    print("-"*40)
    r = get_sol(7.93, 1.97)
    if r:
        print(f"  pH sol    : {r['ph_sol']}")
        print(f"  Carbone   : {r['carbone_g_kg']} g/kg")
        print(f"  Argile    : {r['argile_pct']} %")
        print("\n✓ ISRIC OK")
    else:
        print("✗ Echec — reessayer dans 1 min")
