import math
import json
import uuid
import os
import html
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

G = 6.67430e-11
AU = 149597870700.0
DAY = 86400.0
MS = 1.989e30

OUT = Path("experiments")
OUT.mkdir(exist_ok=True)

PLANETS = [
    ("Mercury", .387, 3.3011e23),
    ("Venus", .723, 4.8675e24),
    ("Earth", 1.000, 5.9722e24),
    ("Mars", 1.524, 6.4171e23),
    ("Jupiter", 5.203, 1.8982e27),
    ("Saturn", 9.537, 5.6834e26),
    ("Uranus", 19.191, 8.6810e25),
    ("Neptune", 30.069, 1.02413e26)
]

def new_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]

def save_json(data, eid, suffix):
    path = OUT / f"{eid}_{suffix}.json"
    path.write_text(json.dumps(data, indent=2))
    return path

# =====================================
# TWO BODY SIMULATION
# =====================================

def two_body(days=365, dt=3600):
    mu = G * MS
    x, y = AU, 0.0
    vx, vy = 0.0, math.sqrt(mu / AU)

    def acceleration(x, y):
        r = math.hypot(x, y)
        return -mu*x/r**3, -mu*y/r**3

    def energies(x, y, vx, vy):
        r = math.hypot(x, y)
        kinetic = .5*(vx*vx + vy*vy)
        potential = -mu/r
        return kinetic, potential, kinetic + potential

    initial = energies(x, y, vx, vy)[2]
    frames = []
    steps = int(days * DAY / dt)
    sample = max(1, int(DAY / dt))

    for i in range(steps + 1):
        if i % sample == 0:
            k, p, total = energies(x, y, vx, vy)
            frames.append({
                "day": round(i*dt/DAY, 3),
                "x": x/AU,
                "y": y/AU,
                "kinetic": k,
                "potential": p,
                "total": total,
                "energy_error": abs(total-initial)/abs(initial)*100
            })

        ax, ay = acceleration(x, y)
        nx = x + vx*dt + .5*ax*dt*dt
        ny = y + vy*dt + .5*ay*dt*dt
        nax, nay = acceleration(nx, ny)
        vx += .5*(ax+nax)*dt
        vy += .5*(ay+nay)*dt
        x, y = nx, ny

    return {
        "model": "Sun-Earth two body",
        "duration_days": days,
        "timestep_seconds": dt,
        "frames": frames
    }

# =====================================
# N BODY SIMULATION
# =====================================

def nbody_acc(pos, masses):
    n = len(masses)
    acc = [[0.0, 0.0] for _ in range(n)]

    for i in range(n):
        for j in range(i+1, n):
            dx = pos[j][0]-pos[i][0]
            dy = pos[j][1]-pos[i][1]
            d2 = dx*dx + dy*dy

            if d2 == 0:
                raise ArithmeticError("Singular collision")

            inv = 1/(d2*math.sqrt(d2))
            ax = G*dx*inv
            ay = G*dy*inv

            acc[i][0] += masses[j]*ax
            acc[i][1] += masses[j]*ay
            acc[j][0] -= masses[i]*ax
            acc[j][1] -= masses[i]*ay

    return acc

def nbody_energy(pos, vel, masses):
    kinetic = sum(
        .5*m*(v[0]**2+v[1]**2)
        for m, v in zip(masses, vel)
    )
    potential = 0.0

    for i in range(len(masses)):
        for j in range(i+1, len(masses)):
            r = math.hypot(
                pos[j][0]-pos[i][0],
                pos[j][1]-pos[i][1]
            )
            potential -= G*masses[i]*masses[j]/r

    return kinetic, potential, kinetic+potential

def nbody(days=365, dt=21600):
    names = ["Sun"] + [p[0] for p in PLANETS]
    masses = [MS] + [p[2] for p in PLANETS]

    pos = [[0.0, 0.0]]
    vel = [[0.0, 0.0]]

    for i, (_, radius, _) in enumerate(PLANETS):
        angle = i*.73
        r = radius*AU
        pos.append([r*math.cos(angle), r*math.sin(angle)])

        speed = math.sqrt(G*MS/r)
        vel.append([
            -speed*math.sin(angle),
            speed*math.cos(angle)
        ])

    total_mass = sum(masses)

    cx = sum(masses[i]*pos[i][0] for i in range(9))/total_mass
    cy = sum(masses[i]*pos[i][1] for i in range(9))/total_mass
    cvx = sum(masses[i]*vel[i][0] for i in range(9))/total_mass
    cvy = sum(masses[i]*vel[i][1] for i in range(9))/total_mass

    for i in range(9):
        pos[i][0] -= cx
        pos[i][1] -= cy
        vel[i][0] -= cvx
        vel[i][1] -= cvy

    initial = nbody_energy(pos, vel, masses)[2]
    acc = nbody_acc(pos, masses)

    frames = []
    steps = int(days*DAY/dt)
    sample = max(1, int(DAY/dt))

    for step in range(steps+1):
        if step % sample == 0:
            k, p, total = nbody_energy(pos, vel, masses)
            frames.append({
                "day": round(step*dt/DAY, 3),
                "positions": [
                    [round(v[0]/AU, 8), round(v[1]/AU, 8)]
                    for v in pos
                ],
                "kinetic": k,
                "potential": p,
                "total": total,
                "energy_error": abs(total-initial)/abs(initial)*100
            })

        for i in range(9):
            vel[i][0] += .5*acc[i][0]*dt
            vel[i][1] += .5*acc[i][1]*dt

        for i in range(9):
            pos[i][0] += vel[i][0]*dt
            pos[i][1] += vel[i][1]*dt

        acc = nbody_acc(pos, masses)

        for i in range(9):
            vel[i][0] += .5*acc[i][0]*dt
            vel[i][1] += .5*acc[i][1]*dt

    return {
        "model": "Nine body gravity",
        "objects": names,
        "duration_days": days,
        "timestep_seconds": dt,
        "frames": frames
    }

