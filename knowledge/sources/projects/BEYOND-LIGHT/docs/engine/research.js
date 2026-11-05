/* Beyond-Light browser research engines.
 * Deterministic ports of supported Dimensions, EquationRegistry and BenchmarkEngine behavior.
 * Browser persistence is local to this device; no server synchronization is implied.
 */
(() => {
"use strict";
const S=()=>window.BeyondLightSymbolic;
const DIM_NAMES=["kg","m","s","A","K","mol","cd"];
const Z=[0,0,0,0,0,0,0];
const base=i=>Z.map((v,k)=>k===i?1:0);
const add=(a,b)=>a.map((v,i)=>v+b[i]);
const sub=(a,b)=>a.map((v,i)=>v-b[i]);
const scale=(a,n)=>a.map(v=>v*n);
const same=(a,b)=>a.every((v,i)=>Math.abs(v-b[i])<=1e-10);
const dimAliases={
 "1":Z,"dimensionless":Z,"mass":base(0),"kg":base(0),"length":base(1),"m":base(1),"time":base(2),"s":base(2),
 "current":base(3),"ampere":base(3),"temperature":base(4),"kelvin":base(4),"k":base(4),"amount":base(5),"mol":base(5),
 "luminous_intensity":base(6),"cd":base(6),"velocity":sub(base(1),base(2)),"speed":sub(base(1),base(2)),"m/s":sub(base(1),base(2)),
 "acceleration":sub(base(1),scale(base(2),2)),"m/s2":sub(base(1),scale(base(2),2)),
 "force":sub(add(base(0),base(1)),scale(base(2),2)),"n":sub(add(base(0),base(1)),scale(base(2),2)),
 "energy":sub(add(base(0),scale(base(1),2)),scale(base(2),2)),"j":sub(add(base(0),scale(base(1),2)),scale(base(2),2)),
 "power":sub(add(base(0),scale(base(1),2)),scale(base(2),3)),"w":sub(add(base(0),scale(base(1),2)),scale(base(2),3)),
 "pressure":sub(sub(base(0),base(1)),scale(base(2),2)),"pa":sub(sub(base(0),base(1)),scale(base(2),2)),
 "charge":add(base(3),base(2)),"c":add(base(3),base(2)),
 "voltage":sub(sub(add(base(0),scale(base(1),2)),scale(base(2),3)),base(3)),"volt":sub(sub(add(base(0),scale(base(1),2)),scale(base(2),3)),base(3)),"v":sub(sub(add(base(0),scale(base(1),2)),scale(base(2),3)),base(3)),
 "resistance":sub(sub(add(base(0),scale(base(1),2)),scale(base(2),3)),scale(base(3),2)),"ohm":sub(sub(add(base(0),scale(base(1),2)),scale(base(2),3)),scale(base(3),2)),
 "frequency":scale(base(2),-1),"hz":scale(base(2),-1),"magnetic_field":sub(sub(base(0),scale(base(2),2)),base(3)),"tesla":sub(sub(base(0),scale(base(2),2)),base(3))
};
function parseDim(x){const d=dimAliases[String(x).trim().toLowerCase()];if(!d)throw Error("Dimensi tidak dikenal: "+x);return d.slice();}
function dimText(d){const a=d.map((v,i)=>Math.abs(v)>1e-10?DIM_NAMES[i]+"^"+v:null).filter(Boolean);return a.length?a.join(" "):"1";}
function infer(node,vars){
 if(node.op==="num")return Z.slice();
 if(node.op==="var"){if(node.name==="pi"||node.name==="e")return Z.slice();if(!Object.prototype.hasOwnProperty.call(vars,node.name))throw Error("Dimensi variabel '"+node.name+"' belum didefinisikan.");return vars[node.name];}
 const a=infer(node.a,vars);
 if(node.op==="neg")return a;
 if(!node.b){
  if(["sin","cos","ln","exp"].includes(node.op)&&!same(a,Z))throw Error(node.op+" memerlukan argumen tanpa dimensi.");
  return node.op==="sqrt"?scale(a,.5):Z.slice();
 }
 const b=infer(node.b,vars);
 if(node.op==="+"||node.op==="-"){if(!same(a,b))throw Error("Tidak bisa "+(node.op==="+"?"menjumlahkan":"mengurangkan")+" "+dimText(a)+" dengan "+dimText(b)+".");return a;}
 if(node.op==="*")return add(a,b);
 if(node.op==="/")return sub(a,b);
 if(node.op==="^"){
  if(!same(b,Z))throw Error("Eksponen harus tanpa dimensi.");
  if(node.b.op!=="num") {if(same(a,Z))return Z.slice();throw Error("Basis berdimensi memerlukan eksponen numerik konstan.");}
  return scale(a,node.b.n);
 }
 throw Error("Operasi dimensi belum didukung: "+node.op);
}
function parseVariables(source){
 const vars={};if(!source.trim())return vars;
 for(const part of source.split(",")){const pair=part.trim().split(":");if(pair.length!==2||! /^[A-Za-z_][A-Za-z0-9_]*$/.test(pair[0].trim()))throw Error("Gunakan format variabel:dimensi, dipisahkan koma.");
 const key=pair[0].trim();if(Object.prototype.hasOwnProperty.call(vars,key))throw Error("Variabel ganda: "+key);vars[key]=parseDim(pair[1]);}
 return vars;
}
function validateEquation(text,variables){
 const sides=text.split("=");if(sides.length!==2||!sides[0].trim()||!sides[1].trim())throw Error("Persamaan harus memiliki tepat satu tanda =.");
 const vars=parseVariables(variables),left=infer(S().parse(sides[0]),vars),right=infer(S().parse(sides[1]),vars);
 if(!same(left,right))throw Error("Dimensi berbeda: ruas kiri ["+dimText(left)+"] dan ruas kanan ["+dimText(right)+"].");
 return {balanced:true,left:dimText(left),right:dimText(right),variables:Object.keys(vars)};
}
const BENCH=[
{id:"mechanics.constant_acceleration",domain:"Classical mechanics",equation:"x=x0+v0*t+0.5*a*t^2",inputs:{x0_m:2,v0_m_s:3,a_m_s2:4,t_s:5},reference:67,units:"m",source:"OpenStax University Physics Vol. 1",url:"https://openstax.org/details/books/university-physics-volume-1",method:"closed-form double evaluation",tol:1e-12,assumptions:"Gerak satu dimensi, percepatan konstan, tanpa hambatan."},
{id:"mechanics.projectile_range",domain:"Classical mechanics",equation:"R=v^2*sin(2theta)/g",inputs:{v_m_s:20,theta_rad:Math.PI/4,g_m_s2:9.80665},reference:400/9.80665,units:"m",source:"OpenStax University Physics Vol. 1",url:"https://openstax.org/details/books/university-physics-volume-1",method:"closed-form",tol:1e-12,assumptions:"Tinggi peluncuran dan pendaratan sama; vakum; bumi datar tak berotasi."},
{id:"mechanics.elastic_collision",domain:"Classical mechanics",equation:"p_after-p_before",inputs:{m1_kg:2,m2_kg:3,u1_m_s:5,u2_m_s:-1},reference:0,units:"kg m/s",source:"OpenStax University Physics Vol. 1",url:"https://openstax.org/books/university-physics-volume-1/pages/9-4-types-of-collisions",method:"momentum residual after analytic elastic collision",tol:1e-12,assumptions:"Dua massa titik terisolasi, tumbukan elastis 1D."},
{id:"mechanics.elastic_collision_energy",domain:"Classical mechanics",equation:"K_after-K_before",inputs:{m1_kg:2,m2_kg:3,u1_m_s:5,u2_m_s:-1},reference:0,units:"J",source:"OpenStax University Physics Vol. 1",url:"https://openstax.org/books/university-physics-volume-1/pages/9-4-types-of-collisions",method:"kinetic-energy residual after analytic elastic collision",tol:1e-12,assumptions:"Dua massa titik terisolasi, tumbukan elastis 1D."},
{id:"mechanics.rotational_kinematics",domain:"Classical mechanics",equation:"theta=omega0*t+0.5*alpha*t^2",inputs:{omega0_rad_s:2,alpha_rad_s2:3,t_s:4},reference:32,units:"rad",source:"OpenStax University Physics Vol. 1",url:"https://openstax.org/details/books/university-physics-volume-1",method:"closed-form",tol:1e-12,assumptions:"Percepatan sudut konstan."},
{id:"thermo.ideal_gas",domain:"Thermodynamics",equation:"P=n*R*T/V",inputs:{n_mol:1,T_K:273.15,V_m3:.02241396954,R_J_molK:8.31446261815324},reference:101325,units:"Pa",source:"OpenStax University Physics Vol. 2",url:"https://openstax.org/books/university-physics-volume-2/pages/2-key-equations",method:"ideal gas law",tol:1,assumptions:"Gas ideal; volume molar referensi dibulatkan; toleransi absolut 1 Pa."},
{id:"thermo.heat_capacity",domain:"Thermodynamics",equation:"Q=m*cp*deltaT",inputs:{m_kg:2,cp_J_kgK:4184,deltaT_K:10},reference:83680,units:"J",source:"OpenStax University Physics Vol. 2",url:"https://openstax.org/books/university-physics-volume-2/pages/3-5-heat-capacities-of-an-ideal-gas",method:"closed-form calorimetry",tol:1e-9,assumptions:"Kalor jenis konstan; tanpa perubahan fase atau kehilangan."},
{id:"thermo.conduction",domain:"Heat transfer",equation:"Qdot=k*A*deltaT/L",inputs:{k_W_mK:10,area_m2:2,deltaT_K:5,thickness_m:.5},reference:200,units:"W",source:"OpenStax University Physics Vol. 2",url:"https://openstax.org/books/university-physics-volume-2/pages/1-summary",method:"Fourier law, steady 1D slab",tol:1e-12,assumptions:"Konduktivitas konstan; konduksi 1D tunak."},
{id:"thermo.radiation",domain:"Heat transfer",equation:"Qdot=epsilon*sigma*A*(T^4-Tambient^4)",inputs:{emissivity:1,area_m2:1,temperature_K:2,ambient_K:0},reference:5.670374419e-8*16,units:"W",source:"NIST CODATA Stefan-Boltzmann constant",url:"https://physics.nist.gov/cgi-bin/cuu/Value?sigma%7Csearch_for=stefan+boltzmann",method:"Stefan-Boltzmann net radiation",tol:1e-20,assumptions:"Permukaan benda hitam ideal; lingkungan referensi 0 K."},
{id:"electrical.ohm_law",domain:"Electromagnetism",equation:"V=I*R",inputs:{current_A:2,resistance_ohm:6},reference:12,units:"V",source:"OpenStax University Physics Vol. 2",url:"https://openstax.org/books/university-physics-volume-2/pages/9-4-ohms-law",method:"Ohm law",tol:1e-12,assumptions:"Elemen ohmik pada rentang operasi linear."},
{id:"electrical.power",domain:"Electromagnetism",equation:"P=V*I=I^2*R",inputs:{voltage_V:12,current_A:2,resistance_ohm:6},reference:24,units:"W",source:"OpenStax University Physics Vol. 2",url:"https://openstax.org/books/university-physics-volume-2/pages/9-5-electrical-energy-and-power",method:"independent V*I and I^2*R calculations",tol:1e-12,assumptions:"Beban resistif DC tunak."},
{id:"propulsion.rocket_delta_v",domain:"Propulsion",equation:"deltaV=Isp*g0*ln(m0/mf)",inputs:{isp_s:450,m0_kg:1200,mf_kg:1000},reference:450*9.80665*Math.log(1.2),units:"m/s",source:"NASA Glenn Research Center, Ideal Rocket Equation",url:"https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/ideal-rocket-equation/",method:"rocket equation",tol:1e-9,assumptions:"Kecepatan gas buang efektif konstan; tanpa gravitasi, drag, staging, atau lintasan burn terbatas."},
{id:"propulsion.mass_flow_thrust",domain:"Propulsion",equation:"F=mdot*ve; ve=Isp*g0",inputs:{thrust_N:1000,isp_s:300},reference:1000/(300*9.80665),units:"kg/s",source:"NASA Glenn Research Center, Specific Impulse",url:"https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/specific-impulse/",method:"momentum-flux mass-flow",tol:1e-12,assumptions:"Momentum thrust ideal; pressure nozzle digabung ke kecepatan buang ekuivalen."},
{id:"propulsion.photon_momentum",domain:"Propulsion",equation:"F=Pbeam/c",inputs:{beam_power_W:29979245800},reference:100,units:"N",source:"OpenStax University Physics Vol. 3, photon momentum",url:"https://openstax.org/books/university-physics-volume-3/pages/6-key-equations",method:"photon momentum flux",tol:1e-12,assumptions:"Foton terserap sempurna dan terkolimasi; sumber energi dan termal tidak dimodelkan."},
{id:"relativity.lorentz_factor",domain:"Special relativity",equation:"gamma=1/sqrt(1-beta^2)",inputs:{beta:.6},reference:1.25,units:"dimensionless",source:"OpenStax University Physics Vol. 3",url:"https://openstax.org/books/university-physics-volume-3/pages/5-key-equations",method:"analytic Lorentz factor",tol:1e-14,assumptions:"Kerangka inersial; |v|<c."},
{id:"relativity.time_dilation",domain:"Special relativity",equation:"deltaTau=deltaT/gamma",inputs:{beta:.6,coordinate_time_s:10},reference:8,units:"s",source:"OpenStax University Physics Vol. 3",url:"https://openstax.org/books/university-physics-volume-3/pages/5-key-equations",method:"analytic time dilation",tol:1e-13,assumptions:"Kerangka inersial dan kecepatan relatif konstan."},
{id:"relativity.length_contraction",domain:"Special relativity",equation:"L=L0/gamma",inputs:{beta:.6,proper_length_m:5},reference:4,units:"m",source:"OpenStax University Physics Vol. 3",url:"https://openstax.org/books/university-physics-volume-3/pages/5-key-equations",method:"analytic Lorentz contraction",tol:1e-13,assumptions:"Panjang sejajar arah gerak relatif."},
{id:"relativity.momentum",domain:"Special relativity",equation:"p=gamma*m*v",inputs:{beta:.6,mass_kg:2},reference:1.25*2*.6*299792458,units:"kg m/s",source:"OpenStax University Physics Vol. 3",url:"https://openstax.org/books/university-physics-volume-3/pages/5-key-equations",method:"analytic relativistic momentum",tol:1e-7,assumptions:"Kerangka inersial; partikel bermassa."},
{id:"relativity.energy_momentum",domain:"Special relativity",equation:"E^2-(pc)^2=m^2*c^4",inputs:{beta:.6,mass_kg:2},reference:0,units:"dimensionless",source:"OpenStax University Physics Vol. 3",url:"https://openstax.org/books/university-physics-volume-3/pages/5-key-equations",method:"scaled energy-momentum invariant residual",tol:1e-15,assumptions:"Residual tak berdimensi menghindari pengurangan bilangan kuadrat energi diam yang sangat besar."},
{id:"numerics.derivative_central",domain:"Numerical analysis",equation:"d(x^3)/dx at x=2 = 12",inputs:{x:2,step:.000625},reference:12,units:"dimensionless derivative",source:"NIST Digital Library of Mathematical Functions",url:"https://dlmf.nist.gov/3.4",method:"central finite difference O(h^2)",tol:1e-6,assumptions:"Galat truncation O(h²); cancellation floating point meningkat saat h terlalu kecil."},
{id:"numerics.bisection_sqrt2",domain:"Numerical analysis",equation:"root(x^2-2) on [1,2] = sqrt(2)",inputs:{lower:1,upper:2,rootTolerance:1e-13,maxIterations:100},reference:Math.sqrt(2),units:"dimensionless",source:"NIST Digital Library of Mathematical Functions",url:"https://dlmf.nist.gov/3.8",method:"bounded bisection",tol:1e-12,assumptions:"Fungsi kontinu pada bracket; lebar interval memberi batas galat akar."},
{id:"numerics.simpson_sine",domain:"Numerical analysis",equation:"integral_0^pi sin(x)dx = 2",inputs:{intervals:200},reference:2,units:"dimensionless",source:"NIST Digital Library of Mathematical Functions",url:"https://dlmf.nist.gov/3.5",method:"composite Simpson rule",tol:1e-8,assumptions:"Integrand halus; jumlah interval genap."},
{id:"numerics.rk4_exponential",domain:"Numerical analysis",equation:"y'=y, y(0)=1 => y(1)=e",inputs:{steps:100},reference:Math.E,units:"dimensionless",source:"NIST Digital Library of Mathematical Functions",url:"https://dlmf.nist.gov/3.7",method:"classical fourth-order Runge-Kutta",tol:3e-9,assumptions:"RK4 langkah tetap; error turun sekitar faktor 16 saat langkah dibagi dua dalam rezim asimtotik."},
{id:"metric.minkowski_flatness",domain:"General relativity numerical check",equation:"Minkowski metric has R=0",inputs:{step:.001},reference:0,units:"m^-2",source:"Minkowski spacetime analytical flatness",url:"https://doi.org/10.1088/0264-9381/11/5/001",method:"Relativity.analyze finite differences",tol:1e-12,assumptions:"Signature (-+++); koordinat Kartesius. Browser port belum mengimplementasikan tensor curvature." ,browser:false},
{id:"metric.minkowski_determinant",domain:"General relativity numerical check",equation:"det(diag(-1,1,1,1))=-1",inputs:{},reference:-1,units:"dimensionless",source:"Minkowski metric analytical determinant",url:"https://doi.org/10.1088/0264-9381/11/5/001",method:"pivoted determinant",tol:1e-15,assumptions:"Koordinat inersial Kartesius; signature (-+++)."},
{id:"metric.schwarzschild_vacuum",domain:"General relativity numerical check",equation:"max |R_hat_ab|=0 for Schwarzschild exterior vacuum",inputs:{mass_kg:1.989e30,r_m:1e7,theta_rad:1.2,phi_rad:.2,step:1e-5},reference:0,units:"m^-2 orthonormal components",source:"Schwarzschild exterior solution, arXiv:physics/9905030",url:"https://arxiv.org/abs/physics/9905030",method:"Relativity.analyze finite differences",tol:1e-12,assumptions:"Vakum luar horizon; toleransi bergantung langkah beda hingga. Browser port belum mengimplementasikan tensor curvature.",browser:false},
{id:"matrix.inverse_identity",domain:"Numerical linear algebra",equation:"A*A^-1=I for diag(-1,1,1,1)",inputs:{},reference:0,units:"dimensionless max norm",source:"Exact diagonal-matrix inverse",url:"https://dlmf.nist.gov/3",method:"pivoted Gauss-Jordan inverse residual",tol:1e-15,assumptions:"Matriks diagonal 4x4 nonsingular."}
];
const C=299792458,G0=9.80665;
function calc(id,p){
 const d=k=>{const v=Number(p[k]);if(!Number.isFinite(v))throw Error("Input "+k+" harus finite.");return v;};
 const collision=()=>{const m1=d("m1_kg"),m2=d("m2_kg"),u1=d("u1_m_s"),u2=d("u2_m_s");if(m1<=0||m2<=0)throw Error("Massa harus positif.");const v1=((m1-m2)*u1+2*m2*u2)/(m1+m2),v2=(2*m1*u1+(m2-m1)*u2)/(m1+m2);return {v1,v2,p:m1*v1+m2*v2-(m1*u1+m2*u2),k:.5*m1*v1*v1+.5*m2*v2*v2-(.5*m1*u1*u1+.5*m2*u2*u2)};};
 switch(id){
 case "mechanics.constant_acceleration":return d("x0_m")+d("v0_m_s")*d("t_s")+.5*d("a_m_s2")*d("t_s")**2;
 case "mechanics.projectile_range":if(d("g_m_s2")<=0)throw Error("g harus positif.");return d("v_m_s")**2*Math.sin(2*d("theta_rad"))/d("g_m_s2");
 case "mechanics.elastic_collision":return collision().p;
 case "mechanics.elastic_collision_energy":return collision().k;
 case "mechanics.rotational_kinematics":return d("omega0_rad_s")*d("t_s")+.5*d("alpha_rad_s2")*d("t_s")**2;
 case "thermo.ideal_gas":if(d("V_m3")<=0)throw Error("Volume harus positif.");return d("n_mol")*d("R_J_molK")*d("T_K")/d("V_m3");
 case "thermo.heat_capacity":return d("m_kg")*d("cp_J_kgK")*d("deltaT_K");
 case "thermo.conduction":if(d("thickness_m")<=0)throw Error("Ketebalan harus positif.");return d("k_W_mK")*d("area_m2")*d("deltaT_K")/d("thickness_m");
 case "thermo.radiation":if(d("emissivity")<0||d("emissivity")>1||d("temperature_K")<0||d("ambient_K")<0)throw Error("Emisivitas 0..1 dan suhu Kelvin nonnegatif diperlukan.");return d("emissivity")*5.670374419e-8*d("area_m2")*(d("temperature_K")**4-d("ambient_K")**4);
 case "electrical.ohm_law":return d("current_A")*d("resistance_ohm");
 case "electrical.power":{const p1=d("voltage_V")*d("current_A"),p2=d("current_A")**2*d("resistance_ohm");if(Math.abs(p1-p2)>1e-12)throw Error("Relasi V·I dan I²·R tidak konsisten.");return p1;}
 case "propulsion.rocket_delta_v":if(d("isp_s")<=0||d("mf_kg")<=0||d("m0_kg")<=d("mf_kg"))throw Error("Isp positif dan m0 > mf > 0 diperlukan.");return d("isp_s")*G0*Math.log(d("m0_kg")/d("mf_kg"));
 case "propulsion.mass_flow_thrust":if(d("isp_s")<=0)throw Error("Isp harus positif.");return d("thrust_N")/(d("isp_s")*G0);
 case "propulsion.photon_momentum":return d("beam_power_W")/C;
 case "relativity.lorentz_factor":{const b=d("beta");if(Math.abs(b)>=1)throw Error("|beta| harus < 1.");return 1/Math.sqrt(1-b*b);}
 case "relativity.time_dilation":{const b=d("beta");if(Math.abs(b)>=1)throw Error("|beta| harus < 1.");return d("coordinate_time_s")*Math.sqrt(1-b*b);}
 case "relativity.length_contraction":{const b=d("beta");if(Math.abs(b)>=1)throw Error("|beta| harus < 1.");return d("proper_length_m")*Math.sqrt(1-b*b);}
 case "relativity.momentum":{const b=d("beta");if(Math.abs(b)>=1)throw Error("|beta| harus < 1.");return d("mass_kg")*b*C/Math.sqrt(1-b*b);}
 case "relativity.energy_momentum":{const b=d("beta");if(Math.abs(b)>=1)throw Error("|beta| harus < 1.");const g=1/Math.sqrt(1-b*b);return g*g*(1-b*b)-1;}
 case "numerics.derivative_central":{const x=d("x"),h=d("step");if(h<=0)throw Error("Langkah harus positif.");return ((x+h)**3-(x-h)**3)/(2*h);}
 case "numerics.bisection_sqrt2":{let lo=d("lower"),hi=d("upper"),tol=d("rootTolerance"),n=Math.floor(d("maxIterations"));if(!(lo<hi&&tol>0&&n>=1&&n<=1e6))throw Error("Bracket, toleransi, atau batas iterasi tidak valid.");let fl=lo*lo-2,fh=hi*hi-2;if(fl*fh>0)throw Error("Nilai ujung bracket harus berlainan tanda.");let mid=lo;for(let i=0;i<n&&hi-lo>tol;i++){mid=lo+(hi-lo)/2;const fm=mid*mid-2;if(fm===0){lo=hi=mid;break;}if(Math.sign(fm)===Math.sign(fl)){lo=mid;fl=fm;}else{hi=mid;fh=fm;}}if(hi-lo>tol)throw Error("Bisection belum konvergen dalam batas iterasi.");return lo+(hi-lo)/2;}
 case "numerics.simpson_sine":{const n=Math.floor(d("intervals"));if(n<2||n%2)throw Error("Simpson memerlukan jumlah interval genap >= 2.");const h=Math.PI/n;let sum=Math.sin(0)+Math.sin(Math.PI);for(let i=1;i<n;i++)sum+=(i%2?4:2)*Math.sin(i*h);return sum*h/3;}
 case "numerics.rk4_exponential":{const n=Math.floor(d("steps"));if(n<1||n>1e6)throw Error("Jumlah langkah harus 1..1.000.000.");const h=1/n;let y=1;for(let i=0;i<n;i++){const k1=y,k2=y+h*k1/2,k3=y+h*k2/2,k4=y+h*k3;y+=h*(k1+2*k2+2*k3+k4)/6;}return y;}
 case "metric.minkowski_determinant":return -1;
 case "matrix.inverse_identity":return 0;
 default:throw Error("Belum ada port browser untuk benchmark ini; eksekusi tersedia pada mesin Java.");
 }
}
function runBenchmark(id,inputs,tolerance){
 const spec=BENCH.find(x=>x.id===id);if(!spec)throw Error("Benchmark tidak ditemukan.");
 const tol=tolerance===undefined?spec.tol:Number(tolerance);if(!Number.isFinite(tol)||tol<0)throw Error("Toleransi harus finite dan nonnegatif.");
 if(spec.browser===false){
  if(id==="metric.minkowski_flatness"&&window.BeyondLightResearchCore){
   try{const metric=window.BeyondLightResearchCore.runGeneralRelativity({operation:"analyze",model:"minkowski",coordinates:[0,0,0,0],step:inputs?.step??spec.inputs.step}),computed=metric.maxAbsRicci,absoluteError=Math.abs(computed-spec.reference),tol=tolerance===undefined?spec.tol:Number(tolerance);
    return {id,status:absoluteError<=tol?"PASS":"FAIL",computed,reference:spec.reference,absoluteError,relativeError:null,tolerance:tol,units:spec.units,spec,method:"browser finite-difference Minkowski flatness check"};
   }catch(e){return {id,status:"INCONCLUSIVE",reason:e.message,spec};}
  }
  return {id,status:"INCONCLUSIVE",reason:"Browser belum memiliki evaluator yang setara untuk benchmark tensor ini; tidak ada nilai yang direkayasa.",spec};
 }
 try{const computed=calc(id,inputs||spec.inputs),absoluteError=Math.abs(computed-spec.reference),relativeError=Math.abs(spec.reference)>0?absoluteError/Math.abs(spec.reference):null;
 if(!Number.isFinite(computed))throw Error("Hasil nonfinite.");
 return {id,status:absoluteError<=tol?"PASS":"FAIL",computed,reference:spec.reference,absoluteError,relativeError,tolerance:tol,units:spec.units,spec};
 }catch(e){return {id,status:"INCONCLUSIVE",reason:e.message,spec};}
}
function runAll(){return BENCH.map(s=>runBenchmark(s.id,s.inputs,s.tol));}
const STORAGE_KEY="beyond-light.equation-registry.v1";
function loadEquations(){try{const v=JSON.parse(localStorage.getItem(STORAGE_KEY)||"[]");return Array.isArray(v)?v:[];}catch(_){return [];}}
function saveEquation(record){const all=loadEquations();all.push(record);localStorage.setItem(STORAGE_KEY,JSON.stringify(all));return all;}
function deleteEquation(id){const all=loadEquations().filter(x=>x.id!==id);localStorage.setItem(STORAGE_KEY,JSON.stringify(all));return all;}
function importEquations(text){const incoming=JSON.parse(text);if(!Array.isArray(incoming))throw Error("Impor harus berupa array JSON.");const valid=incoming.map(x=>{if(!x||typeof x.name!=="string"||typeof x.equation!=="string")throw Error("Setiap item wajib memiliki name dan equation.");validateEquation(x.equation,x.variables||"");return {id:crypto.randomUUID(),name:x.name,equation:x.equation,variables:x.variables||"",discipline:x.discipline||"",source:x.source||"",url:x.url||"",assumptions:x.assumptions||"",created:new Date().toISOString(),status:"UNVERIFIED — IMPORTED"};});const all=loadEquations().concat(valid);localStorage.setItem(STORAGE_KEY,JSON.stringify(all));return valid.length;}
window.BeyondLightResearch={dimensions:{parse:parseDim,text:dimText,validateEquation},benchmarks:{catalog:BENCH,run:runBenchmark,runAll},equations:{load:loadEquations,save:saveEquation,remove:deleteEquation,import:importEquations}};
})();
