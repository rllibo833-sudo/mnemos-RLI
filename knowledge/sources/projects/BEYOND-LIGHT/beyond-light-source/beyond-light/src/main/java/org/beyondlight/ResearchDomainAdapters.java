package org.beyondlight;

import java.time.Instant;
import java.util.*;

/**
 * Explicit adapters for the existing scientific, mathematical and engineering
 * modules. These are workflows over existing classes, not claims that every
 * source file is an independent research engine.
 */
public final class ResearchDomainAdapters {
    private ResearchDomainAdapters() {}

    public static void register(EngineRegistry registry) {
        registry.register(new CatalogValidation());
        registry.register(new SymbolicAnalysis());
        registry.register(new RelativityAnalysis());
        registry.register(new FeasibilityAnalysis());
        registry.register(new BenchmarkAnalysis());
        registry.register(new MaterialSelection());
        registry.register(new UncertaintyAnalysis());
        registry.register(new TechnologyDomainAnalysis());
        registry.register(new CrossDomainAnalysis());
        registry.register(new MetricGeometryAnalysis());
        registry.register(new EngineeringCalculation());
        registry.register(new OpenDataDiscovery());
    }

    private abstract static class Adapter implements ResearchEngine {
        protected Instant start;
        protected AnalysisResult result(ResearchRequest request, Map<String,Object> output,
                                        List<SourceRecord> sources, List<String> limits) {
            return new AnalysisResult(null, request.id(), id(), status(output), start, Instant.now(),
                    output, sources, limits, "");
        }
        protected String status(Map<String,Object> output) {
            return Objects.toString(output.getOrDefault("status", "COMPLETED"));
        }
        protected void begin() { start = Instant.now(); }
        protected Map<String,Object> context(ResearchRequest request) { return request.context(); }
        protected String text(Map<String,Object> c, String key) {
            Object value=c.get(key);
            if(value==null||value.toString().isBlank())throw new IllegalArgumentException("missing required context field: "+key);
            return value.toString();
        }
        protected double number(Map<String,Object> c,String key) {
            Object value=c.get(key);
            if(!(value instanceof Number n)||!Double.isFinite(n.doubleValue()))
                throw new IllegalArgumentException("missing or nonfinite numeric context field: "+key);
            return n.doubleValue();
        }
        protected double optional(Map<String,Object> c,String key,double fallback) {
            Object value=c.get(key);
            if(value==null)return fallback;
            if(!(value instanceof Number n)||!Double.isFinite(n.doubleValue()))
                throw new IllegalArgumentException(key+" must be a finite number");
            return n.doubleValue();
        }
        protected Map<String,Double> numericMap(Object raw,String label) {
            if(!(raw instanceof Map<?,?> map))throw new IllegalArgumentException(label+" must be a JSON object of numeric values");
            Map<String,Double> out=new LinkedHashMap<>();
            for(var entry:map.entrySet()) {
                if(!(entry.getValue() instanceof Number n)||!Double.isFinite(n.doubleValue()))
                    throw new IllegalArgumentException(label+"."+entry.getKey()+" must be finite numeric data");
                out.put(String.valueOf(entry.getKey()),n.doubleValue());
            }
            return out;
        }
        protected List<SourceRecord> sourceRecords(List<Map<String,Object>> values) {
            Map<String,SourceRecord> unique=new LinkedHashMap<>();
            for(Map<String,Object> value:values) {
                SourceRecord source=SourceRecord.fromMap(value);
                unique.putIfAbsent(source.id(),source);
            }
            return List.copyOf(unique.values());
        }
        protected List<String> limitations(String... values) { return List.of(values); }
    }

