import math
import json
import uuid
from pathlib import Path
from datetime import datetime

# ==========================================
# ORBIT 3.0 - PHYSICS LABORATORY
# ==========================================

G = 6.67430e-11
AU = 149597870700.0
DAY = 86400.0
MS = 1.989e30

PLANETS = [
    ("Mercury", 0.387, 3.3011e23),
    ("Venus", 0.723, 4.8675e24),
    ("Earth", 1.000, 5.9722e24),
    ("Mars", 1.524, 6.4171e23),
    ("Jupiter", 5.203, 1.8982e27),
    ("Saturn", 9.537, 5.6834e26),
    ("Uranus", 19.191, 8.6810e25),
    ("Neptune", 30.069, 1.02413e26)
]

OUT = Path("experiments")
OUT.mkdir(exist_ok=True)


def experiment_id():
    return (
        datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        + "_" + uuid.uuid4().hex[:8]
    )


def save_result(data):
    eid = experiment_id()
    data["experiment_id"] = eid
    data["created"] = datetime.now().isoformat()

    path = OUT / f"{eid}.json"

    with path.open("w") as f:
        json.dump(data, f, indent=2)

    return path


def ask_float(label, default, minimum=None, maximum=None):
    raw = input(f"{label} [{default}]: ").strip()
    value = default if not raw else float(raw)

    if not math.isfinite(value):
        raise ValueError("Angka harus finite.")

    if minimum is not None and value < minimum:
        raise ValueError(f"Nilai minimum {minimum}")

    if maximum is not None and value > maximum:
        raise ValueError(f"Nilai maksimum {maximum}")

    return value


# ==========================================
# TWO BODY ORBITAL MECHANICS
# ==========================================

def orbital_simulation(
    sun_factor=1.0,
    speed_factor=1.0,
    duration=365,
    dt=3600
):
    mu = G * MS * sun_factor
    r0 = AU

    x, y = r0, 0.0
    vx = 0.0
    vy = math.sqrt(mu / r0) * speed_factor

    def energy(x, y, vx, vy):
        r = math.hypot(x, y)
        return 0.5 * (vx**2 + vy**2) - mu / r

    initial_energy = energy(x, y, vx, vy)
    initial_h = x * vy - y * vx

    min_r = r0
    max_r = r0
    trajectory = []

    steps = int(duration * DAY / dt)

    for i in range(steps):
        r = math.hypot(x, y)

        ax = -mu * x / r**3
        ay = -mu * y / r**3

        nx = x + vx * dt + 0.5 * ax * dt**2
        ny = y + vy * dt + 0.5 * ay * dt**2

        nr = math.hypot(nx, ny)

        nax = -mu * nx / nr**3
        nay = -mu * ny / nr**3

        nvx = vx + 0.5 * (ax + nax) * dt
        nvy = vy + 0.5 * (ay + nay) * dt

        x, y, vx, vy = nx, ny, nvx, nvy

        r = math.hypot(x, y)
        min_r = min(min_r, r)
        max_r = max(max_r, r)

        if i % max(1, int(DAY / dt)) == 0:
            trajectory.append([
                round(x / AU, 8),
                round(y / AU, 8)
            ])

    final_energy = energy(x, y, vx, vy)
    final_r = math.hypot(x, y)
    final_speed = math.hypot(vx, vy)

    # Specific orbital energy and eccentricity
    eps = initial_energy
    h = initial_h

    eccentricity_sq = 1 + (
        2 * eps * h**2 / mu**2
    )

    eccentricity = math.sqrt(max(0, eccentricity_sq))

    if eps < 0 and eccentricity < 1:
        orbit_type = "ELLIPTICAL / CIRCULAR"
        periapsis = h**2 / (mu * (1 + eccentricity))
        apoapsis = h**2 / (mu * (1 - eccentricity))
    elif abs(eccentricity - 1) < 1e-9:
        orbit_type = "PARABOLIC"
        periapsis = h**2 / (2 * mu)
        apoapsis = None
    elif eps > 0:
        orbit_type = "HYPERBOLIC / ESCAPE"
        periapsis = h**2 / (mu * (1 + eccentricity))
        apoapsis = None
    else:
        orbit_type = "UNCLASSIFIED"
        periapsis = None
        apoapsis = None

    drift = (
        abs(final_energy - initial_energy)
        / max(abs(initial_energy), 1e-30)
    ) * 100

    return {
        "model": "two_body",
        "sun_mass_factor": sun_factor,
        "initial_speed_factor": speed_factor,
        "duration_days": duration,
        "timestep_seconds": dt,
        "orbit_type": orbit_type,
        "eccentricity": eccentricity,
        "initial_velocity_km_s": vy / 1000,
        "final_velocity_km_s": final_speed / 1000,
        "final_distance_AU": final_r / AU,
        "minimum_distance_AU": min_r / AU,
        "maximum_distance_AU": max_r / AU,
        "periapsis_AU": (
            periapsis / AU if periapsis is not None else None
        ),
        "apoapsis_AU": (
            apoapsis / AU if apoapsis is not None else None
        ),
        "initial_energy_J_kg": initial_energy,
        "final_energy_J_kg": final_energy,
        "energy_error_percent": drift,
        "trajectory": trajectory
    }


