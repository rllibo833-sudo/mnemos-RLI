/* Evidence classification and Pareto utilities ported from FeasibilityClassification.java
 * and TechnologyDesignEngine.java. These tools interpret supplied records; they do not
 * generate a physical feasibility assessment or domain-specific design candidates.
 */
(() => {
"use strict";
const STATUS={MAT_VALID:"MATHEMATICALLY_VALIDATED",MAT_BAD:"MATHEMATICALLY_INCONSISTENT",PHYS_OK:"PHYSICALLY_SUPPORTED_WITHIN_MODEL",PHYS_BAD:"PHYSICAL_VIOLATION_DETECTED",ENG_OK:"ENGINEERINGALLY_PLAUSIBLE_WITH_AVAILABLE_DATA",ENG_BAD:"ENGINEERINGALLY_INFEASIBLE",MISSING:"INSUFFICIENT_DATA",THEORY:"THEORETICAL_ONLY"};
function classify(bundle){
 const a=bundle?.assessment;if(!a)return {classifications:["INSUFFICIENT_DATA"],reasons:["Assessment tidak disertakan."],missingEvidence:["assessment"],conclusion:"Tidak ada kesimpulan",experimentallySupported:false};
 const labels=[],reasons=[],missing=[];
 const math=a.mathematical?.status===STATUS.MAT_VALID;
 const phys=a.conservation?.status===STATUS.PHYS_OK&&a.energyThermal?.status===STATUS.PHYS_OK;
 const physicalBad=a.conservation?.status===STATUS.PHYS_BAD||a.energyThermal?.status===STATUS.PHYS_BAD;
 const engStatus=String(a.engineering?.status||"");
 const engBad=engStatus===STATUS.ENG_BAD||engStatus.includes("INFEASIBLE");
 const theoretical=a.overallClassification===STATUS.THEORY||a.mathematical?.status===STATUS.THEORY;
 if(theoretical){labels.push("THEORETICAL_ONLY");reasons.push("Model keluarga ini tidak menyediakan mekanisme gaya dorong dan sumber energi terverifikasi.");}
 if(math){labels.push("MATHEMATICALLY_CONSISTENT");reasons.push("Domain perhitungan dan relasi model berhasil dievaluasi secara matematis.");}
 else if(a.mathematical?.status===STATUS.MAT_BAD){labels.push("PHYSICALLY_INCONSISTENT");reasons.push("Input atau persamaan gagal pemeriksaan matematis.");}
 if(physicalBad){labels.push("PHYSICALLY_INCONSISTENT");reasons.push("Sedikitnya satu pemeriksaan konservasi/energi menunjukkan pelanggaran dalam model.");}
 else if(phys){labels.push("PHYSICALLY_CONSISTENT");reasons.push("Pemeriksaan hukum fisika yang diimplementasikan lolos dalam batas model dan toleransinya.");}
 const benchmarks=Array.isArray(bundle.benchmarkResults)?bundle.benchmarkResults:[];
 const numericalPassed=benchmarks.length>0&&benchmarks.every(x=>x.status==="PASS");
 if(!numericalPassed){labels.push("NUMERICALLY_INCONCLUSIVE");missing.push("Benchmark numerik relevan belum seluruhnya lulus atau belum dilampirkan.");}
 const raw=bundle.experimentalEvidence||{};
 const matched=Boolean(raw.recordId&&raw.rawDataReference&&raw.testConditions&&raw.measurementUnits);
 if(matched){labels.push("EXPERIMENTALLY_SUPPORTED");reasons.push("Metadata pengukuran mentah dan kondisi pengujian ditautkan dalam paket bukti.");}
 else missing.push("Data mentah eksperimen yang cocok beserta ID, referensi, kondisi uji, dan satuan pengukuran belum lengkap.");
 const results=a.results&&typeof a.results==="object"?Object.keys(a.results):[];
 if(results.length&&!theoretical){labels.push("ENGINEERING_ESTIMATE");reasons.push("Keluaran rekayasa berasal dari model dan parameter yang diberikan; bukan sertifikasi rancangan.");}
 if(engStatus===STATUS.ENG_BAD){labels.push("ENGINEERING_INFEASIBLE");reasons.push("Pemeriksaan rekayasa menemukan batas yang gagal berdasarkan data yang tersedia.");}
 else if(engStatus===STATUS.MISSING||engStatus.includes("MISSING")||engStatus.includes("INCOMPLETE")){labels.push("INSUFFICIENT_DATA");missing.push("Properti material, kapasitas sistem, atau spesifikasi komponen belum lengkap.");}
 else if(engStatus===STATUS.ENG_OK&&Array.isArray(a.engineering?.checks)&&a.engineering.checks.length){labels.push("ENGINEERING_SCREENING");reasons.push("Penyaringan komponen lolos pada properti yang diketahui; belum menilai manufaktur atau kualifikasi.");}
 if(!labels.length)labels.push("INSUFFICIENT_DATA");
 return {classifications:[...new Set(labels)],reasons,missingEvidence:missing,conclusion:"Tidak ada label ini yang membuktikan mesin nyata dapat dibuat.",experimentallySupported:matched,experimentalEvidenceGate:matched?"metadata lengkap":"butuh recordId, rawDataReference, testConditions, measurementUnits"};
}
function rankCandidates(payload){
 const root=payload?.result||payload||{};
 const all=Array.isArray(root.allCandidates)?root.allCandidates:[];
 const objectives=Array.isArray(payload?.objectives)?payload.objectives:Array.isArray(root.objectives)?root.objectives:[];
 if(!objectives.length)throw Error("Daftar objectives diperlukan.");
 const passing=all.filter(x=>x.candidateFeasible===true);
 const value=(c,k)=>{const n=Number(c[k]);if(!Number.isFinite(n))throw Error("Kandidat kehilangan nilai objective finite: "+k);return n;};
 const dominates=(a,b)=>{let strict=false;for(const o of objectives){const av=value(a,o.metric),bv=value(b,o.metric),dir=String(o.direction).toUpperCase();if(dir==="MINIMIZE"){if(av>bv)return false;if(av<bv)strict=true;}else if(dir==="MAXIMIZE"){if(av<bv)return false;if(av>bv)strict=true;}else throw Error("Arah objective harus MINIMIZE atau MAXIMIZE: "+o.metric);}return strict;};
 const front=passing.filter(a=>!passing.some(b=>a!==b&&dominates(b,a)));
 const sortMetric=payload?.sortMetric||objectives[0].metric;
 front.sort((a,b)=>value(a,sortMetric)-value(b,sortMetric));
 return {status:passing.length?"CANDIDATE_DESIGNS_WITHIN_MODEL_ENVELOPE":"NO_DESIGN_WITHIN_GIVEN_ENVELOPE",candidatesEvaluated:all.length,invalidOrUnsolvableCandidates:Number(root.invalidOrUnsolvableCandidates||0),withinEnvelope:passing.length,paretoCandidates:front.slice(0,20),objectives,scope:"Pareto ranking only: candidates must already be generated and evaluated by a domain engine. No new design candidates are generated in browser."};
}
window.BeyondLightDecision={classify,rankCandidates};
})();
