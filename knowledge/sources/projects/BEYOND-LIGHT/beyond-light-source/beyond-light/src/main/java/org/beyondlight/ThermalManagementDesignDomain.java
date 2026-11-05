package org.beyondlight;

import java.util.*;

/**
 * Steady-state thermal-management envelope exploration.
 * Sweeps the required cooling-system rating against the existing conduction/radiation model.
 */
public final class ThermalManagementDesignDomain implements TechnologyDesignDomain {
 private static final List<Objective> OBJECTIVES=List.of(
   new Objective("coolingCapacityW",Direction.MINIMIZE),
   new Objective("marginW",Direction.MAXIMIZE));
 @Override public String id(){return "thermal.management.steady-state";}
 @Override public String title(){return "Eksplorasi envelope manajemen termal steady-state";}
 @Override public String model(){return "Konduksi + radiasi Stefan-Boltzmann + margin kapasitas pendinginan";}
 @Override public List<Objective> objectives(){return OBJECTIVES;}
 @Override public List<Map<String,Object>> inputSchema(){return List.of(
   Map.of("name","conductivityWmK","unit","W/(m K)","minimumExclusive",0),
   Map.of("name","areaM2","unit","m2","minimumExclusive",0),
   Map.of("name","deltaTemperatureK","unit","K","minimumExclusive",0),
   Map.of("name","thicknessM","unit","m","minimumExclusive",0),
   Map.of("name","emissivity","unit","1","rangeInclusive","[0,1]"),
   Map.of("name","radiatorTemperatureK","unit","K","mustExceed","ambientTemperatureK"),
   Map.of("name","ambientTemperatureK","unit","K","minimumInclusive",0),
   Map.of("name","requiredHeatW","unit","W","minimumInclusive",0),
   Map.of("name","minCoolingCapacityW","unit","W","minimumExclusive",0),
   Map.of("name","maxCoolingCapacityW","unit","W","minimumInclusive","minCoolingCapacityW"),
   Map.of("name","coolingCapacitySteps","unit","count","range","1..30"));}
 @Override public List<Map<String,Object>> generateCandidates(Request r){
  double conductivity=r.value("conductivityWmK"),area=r.value("areaM2"),deltaT=r.value("deltaTemperatureK");
  double thickness=r.value("thicknessM"),emissivity=r.value("emissivity"),radiatorT=r.value("radiatorTemperatureK");
  double ambientT=r.value("ambientTemperatureK"),heat=r.value("requiredHeatW");
  double min=r.value("minCoolingCapacityW"),max=r.value("maxCoolingCapacityW");
  int steps=steps(r.value("coolingCapacitySteps"));
  for(double v:new double[]{conductivity,area,deltaT,thickness,emissivity,radiatorT,ambientT,heat,min,max})
   if(!Double.isFinite(v))throw new IllegalArgumentException("Thermal inputs must be finite.");
  if(conductivity<=0||area<=0||deltaT<=0||thickness<=0||emissivity<0||emissivity>1||
     ambientT<0||radiatorT<=ambientT||heat<0||min<=0||max<min)
   throw new IllegalArgumentException("Invalid steady-state thermal search bounds.");
  List<Map<String,Object>> candidates=new ArrayList<>();
  for(int i=0;i<steps;i++){
   double capacity=steps==1?min:min+(max-min)*i/(steps-1d);
   Map<String,Object> candidate=new LinkedHashMap<>();
   candidate.put("coolingCapacityW",capacity);
   candidates.add(candidate);
  }
  return candidates;
 }
 @Override public Evaluation evaluate(Request r,Map<String,Object> candidate){
  double capacity=n(candidate,"coolingCapacityW");
  FeasibilityEngine.Thermal thermal=FeasibilityEngine.thermal(
    r.value("conductivityWmK"),r.value("areaM2"),r.value("deltaTemperatureK"),r.value("thicknessM"),
    r.value("emissivity"),r.value("radiatorTemperatureK"),r.value("ambientTemperatureK"),
    r.value("requiredHeatW"),capacity);
  boolean pass=FeasibilityEngine.ENG_OK.equals(thermal.status())&&Double.isFinite(thermal.marginW())&&thermal.marginW()>=0;
  Map<String,Object> metrics=new LinkedHashMap<>();
  metrics.put("coolingCapacityW",capacity);
  metrics.put("conductionW",thermal.conductionW());
  metrics.put("radiationW",thermal.radiationW());
  metrics.put("netRejectedW",thermal.netRejectedW());
  metrics.put("requiredHeatW",thermal.requiredHeatW());
  metrics.put("marginW",thermal.marginW());
  metrics.put("feasibilityClassification",thermal.status());
  metrics.put("unknowns",thermal.unknowns());
  metrics.put("screenStatus",pass?"WITHIN_STEADY_STATE_THERMAL_ENVELOPE":"OUTSIDE_THERMAL_ENVELOPE_OR_MISSING_DATA");
  Map<String,Object> checks=new LinkedHashMap<>();
  checks.put("coolingCapacitySupplied",capacity>0);
  checks.put("thermalMarginNonnegative",thermal.marginW()>=0);
  checks.put("thermalModelStatus",thermal.status());
  return new Evaluation(pass,metrics,checks);
 }
 @Override public String sortMetric(){return "coolingCapacityW";}
 @Override public Map<String,Object> searchSpace(Request r){
  return Map.of("coolingCapacityRangeW",List.of(r.value("minCoolingCapacityW"),r.value("maxCoolingCapacityW")),
    "coolingCapacitySteps",(int)r.value("coolingCapacitySteps"));
 }
 @Override public List<String> equations(){return List.of(
   "Q_conduction = k*A*deltaT/thickness",
   "Q_radiation = emissivity*sigma_SB*A*(T_radiator^4-T_ambient^4)",
   "coolingMargin = coolingCapacity-Q_conduction-Q_radiation-Q_required");}
 @Override public List<Map<String,Object>> sources(){return List.of(
   Map.of("type","built-in deterministic model","description","Uses Physics.conductionPower, Physics.radiativePower and the shared Stefan-Boltzmann constant; boundary conditions are user supplied."));}
 @Override public List<String> limitations(){return List.of(
   "Steady-state screening only; no transient response, 3D temperature field, thermal gradients, heat-pipe model, coolant flow, or control dynamics.",
   "Conductivity, geometry, emissivity, temperatures, heat load and cooling-capacity bounds are supplied inputs, not inferred or experimentally validated by this domain.",
   "The existing conduction-plus-radiation balance is used as implemented; passing is an envelope result, not radiator hardware validation or a safety certification.",
   "Material temperature dependence, contact resistance, view factors, shielding, mass, power consumption and manufacturing constraints are not modeled.");}
 @Override public Map<String,Object> resultDetails(Request r,List<Map<String,Object>> evaluated){
  if(evaluated.isEmpty())return Map.of();
  Map<String,Object> first=evaluated.get(0);
  double threshold=((Number)first.get("netRejectedW")).doubleValue()+r.value("requiredHeatW");
  return Map.of("minimumCoolingCapacityRequiredByThisModelW",threshold,
    "modelType","STEADY_STATE_SCREEN_ONLY");
 }
 private static int steps(double value){
  if(!Double.isFinite(value)||value<1||value>30||value!=Math.rint(value))
   throw new IllegalArgumentException("coolingCapacitySteps must be an integer from 1 to 30");
  return (int)value;
 }
 private static double n(Map<String,Object> map,String key){
  Object value=map.get(key);
  if(!(value instanceof Number number)||!Double.isFinite(number.doubleValue()))
   throw new IllegalArgumentException("candidate is missing finite "+key);
  return number.doubleValue();
 }
}
