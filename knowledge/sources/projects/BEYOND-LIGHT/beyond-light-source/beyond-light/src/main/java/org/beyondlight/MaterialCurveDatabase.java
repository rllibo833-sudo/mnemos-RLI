package org.beyondlight;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Provenance-preserving material curves. Evaluations are forbidden beyond the measured-data range. */
public final class MaterialCurveDatabase {
    public record Evaluation(String curveId, String materialId, String property, double temperatureK,
                             double value, String unit, String method, String evidenceType,
                             double dataMinK, double dataMaxK, Double fitErrorPct, String source,
                             String status, String limitations) {}
    private final Path path;
    public MaterialCurveDatabase(Path path) { this.path = path; }

    public List<Map<String,Object>> all() {
        try {
            List<Map<String,Object>> out = new ArrayList<>();
            if (Files.exists(path)) for (String line : Files.readAllLines(path)) if (!line.isBlank()) out.add(Json.map(Json.parse(line)));
            return List.copyOf(out);
        } catch (IOException e) { throw new IllegalStateException("material curve archive read failed", e); }
    }

    public Evaluation evaluate(String id, double temperatureK) {
        if (!Double.isFinite(temperatureK) || temperatureK <= 0) throw new IllegalArgumentException("temperature must be finite and > 0 K");
        Map<String,Object> c = all().stream().filter(v -> Objects.equals(v.get("id"), id)).findFirst().orElseThrow(() -> new IllegalArgumentException("material curve not found: " + id));
        double min=num(c,"dataMinK"), max=num(c,"dataMaxK");
        if (temperatureK < min || temperatureK > max) throw new IllegalArgumentException("temperature outside source data range ["+min+", "+max+"] K; extrapolation is disabled");
        if(!str(c,"axis").isBlank()&&!str(c,"axis").equals("temperature")) throw new IllegalArgumentException("curve is not temperature-dependent; use evaluateAt(x)");
        String kind=str(c,"kind"), unit=str(c,"propertyUnit"), method=kind;
        double value;
        if (kind.equals("NIST_LOG10_POLYNOMIAL")) {
            double x=Math.log10(temperatureK), power=1, sum=0;
            for (Object a:list(c,"coefficients")) { sum += ((Number)a).doubleValue()*power; power*=x; }
            value=Math.pow(10,sum); method="NIST fit: log10(y)=Σ ai·log10(T)^i";
        } else if (kind.equals("NIST_POLYNOMIAL")) {
            double x=temperatureK, sum=0, power=1;
            for (Object a:list(c,"coefficients")) { sum += ((Number)a).doubleValue()*power; power*=x; }
            value=sum; method="NIST fit: y=Σ ai·T^i";
            if (c.get("lowTemperatureK") instanceof Number low && temperatureK < low.doubleValue()) value=num(c,"lowTemperatureValue");
        } else if (kind.equals("POINTS_LINEAR")) {
            List<Object> pts=list(c,"points");
            double t0=((Number)Json.map(pts.get(0)).get("temperatureK")).doubleValue();
            double tN=((Number)Json.map(pts.get(pts.size()-1)).get("temperatureK")).doubleValue();
            if (temperatureK<t0 || temperatureK>tN) throw new IllegalArgumentException("temperature outside stored point range ["+t0+", "+tN+"] K; extrapolation is disabled");
            value=Double.NaN;
            for(int i=1;i<pts.size();i++){Map<String,Object>a=Json.map(pts.get(i-1)),b=Json.map(pts.get(i));double ta=num(a,"temperatureK"),tb=num(b,"temperatureK");if(temperatureK<=tb){double ya=num(a,"value"),yb=num(b,"value");value=ya+(yb-ya)*(temperatureK-ta)/(tb-ta);break;}}
            method="piecewise linear interpolation between stored source points";
        } else throw new IllegalArgumentException("unsupported curve kind: "+kind);
        if (!Double.isFinite(value)) throw new IllegalArgumentException("curve evaluation is non-finite");
        Double error=c.get("fitErrorPct") instanceof Number n?n.doubleValue():null;
        return new Evaluation(id,str(c,"materialId"),str(c,"property"),temperatureK,value,unit,method,str(c,"evidenceType"),min,max,error,str(c,"source"),"EVALUATED_WITHIN_SOURCE_DATA_RANGE",str(c,"limitations"));
    }