    private static final class CatalogValidation extends Adapter {
        public String id(){return "science.catalog-validation";}
        public boolean supports(ResearchRequest r){return "catalog-validation".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();
            Map<String,Object> validation=ScientificCatalog.validate();
            Map<String,Object> output=new LinkedHashMap<>(validation);
            output.put("catalogSummary",Map.of("constants",ScientificCatalog.constants().size(),
                    "equations",ScientificCatalog.equations().size(),
                    "technologyDomains",TechnologyDesignDomains.catalog().size()));
            List<Map<String,Object>> refs=new ArrayList<>();
            for(Map<String,Object> constant:ScientificCatalog.constants()) {
                Map<String,Object> ref=new LinkedHashMap<>();
                ref.put("id",constant.get("id"));ref.put("title","Scientific constant: "+constant.get("id"));
                ref.put("sourceType","scientific-constant-record");ref.put("provider",constant.get("source"));
                ref.put("url",constant.get("sourceUrl"));ref.put("verificationStatus",constant.get("verification"));
                refs.add(ref);
            }
            return result(r,output,sourceRecords(refs),limitations(
                    "Catalog validation checks metadata completeness, units and internal consistency; it is not an independent audit of the cited primary sources.",
                    "A PASS means the configured catalog passed its implemented checks, not that every scientific claim was experimentally verified."));
        }
    }

    private static final class SymbolicAnalysis extends Adapter {
        public String id(){return "mathematics.symbolic";}
        public boolean supports(ResearchRequest r){return "symbolic".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Object> c=context(r);
            String operation=Objects.toString(c.getOrDefault("operation","simplify"));
            String expression=text(c,"expression");
            String variable=Objects.toString(c.getOrDefault("variable","x"));
            String value=switch(operation) {
                case "simplify" -> Symbolic.simplifyText(expression);
                case "differentiate" -> Symbolic.derivative(expression,variable);
                case "integrate" -> Symbolic.integrate(expression,variable);
                case "substitute" -> Symbolic.substitute(expression,variable,text(c,"replacement"));
                case "evaluate" -> Double.toString(Symbolic.evaluate(expression,numericMap(c.get("values"),"values")));
                case "isolate" -> {
                    String[] sides=expression.split("=(?!=)",2);
                    if(sides.length!=2)throw new IllegalArgumentException("isolate expression must be lhs=rhs");
                    yield Symbolic.isolate(sides[0],sides[1],variable);
                }
                default -> throw new IllegalArgumentException("unsupported symbolic operation: "+operation);
            };
            Map<String,Object> out=new LinkedHashMap<>();
            out.put("status","SYMBOLIC_OPERATION_COMPLETED");out.put("operation",operation);
            out.put("inputExpression",expression);out.put("variable",variable);out.put("result",value);
            return result(r,out,List.of(),limitations(
                    "Symbolic output is limited to operations and expression forms implemented by the internal parser.",
                    "This operation does not establish that the supplied equation models a real physical system.",
                    "No external equation source, dimensional analysis or domain-specific validation is implied."));
        }
    }

    private static final class RelativityAnalysis extends Adapter {
        public String id(){return "physics.special-relativity";}
        public boolean supports(ResearchRequest r){return "relativity".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Object> c=context(r);
            Physics.Relativistic value=Physics.relativity(number(c,"massKg"),number(c,"velocityMs"),
                    optional(c,"elapsedTimeS",0),optional(c,"lengthM",0));
            Map<String,Object> out=new LinkedHashMap<>(Main.recordMap(value));
            out.put("status","RELATIVITY_MODEL_EVALUATED");
            out.put("model","Special relativity, inertial-frame constant-velocity calculation");
            List<Map<String,Object>> refs=ScientificCatalog.constants().stream()
                    .filter(x->"c".equals(x.get("id"))).toList();
            return result(r,out,sourceRecords(refs),limitations(
                    "The calculation assumes inertial frames and the supplied constant velocity.",
                    "It does not model acceleration, gravity, curved spacetime, measurement uncertainty or experimental apparatus."));
        }
    }

