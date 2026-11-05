package org.beyondlight;

import java.time.Instant;
import java.util.*;

/**
 * Sequential, explicitly coupled screening across energy storage, thermal rejection,
 * and structural sizing. Every coupling is reported and uses supplied operating assumptions.
 */
public final class CrossDomainTechnologyResearch {
 private CrossDomainTechnologyResearch() {}
 private static final List<String> ENERGY=List.of(
  "energyJ","minEnergyDensityJkg","maxEnergyDensityJkg","energyDensitySteps",
  "minEfficiency","maxEfficiency","efficiencySteps","maximumStorageMassKg","maximumInputEnergyJ");
 private static final List<String> THERMAL=List.of(
  "conductivityWmK","areaM2","deltaTemperatureK","thicknessM","emissivity",
  "radiatorTemperatureK","ambientTemperatureK","minCoolingCapacityW","maxCoolingCapacityW","coolingCapacitySteps");
 private static final List<String> STRUCTURE=List.of(
  "tensileLoadN","shearLoadN","baseAreaM2","baseShearAreaM2","baseSecondMomentM4",
  "memberLengthM","youngModulusPa","yieldStrengthPa","densityKgM3","requiredSafetyFactor",
  "effectiveLengthFactor","minSectionScale","maxSectionScale","sectionScaleSteps");

 public static Map<String,Object> explore(Map<String,Double> supplied,MachineDesign.Assembly assembly) {
  Map<String,Double> energyInputs=select(supplied,ENERGY);
  Map<String,Object> energyRun=TechnologyDesignEngine.explore(
    TechnologyDesignDomains.require("energy.storage.envelope"),
    new TechnologyDesignDomain.Request(energyInputs,Map.of(),assembly));
  Map<String,Object> energyResult=result(energyRun);
  Map<String,Object> energyCandidate=best(energyResult,"minimumStorageMassKg");
  if(energyCandidate==null)return report("ENERGY_STORAGE_NO_FEASIBLE_CANDIDATE",energyRun,null,null,Map.of());

  double storageMass=num(energyCandidate,"minimumStorageMassKg");
  double conversionLoss=num(energyCandidate,"conversionLossJ");
  double duration=required(supplied,"operatingDurationS");
  if(duration<=0)throw new IllegalArgumentException("operatingDurationS must be positive");
  double derivedHeatW=conversionLoss/duration;

  Map<String,Double> thermalInputs=select(supplied,THERMAL);
  thermalInputs.put("requiredHeatW",derivedHeatW);
  Map<String,Object> thermalRun=TechnologyDesignEngine.explore(
    TechnologyDesignDomains.require("thermal.management.steady-state"),
    new TechnologyDesignDomain.Request(thermalInputs,Map.of(),assembly));
  Map<String,Object> thermalResult=result(thermalRun);
  Map<String,Object> thermalCandidate=best(thermalResult,"coolingCapacityW");
  if(thermalCandidate==null)return report("THERMAL_MANAGEMENT_NO_FEASIBLE_CANDIDATE",energyRun,thermalRun,null,
    coupling(storageMass,conversionLoss,duration,derivedHeatW,null,null));

  double acceleration=required(supplied,"designAccelerationMS2");
  if(acceleration<0)throw new IllegalArgumentException("designAccelerationMS2 must be nonnegative");
  double compression=required(supplied,"baseCompressiveLoadN")+storageMass*acceleration;
  Map<String,Double> structureInputs=select(supplied,STRUCTURE);
  structureInputs.put("compressiveLoadN",compression);
  Map<String,Object> structureRun=TechnologyDesignEngine.explore(
    TechnologyDesignDomains.require("structures.member.envelope"),
    new TechnologyDesignDomain.Request(structureInputs,Map.of(),assembly));
  Map<String,Object> structureResult=result(structureRun);
  Map<String,Object> structureCandidate=best(structureResult,"estimatedMemberMassKg");
  String status=structureCandidate==null?"STRUCTURES_NO_FEASIBLE_CANDIDATE":"CROSS_DOMAIN_SCREEN_COMPLETE";
  return report(status,energyRun,thermalRun,structureRun,
    coupling(storageMass,conversionLoss,duration,derivedHeatW,compression,structureCandidate));
 }

