import math
import json
from datetime import datetime

G = 6.67430e-11
AU = 149597870700
M_SUN = 1.989e30

planets = {
    "Mercury": (0.387, 87.97),
    "Venus": (0.723, 224.70),
    "Earth": (1.000, 365.25),
    "Mars": (1.524, 686.98),
    "Jupiter": (5.203, 4332.59),
    "Saturn": (9.537, 10759.22),
    "Uranus": (19.191, 30688.5),
    "Neptune": (30.069, 60182)
}

def calculate(a, period):
    r = a * AU
    v = math.sqrt(G * M_SUN / r)
    force = G * M_SUN * 5.972e24 / r**2
    return {
        "distance_AU": a,
        "period_days": period,
        "orbital_velocity_km_s": v / 1000,
        "gravity_force_N": force
    }

print("\n" + "="*48)
print("          O R B I T  LABORATORY")
print("="*48)
print("Simulasi mekanika orbit tata surya\n")

results = {}

for name, (a, period) in planets.items():
    data = calculate(a, period)
    results[name] = data
    print(f"{name:9} | {a:7.3f} AU | "
          f"{data['orbital_velocity_km_s']:8.3f} km/s | "
          f"{period:9,.2f} hari")

print("\n" + "="*48)
print("EKSPERIMEN: PERUBAHAN JARAK ORBIT BUMI")
print("="*48)

for distance in [0.5, 0.75, 1, 1.5, 2, 3]:
    velocity = math.sqrt(G*M_SUN/(distance*AU))/1000
    period = 365.25 * distance**1.5
    print(f"{distance:4.2f} AU | "
          f"Kecepatan: {velocity:7.2f} km/s | "
          f"Periode: {period:9.2f} hari")

with open("orbit_dataset.json", "w") as f:
    json.dump({
        "created": datetime.now().isoformat(),
        "planets": results
    }, f, indent=2)

print("\nDataset tersimpan: orbit_dataset.json")
print("Laboratorium selesai dijalankan.")
print("="*48)
