package org.beyondlight;

import java.util.*;

/** Ideal reaction-thruster implementation of the reusable technology-domain contract. */
public final class ReactionPropulsionDomain implements TechnologyDesignDomain {
 private static final double[] ISP={250,450,900,1500,3000,6000};
 private static final double[] EFF={.5,.7,.85,.95};
 private static final double[] DAYS={1,3,7,30,90,180};
 private static final List<Objective> OBJECTIVES=List.of(
   new Objective("propellantKg",Direction.MINIMIZE),new Objective("inputPowerW",Direction.MINIMIZE),
   new Objective("burnDurationDays",Direction.MINIMIZE));
 @Override public String id(){return "propulsion.reaction.ideal";}
 @Override public String title(){return "Eksplorasi desain pendorong reaksi ideal";}
 @Override public String model(){return "Persamaan roket ideal + pemeriksaan konsistensi + screening FeasibilityEngine";}
 @Override public List<Objective> objectives(){return OBJECTIVES;}
 @Override public List<Map<String,Object>> inputSchema(){return List.of(
   Map.of("name","dryMassKg","unit","kg","minimumExclusive",0),Map.of("name","payloadKg","unit","kg","minimumInclusive",0),
   Map.of("name","targetDeltaVMs","unit","m/s","minimumExclusive",0),Map.of("name","availablePowerW","unit","W","minimumExclusive",0),
   Map.of("name","coolingCapacityW","unit","W","minimumInclusive",0),Map.of("name","maximumBurnDays","unit","day","minimumExclusive",0));}
 @Override public String sortMetric(){return "inputPowerW";}
 @Override public List<Map<String,Object>> generateCandidates(Request r){
  double dry=r.value("dryMassKg"),payload=r.value("payloadKg"),dv=r.value("targetDeltaVMs"),power=r.value("availablePowerW"),heat=r.value("coolingCapacityW"),days=r.value("maximumBurnDays");
  for(double v:new double[]{dry,payload,dv,power,heat,days})if(!Double.isFinite(v))throw new IllegalArgumentException("All design limits must be finite.");
  if(dry<=0||payload<0||dv<=0||power<=0||heat<0||days<=0||dry>1e8||payload>1e8||dv>1e7||power>1e15||heat>1e15||days>36500)throw new IllegalArgumentException("Mission inputs are outside the bounded exploration range.");
  TreeSet<Double> durations=new TreeSet<>();for(double d:DAYS)if(d<=days)durations.add(d);durations.add(days);
  List<Map<String,Object>> candidates=new ArrayList<>();for(double isp:ISP)for(double efficiency:EFF)for(double duration:durations){Map<String,Object> c=new LinkedHashMap<>();c.put("specificImpulseS",isp);c.put("efficiency",efficiency);c.put("burnDurationDays",duration);candidates.add(c);}return candidates;
 }
 @Override public Evaluation evaluate(Request r,Map<String,Object> c){
  double dry=r.value("dryMassKg"),payload=r.value("payloadKg"),dv=r.value("targetDeltaVMs"),maxPower=r.value("availablePowerW"),maxHeat=r.value("coolingCapacityW");
  double isp=n(c,"specificImpulseS"),eta=n(c,"efficiency"),days=n(c,"burnDurationDays"),finalMass=dry+payload;
  double ve=isp*Core.G0,ratio=dv/ve;if(ratio>700)throw new IllegalArgumentException("rocket equation overflow limit");
  double prop=finalMass*Math.expm1(ratio),wet=finalMass+prop,duration=days*86400,mdot=prop/duration,thrust=mdot*ve,pkin=.5*mdot*ve*ve,pin=pkin/eta,heat=pin-pkin;
  if(!Double.isFinite(prop+wet+mdot+thrust+pkin+pin+heat))throw new IllegalArgumentException("nonfinite candidate result");
  Core.Propulsion cross=Core.propulsion(dry,payload,dv,isp,thrust,eta);
  FeasibilityEngine.Assessment assessment=FeasibilityEngine.assess("electric",dry,payload,dv,isp,thrust,eta,duration,maxPower,maxHeat,r.assembly());
  double massResidual=prop-cross.propellantKg(),momentumResidual=thrust-mdot*ve,energyResidual=pin-pkin-heat;
  boolean equationCheck=Math.abs(massResidual)<=1e-8*Math.max(1,prop)&&Math.abs(momentumResidual)<=1e-9*Math.max(1,thrust)&&Math.abs(energyResidual)<=1e-9*Math.max(1,pin);
  boolean powerPass=pin<=maxPower,heatPass=heat<=maxHeat,empiricalApplied=false,empiricalRangePass=true,empiricalPerformancePass=true;
  Map<String,Object> metrics=new LinkedHashMap<>();metrics.put("architecture","Idealized reaction thruster; performance envelope, no hardware geometry");
  metrics.put("propellantKg",prop);metrics.put("initialMassKg",wet);metrics.put("thrustN",thrust);metrics.put("massFlowKgS",mdot);metrics.put("exhaustVelocityMS",ve);metrics.put("inputPowerW",pin);metrics.put("idealizedWasteHeatW",heat);
  metrics.put("powerConstraintPass",powerPass);metrics.put("heatConstraintPass",heatPass);metrics.put("equationCrossChecksPass",equationCheck);
  metrics.put("feasibilityClassification",assessment.overallClassification());metrics.put("engineeringStage",assessment.engineering().status());
  Object raw=r.context().get("empiricalPerformanceConstraint");
  if(raw instanceof TechnologyDesignExplorer.EmpiricalPerformanceConstraint model){
   empiricalApplied=true;empiricalRangePass=pin>=model.minPowerW()&&pin<=model.maxPowerW();
   double prediction=model.interceptN()+model.slopePerStandardDeviation()*(pin-model.meanPowerW())/model.sdPowerW();
   double conservative=prediction-model.crossValidationRmseN();empiricalPerformancePass=empiricalRangePass&&Double.isFinite(conservative)&&conservative>=thrust;
   metrics.put("empiricalPowerRangePass",empiricalRangePass);metrics.put("empiricalPredictedThrustN",prediction);
   metrics.put("empiricalPredictedThrustMinusCvRmseN",conservative);metrics.put("empiricalPerformancePass",empiricalPerformancePass);
  }
  metrics.put("empiricalModelConstraintApplied",empiricalApplied);
  boolean feasible=powerPass&&heatPass&&equationCheck&&empiricalPerformancePass;
  metrics.put("screenStatus",feasible?"WITHIN_USER_ENVELOPE_SCREEN":"OUTSIDE_USER_ENVELOPE_OR_CHECK_FAILED");
  Map<String,Object> checks=new LinkedHashMap<>();checks.put("powerConstraintPass",powerPass);checks.put("heatConstraintPass",heatPass);checks.put("equationCrossChecksPass",equationCheck);checks.put("empiricalConstraintApplied",empiricalApplied);if(empiricalApplied){checks.put("empiricalPowerRangePass",empiricalRangePass);checks.put("empiricalPerformancePass",empiricalPerformancePass);}
  metrics.put("residuals",Map.of("propellantKg",massResidual,"momentumN",momentumResidual,"powerW",energyResidual));
  return new Evaluation(feasible,metrics,checks);
 }
 @Override public Map<String,Object> searchSpace(Request r){TreeSet<Double>d=new TreeSet<>();for(double x:DAYS)if(x<=r.value("maximumBurnDays"))d.add(x);d.add(r.value("maximumBurnDays"));return Map.of("sweptIspS",Arrays.stream(ISP).boxed().toList(),"sweptEfficiency",Arrays.stream(EFF).boxed().toList(),"durationChoicesDays",d);}
 @Override public List<String> equations(){return List.of("ve=Isp*g0","m_prop=m_final*(exp(deltaV/ve)-1)","F=mdot*ve","P_input=0.5*mdot*ve^2/efficiency");}
 @Override public List<Map<String,Object>> sources(){return List.of(Map.of("title","NASA Glenn — Ideal Rocket Equation","url","https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/ideal-rocket-equation/"));}
 @Override public List<String> limitations(){return List.of("Sweep parameters are hypothetical search bounds, not measured engine performance.","A passing candidate only satisfies selected idealized power/heat bounds and internal equation checks.","No chamber/nozzle geometry, materials stress, thermal gradients, control system, manufacturing, independent experiment, or prototype is validated.","The component assembly is assessed only at the level reported by the existing feasibility engine.");}
 @Override public Map<String,Object> resultDetails(Request r,List<Map<String,Object>> evaluated){Object raw=r.context().get("empiricalPerformanceConstraint");if(!(raw instanceof TechnologyDesignExplorer.EmpiricalPerformanceConstraint m))return Map.of();return Map.of("empiricalModelConstraintApplied",true,"empiricalModelPredictor",m.predictor(),"empiricalModelEquation",m.modelEquation(),"empiricalModelPowerRangeW",List.of(m.minPowerW(),m.maxPowerW()),"empiricalModelCvRmseN",m.crossValidationRmseN(),"empiricalModelPassCount",(int)evaluated.stream().filter(c->Boolean.TRUE.equals(c.get("empiricalPerformancePass"))).count());}
 private static double n(Map<String,Object>m,String k){return ((Number)m.get(k)).doubleValue();}
}
