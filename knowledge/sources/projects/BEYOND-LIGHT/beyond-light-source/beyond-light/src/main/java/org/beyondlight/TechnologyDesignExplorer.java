package org.beyondlight;

import java.util.*;

/** Compatibility facade for the ideal reaction-propulsion domain on the shared design engine. */
public final class TechnologyDesignExplorer {
 public record EmpiricalPerformanceConstraint(String predictor,double meanPowerW,double sdPowerW,
   double minPowerW,double maxPowerW,double interceptN,double slopePerStandardDeviation,
   double crossValidationRmseN,String modelEquation){}
 private TechnologyDesignExplorer(){}
 public static Map<String,Object> explore(double dryKg,double payloadKg,double deltaVMs,double maxPowerW,
   double maxHeatW,double maxDurationDays,MachineDesign.Assembly assembly){
  return explore(dryKg,payloadKg,deltaVMs,maxPowerW,maxHeatW,maxDurationDays,assembly,null);
 }
 public static Map<String,Object> explore(double dryKg,double payloadKg,double deltaVMs,double maxPowerW,
   double maxHeatW,double maxDurationDays,MachineDesign.Assembly assembly,EmpiricalPerformanceConstraint empirical){
  Map<String,Double> inputs=new LinkedHashMap<>();inputs.put("dryMassKg",dryKg);inputs.put("payloadKg",payloadKg);
  inputs.put("targetDeltaVMs",deltaVMs);inputs.put("availablePowerW",maxPowerW);
  inputs.put("coolingCapacityW",maxHeatW);inputs.put("maximumBurnDays",maxDurationDays);
  Map<String,Object> context=empirical==null?Map.of():Map.of("empiricalPerformanceConstraint",empirical);
  return TechnologyDesignEngine.explore(new ReactionPropulsionDomain(),new TechnologyDesignDomain.Request(inputs,context,assembly));
 }
}
