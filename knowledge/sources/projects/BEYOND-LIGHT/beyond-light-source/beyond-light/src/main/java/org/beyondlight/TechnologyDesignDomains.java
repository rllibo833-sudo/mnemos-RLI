package org.beyondlight;

import java.util.*;

/** Registry of built-in domains supported by the shared technology design engine. */
public final class TechnologyDesignDomains {
 private static final List<TechnologyDesignDomain> DOMAINS=List.of(new ReactionPropulsionDomain(),new EnergyStorageDesignDomain(),new ThermalManagementDesignDomain(),new StructuralDesignDomain());
 private TechnologyDesignDomains(){}
 public static List<TechnologyDesignDomain> all(){return DOMAINS;}
 public static TechnologyDesignDomain require(String id){return DOMAINS.stream().filter(d->d.id().equals(id)).findFirst().orElseThrow(()->new IllegalArgumentException("unknown technology domain: "+id));}
 public static List<Map<String,Object>> catalog(){return DOMAINS.stream().map(d->{Map<String,Object>m=new LinkedHashMap<>();m.put("id",d.id());m.put("title",d.title());m.put("model",d.model());m.put("inputSchema",d.inputSchema());m.put("objectives",d.objectives().stream().map(o->Map.of("metric",o.metric(),"direction",o.direction().name())).toList());m.put("limitations",d.limitations());return m;}).toList();}
}
