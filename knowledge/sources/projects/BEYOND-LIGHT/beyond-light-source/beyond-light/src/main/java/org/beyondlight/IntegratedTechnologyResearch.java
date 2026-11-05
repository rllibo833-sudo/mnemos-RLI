package org.beyondlight;

import java.time.Instant;
import java.util.*;

/** Uses a narrowly qualified data-derived thrust/power pattern to constrain design candidates. */
public final class IntegratedTechnologyResearch {
 private IntegratedTechnologyResearch() {}
 private record ModelUse(TechnologyDesignExplorer.EmpiricalPerformanceConstraint constraint,
                         Map<String,Object> report) {}

 public static Map<String,Object> explore(DataRepository.Dataset dataset,String target,String powerVariable,
   double dryKg,double payloadKg,double deltaVMs,double maxPowerW,double maxHeatW,
   double maxDurationDays,MachineDesign.Assembly assembly) {
  Map<String,Object> model=AutonomousModelExplorer.explore(dataset,target);
  ModelUse use=qualifyModel(dataset,target,powerVariable,model);
  Map<String,Object> design=TechnologyDesignExplorer.explore(dryKg,payloadKg,deltaVMs,
    maxPowerW,maxHeatW,maxDurationDays,assembly,use.constraint());

  Map<String,Object> result=new LinkedHashMap<>();
  result.put("status","INTEGRATED_MODEL_DESIGN_FEASIBILITY_SCREEN_COMPLETE");
  result.put("modelExploration",model);
  result.put("modelApplication",use.report());
  result.put("designExploration",design);
  Map<String,Object> designResult=Json.map(design.get("result"));
  result.put("candidatesEvaluated",designResult.get("candidatesEvaluated"));
  result.put("candidatesWithinEnvelope",designResult.get("withinEnvelope"));
  result.put("feasibilityEngineAppliedPerCandidate",true);
  result.put("empiricalConstraintApplied",use.constraint()!=null);

  Map<String,Object> out=new LinkedHashMap<>();
  out.put("id",UUID.randomUUID().toString());
  out.put("date",Instant.now().toString());
  out.put("recordType","INTEGRATED_TECHNOLOGY_RESEARCH");
  out.put("category","research");
  out.put("title","Riset terpadu model, desain, dan kelayakan: "+dataset.filename());
  out.put("model","AutonomousModelExplorer → gated empirical power/performance constraint → TechnologyDesignExplorer → FeasibilityEngine");
  out.put("inputs",Map.of("datasetId",dataset.id(),"filename",dataset.filename(),"target",target,
    "powerVariable",powerVariable,"dryMassKg",dryKg,"payloadKg",payloadKg,"targetDeltaVMs",deltaVMs,
    "availablePowerW",maxPowerW,"coolingCapacityW",maxHeatW,"maximumBurnDays",maxDurationDays));
  out.put("result",result);
  out.put("sources",List.of(Map.of("datasetId",dataset.id(),"filename",dataset.filename(),
    "source",dataset.source(),"author",dataset.author(),"year",dataset.year(),"doi",dataset.doi())));
  out.put("equations",List.of("Empirical thrust estimate = fitted intercept + fitted slope × standardized input power.",
    "Candidate thrust is screened against the estimate minus one internal cross-validation RMSE."));
  out.put("status",use.constraint()==null?"DESIGN_SCREEN_RUN_MODEL_NOT_QUALIFIED_FOR_PARAMETER_USE":"DATA_DERIVED_DESIGN_CONSTRAINT_APPLIED_MODEL_SCREEN_ONLY");
  out.put("limitations",List.of(
    "A gated data-derived relationship is used only as an empirical screening constraint; it is not treated as a physical law or causal relation.",
    "The gate uses dataset units, sample count, a one-variable linear form, positive slope, and internal cross-validation against a constant baseline.",
    "Design points outside the measured power range are rejected when the constraint is active; no extrapolation is made.",
    "Cross-validation reuses one dataset and its RMSE is not a statistical confidence bound; independent validation and hardware testing remain necessary."));
  return out;
 }