# =====================================
# HTML VISUALIZATION
# =====================================

def make_html(eid, earth, system):
    data = json.dumps(
        {"earth": earth, "system": system},
        separators=(",", ":")
    ).replace("</", "<\\/")

    page = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ORBIT 4.0 Laboratory</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0b1020;color:#e7edff;
font-family:system-ui,sans-serif}
header{padding:20px;background:#121b31}
h1{margin:0;font-size:25px}
small{color:#9caacb}
main{padding:14px;max-width:1000px;margin:auto}
.card{background:#131d33;border:1px solid #293653;
border-radius:13px;padding:14px;margin-bottom:14px}
h2{font-size:17px;margin:0 0 12px}
canvas{width:100%;display:block;background:#080d19;
border-radius:9px}
button,select{background:#263958;color:white;
border:1px solid #52688d;border-radius:8px;
padding:10px;margin:3px}
.controls{display:flex;flex-wrap:wrap;align-items:center}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.stat{background:#0c1528;padding:12px;border-radius:9px}
.stat b{display:block;font-size:19px;overflow-wrap:anywhere}
#status{color:#a9c9ff}
</style>
</head>
<body>
<header>
<h1>ORBIT 4.0</h1>
<small>Physics & Numerical Simulation Laboratory</small>
</header>
<main>
<div class="card">
<h2>Simulation controls</h2>
<div class="controls">
<button onclick="play()">Play / Pause</button>
<button onclick="reset()">Reset</button>
<select id="mode" onchange="reset()">
<option value="earth">Sun-Earth orbit</option>
<option value="system">Nine-body system</option>
</select>
<select id="speed">
<option value="1">1x</option>
<option value="2">2x</option>
<option value="4">4x</option>
<option value="8">8x</option>
</select>
</div>
<p id="status">Ready</p>
<canvas id="orbit" height="420"></canvas>
</div>
<div class="card">
<h2>Energy analysis</h2>
<canvas id="energy" height="220"></canvas>
<p><small>Specific energy for two-body model; total mechanical energy for nine-body model.</small></p>
</div>
<div class="card">
<h2>Live measurements</h2>
<div class="stats">
<div class="stat">Simulation day<b id="day">0</b></div>
<div class="stat">Energy error<b id="error">0%</b></div>
<div class="stat">Kinetic energy<b id="kinetic">-</b></div>
<div class="stat">Potential energy<b id="potential">-</b></div>
</div>
</div>
<div class="card">
<h2>Experiment information</h2>
<p>Experiment ID: <span id="eid"></span></p>
<p>All numerical results are generated locally by Python.</p>
</div>
</main>
<script>
const DATA = __DATA__;
const ID = "__ID__";
document.getElementById("eid").textContent=ID;

const colors=["#ffd166","#8ba8ff","#f5d7a1","#8de0d0",
"#f18b83","#d9a6ff","#e9c78d","#8cd7ee","#a9b3c7"];

const orbit=document.getElementById("orbit");
const ctx=orbit.getContext("2d");
const energy=document.getElementById("energy");
const ec=energy.getContext("2d");

let index=0, running=false, timer=null;

function frames(){
 return document.getElementById("mode").value==="earth"
 ? DATA.earth.frames : DATA.system.frames;
}

function play(){
 running=!running;
 if(running) animate();
}

function reset(){
 running=false;
 index=0;
 draw();
}

function animate(){
 if(!running)return;
 draw();
 const rate=Number(document.getElementById("speed").value);
 index=(index+rate)%frames().length;
 timer=setTimeout(animate,70);
}

function draw(){
 const f=frames();
 const mode=document.getElementById("mode").value;
 const frame=f[index]||f[0];

 ctx.clearRect(0,0,orbit.width,orbit.height);
 const cx=orbit.width/2,cy=orbit.height/2;
 ctx.fillStyle="#080d19";
 ctx.fillRect(0,0,orbit.width,orbit.height);

 if(mode==="earth"){
 const scale=Math.min(orbit.width,orbit.height)*.39;
 ctx.strokeStyle="#43516d";
 ctx.beginPath();
 ctx.arc(cx,cy,scale,0,Math.PI*2);
 ctx.stroke();

 ctx.fillStyle="#ffd166";
 ctx.beginPath();
 ctx.arc(cx,cy,9,0,Math.PI*2);
 ctx.fill();

 ctx.strokeStyle="#8ba8ff";
 ctx.beginPath();
 ctx.arc(cx,cy,scale,0,Math.PI*2);
 ctx.stroke();

 ctx.fillStyle="#8ba8ff";
 ctx.beginPath();
 ctx.arc(cx+frame.x*scale,cy-frame.y*scale,5,0,Math.PI*2);
 ctx.fill();

 ctx.fillStyle="white";
 ctx.fillText("Sun",cx+12,cy-12);
 ctx.fillText("Earth",cx+frame.x*scale+8,cy-frame.y*scale);
 }else{
 // Logarithmic radial display preserves visibility
 // of both inner and outer planets.
 const maxR=30.1;
 const scale=Math.min(orbit.width,orbit.height)*.43;
 const positions=frame.positions;

 positions.forEach((p,i)=>{
 const r=Math.hypot(p[0],p[1]);
 const displayR=Math.log1p(r)/Math.log1p(maxR)*scale;
 const angle=Math.atan2(p[1],p[0]);
 const x=cx+Math.cos(angle)*displayR;
 const y=cy-Math.sin(angle)*displayR;
 const size=i===0?8:(i>=5?4:3);

 ctx.fillStyle=colors[i];
 ctx.beginPath();
 ctx.arc(x,y,size,0,Math.PI*2);
 ctx.fill();

 ctx.fillStyle="#dce5ff";
 ctx.font="10px sans-serif";
 ctx.fillText(["Sun","Me","Ve","Ea","Ma","Ju","Sa","Ur","Ne"][i],
 x+size+2,y-3);
 });
 }

 document.getElementById("day").textContent=frame.day;
 document.getElementById("error").textContent=
 frame.energy_error.toExponential(3)+"%";
 document.getElementById("kinetic").textContent=
 frame.kinetic.toExponential(4);
 document.getElementById("potential").textContent=
 frame.potential.toExponential(4);
 document.getElementById("status").textContent=
 (running?"PLAYING":"PAUSED")+" | Frame "+(index+1)+" / "+f.length;

 drawEnergy(f,index);
}

function drawEnergy(f,current){
 const w=energy.width,h=energy.height;
 ec.clearRect(0,0,w,h);
 ec.fillStyle="#080d19";
 ec.fillRect(0,0,w,h);

 const values=f.map(v=>[
 v.kinetic,v.potential,v.total
 ]);
 const all=values.flat();
 const min=Math.min(...all);
 const max=Math.max(...all);
 const span=max-min||1;

 const colors2=["#ffd166","#8ba8ff","#7ee0b1"];
 const names=["Kinetic","Potential","Total"];

 for(let s=0;s<3;s++){
 ec.strokeStyle=colors2[s];
 ec.lineWidth=2;
 ec.beginPath();

 values.forEach((v,i)=>{
 const x=12+i/(Math.max(1,values.length-1))*(w-24);
 const y=h-12-(v[s]-min)/span*(h-30);
 if(i===0)ec.moveTo(x,y);else ec.lineTo(x,y);
 });
 ec.stroke();
 }

 const x=12+current/(Math.max(1,f.length-1))*(w-24);
 ec.strokeStyle="white";
 ec.setLineDash([4,4]);
 ec.beginPath();
 ec.moveTo(x,0);
 ec.lineTo(x,h);
 ec.stroke();
 ec.setLineDash([]);

 ec.font="11px sans-serif";
 names.forEach((n,i)=>{
 ec.fillStyle=colors2[i];
 ec.fillText(n,12+i*105,15);
 });
}

draw();
</script>
</body>
</html>'''

    page = page.replace("__DATA__", data).replace("__ID__", eid)
    path = Path("orbit4_visualization.html")
    path.write_text(page)
    return path

# =====================================
# MAIN
# =====================================

def main():
    eid = new_id()

    print("\n======================================")
    print("       ORBIT 4.0 VISUAL LAB")
    print("======================================")
    print("Menyiapkan simulasi dua benda...")
    earth = two_body(365, 3600)

    print("Menyiapkan simulasi sembilan benda...")
    system = nbody(365, 21600)

    a = save_json(earth, eid, "earth")
    b = save_json(system, eid, "nbody")

    html_path = make_html(eid, earth, system)

    print("\n======================================")
    print("       SIMULATION COMPLETED")
    print("======================================")
    print("Experiment ID:", eid)
    print("Earth dataset:", a)
    print("N-body dataset:", b)
    print("Visualization:", html_path)
    print("N-body energy error:",
          system["frames"][-1]["energy_error"], "%")
    print("\nMembuka visualisasi...")

    opener = shutil.which("termux-open")
    if opener:
        subprocess.Popen([opener, str(html_path.resolve())])
        print("File dikirim ke browser Android.")
    else:
        print("Buka file ini melalui browser:")
        print(str(html_path.resolve()))
        print("Atau jalankan: termux-open orbit4_visualization.html")

if __name__ == "__main__":
    main()
