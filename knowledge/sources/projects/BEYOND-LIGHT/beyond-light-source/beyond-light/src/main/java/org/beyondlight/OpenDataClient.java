package org.beyondlight;

import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;

/** User-triggered search/import of openly published numeric CSV files from Zenodo. */
public final class OpenDataClient {
 private static final String API="https://zenodo.org/api/records";
 private static final int MAX_BYTES=10_000_000;
 private static final HttpClient HTTP=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(15)).followRedirects(HttpClient.Redirect.NEVER).build();
 private OpenDataClient(){}
 public static List<Map<String,Object>> search(String query)throws Exception{
  String q=URLEncoder.encode(query,StandardCharsets.UTF_8);URI uri=URI.create(API+"?q="+q+"&size=10");String body=getText(uri);Object parsed=Json.parse(body);List<?> hits;
  if(parsed instanceof List<?> list)hits=list;else{Map<String,Object> root=Json.map(parsed);Object h=root.get("hits");if(h instanceof Map<?,?> hm&&hm.get("hits") instanceof List<?> l)hits=l;else if(root.get("results") instanceof List<?> l)hits=l;else hits=List.of();}
  List<Map<String,Object>> result=new ArrayList<>();for(Object hit:hits){Map<String,Object> rec=Json.map(hit);Map<String,Object> meta=rec.get("metadata") instanceof Map<?,?>?Json.map(rec.get("metadata")):rec;String id=Objects.toString(rec.get("id"),"");if(!id.matches("[0-9]+"))continue;
   String title=Objects.toString(meta.get("title"),"Untitled dataset");String doi=Objects.toString(meta.get("doi"),"");if(doi.isBlank()&&meta.get("prereserve_doi") instanceof Map<?,?> reserve)doi=Objects.toString(Json.map(reserve).get("doi"),"");
   String year=Objects.toString(meta.get("publication_date"),"");if(year.length()>4)year=year.substring(0,4);String author=creatorNames(meta.get("creators"));String description=plain(Objects.toString(meta.get("description"),""));
   List<Map<String,Object>> files=new ArrayList<>();Object fs=rec.get("files");if(fs instanceof List<?> fl)for(Object fo:fl){Map<String,Object> f=Json.map(fo);String name=Objects.toString(f.get("key"),Objects.toString(f.get("filename"),""));if(!name.toLowerCase(Locale.ROOT).endsWith(".csv"))continue;long size=f.get("size") instanceof Number n?n.longValue():0;if(size>MAX_BYTES)continue;files.add(Map.of("name",name,"size",size));}
   Map<String,Object> item=new LinkedHashMap<>();item.put("recordId",id);item.put("title",title);item.put("doi",doi);item.put("year",year);item.put("authors",author);item.put("description",description.length()>1200?description.substring(0,1200):description);item.put("recordUrl","https://zenodo.org/records/"+id);item.put("files",files);result.add(item);
  }return List.copyOf(result);
 }
 public static Map<String,Object> downloadAndImport(String recordId,String filename,DataRepository repository)throws Exception{
  if(recordId==null||!recordId.matches("[0-9]{1,20}"))throw new IllegalArgumentException("Zenodo record id is invalid");if(filename==null||!filename.matches("[A-Za-z0-9._-]{1,180}\\.csv"))throw new IllegalArgumentException("Only simple CSV filenames can be imported.");
  Map<String,Object> rec=Json.map(Json.parse(getText(URI.create(API+"/"+recordId))));Map<String,Object> meta=rec.get("metadata") instanceof Map<?,?>?Json.map(rec.get("metadata")):rec;Map<String,Object> file=null;Object fs=rec.get("files");if(fs instanceof List<?> fl)for(Object fo:fl){Map<String,Object> f=Json.map(fo);if(filename.equals(Objects.toString(f.get("key"),Objects.toString(f.get("filename"),"")))){file=f;break;}}if(file==null)throw new IllegalArgumentException("CSV file is not listed on the selected open record.");long declared=file.get("size") instanceof Number n?n.longValue():-1;if(declared>MAX_BYTES)throw new IllegalArgumentException("CSV exceeds the 10 MB import limit.");
  String path="/"+recordId+"/files/"+URLEncoder.encode(filename,StandardCharsets.UTF_8).replace("+","%20")+"/content";byte[] bytes=getLimited(URI.create("https://zenodo.org/api/records"+path));String raw=new String(bytes,StandardCharsets.UTF_8);if(raw.startsWith("\uFEFF"))raw=raw.substring(1);
  String doi=Objects.toString(meta.get("doi"),"");String title=Objects.toString(meta.get("title"),"Zenodo open dataset");String authors=creatorNames(meta.get("creators"));String year=Objects.toString(meta.get("publication_date"),"");if(year.length()>4)year=year.substring(0,4);
  String recordUrl="https://zenodo.org/records/"+recordId;Map<String,String> provenance=Map.of("source","Zenodo: "+title+" ("+recordUrl+")","author",authors,"year",year,"doi",doi,"conditions","Downloaded from public Zenodo record; original CSV retained. Numeric dataset not independently verified.");DataRepository.Dataset preview=repository.preview(filename,"csv",raw,provenance);DataRepository.Dataset stored=repository.commit(preview.id());Map<String,Object> out=new LinkedHashMap<>();out.put("dataset",Map.of("id",stored.id(),"filename",stored.filename(),"rows",stored.rows(),"variables",Arrays.asList(stored.variables().split(",")),"status",stored.status()));out.put("source",Map.of("title",title,"doi",doi,"url","https://zenodo.org/records/"+recordId,"authors",authors));out.put("note","File tersimpan lokal setelah validasi angka. Status ilmiahnya tetap belum diverifikasi.");return out;
 }
 private static String getText(URI uri)throws Exception{HttpRequest req=HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(30)).header("Accept","application/json").header("User-Agent","BeyondLight-local-research/0.1").GET().build();HttpResponse<String> r=HTTP.send(req,HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));if(r.statusCode()!=200)throw new IOException("Open repository returned HTTP "+r.statusCode());return r.body();}
 private static byte[] getLimited(URI uri)throws Exception{for(int redirects=0;redirects<4;redirects++){if(!"https".equalsIgnoreCase(uri.getScheme())||!allowedHost(uri.getHost()))throw new IOException("Download redirected outside approved Zenodo hosts.");HttpRequest req=HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(90)).header("Accept","text/csv, text/plain, application/octet-stream").header("User-Agent","BeyondLight-local-research/0.1").GET().build();HttpResponse<InputStream> r=HTTP.send(req,HttpResponse.BodyHandlers.ofInputStream());int code=r.statusCode();if(code>=300&&code<400){String loc=r.headers().firstValue("location").orElseThrow(()->new IOException("download redirect without location"));uri=uri.resolve(loc);r.body().close();continue;}if(code!=200){r.body().close();throw new IOException("Dataset download returned HTTP "+code);}try(InputStream in=r.body()){byte[] b=in.readNBytes(MAX_BYTES+1);if(b.length>MAX_BYTES)throw new IOException("Downloaded CSV exceeds 10 MB limit.");return b;}}throw new IOException("Too many redirects while downloading dataset.");}
 private static boolean allowedHost(String h){if(h==null)return false;String x=h.toLowerCase(Locale.ROOT);return x.equals("zenodo.org")||x.endsWith(".zenodo.org")||x.equals("zenodo.net")||x.endsWith(".zenodo.net");}
 private static String creatorNames(Object o){if(!(o instanceof List<?> list))return "";return list.stream().limit(8).map(v->v instanceof Map<?,?>m?Objects.toString(m.get("name"),""):String.valueOf(v)).filter(x->!x.isBlank()).reduce((a,b)->a+"; "+b).orElse("");}
 private static String plain(String html){return html.replaceAll("(?is)<script.*?>.*?</script>"," ").replaceAll("(?is)<style.*?>.*?</style>"," ").replaceAll("<[^>]+>"," ").replace("&nbsp;"," ").replace("&amp;","&").replace("&lt;","<").replace("&gt;",">").replaceAll("\\s+"," ").trim();}
}
