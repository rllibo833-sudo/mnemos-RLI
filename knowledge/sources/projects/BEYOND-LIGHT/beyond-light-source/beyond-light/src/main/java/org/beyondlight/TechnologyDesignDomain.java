package org.beyondlight;

import java.util.*;

/** Domain contract consumed by the shared candidate search and Pareto engine. */
public interface TechnologyDesignDomain {
 enum Direction { MINIMIZE, MAXIMIZE }
 record Objective(String metric,Direction direction) {}
 record Request(Map<String,Double> inputs,Map<String,Object> context,MachineDesign.Assembly assembly) {
  public Request {
   inputs=Collections.unmodifiableMap(new LinkedHashMap<>(inputs));
   context=Collections.unmodifiableMap(new LinkedHashMap<>(context));
  }
  public double value(String name){Double v=inputs.get(name);if(v==null)throw new IllegalArgumentException("missing domain input: "+name);return v;}
 }
 record Evaluation(boolean feasible,Map<String,Object> metrics,Map<String,Object> checks) {
  public Evaluation {metrics=Collections.unmodifiableMap(new LinkedHashMap<>(metrics));checks=Collections.unmodifiableMap(new LinkedHashMap<>(checks));}
 }
 String id();
 String title();
 String model();
 List<Map<String,Object>> generateCandidates(Request request);
 Evaluation evaluate(Request request,Map<String,Object> candidate);
 List<Objective> objectives();
 List<Map<String,Object>> inputSchema();
 default String sortMetric(){return objectives().get(0).metric();}
 Map<String,Object> searchSpace(Request request);
 List<String> equations();
 List<Map<String,Object>> sources();
 List<String> limitations();
 default Map<String,Object> resultDetails(Request request,List<Map<String,Object>> evaluated){return Map.of();}
}