    private static final class FeasibilityAnalysis extends Adapter {
        public String id(){return "engineering.feasibility-assessment";}
        public boolean supports(ResearchRequest r){return "feasibility".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Object> c=context(r);
            FeasibilityEngine.Assessment assessment=FeasibilityEngine.assess(text(c,"propulsionFamily"),
                    number(c,"dryMassKg"),number(c,"payloadKg"),number(c,"deltaVMs"),number(c,"ispS"),
                    number(c,"thrustN"),number(c,"efficiency"),number(c,"durationS"),
                    number(c,"availablePowerW"),number(c,"coolingW"),Main.MACHINE.assemble());
            boolean benchmark=Boolean.TRUE.equals(c.get("numericalBenchmarksPassed"));
            boolean rawExperiment=Boolean.TRUE.equals(c.get("matchedRawExperimentalData"));
            FeasibilityClassification.Report classification=FeasibilityClassification.evaluate(assessment,benchmark,rawExperiment);
            Map<String,Object> out=new LinkedHashMap<>();
            out.put("status",assessment.overallClassification());
            out.put("assessment",Main.recordMap(assessment));
            out.put("evidenceClassification",Main.recordMap(classification));
            return result(r,out,List.of(),limitations(
                    "Feasibility labels apply only to the supplied propulsion family, assumptions and implemented checks.",
                    "Benchmark and raw experimental-data flags are caller assertions; this adapter does not independently verify those claims.",
                    "A passing engineering screen is not a safety certification, qualified design or proof of buildability."));
        }
    }

    private static final class BenchmarkAnalysis extends Adapter {
        public String id(){return "science.numerical-benchmarks";}
        public boolean supports(ResearchRequest r){return "benchmark".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Object> c=context(r);double tolerance=optional(c,"tolerance",Double.NaN);
            List<Map<String,Object>> runs=new ArrayList<>();
            String group=Objects.toString(c.getOrDefault("benchmarkGroup",""));
            if(!group.isBlank()) {
                List<BenchmarkEngine.Run> groupRuns=Double.isNaN(tolerance)
                        ?BenchmarkEngine.runGroup(group):BenchmarkEngine.runGroup(group,tolerance);
                for(BenchmarkEngine.Run run:groupRuns)runs.add(Main.recordMap(run));
            }
            else {
                String benchmarkId=text(c,"benchmarkId");
                BenchmarkEngine.Run run=Double.isNaN(tolerance)?BenchmarkEngine.run(benchmarkId)
                        :BenchmarkEngine.run(benchmarkId,tolerance);
                runs.add(Main.recordMap(run));
            }
            Map<String,Object> out=new LinkedHashMap<>();
            out.put("status",runs.stream().allMatch(x->"PASS".equals(x.get("status"))||"WITHIN_TOLERANCE".equals(x.get("status")))
                    ?"BENCHMARKS_PASSED":"BENCHMARK_RESULTS_RECORDED");
            out.put("runs",runs);out.put("runCount",runs.size());
            return result(r,out,List.of(),limitations(
                    "Benchmarks compare implemented numerical results with the reference values and tolerances recorded in the benchmark catalog.",
                    "Passing benchmark cases do not validate every engine path or establish physical correctness outside the benchmark cases.",
                    "Reference independence and source suitability must be reviewed for each benchmark definition."));
        }
    }

