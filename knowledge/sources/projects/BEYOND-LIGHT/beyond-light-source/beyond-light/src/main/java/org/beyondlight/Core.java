package org.beyondlight;

import java.util.*;

/** Deterministic SI calculations. Ideal equations; model boundaries are reported by callers. */
public final class Core {
  public static final double G0=ScientificCatalog.value("g0"), C=ScientificCatalog.value("c");
  public record Propulsion(double thrustN,double exhaustVelocity,double massFlowKgS,double deltaV,double propellantKg,double kineticPowerW,double electricalPowerW,double burnSeconds,double initialMassKg,double finalMassKg) {}
  public record Material(String name,double density,double yieldPa,double conductivity,double meltingK,String source) {}
  public record Structure(double volumeM3,double massKg,double stressPa,double safetyFactor,double heatCapacityJPerK,String assessment) {}
  public static final List<Material> MATERIALS=List.of(
    new Material("Ti-6Al-4V (density/conductivity only)",4430,0,6.92,0,"NASA JSC PathFinder Materials Database, 2006, https://tpsx.arc.nasa.gov/Material?id=261"),
    new Material("Ti-6Al-4V (handbook density/conductivity)",4430,0,7.3,0,"NASA Space Nuclear Propulsion Material Property Handbook, SNP-HDBK-0008, https://ntrs.nasa.gov/citations/20240004217"));
  private Core() {}
  public static Propulsion propulsion(double dryMass,double payload,double deltaV,double isp,double thrust,double efficiency) {
    positive(dryMass,"dry mass"); positive(payload,"payload"); positive(deltaV,"delta-v"); positive(isp,"specific impulse"); positive(thrust,"thrust");
    if (!(efficiency>0 && efficiency<=1)) throw new IllegalArgumentException("efficiency must be in (0,1]");
    double ve=isp*G0, mf=dryMass+payload, m0=mf*Math.exp(deltaV/ve), prop=m0-mf, mdot=thrust/ve;
    double pkin=.5*mdot*ve*ve, pe=pkin/efficiency;
    if(!Double.isFinite(m0)||!Double.isFinite(prop)||!Double.isFinite(pkin)||!Double.isFinite(pe)) throw new IllegalArgumentException("requested parameters exceed finite numerical range");
    return new Propulsion(thrust,ve,mdot,ve*Math.log(m0/mf),prop,pkin,pe,prop/mdot,m0,mf);
  }
  public static Structure material(double volume,double loadN,double area,double safety,double density,double yieldPa,double specificHeat) {
    positive(volume,"volume"); positive(area,"area"); positive(safety,"safety factor"); positive(density,"density");
    if(loadN<0) throw new IllegalArgumentException("load must be nonnegative");
    double stress=loadN/area, mass=volume*density, margin=yieldPa>0?yieldPa/stress:Double.NaN;
    String assessment=yieldPa<=0?"Cannot evaluate strength: verified yield-strength data missing":margin>=safety?"Passes supplied static yield screening only":"Fails supplied static yield screening";
    return new Structure(volume,mass,stress,margin,mass*specificHeat,assessment);
  }
  public static double integrateSimpson(java.util.function.DoubleUnaryOperator f,double a,double b,int n) {
    if(n<2||n>1_000_000) throw new IllegalArgumentException("interval count must be 2..1,000,000"); if(n%2==1)n++;
    double h=(b-a)/n, sum=f.applyAsDouble(a)+f.applyAsDouble(b);
    for(int i=1;i<n;i++)sum+=(i%2==0?2:4)*f.applyAsDouble(a+i*h);
    return sum*h/3;
  }
  public static double[] rk4(java.util.function.BiFunction<Double,Double,Double> dydt,double y0,double t0,double t1,int steps) {
    if(steps<1||steps>1_000_000)throw new IllegalArgumentException("steps must be 1..1,000,000");
    double[] out=new double[steps+1]; out[0]=y0; double h=(t1-t0)/steps,y=y0,t=t0;
    for(int i=1;i<=steps;i++){double k1=dydt.apply(t,y),k2=dydt.apply(t+h/2,y+h*k1/2),k3=dydt.apply(t+h/2,y+h*k2/2),k4=dydt.apply(t+h,y+h*k3); y+=h*(k1+2*k2+2*k3+k4)/6;t+=h;out[i]=y;}return out;
  }
  public static double convert(double value,String from,String to) {
    Map<String,Double> f=Map.ofEntries(Map.entry("m",1d),Map.entry("km",1000d),Map.entry("s",1d),Map.entry("h",3600d),Map.entry("kg",1d),Map.entry("g",.001),Map.entry("N",1d),Map.entry("kN",1000d),Map.entry("W",1d),Map.entry("kW",1000d),Map.entry("J",1d),Map.entry("MJ",1e6));
    if(!f.containsKey(from)||!f.containsKey(to))throw new IllegalArgumentException("unsupported unit conversion"); return value*f.get(from)/f.get(to);
  }
  static void positive(double n,String what){if(!Double.isFinite(n)||n<=0)throw new IllegalArgumentException(what+" must be finite and positive");}
}