def run_orbit():
    print("\n--- ORBITAL MECHANICS ---")

    mass = ask_float("Massa Matahari (x)", 1, 0.01, 100)
    speed = ask_float("Kecepatan awal (x kecepatan orbit Bumi)", 1, 0, 10)
    days = ask_float("Durasi simulasi (hari)", 365, 1, 36500)
    hours = ask_float("Timestep (jam)", 1, 0.01, 24)

    result = orbital_simulation(
        mass,
        speed,
        days,
        hours * 3600
    )

    print("\nHASIL ORBIT")
    print("Klasifikasi:", result["orbit_type"])
    print("Eksentrisitas:", round(result["eccentricity"], 8))
    print("Jarak akhir:", round(result["final_distance_AU"], 6), "AU")
    print("Kecepatan akhir:", round(result["final_velocity_km_s"], 4), "km/s")
    print("Periapsis:", result["periapsis_AU"], "AU")
    print("Apoapsis:", result["apoapsis_AU"], "AU")
    print("Kesalahan energi:", result["energy_error_percent"], "%")

    print("\nDataset:", save_result(result))


# ==========================================
# N BODY GRAVITATIONAL SIMULATION
# ==========================================

def nbody_acceleration(pos, masses):
    n = len(masses)
    acc = [[0.0, 0.0] for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            dx = pos[j][0] - pos[i][0]
            dy = pos[j][1] - pos[i][1]

            d2 = dx * dx + dy * dy

            if d2 == 0:
                raise ArithmeticError("Tabrakan titik massa.")

            inv_d3 = 1.0 / (d2 * math.sqrt(d2))

            ax = G * dx * inv_d3
            ay = G * dy * inv_d3

            acc[i][0] += masses[j] * ax
            acc[i][1] += masses[j] * ay

            acc[j][0] -= masses[i] * ax
            acc[j][1] -= masses[i] * ay

    return acc


def nbody_energy(pos, vel, masses):
    kinetic = 0.0
    potential = 0.0

    for i, mass in enumerate(masses):
        speed2 = vel[i][0]**2 + vel[i][1]**2
        kinetic += 0.5 * mass * speed2

        for j in range(i + 1, len(masses)):
            distance = math.hypot(
                pos[j][0] - pos[i][0],
                pos[j][1] - pos[i][1]
            )

            potential -= G * mass * masses[j] / distance

    return kinetic + potential


def nbody_simulation(days=365, dt=21600):
    names = ["Sun"] + [p[0] for p in PLANETS]
    masses = [MS] + [p[2] for p in PLANETS]

    pos = [[0.0, 0.0]]
    vel = [[0.0, 0.0]]

    # Approximate circular initial orbits.
    for i, (_, radius, _) in enumerate(PLANETS):
        angle = i * 0.73
        r = radius * AU

        pos.append([
            r * math.cos(angle),
            r * math.sin(angle)
        ])

        speed = math.sqrt(G * MS / r)

        vel.append([
            -speed * math.sin(angle),
            speed * math.cos(angle)
        ])

    # Shift to center-of-mass reference frame.
    total_mass = sum(masses)

    cx = sum(masses[i] * pos[i][0] for i in range(len(masses))) / total_mass
    cy = sum(masses[i] * pos[i][1] for i in range(len(masses))) / total_mass

    cvx = sum(masses[i] * vel[i][0] for i in range(len(masses))) / total_mass
    cvy = sum(masses[i] * vel[i][1] for i in range(len(masses))) / total_mass

    for i in range(len(masses)):
        pos[i][0] -= cx
        pos[i][1] -= cy
        vel[i][0] -= cvx
        vel[i][1] -= cvy

    initial_energy = nbody_energy(pos, vel, masses)
    max_drift = 0.0

    acc = nbody_acceleration(pos, masses)

    steps = int(days * DAY / dt)
    trajectory = []

    for step in range(steps):
        # Leapfrog: kick
        for i in range(len(masses)):
            vel[i][0] += 0.5 * acc[i][0] * dt
            vel[i][1] += 0.5 * acc[i][1] * dt

        # Drift
        for i in range(len(masses)):
            pos[i][0] += vel[i][0] * dt
            pos[i][1] += vel[i][1] * dt

        # Recalculate gravity
        acc = nbody_acceleration(pos, masses)

        # Kick
        for i in range(len(masses)):
            vel[i][0] += 0.5 * acc[i][0] * dt
            vel[i][1] += 0.5 * acc[i][1] * dt

        if step % max(1, int(DAY / dt)) == 0:
            current_energy = nbody_energy(pos, vel, masses)

            drift = (
                abs(current_energy - initial_energy)
                / max(abs(initial_energy), 1e-30)
            ) * 100

            max_drift = max(max_drift, drift)

            trajectory.append({
                names[i]: [
                    round(pos[i][0] / AU, 6),
                    round(pos[i][1] / AU, 6)
                ]
                for i in range(len(masses))
            })

    final_energy = nbody_energy(pos, vel, masses)

    return {
        "model": "nine_body_gravity",
        "objects": names,
        "duration_days": days,
        "timestep_seconds": dt,
        "initial_energy_J": initial_energy,
        "final_energy_J": final_energy,
        "final_energy_error_percent": (
            abs(final_energy - initial_energy)
            / max(abs(initial_energy), 1e-30)
        ) * 100,
        "maximum_sampled_energy_error_percent": max_drift,
        "trajectory": trajectory
    }


def run_nbody():
    print("\n--- N-BODY GRAVITY ---")
    days = ask_float("Durasi (hari)", 365, 1, 3650)
    hours = ask_float("Timestep (jam)", 6, 0.1, 24)

    print("\nMenghitung gravitasi sembilan benda...")

    result = nbody_simulation(days, hours * 3600)

    print("\nHASIL N-BODY")
    print("Jumlah benda:", len(result["objects"]))
    print("Benda:", ", ".join(result["objects"]))
    print("Kesalahan energi akhir:",
          result["final_energy_error_percent"], "%")
    print("Kesalahan maksimum terukur:",
          result["maximum_sampled_energy_error_percent"], "%")

    print("\nDataset:", save_result(result))


# ==========================================
# MASS EXPERIMENT
# ==========================================

def run_mass_experiment():
    print("\n--- MASS EXPERIMENT ---")
    print("Kecepatan awal Bumi dipertahankan konstan.")

    for factor in [0.5, 1, 1.5, 2]:
        result = orbital_simulation(
            sun_factor=factor,
            speed_factor=1,
            duration=365,
            dt=3600
        )

        print(
            f"\nMatahari {factor}x"
            f"\nOrbit: {result['orbit_type']}"
            f"\nEksentrisitas: {result['eccentricity']:.6f}"
            f"\nJarak akhir: {result['final_distance_AU']:.6f} AU"
            f"\nKecepatan akhir: {result['final_velocity_km_s']:.4f} km/s"
        )

        print("Dataset:", save_result(result))


# ==========================================
# ESCAPE VELOCITY
# ==========================================

def run_escape():
    print("\n--- ESCAPE VELOCITY ---")

    mass = ask_float("Massa objek pusat (kg)", MS, 1, 1e40)
    radius = ask_float("Jarak dari pusat (meter)", AU, 1, 1e15)

    velocity = math.sqrt(2 * G * mass / radius)

    print("\nKecepatan lepas:")
    print(f"{velocity:.6f} m/s")
    print(f"{velocity / 1000:.6f} km/s")

    save_result({
        "model": "escape_velocity",
        "mass_kg": mass,
        "radius_m": radius,
        "escape_velocity_m_s": velocity
    })


# ==========================================
# GRAVITATIONAL FORCE
# ==========================================

def run_gravity():
    print("\n--- GRAVITY CALCULATOR ---")

    m1 = ask_float("Massa benda pertama (kg)", 5.9722e24, 1e-20, 1e40)
    m2 = ask_float("Massa benda kedua (kg)", MS, 1e-20, 1e40)
    r = ask_float("Jarak antar pusat massa (meter)", AU, 1, 1e15)

    force = G * m1 * m2 / r**2
    acceleration1 = force / m1
    acceleration2 = force / m2

    print("\nHASIL")
    print(f"Gaya gravitasi: {force:.8e} N")
    print(f"Percepatan benda pertama: {acceleration1:.8e} m/s²")
    print(f"Percepatan benda kedua: {acceleration2:.8e} m/s²")

    save_result({
        "model": "gravity_calculator",
        "mass_1_kg": m1,
        "mass_2_kg": m2,
        "distance_m": r,
        "force_N": force,
        "acceleration_1_m_s2": acceleration1,
        "acceleration_2_m_s2": acceleration2
    })


# ==========================================
# EXPERIMENT DATABASE
# ==========================================

def show_database():
    files = sorted(OUT.glob("*.json"))

    print("\n--- EXPERIMENT DATABASE ---")
    print("Total eksperimen:", len(files))

    for file in files[-20:]:
        try:
            with file.open() as f:
                data = json.load(f)

            print(
                "\nID:", data.get("experiment_id", file.stem),
                "\nModel:", data.get("model", "unknown"),
                "\nWaktu:", data.get("created", "unknown"),
                "\nFile:", file.name
            )
        except (OSError, json.JSONDecodeError):
            print("File rusak:", file.name)


# ==========================================
# MAIN MENU
# ==========================================

def main():
    while True:
        print("""
================================================
       O R B I T  LABORATORY 3.0
          PHYSICS & SIMULATION
================================================

[1] Orbital Mechanics
[2] N-Body Gravity (9 objects)
[3] Solar Mass Experiment
[4] Escape Velocity
[5] Gravity Calculator
[6] Experiment Database
[0] Exit

================================================
""")

        choice = input("Pilih eksperimen: ").strip()

        try:
            if choice == "1":
                run_orbit()
            elif choice == "2":
                run_nbody()
            elif choice == "3":
                run_mass_experiment()
            elif choice == "4":
                run_escape()
            elif choice == "5":
                run_gravity()
            elif choice == "6":
                show_database()
            elif choice == "0":
                print("\nORBIT 3.0 terminated.")
                break
            else:
                print("Pilihan tidak tersedia.")

        except (ValueError, OverflowError, ArithmeticError) as error:
            print("\nEksperimen gagal:", error)

        except KeyboardInterrupt:
            print("\nEksperimen dihentikan.")

        input("\nTekan ENTER untuk kembali ke menu...")


if __name__ == "__main__":
    main()
