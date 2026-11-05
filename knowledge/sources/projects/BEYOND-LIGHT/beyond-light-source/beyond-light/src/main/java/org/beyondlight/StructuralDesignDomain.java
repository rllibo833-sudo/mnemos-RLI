package org.beyondlight;

import java.util.*;

/** Deterministic structural section-envelope search using existing stress and Euler-buckling checks. */
public final class StructuralDesignDomain implements TechnologyDesignDomain {
 private static final List<Objective> OBJECTIVES=List.of(
   new Objective("estimatedMemberMassKg",Direction.MINIMIZE),
   new Objective("minimumSafetyMargin",Direction.MAXIMIZE));
 @Override public String id(){return "structures.member.envelope";}
 @Override public String title(){return "Eksplorasi envelope struktur anggota/prismatic member";}
 @Override public String model(){return "Von Mises stress + elastic Euler buckling + section-scale sweep";}
 @Override public List<Objective> objectives(){return OBJECTIVES;}
 @Override public List<Map<String,Object>> inputSchema(){return List.of(
   Map.of("name","tensileLoadN","unit","N","minimumInclusive",0),
   Map.of("name","compressiveLoadN","unit","N","minimumInclusive",0),
   Map.of("name","shearLoadN","unit","N","minimumInclusive",0),
   Map.of("name","baseAreaM2","unit","m2","minimumExclusive",0),
   Map.of("name","baseShearAreaM2","unit","m2","minimumExclusive",0),
   Map.of("name","baseSecondMomentM4","unit","m4","minimumExclusive",0),
   Map.of("name","memberLengthM","unit","m","minimumExclusive",0),
   Map.of("name","youngModulusPa","unit","Pa","minimumExclusive",0),
   Map.of("name","yieldStrengthPa","unit","Pa","minimumExclusive",0),
   Map.of("name","densityKgM3","unit","kg/m3","minimumExclusive",0),
   Map.of("name","requiredSafetyFactor","unit","1","minimumExclusive",0),
   Map.of("name","effectiveLengthFactor","unit","1","minimumExclusive",0),
   Map.of("name","minSectionScale","unit","1","minimumExclusive",0),
   Map.of("name","maxSectionScale","unit","1","minimumInclusive","minSectionScale"),
   Map.of("name","sectionScaleSteps","unit","count","range","1..30"));}
 @Override public List<Map<String,Object>> generateCandidates(Request r){
  double[] v=values(r);
  for(double x:v)if(!Double.isFinite(x))throw new IllegalArgumentException("Structural inputs must be finite.");
  if(v[0]<0||v[1]<0||v[2]<0||v[3]<=0||v[4]<=0||v[5]<=0||v[6]<=0||v[7]<=0||v[8]<=0||v[9]<=0||v[10]<=0||v[11]<=0||v[12]<=0||v[13]<v[12])
   throw new IllegalArgumentException("Invalid structural loads, material properties, geometry, or section-scale bounds.");
  int steps=steps(r.value("sectionScaleSteps"));
  List<Map<String,Object>> out=new ArrayList<>();
  for(int i=0;i<steps;i++){
   double scale=steps==1?v[12]:v[12]+(v[13]-v[12])*i/(steps-1d);
   out.add(Map.of("sectionScale",scale));
  }
  return out;
 }
 @Override public Evaluation evaluate(Request r,Map<String,Object> candidate){
  double scale=n(candidate,"sectionScale");
  if(scale<=0)throw new IllegalArgumentException("sectionScale must be positive");
  double area=r.value("baseAreaM2")*scale;
  double shearArea=r.value("baseShearAreaM2")*scale;
  double inertia=r.value("baseSecondMomentM4")*scale*scale;
  double length=r.value("memberLengthM"),young=r.value("youngModulusPa"),yield=r.value("yieldStrengthPa");
  double requiredSf=r.value("requiredSafetyFactor"),effective=r.value("effectiveLengthFactor");
  FeasibilityEngine.Stress stress=FeasibilityEngine.stress(
    r.value("tensileLoadN"),r.value("compressiveLoadN"),r.value("shearLoadN"),
    area,shearArea,length,young,yield,requiredSf);
  double bucklingCapacity=FeasibilityEngine.eulerBucklingLoad(young,inertia,length,effective);
  double compression=r.value("compressiveLoadN");
  double bucklingSf=compression==0?Double.POSITIVE_INFINITY:bucklingCapacity/compression;
  double bucklingMargin=bucklingCapacity-compression*requiredSf;
  boolean stressPass=FeasibilityEngine.ENG_OK.equals(stress.status());
  boolean bucklingPass=Double.isFinite(bucklingCapacity)&&bucklingMargin>=0;
  boolean pass=stressPass&&bucklingPass;
  double mass=r.value("densityKgM3")*area*length;
  double stressSf=stress.safetyFactor()==null?Double.NaN:stress.safetyFactor();
  double stressMargin=Double.isFinite(stressSf)?stressSf-requiredSf:Double.NaN;
  double minimumMargin=Double.isFinite(stressMargin)?Math.min(stressMargin,bucklingSf-requiredSf):Double.NaN;
  Map<String,Object> metrics=new LinkedHashMap<>();
  metrics.put("sectionScale",scale);metrics.put("areaM2",area);metrics.put("shearAreaM2",shearArea);
  metrics.put("secondMomentM4",inertia);metrics.put("estimatedMemberMassKg",mass);
  metrics.put("vonMisesStressPa",stress.vonMisesPa());metrics.put("stressSafetyFactor",stressSf);
  metrics.put("stressMargin",stressMargin);metrics.put("stressStatus",stress.status());
  metrics.put("criticalEulerLoadN",bucklingCapacity);metrics.put("appliedCompressionLoadN",compression);
  metrics.put("bucklingSafetyFactor",bucklingSf);metrics.put("bucklingMarginN",bucklingMargin);
  metrics.put("minimumSafetyMargin",minimumMargin);
  metrics.put("unknowns",stress.unknowns());
  metrics.put("screenStatus",pass?"WITHIN_STRUCTURAL_MEMBER_ENVELOPE":"OUTSIDE_STRUCTURAL_ENVELOPE_OR_MISSING_DATA");
  Map<String,Object> checks=new LinkedHashMap<>();
  checks.put("stressCheck",stress.status());checks.put("stressSafetyFactorPass",stressPass);
  checks.put("eulerBucklingPass",bucklingPass);checks.put("requiredSafetyFactor",requiredSf);
  return new Evaluation(pass,metrics,checks);
 }
 @Override public String sortMetric(){return "estimatedMemberMassKg";}
 @Override public Map<String,Object> searchSpace(Request r){
  return Map.of("sectionScaleRange",List.of(r.value("minSectionScale"),r.value("maxSectionScale")),
    "sectionScaleSteps",(int)r.value("sectionScaleSteps"));
 }
 @Override public List<String> equations(){return List.of(
  "A = A_base*scale; I = I_base*scale^2 (geometrically similar section assumption)",
  "sigma_vm = sqrt((F_t/A-F_c/A)^2 + 3*(F_s/A_s)^2)",
  "SF_stress = yieldStrength/sigma_vm",
  "P_cr = pi^2*E*I/(K*L)^2",
  "SF_buckling = P_cr/F_compression");}
 @Override public List<Map<String,Object>> sources(){return List.of(
  Map.of("type","built-in deterministic engineering models","description","Uses FeasibilityEngine.stress and FeasibilityEngine.eulerBucklingLoad; material and geometry inputs are supplied by the caller."));}
 @Override public List<String> limitations(){return List.of(
  "Member-level screening only; no joints, local plate buckling, fatigue, fracture, vibration, impact, thermal stress, nonlinear plasticity, or finite-element analysis.",
  "Section scaling assumes geometrically similar cross-sections: area scales linearly and second moment scales with scale squared.",
  "Euler buckling assumes an ideal straight elastic prismatic column with the supplied effective-length factor; imperfections and inelastic buckling are not modeled.",
  "Yield strength, modulus, density, geometry and loads are user-supplied; no missing material property is inferred and no passing result is a certification.");}
 private static double[] values(Request r){return new double[]{r.value("tensileLoadN"),r.value("compressiveLoadN"),r.value("shearLoadN"),r.value("baseAreaM2"),r.value("baseShearAreaM2"),r.value("baseSecondMomentM4"),r.value("memberLengthM"),r.value("youngModulusPa"),r.value("yieldStrengthPa"),r.value("densityKgM3"),r.value("requiredSafetyFactor"),r.value("effectiveLengthFactor"),r.value("minSectionScale"),r.value("maxSectionScale")};}
 private static int steps(double value){if(!Double.isFinite(value)||value<1||value>30||value!=Math.rint(value))throw new IllegalArgumentException("sectionScaleSteps must be an integer from 1 to 30");return (int)value;}
 private static double n(Map<String,Object> map,String key){Object value=map.get(key);if(!(value instanceof Number number)||!Double.isFinite(number.doubleValue()))throw new IllegalArgumentException("candidate is missing finite "+key);return number.doubleValue();}
}