    private static final class MaterialSelection extends Adapter {
        public String id(){return "engineering.material-selection";}
        public boolean supports(ResearchRequest r){return "material-selection".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Double> requirements=numericMap(context(r).getOrDefault("requirements",Map.of()),"requirements");
            List<Map<String,Object>> selected=Main.MATS.select(requirements);
            Map<String,Object> out=new LinkedHashMap<>();out.put("status","MATERIAL_REQUIREMENTS_SCREENED");
            out.put("requirements",requirements);out.put("materials",selected);
            out.put("materialRecords",Main.MATS.all().stream().map(ScientificCatalog::materialRecord).toList());
            List<Map<String,Object>> refs=new ArrayList<>();
            for(MaterialDatabase.Material material:Main.MATS.all()){
                Map<String,Object> ref=new LinkedHashMap<>();ref.put("id",material.id());ref.put("title",material.name());
                ref.put("sourceType","material-property-record");ref.put("provider",material.source());
                ref.put("url",material.source().contains("https://")?material.source().substring(material.source().lastIndexOf("https://")):"");
                ref.put("verificationStatus",material.verification());refs.add(ref);
            }
            return result(r,out,sourceRecords(refs),limitations(
                    "Selection compares only supplied thresholds against available properties; missing properties remain unknown.",
                    "Material records may have grade, temperature, condition and traceability limitations; null values are not inferred.",
                    "A material match is not a design allowable, procurement approval or component qualification."));
        }
    }

    private static final class UncertaintyAnalysis extends Adapter {
        public String id(){return "science.uncertainty-analysis";}
        public boolean supports(ResearchRequest r){return "uncertainty".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Object> c=context(r);String mode=Objects.toString(c.getOrDefault("mode","propagate"));
            String expression=text(c,"expression");Map<String,Double> means=numericMap(c.get("means"),"means");
            Map<String,Object> out=new LinkedHashMap<>();out.put("mode",mode);out.put("expression",expression);
            switch(mode){
                case "propagate" -> {
                    Map<String,Double> sigma=numericMap(c.get("sigma"),"sigma");
                    Map<String,Double> correlations=c.containsKey("correlations")?numericMap(c.get("correlations"),"correlations"):Map.of();
                    out.put("result",Main.recordMap(Uncertainty.propagate(expression,means,sigma,correlations)));
                    out.put("status","UNCERTAINTY_PROPAGATED");
                }
                case "sensitivity" -> {out.put("result",Uncertainty.sensitivity(expression,means));out.put("status","SENSITIVITY_ANALYZED");}
                case "monte-carlo" -> {
                    Map<String,Double> sigma=numericMap(c.get("sigma"),"sigma");
                    int samples=(int)number(c,"samples");long seed=(long)optional(c,"seed",1);
                    out.put("result",Main.recordMap(Uncertainty.monteCarlo(expression,means,sigma,samples,seed)));
                    out.put("status","MONTE_CARLO_COMPLETED");
                }
                case "sweep" -> {
                    String variable=text(c,"variable");
                    out.put("result",Main.recordMap(Uncertainty.sweep(expression,means,variable,
                            number(c,"minimum"),number(c,"maximum"),(int)number(c,"points"))));
                    out.put("status","PARAMETER_SWEEP_COMPLETED");
                }
                default -> throw new IllegalArgumentException("uncertainty mode must be propagate, sensitivity, monte-carlo or sweep");
            }
            return result(r,out,List.of(),limitations(
                    "Uncertainty results depend on the supplied input distributions, standard deviations, correlations and model expression.",
                    "First-order propagation is a local linear approximation; Monte Carlo uses independent Gaussian perturbations unless the underlying method is extended.",
                    "Model-form uncertainty and unreported systematic errors are not automatically included."));
        }
    }

    private static final class TechnologyDomainAnalysis extends Adapter {
        public String id(){return "engineering.technology-domain";}
        public boolean supports(ResearchRequest r){return "technology-domain".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Object> c=context(r);String domainId=text(c,"domainId");
            Map<String,Double> inputs=numericMap(c.get("inputs"),"inputs");
            Map<String,Object> extra=c.get("domainContext") instanceof Map<?,?>?Json.map(c.get("domainContext")):Map.of();
            Map<String,Object> out=TechnologyDesignEngine.explore(TechnologyDesignDomains.require(domainId),
                    new TechnologyDesignDomain.Request(inputs,extra,Main.MACHINE.assemble()));
            return result(r,out,sourceRecords(sourceMaps(out.get("sources"))),limitations(
                    "Technology-domain results are bounded deterministic candidate screens, not validated hardware designs.",
                    "Required fields and assumptions are defined by the selected domain input schema.",
                    "Material properties, geometry, operating conditions and limits must be supported by suitable evidence supplied by the user."));
        }
    }