 private static Map<String,Object> report(String status,Map<String,Object> energy,Map<String,Object> thermal,
                                          Map<String,Object> structures,Map<String,Object> coupling) {
  Map<String,Object> result=new LinkedHashMap<>();
  result.put("status",status);
  result.put("energyStorage",energy);
  if(thermal!=null)result.put("thermalManagement",thermal);
  if(structures!=null)result.put("structures",structures);
  result.put("coupling",coupling);
  result.put("allStagesPassed",status.equals("CROSS_DOMAIN_SCREEN_COMPLETE"));
  result.put("limitations",List.of(
   "Sequential deterministic screening, not a coupled multiphysics solver or an autonomous invention claim.",
   "Storage conversion loss is averaged over the user-supplied operating duration and passed to the steady-state thermal envelope as required heat.",
   "Selected storage mass is converted to an added compressive load using the user-supplied design acceleration; thermal hardware mass is not modeled.",
   "Thermal radiation/conduction and structural stress/Euler buckling retain the limitations of their individual domains; all material, geometry, load, and operating assumptions are user-supplied."));
  Map<String,Object> out=new LinkedHashMap<>();
  out.put("id",UUID.randomUUID().toString());out.put("date",Instant.now().toString());
  out.put("recordType","CROSS_DOMAIN_TECHNOLOGY_RESEARCH");out.put("category","research");
  out.put("title","Eksplorasi teknologi lintas-domain: energi → termal → struktur");
  out.put("model","EnergyStorageDesignDomain → ThermalManagementDesignDomain → StructuralDesignDomain");
  out.put("result",result);out.put("inputs",Map.of("couplingMode","sequential explicit variable transfer"));
  out.put("status",status);out.put("limitations",result.get("limitations"));
  out.put("sources",List.of(Map.of("type","built-in deterministic domain models","description","Each stage reports its equations, inputs, constraints and limitations.")));
  out.put("equations",List.of("Qdot_loss = conversionLossJ / operatingDurationS",
    "F_compression,total = F_compression,base + storageMassKg * designAccelerationMS2"));
  return out;
 }
 private static Map<String,Object> coupling(double mass,double loss,double duration,double heat,
                                             Double compression,Map<String,Object> structural) {
  Map<String,Object> m=new LinkedHashMap<>();
  m.put("storageMassKg",mass);m.put("storageConversionLossJ",loss);
  m.put("operatingDurationS",duration);m.put("derivedThermalLoadW",heat);
  if(compression!=null)m.put("derivedStructuralCompressionLoadN",compression);
  m.put("selectedStructuralCandidate",structural);
  return m;
 }
 private static Map<String,Double> select(Map<String,Double> from,List<String> keys) {
  Map<String,Double> out=new LinkedHashMap<>();
  for(String key:keys)out.put(key,required(from,key));
  return out;
 }
 private static double required(Map<String,Double> values,String key) {
  Double value=values.get(key);
  if(value==null||!Double.isFinite(value))throw new IllegalArgumentException("missing or nonfinite cross-domain input: "+key);
  return value;
 }
 private static Map<String,Object> result(Map<String,Object> run){return Json.map(run.get("result"));}
 private static Map<String,Object> best(Map<String,Object> result,String metric) {
  Object raw=result.get("allCandidates");if(!(raw instanceof List<?> candidates))return null;
  Map<String,Object> best=null;
  for(Object item:candidates){Map<String,Object> c=Json.map(item);
   if(!Boolean.TRUE.equals(c.get("candidateFeasible")))continue;
   if(best==null||num(c,metric)<num(best,metric))best=c;
  }
  return best;
 }
 private static double num(Map<String,Object> m,String key){Object v=m.get(key);if(!(v instanceof Number n)||!Double.isFinite(n.doubleValue()))throw new IllegalArgumentException("missing finite metric: "+key);return n.doubleValue();}
}
