package org.beyondlight;

import java.time.Instant;
import java.util.*;

/** Shared orchestration, screening, Pareto ranking, and report envelope for design domains. */
public final class TechnologyDesignEngine {
 private TechnologyDesignEngine() {}

 public static Map<String,Object> explore(TechnologyDesignDomain domain,TechnologyDesignDomain.Request request) {
  List<Map<String,Object>> all=new ArrayList<>(),passing=new ArrayList<>();int invalid=0;
  for(Map<String,Object> proposal:domain.generateCandidates(request)) {
   try {
    TechnologyDesignDomain.Evaluation evaluation=domain.evaluate(request,proposal);
    Map<String,Object> candidate=new LinkedHashMap<>(proposal);
    candidate.putAll(evaluation.metrics());
    candidate.put("candidateFeasible",evaluation.feasible());
    candidate.put("assessmentChecks",evaluation.checks());
    all.add(candidate);
    if(evaluation.feasible())passing.add(candidate);
   } catch(RuntimeException ex) {invalid++;}
  }
  List<Map<String,Object>> pareto=new ArrayList<>();
  for(Map<String,Object> a:passing){boolean dominated=false;for(Map<String,Object>b:passing)if(a!=b&&dominates(b,a,domain.objectives())){dominated=true;break;}if(!dominated)pareto.add(a);}
  pareto.sort(Comparator.comparingDouble(a->objectiveValue(a,domain.sortMetric())));
  if(pareto.size()>20)pareto=new ArrayList<>(pareto.subList(0,20));
  Map<String,Object> result=new LinkedHashMap<>();
  result.put("status",passing.isEmpty()?"NO_DESIGN_WITHIN_GIVEN_ENVELOPE":"CANDIDATE_DESIGNS_WITHIN_MODEL_ENVELOPE");
  result.put("domainId",domain.id());result.put("candidatesEvaluated",all.size());
  result.put("invalidOrUnsolvableCandidates",invalid);result.put("withinEnvelope",passing.size());
  result.put("paretoCandidates",pareto);result.put("allCandidates",all);
  result.putAll(domain.resultDetails(request,all));
  Map<String,Object> out=new LinkedHashMap<>();out.put("id",UUID.randomUUID().toString());out.put("date",Instant.now().toString());
  out.put("recordType","TECHNOLOGY_DESIGN_EXPLORATION");out.put("category","research");
  out.put("title",domain.title());out.put("model",domain.model());
  Map<String,Object> inputs=new LinkedHashMap<>(request.inputs());inputs.put("searchSpace",domain.searchSpace(request));out.put("inputs",inputs);
  out.put("result",result);out.put("inputSchema",domain.inputSchema());out.put("sources",domain.sources());out.put("equations",domain.equations());
  out.put("status",passing.isEmpty()?"NO_CANDIDATE_IN_SCREENED_ENVELOPE":"MODEL_SCREEN_ONLY_NOT_A_VALIDATED_DESIGN");
  out.put("limitations",domain.limitations());out.put("objectives",domain.objectives().stream().map(o->Map.of("metric",o.metric(),"direction",o.direction().name())).toList());
  return out;
 }

 private static boolean dominates(Map<String,Object>a,Map<String,Object>b,List<TechnologyDesignDomain.Objective> objectives){
  boolean strictly=false;
  for(var o:objectives){double av=objectiveValue(a,o.metric()),bv=objectiveValue(b,o.metric());if(o.direction()==TechnologyDesignDomain.Direction.MINIMIZE){if(av>bv)return false;if(av<bv)strictly=true;}else{if(av<bv)return false;if(av>bv)strictly=true;}}
  return strictly;
 }
 private static double objectiveValue(Map<String,Object> candidate,String metric){Object v=candidate.get(metric);if(!(v instanceof Number n)||!Double.isFinite(n.doubleValue()))throw new IllegalStateException("candidate is missing finite objective "+metric);return n.doubleValue();}
}