    private static final class CrossDomainAnalysis extends Adapter {
        public String id(){return "engineering.cross-domain-technology";}
        public boolean supports(ResearchRequest r){return "cross-domain-technology".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Double> inputs=numericMap(context(r).get("inputs"),"inputs");
            Map<String,Object> out=CrossDomainTechnologyResearch.explore(inputs,Main.MACHINE.assemble());
            return result(r,out,sourceRecords(sourceMaps(out.get("sources"))),limitations(
                    "Cross-domain coupling is sequential: energy storage, then thermal management, then structural screening.",
                    "Transferred variables are explicit model assumptions, not a fully coupled multiphysics solution.",
                    "The stages inherit the limitations of their component domain models and supplied input data."));
        }
    }

    private static final class OpenDataDiscovery extends Adapter {
        public String id(){return "research.open-data-discovery";}
        public boolean supports(ResearchRequest r){
            return r.question().length()>=3&&r.question().length()<=160;
        }
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p)throws Exception{
            begin();
            List<Map<String,Object>> records=OpenDataClient.search(r.question());
            List<Map<String,Object>> provenance=new ArrayList<>();
            for(Map<String,Object> record:records){
                Map<String,Object> source=new LinkedHashMap<>(record);
                source.put("id",record.get("recordId"));
                source.put("sourceType","repository-record-metadata");
                source.put("provider","Zenodo");
                source.put("publicationDate",record.get("year"));
                source.put("url",record.get("recordUrl"));
                source.put("verificationStatus","METADATA_ONLY_NOT_INDEPENDENTLY_VERIFIED");
                provenance.add(source);
            }
            Map<String,Object> out=new LinkedHashMap<>();
            out.put("status",records.isEmpty()?"NO_OPEN_RECORDS_FOUND":"OPEN_RECORD_METADATA_DISCOVERED");
            out.put("provider","Zenodo");out.put("records",records);out.put("recordCount",records.size());
            out.put("analysisMode","metadata discovery only; no CSV download or numeric screening");
            return result(r,out,sourceRecords(provenance),limitations(
                    "This route retrieves repository metadata and does not read or interpret full-text papers or dataset contents.",
                    "Search coverage is limited to the currently connected Zenodo API; an empty result is not evidence that no research exists.",
                    "Record metadata and links are not independently authenticated by this adapter; users must inspect the original source.",
                    "No specialist historical, philosophical, economic, sociological, chemical or biological reasoning engine is claimed."));
        }
    }

    private static final class MetricGeometryAnalysis extends Adapter {
        public String id(){return "physics.metric-geometry";}
        public boolean supports(ResearchRequest r){return "general-relativity".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Object> c=context(r);
            String operation=Objects.toString(c.getOrDefault("operation","analyze"));
            if(operation.equals("field-residual")){
                double[][] residual=Relativity.fieldEquationResidual(matrix(c.get("einsteinTensor"),"einsteinTensor"),
                        matrix(c.get("stressEnergyTensor"),"stressEnergyTensor"),number(c,"coupling"),
                        number(c,"lambda"),matrix(c.get("metricTensor"),"metricTensor"));
                return result(r,Map.of("status","FIELD_EQUATION_RESIDUAL_EVALUATED","residual",Main.jsonSafe(residual)),
                        List.of(),limitations("Residual evaluation checks supplied 4x4 tensors only; it does not derive them from a metric or source model."));
            }
            if(operation.equals("energy-conditions")){
                List<?> raw=list(c.get("pressuresJm3"),"pressuresJm3");
                if(raw.size()!=3)throw new IllegalArgumentException("pressuresJm3 must contain exactly three principal pressures");
                double[] pressures=new double[3];
                for(int i=0;i<3;i++){if(!(raw.get(i) instanceof Number n)||!Double.isFinite(n.doubleValue()))throw new IllegalArgumentException("pressuresJm3 values must be finite");pressures[i]=n.doubleValue();}
                return result(r,Main.recordMap(FeasibilityEngine.diagonalEnergyConditions(number(c,"rhoJm3"),pressures)),
                        List.of(),limitations("This is a diagonal orthonormal-frame energy-condition screen, not a stress-energy tensor derived from a metric."));
            }
            double[] x=vector(c.get("coordinates"),"coordinates",4);
            String model=text(c,"model");
            Relativity.Metric metric=switch(model){
                case "minkowski" -> Relativity::minkowski;
                case "schwarzschild" -> point -> Relativity.schwarzschild(number(c,"massKg"),point);
                case "alcubierre" -> point -> Relativity.alcubierre(number(c,"beta"),number(c,"radiusM"),number(c,"sigma"),point);
                case "morris-thorne" -> point -> Relativity.morrisThorne(number(c,"throatM"),point);
                default -> throw new IllegalArgumentException("model must be minkowski, schwarzschild, alcubierre or morris-thorne");
            };
            double step=optional(c,"step",1e-3);
            Map<String,Object> out=new LinkedHashMap<>();out.put("model",model);out.put("operation",operation);
            List<SourceRecord> sources=List.of();
            switch(operation){
                case "diagnose" -> {out.put("result",Main.recordMap(Relativity.diagnose(metric,x)));out.put("status","METRIC_SIGNATURE_DIAGNOSED");}
                case "convergence" -> {out.put("result",Main.recordMap(Relativity.convergence(metric,x,step)));out.put("status","METRIC_CONVERGENCE_SCREENED");}
                case "analyze" -> {out.put("result",Main.recordMap(Relativity.analyze(metric,x,step)));out.put("status","METRIC_CURVATURE_ANALYZED");}
                case "stress-energy" -> {
                    Relativity.Result curvature=Relativity.analyze(metric,x,step);
                    out.put("curvature",Main.recordMap(curvature));
                    out.put("result",Main.recordMap(Relativity.requiredStressEnergy(curvature,
                            optional(c,"cosmologicalLambdaPerM2",0),optional(c,"toleranceJm3",1e-9))));
                    out.put("status","REQUIRED_STRESS_ENERGY_SCREENED");
                    Map<String,Object> ref=Map.of("id","doi:10.1002/andp.19163540702","title","Einstein field equations (1916)",
                            "sourceType","foundational-theory-paper","provider","Annalen der Physik",
                            "doi","10.1002/andp.19163540702","url","https://doi.org/10.1002/andp.19163540702",
                            "verificationStatus","BIBLIOGRAPHIC_REFERENCE_NOT_INDEPENDENTLY_REVIEWED");
                    sources=sourceRecords(List.of(ref));
                }
                default -> throw new IllegalArgumentException("operation must be analyze, diagnose, convergence, stress-energy, field-residual or energy-conditions");
            }
            return result(r,out,sources,limitations(
                    "Metric curvature is computed numerically by finite differences and depends on coordinate scaling and the supplied step size.",
                    "Metric ansatz selection does not establish that a spacetime solution is physically realizable or sourced by available matter.",
                    "The diagonal stress-energy/energy-condition reduction rejects unsupported off-diagonal cases; it is not a general tensor-frame solver.",
                    "No exotic matter, propulsion mechanism or buildable device is implied by a mathematical metric calculation."));
        }
    }

    private static final class EngineeringCalculation extends Adapter {
        public String id(){return "engineering.calculation";}
        public boolean supports(ResearchRequest r){return "engineering-calculation".equals(r.context().get("workflow"));}
        public AnalysisResult execute(ResearchRequest r,ResearchPlan p){
            begin();Map<String,Object> c=context(r);String operation=text(c,"operation");
            Map<String,Object> out=new LinkedHashMap<>();out.put("operation",operation);
            switch(operation){
                case "stress" -> out.put("result",Main.recordMap(FeasibilityEngine.stress(number(c,"tensileN"),
                        number(c,"compressiveN"),number(c,"shearN"),number(c,"areaM2"),number(c,"shearAreaM2"),
                        number(c,"lengthM"),number(c,"youngPa"),optional(c,"yieldPa",0),number(c,"safetyFactor"))));
                case "electrical" -> out.put("result",Main.recordMap(FeasibilityEngine.electrical(number(c,"voltageV"),
                        number(c,"currentA"),number(c,"resistanceOhm"),number(c,"durationS"))));
                case "thermal" -> out.put("result",Main.recordMap(FeasibilityEngine.thermal(number(c,"conductivityWmK"),
                        number(c,"areaM2"),number(c,"deltaTemperatureK"),number(c,"thicknessM"),number(c,"emissivity"),
                        number(c,"temperatureK"),number(c,"ambientK"),number(c,"requiredHeatW"),number(c,"coolingW"))));
                case "buckling" -> out.put("criticalLoadN",FeasibilityEngine.eulerBucklingLoad(number(c,"youngPa"),
                        number(c,"secondMomentM4"),number(c,"lengthM"),number(c,"effectiveLengthFactor")));
                case "energy-storage" -> out.put("result",Main.recordMap(FeasibilityEngine.assessEnergyStorage(
                        number(c,"energyJ"),number(c,"energyDensityJkg"),number(c,"efficiency"))));
                case "pressure-hoop" -> out.put("hoopStressPa",FeasibilityEngine.pressureHoopStress(number(c,"pressurePa"),
                        number(c,"radiusM"),number(c,"wallM")));
                case "thermal-expansion" -> out.put("expansionM",FeasibilityEngine.thermalExpansion(number(c,"alphaPerK"),
                        number(c,"lengthM"),number(c,"deltaK")));
                default -> throw new IllegalArgumentException("unsupported engineering calculation: "+operation);
            }
            out.put("status","ENGINEERING_CALCULATION_COMPLETED");
            List<Map<String,Object>> refs=operation.equals("thermal")?ScientificCatalog.constants().stream()
                    .filter(x->"sigma_SB".equals(x.get("id"))).toList():List.of();
            return result(r,out,sourceRecords(refs),limitations(
                    "Calculations use the assumptions and validity limits of the selected formula in FeasibilityEngine.",
                    "Missing yield strength, material properties, geometry, boundary conditions or load cases are not inferred.",
                    "A numerical result is not a component qualification, safety certification or validated design."));
        }
    }

    private static double[] vector(Object raw,String label,int expected){
        List<?> values=list(raw,label);
        if(values.size()!=expected)throw new IllegalArgumentException(label+" must contain exactly "+expected+" numeric values");
        double[] out=new double[expected];
        for(int i=0;i<expected;i++){
            if(!(values.get(i) instanceof Number n)||!Double.isFinite(n.doubleValue()))
                throw new IllegalArgumentException(label+" values must be finite numbers");
            out[i]=n.doubleValue();
        }
        return out;
    }
    private static List<?> list(Object raw,String label){
        if(!(raw instanceof List<?> values))throw new IllegalArgumentException(label+" must be a JSON array");
        return values;
    }
    private static double[][] matrix(Object raw,String label){
        List<?> rows=list(raw,label);
        if(rows.size()!=4)throw new IllegalArgumentException(label+" must be a 4x4 matrix");
        double[][] out=new double[4][4];
        for(int i=0;i<4;i++)out[i]=vector(rows.get(i),label+" row "+i,4);
        return out;
    }

    private static List<Map<String,Object>> sourceMaps(Object raw) {
        if(!(raw instanceof List<?> list))return List.of();
        List<Map<String,Object>> out=new ArrayList<>();
        for(Object item:list)if(item instanceof Map<?,?>)out.add(Json.map(item));
        return out;
    }
}