 private static ModelUse qualifyModel(DataRepository.Dataset dataset,String target,String powerVariable,Map<String,Object> exploration) {
  List<String> failures=new ArrayList<>();
  if(powerVariable==null||powerVariable.isBlank())failures.add("powerVariable must explicitly map a dataset column to available input power");
  Map<String,String> units=units(dataset.units());
  if(!"N".equals(units.get(target)))failures.add("target column must declare unit N (thrust)");
  if(powerVariable==null||!"W".equals(units.get(powerVariable)))failures.add("power predictor must declare unit W; implicit unit conversion is disabled");
  if(dataset.rows()<20)failures.add("at least 20 dataset rows are required for empirical design use");
  int powerIndex=Arrays.asList(dataset.variables().split(",")).indexOf(powerVariable);
  if(powerIndex<0)failures.add("powerVariable is not a dataset column");
  double min=Double.POSITIVE_INFINITY,max=Double.NEGATIVE_INFINITY;
  try {
   List<List<String>> rows;
   if(dataset.format().equals("csv")){List<List<String>> table=DataRepository.csv(dataset.raw());rows=table.subList(1,table.size());}
   else {Map<String,Object> json=Json.map(Json.parse(dataset.raw()));rows=new ArrayList<>();for(Object row:(List<?>)json.get("rows")){List<String> values=new ArrayList<>();for(Object v:(List<?>)row)values.add(String.valueOf(v));rows.add(values);}}
   if(powerIndex>=0)for(List<String> row:rows){double v=Double.parseDouble(row.get(powerIndex));min=Math.min(min,v);max=Math.max(max,v);}
  } catch(RuntimeException ex){failures.add("could not determine observed power range from dataset");}
  Map<String,Object> modelResult=Json.map(exploration.get("result"));
  Object rawModels=modelResult.get("bestModels");
  Map<String,Object> selected=null;
  if(rawModels instanceof List<?> models)for(Object raw:models){
   Map<String,Object> candidate=Json.map(raw);
   if(!validLinearPowerModel(candidate,powerVariable))continue;
   selected=candidate;break;
  }
  if(selected==null)failures.add("no one-term linear model using only the selected power column was found");
  double intercept=Double.NaN,slope=Double.NaN,mean=Double.NaN,sd=Double.NaN,cv=Double.NaN,baseline=Double.NaN;
  String equation="";
  if(selected!=null){
   List<?> coefficients=(List<?>)selected.get("coefficients");
   if(coefficients.size()==2){intercept=((Number)coefficients.get(0)).doubleValue();slope=((Number)coefficients.get(1)).doubleValue();}
   Map<String,Object> normalization=Json.map(Json.map(exploration.get("inputs")).get("normalization"));
   List<?> pair=(List<?>)normalization.get(powerVariable);
   if(pair!=null&&pair.size()==2){mean=((Number)pair.get(0)).doubleValue();sd=((Number)pair.get(1)).doubleValue();}
   cv=number(selected.get("crossValidationRmse"));baseline=number(selected.get("trainingMeanBaselineRmse"));
   equation=Objects.toString(selected.get("equation"),"");
   if(!Boolean.TRUE.equals(selected.get("beatsInternalBaseline"))||!Double.isFinite(cv)||!Double.isFinite(baseline)||baseline<=0||(baseline-cv)/baseline<.10)
    failures.add("cross-validation must beat the constant baseline by at least 10 percent");
   if(!Double.isFinite(slope)||slope<=0)failures.add("fitted thrust must increase with power in this screen");
   if(!Double.isFinite(intercept)||!Double.isFinite(mean)||!Double.isFinite(sd)||sd<=0)failures.add("model coefficients and power normalization must be finite with nonzero spread");
   if(!Double.isFinite(min)||!Double.isFinite(max)||max<=min)failures.add("observed power range must be finite and nonzero");
   if(Double.isFinite(intercept)&&Double.isFinite(slope)&&Double.isFinite(mean)&&Double.isFinite(sd)&&Double.isFinite(cv)&&sd>0&&Double.isFinite(min)&&Double.isFinite(max)){
    double lowest=intercept+slope*(min-mean)/sd-cv;
    if(lowest<=0)failures.add("predicted thrust minus cross-validation RMSE must remain positive across observed power range");
   }
  }
  TechnologyDesignExplorer.EmpiricalPerformanceConstraint constraint=failures.isEmpty()&&selected!=null
    ?new TechnologyDesignExplorer.EmpiricalPerformanceConstraint(powerVariable,mean,sd,min,max,intercept,slope,cv,equation):null;
  Map<String,Object> report=new LinkedHashMap<>();
  report.put("status",constraint==null?"NOT_APPLIED_MODEL_GATE_FAILED":"APPLIED_AS_EMPIRICAL_SCREENING_CONSTRAINT");
  report.put("applied",constraint!=null);
  report.put("checks",Map.of("explicitPowerColumnMapping",powerVariable!=null&&!powerVariable.isBlank(),
    "targetUnitIsNewton", "N".equals(units.get(target)),
    "predictorUnitIsWatt", powerVariable!=null&&"W".equals(units.get(powerVariable)),
    "minimumRowsPassed",dataset.rows()>=20,
    "oneTermLinearPowerModelFound",selected!=null,
    "crossValidationPassed",selected!=null&&Boolean.TRUE.equals(selected.get("beatsInternalBaseline"))&&Double.isFinite(cv)&&Double.isFinite(baseline)&&baseline>0&&(baseline-cv)/baseline>=.10,
    "positiveSlope",Double.isFinite(slope)&&slope>0,
    "observedPowerRangeAvailable",Double.isFinite(min)&&Double.isFinite(max)&&max>min));
  report.put("reasons",failures);
  report.put("selectedEquation",selected==null?null:equation);
  if(selected!=null){report.put("crossValidationRmseN",cv);report.put("constantBaselineRmseN",baseline);report.put("observedPowerRangeW",Double.isFinite(min)&&Double.isFinite(max)?List.of(min,max):List.of());}
  report.put("interpretation","Exploratory empirical screen only; correlation is not promoted to a physical law.");
  return new ModelUse(constraint,report);
 }

 private static boolean validLinearPowerModel(Map<String,Object> model,String powerVariable) {
  if(powerVariable==null||powerVariable.isBlank())return false;
  Object definitions=model.get("termDefinitions");
  if(!(definitions instanceof List<?> list)||list.size()!=1)return false;
  Map<String,Object> term=Json.map(list.get(0));
  return "linear".equals(term.get("kind"))&&List.of(powerVariable).equals(term.get("columns"));
 }
 private static double number(Object x){return x instanceof Number n?n.doubleValue():Double.NaN;}
 private static Map<String,String> units(String raw){Map<String,String> out=new HashMap<>();for(String pair:raw.split(",")){String[] p=pair.trim().split(":",2);if(p.length==2)out.put(p[0].trim(),p[1].trim());}return out;}
}
