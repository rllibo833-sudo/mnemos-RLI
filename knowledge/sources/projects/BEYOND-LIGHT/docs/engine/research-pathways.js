/* Candidate-to-research-path planner. Metadata discovery is a source-finding step, not scientific validation. */
(() => {
"use strict";
const clip=(v,n)=>String(v??"").replace(/\\s+/g," ").trim().slice(0,n);
function create(candidate){
 const c=candidate||{},d=c.evidenceDossier||{},nodes=Array.isArray(d.nodes)?d.nodes:[],neighbors=Array.isArray(d.sharedContext)?d.sharedContext:[];
 const concepts=(c.sharedConcepts||[]).slice(0,5).join(", ");
 const raw="research metadata: "+clip(c.sourceTitle,48)+"; "+clip(c.targetTitle,48)+(concepts?"; "+clip(concepts,38):"");
 const question=clip(raw,160);
 const kinds=nodes.map(n=>String(n.kind||"").toLowerCase());
 const layers=nodes.map(n=>String(n.layer||"").toLowerCase());
 const dataLike=kinds.some(k=>/dataset|data|experiment|measurement|observation/.test(k))||layers.some(k=>/experimental|dataset|measurement/.test(k));
 const testability=dataLike
  ? {status:"NEEDS_DATA",engineCandidates:["dataset.deterministic-analysis","research.autonomous-model-exploration"],reason:"Belum ada dataset lokal yang terikat ke kandidat beserta kolom target/prediktor. Mesin yang cocok sudah tersedia, tetapi inputnya belum ada.",required:["datasetId lokal","nama kolom target dan prediktor","satuan serta provenance dataset"]}
  : {status:"NEEDS_METHOD",engineCandidates:[],reason:"Belum ada metode uji domain-spesifik yang dapat dipilih secara bertanggung jawab hanya dari metadata graph. Pencarian metadata sumber dapat membantu menyusun metode, tetapi bukan pengujian kandidat.",required:["rumusan operasional yang dapat diuji","metode atau protokol yang sesuai domain","data/observasi yang dapat diperiksa"]};
 return {id:String(c.id||"candidate"),candidateId:String(c.id||"candidate"),question,testability,goal:"Cari rekaman sumber terbuka yang relevan, lalu periksa apakah sumber benar-benar mendukung, membatasi, atau bertentangan dengan relasi yang diusulkan.",hypothesis:"PROPOSED_QUESTION_ONLY",route:{workflow:"open-data-discovery",engineId:"research.open-data-discovery",scope:"Zenodo metadata search"},dossier:{nodes:nodes.map(n=>({id:n.id,title:n.title,kind:n.kind,layer:n.layer,evidence:n.evidence,excerpt:clip(n.excerpt,700),sourceReferences:n.sourceReferences||[]})),sharedContext:neighbors.map(n=>({id:n.id,title:n.title,layer:n.layer,evidence:n.evidence,excerpt:clip(n.excerpt,700),sourceReferences:n.sourceReferences||[]})),knownSourceCount:Number(d.knownSourceCount||0),missingEvidence:d.missingEvidence||[]},executionStatus:"READY_FOR_METADATA_SEARCH",limitations:["Pencarian hanya mengambil metadata Zenodo; belum membaca full-text atau memverifikasi sumber primer.","Pencarian sumber bukan pengujian hipotesis; relasi tetap UNVERIFIED sampai ditinjau.","Jika tidak ada dataset/input yang sesuai, mesin analisis numerik tidak boleh dipaksakan ke kandidat ini."]};
}
function summarize(result){
 const output=result?.analysis?.output||{},records=output.records||output.output?.records||[];
 return {status:result?.analysis?.status||"UNKNOWN",recordCount:records.length,records:records.slice(0,10).map(r=>({title:r.title,doi:r.doi,year:r.year,authors:r.authors,url:r.recordUrl,description:r.description})),error:result?.analysis?.error||"",evidenceClassification:result?.evidence?.classification||"NOT_CLASSIFIED",limitations:result?.evidence?.uncertainty||[]};
}
window.BeyondLightResearchPathways={create,summarize};
})();