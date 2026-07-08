"""BAM · Open-Meteo — gratuit, sans compte, sans clé"""
import requests

def get_meteo(lat: float, lon: float) -> dict:
    """
    Retourne pluie_7j_mm, temp_max_c, humidite_sol pour un point GPS.
    Exemple : get_meteo(7.93, 1.97)
    """
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "daily": "precipitation_sum,temperature_2m_max",
            "hourly": "soil_moisture_0_to_7cm",
            "forecast_days": 7, "timezone": "Africa/Porto-Novo"
        }, timeout=15)
        r.raise_for_status()
        d = r.json()
        return {
            "pluie_7j_mm":  round(sum(v or 0 for v in d["daily"]["precipitation_sum"]), 2),
            "temp_max_c":   round(d["daily"]["temperature_2m_max"][0] or 0, 1),
            "humidite_sol": round(d["hourly"]["soil_moisture_0_to_7cm"][0] or 0, 4)
        }
    except Exception as e:
        print(f"  ✗ Open-Meteo : {e}"); return {}

if __name__ == "__main__":
    print("Test Open-Meteo → Savalou"); print("-"*40)
    r = get_meteo(7.93, 1.97)
    if r:
        print(f"  Pluie 7j     : {r['pluie_7j_mm']} mm")
        print(f"  Temp max     : {r['temp_max_c']} C")
        print(f"  Humidite sol : {r['humidite_sol']}")
        print("\n✓ Open-Meteo OK")
    else:
        print("✗ Echec")
