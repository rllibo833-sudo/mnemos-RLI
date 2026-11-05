import math
import json
import os
from datetime import datetime

G = 6.67430e-11
AU = 149597870700
MS = 1.989e30
DAY = 86400

def simulate(mass_factor=1.0, duration=365, dt=3600):
    sun_mass = MS * mass_factor
    r = AU
    x, y = r, 0.0
    vx, vy = 0.0, math.sqrt(G * sun_mass / r)

    path = []
    energy = []
    steps = int(duration * DAY / dt)

    for i in range(steps):
        distance = math.sqrt(x*x + y*y)
        ax = -G * sun_mass * x / distance**3
        ay = -G * sun_mass * y / distance**3

        # Velocity Verlet
        nx = x + vx*dt + 0.5*ax*dt**2
        ny = y + vy*dt + 0.5*ay*dt**2

        nd = math.sqrt(nx*nx + ny*ny)
        nax = -G * sun_mass * nx / nd**3
        nay = -G * sun_mass * ny / nd**3

        nvx = vx + 0.5*(ax+nax)*dt
        nvy = vy + 0.5*(ay+nay)*dt

        x, y, vx, vy = nx, ny, nvx, nvy

        if i % 24 == 0:
            path.append([round(x/AU, 6), round(y/AU, 6)])
            speed = math.sqrt(vx**2 + vy**2)
            kinetic = 0.5 * speed**2
            potential = -G*sun_mass/nd
            energy.append(kinetic + potential)

    return {
        "mass_sun": mass_factor,
        "duration_days": duration,
        "time_step_seconds": dt,
        "final_distance_AU": round(math.sqrt(x*x+y*y)/AU, 6),
        "final_velocity_km_s": round(math.sqrt(vx**2+vy**2)/1000, 6),
        "trajectory": path,
        "energy": energy
    }

def save(result):
    os.makedirs("experiments", exist_ok=True)
    filename = datetime.now().strftime("experiments/orbit_%Y%m%d_%H%M%S.json")
    with open(filename, "w") as f:
        json.dump(result, f, indent=2)
    return filename

def main():
    print("\n========================================")
    print("          ORBIT LABORATORY 2.0")
    print("========================================")
    print("1. Simulasi orbit Bumi")
    print("2. Ubah massa Matahari")
    print("3. Bandingkan massa Matahari")
    print("4. Keluar")

    choice = input("\nPilih eksperimen: ").strip()

    if choice == "4":
        return

    if choice == "1":
        factor = 1.0
    elif choice == "2":
        try:
            factor = float(input("Massa Matahari (kelipatan): "))
            if not 0.01 <= factor <= 100:
                raise ValueError
        except ValueError:
            print("Masukkan angka antara 0.01 dan 100.")
            return
    elif choice == "3":
        for factor in [0.5, 1, 1.5, 2]:
            result = simulate(factor)
            print(f"\nMassa {factor}x")
            print("Jarak akhir:", result["final_distance_AU"], "AU")
            print("Kecepatan:", result["final_velocity_km_s"], "km/s")
            print("Data:", save(result))
        return
    else:
        print("Pilihan tidak valid.")
        return

    result = simulate(factor)
    filename = save(result)

    print("\nHASIL SIMULASI")
    print("Massa Matahari:", factor, "x")
    print("Jarak akhir:", result["final_distance_AU"], "AU")
    print("Kecepatan akhir:", result["final_velocity_km_s"], "km/s")
    print("Jumlah titik lintasan:", len(result["trajectory"]))
    print("Data eksperimen:", filename)
    print("\nSimulasi selesai.")

if __name__ == "__main__":
    main()
