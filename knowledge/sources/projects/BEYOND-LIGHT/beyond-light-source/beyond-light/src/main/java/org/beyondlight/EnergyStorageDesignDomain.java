package org.beyondlight;

import java.util.*;

/** User-bounded energy-storage envelope exploration; it does not select a chemistry or hardware. */
public final class EnergyStorageDesignDomain implements TechnologyDesignDomain {
 private static final List<Objective> OBJECTIVES=List.of(
   new Objective("minimumStorageMassKg",Direction.MINIMIZE),
   new Objective("requiredInputEnergyJ",Direction.MINIMIZE),
   new Objective("conversionLossJ",Direction.MINIMIZE));
 @Override public String id(){return "energy.storage.envelope";}
 @Override public String title(){return "Eksplorasi envelope penyimpanan energi ideal";}
 @Override public String model(){return "Energi tersimpan + densitas energi spesifik + efisiensi konversi; tanpa model kimia";}
 @Override public List<Objective> objectives(){return OBJECTIVES;}
 @Override public List<Map<String,Object>> inputSchema(){return List.of(
   Map.of("name","energyJ","unit","J","minimumExclusive",0),
   Map.of("name","minEnergyDensityJkg","unit","J/kg","minimumExclusive",0),
   Map.of("name","maxEnergyDensityJkg","unit","J/kg","minimumInclusive","minEnergyDensityJkg"),
   Map.of("name","energyDensitySteps","unit","count","range","1..30"),
   Map.of("name","minEfficiency","unit","1","rangeExclusiveInclusive","(0,1]"),
   Map.of("name","maxEfficiency","unit","1","rangeExclusiveInclusive","(0,1]"),
   Map.of("name","efficiencySteps","unit","count","range","1..30"),
   Map.of("name","maximumStorageMassKg","unit","kg","zeroMeans","no supplied limit"),
   Map.of("name","maximumInputEnergyJ","unit","J","zeroMeans","no supplied limit"));}
 @Override public List<Map<String,Object>> generateCandidates(Request r){
  double energy=r.value("energyJ"),minDensity=r.value("minEnergyDensityJkg"),maxDensity=r.value("maxEnergyDensityJkg");
  double minEff=r.value("minEfficiency"),maxEff=r.value("maxEfficiency"),massLimit=r.value("maximumStorageMassKg"),inputLimit=r.value("maximumInputEnergyJ");
  int densitySteps=steps(r.value("energyDensitySteps")),efficiencySteps=steps(r.value("efficiencySteps"));
  if(!Double.isFinite(energy)||energy<=0||!Double.isFinite(minDensity)||!Double.isFinite(maxDensity)||minDensity<=0||maxDensity<minDensity||maxDensity>1e15||!Double.isFinite(minEff)||!Double.isFinite(maxEff)||minEff<=0||maxEff>1||maxEff<minEff||!Double.isFinite(massLimit)||massLimit<0||!Double.isFinite(inputLimit)||inputLimit<0)throw new IllegalArgumentException("Invalid energy-storage search bounds.");
  List<Double> densities=grid(minDensity,maxDensity,densitySteps),efficiencies=grid(minEff,maxEff,efficiencySteps);
  List<Map<String,Object>> candidates=new ArrayList<>();for(double density:densities)for(double efficiency:efficiencies){Map<String,Object> c=new LinkedHashMap<>();c.put("energyDensityJkg",density);c.put("efficiency",efficiency);candidates.add(c);}return candidates;
 }
 @Override public Evaluation evaluate(Request r,Map<String,Object> c){
  double energy=r.value("energyJ"),density=n(c,"energyDensityJkg"),efficiency=n(c,"efficiency");
  FeasibilityEngine.EnergyStorage storage=FeasibilityEngine.assessEnergyStorage(energy,density,efficiency);
  double massLimit=r.value("maximumStorageMassKg"),inputLimit=r.value("maximumInputEnergyJ");
  boolean massPass=massLimit==0||storage.minimumStorageMassKg()<=massLimit;
  boolean inputPass=inputLimit==0||storage.requiredInputEnergyJ()<=inputLimit;
  double residual=storage.requiredInputEnergyJ()-storage.deliveredEnergyJ()-storage.conversionLossJ();
  boolean energyBalancePass=Math.abs(residual)<=1e-10*Math.max(1,storage.requiredInputEnergyJ());
  Map<String,Object> metrics=new LinkedHashMap<>();metrics.put("deliveredEnergyJ",storage.deliveredEnergyJ());
  metrics.put("minimumStorageMassKg",storage.minimumStorageMassKg());metrics.put("requiredInputEnergyJ",storage.requiredInputEnergyJ());
  metrics.put("conversionLossJ",storage.conversionLossJ());metrics.put("massConstraintPass",massPass);
  metrics.put("inputEnergyConstraintPass",inputPass);metrics.put("energyBalancePass",energyBalancePass);
  metrics.put("feasibilityClassification",storage.status());
  metrics.put("screenStatus",massPass&&inputPass&&energyBalancePass?"WITHIN_USER_ENVELOPE_SCREEN":"OUTSIDE_USER_ENVELOPE_OR_CHECK_FAILED");
  Map<String,Object> checks=Map.of("massConstraintPass",massPass,"inputEnergyConstraintPass",inputPass,"energyBalancePass",energyBalancePass);
  return new Evaluation(massPass&&inputPass&&energyBalancePass,metrics,checks);
 }
 @Override public Map<String,Object> searchSpace(Request r){return Map.of("energyDensityRangeJkg",List.of(r.value("minEnergyDensityJkg"),r.value("maxEnergyDensityJkg")),"energyDensitySteps",(int)r.value("energyDensitySteps"),"efficiencyRange",List.of(r.value("minEfficiency"),r.value("maxEfficiency")),"efficiencySteps",(int)r.value("efficiencySteps"));}
 @Override public List<String> equations(){return List.of("minimumStorageMass=deliveredEnergy/energyDensity","requiredInputEnergy=deliveredEnergy/efficiency","conversionLoss=requiredInputEnergy-deliveredEnergy");}
 @Override public List<Map<String,Object>> sources(){return List.of(Map.of("type","user-supplied envelope","description","Energy-density and efficiency bounds are search assumptions, not measured material or device properties."));}
 @Override public List<String> limitations(){return List.of("This domain explores abstract storage envelopes; it does not identify batteries, capacitors, fuel cells, or a chemistry.","Energy density, efficiency, mass limits, and energy limits are supplied by the user and are not inferred from a validated component database.","Power delivery, charge/discharge rate, cycle life, thermal behavior, packaging, controls, safety, manufacturing, and prototype performance are not modeled.","Results are arithmetic screening only, not an engineering feasibility certification.");}
 private static int steps(double x){if(!Double.isFinite(x)||x<1||x>30||x!=Math.rint(x))throw new IllegalArgumentException("energy-density and efficiency step counts must be integers from 1 to 30");return (int)x;}
 private static List<Double> grid(double low,double high,int count){if(count==1)return List.of(low);List<Double> values=new ArrayList<>();for(int i=0;i<count;i++)values.add(low+(high-low)*i/(count-1));return values;}
 private static double n(Map<String,Object>m,String k){return ((Number)m.get(k)).doubleValue();}
}