    /** Generic x-axis point-curve interpolation, e.g. stress versus strain; no extrapolation. */
    public Map<String,Object> evaluateAt(String id,double x) {
        Map<String,Object> c=all().stream().filter(v->Objects.equals(v.get("id"),id)).findFirst().orElseThrow(()->new IllegalArgumentException("material curve not found: "+id));
        if(Objects.toString(c.get("kind"),"").equals("POINTS_LINEAR")) {
            String axis=Objects.toString(c.get("axis"),"temperature"), key=axis.equals("temperature")?"temperatureK":"x";
            List<Object> pts=list(c,"points");double first=num(Json.map(pts.get(0)),key),last=num(Json.map(pts.get(pts.size()-1)),key);
            if(!Double.isFinite(x)||x<first||x>last)throw new IllegalArgumentException("x outside source point range ["+first+", "+last+"]; extrapolation is disabled");
            double value=Double.NaN;for(int i=1;i<pts.size();i++){Map<String,Object>a=Json.map(pts.get(i-1)),b=Json.map(pts.get(i));double xa=num(a,key),xb=num(b,key);if(x<=xb){value=num(a,"value")+(num(b,"value")-num(a,"value"))*(x-xa)/(xb-xa);break;}}
            Map<String,Object> out=new LinkedHashMap<>();out.put("curveId",id);out.put("materialId",c.get("materialId"));out.put("property",c.get("property"));out.put("x",x);out.put("axis",axis);out.put("axisUnit",c.getOrDefault("axisUnit","K"));out.put("value",value);out.put("propertyUnit",c.get("propertyUnit"));out.put("method","piecewise linear interpolation between stored source points");out.put("evidenceType",c.get("evidenceType"));out.put("source",c.get("source"));out.put("status","INTERPOLATED_WITHIN_SOURCE_POINT_RANGE");out.put("uncertainty",c.get("uncertainty"));return out;
        }
        if(!str(c,"kind").startsWith("NIST_"))throw new IllegalArgumentException("unsupported curve kind");
        Map<String,Object> out=new LinkedHashMap<>(Main.recordMap(evaluate(id,x)));out.put("x",x);out.put("axis","temperature");out.put("axisUnit","K");return out;
    }

    /** Adds source point observations. Points must be ordered, finite and have no duplicate temperatures. */
    public Map<String,Object> addPointCurve(Map<String,Object> input) {
        for(String k:List.of("id","materialId","property","propertyUnit","source","conditions","uncertainty","limitations")) if(Objects.toString(input.get(k),"").isBlank()) throw new IllegalArgumentException("curve field required: "+k);
        if(!Objects.toString(input.get("source"),"").startsWith("https://")) throw new IllegalArgumentException("curve source must be an HTTPS reference");
        List<Object> points=list(input,"points"); if(points.size()<2) throw new IllegalArgumentException("at least two source points required");
        String axis=Objects.toString(input.getOrDefault("axis","temperature"),"temperature"),axisUnit=Objects.toString(input.getOrDefault("axisUnit","K"),"K");if(axis.isBlank()||axisUnit.isBlank())throw new IllegalArgumentException("axis name and unit required");String key=axis.equals("temperature")?"temperatureK":"x";
        double prev=Double.NEGATIVE_INFINITY;
        for(Object o:points){Map<String,Object> p=Json.map(o);double x=num(p,key),v=num(p,"value");if(!Double.isFinite(x)||!Double.isFinite(v)||x<=prev)throw new IllegalArgumentException("points must be finite and strictly increasing on axis "+axis);prev=x;}
        Map<String,Object> c=new LinkedHashMap<>(input);c.put("kind","POINTS_LINEAR");c.put("axis",axis);c.put("axisUnit",axisUnit);c.put("evidenceType","SOURCE_POINT_DATA");c.put("dataMinK",axis.equals("temperature")?num(Json.map(points.get(0)),key):null);c.put("dataMaxK",axis.equals("temperature")?prev:null);c.put("xMin",axis.equals("temperature")?null:num(Json.map(points.get(0)),key));c.put("xMax",axis.equals("temperature")?null:prev);c.put("retrievedOn","2026-11-03");
        appendUnique(c);return c;
    }

    public void importPointCurves(List<Object> curves) { for(Object c:curves)addPointCurve(Json.map(c)); }
    private void appendUnique(Map<String,Object> c){
        if(all().stream().anyMatch(x->Objects.equals(x.get("id"),c.get("id"))))throw new IllegalArgumentException("duplicate curve id; existing data was preserved: "+c.get("id"));
        try{Files.createDirectories(path.getParent());Files.writeString(path,Json.stringify(c)+"\n",StandardCharsets.UTF_8,StandardOpenOption.CREATE,StandardOpenOption.APPEND);}catch(IOException e){throw new IllegalStateException("curve save failed",e);}
    }
    private static String str(Map<String,Object>m,String k){return Objects.toString(m.get(k),"");}
    private static double num(Map<String,Object>m,String k){Object v=m.get(k);if(!(v instanceof Number n))throw new IllegalArgumentException("missing numeric field: "+k);return n.doubleValue();}
    @SuppressWarnings("unchecked") private static List<Object> list(Map<String,Object>m,String k){Object v=m.get(k);if(!(v instanceof List<?> l))throw new IllegalArgumentException("missing list: "+k);return (List<Object>)l;}
}
