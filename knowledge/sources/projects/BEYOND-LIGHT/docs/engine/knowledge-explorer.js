/* Beyond-Light Knowledge Graph Explorer
 * Deterministic, local-first graph analysis. Suggestions are hypotheses, never facts.
 * No LLM, server, credentials, or writes to the canonical Mnemos Knowledge graph.
 */
(() => {
  "use strict";
  const STOP = new Set(("yang dan atau dari dengan untuk pada dalam ini itu adalah sebagai oleh terhadap antara ke dari juga dapat akan bisa tidak belum sudah jika maka serta the and for with from that this these are was were how what why where when into onto about through using use based via per one two").split(/\s+/));
  const clean = value => String(value ?? "").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const tokens = value => clean(value).split(/\s+/).filter(x => x.length > 2 && !STOP.has(x));
  const layerOf = node => String(node?.metadata?.knowledge_layer || node?.knowledge_layer || "unclassified");
  const knowledgeOf = node => node?.metadata?.knowledge && typeof node.metadata.knowledge === "object" ? node.metadata.knowledge : {};
  const evidenceOf = node => String(knowledgeOf(node).evidence_status || knowledgeOf(node).outcome_status || "not_recorded");
  const titleOf = node => String(node?.title || node?.id || "Untitled");
  const nodeText = node => [node?.title,node?.kind,node?.content,knowledgeOf(node).hypothesis,knowledgeOf(node).method,...(Array.isArray(knowledgeOf(node).results)?knowledgeOf(node).results:[]),...(Array.isArray(knowledgeOf(node).limitations)?knowledgeOf(node).limitations:[])].filter(Boolean).join(" ");
  const excerpt = node => nodeText(node).replace(/\s+/g," ").trim().slice(0,700);
  const pairKey = (a,b) => [String(a),String(b)].sort().join("::");
  const sourceRefs = node => {
    const refs=[];
    const add=(title,url)=>{const value=String(url||"");if(/^https?:\/\//i.test(value)&&!refs.some(x=>x.url===value))refs.push({title:String(title||titleOf(node)),url:value});};
    const source=node?.source||{};add(source.title||source.filename||titleOf(node),source.uri||source.ref);
    for(const item of Array.isArray(knowledgeOf(node).sources)?knowledgeOf(node).sources:[])add(item.title,item.ref||item.uri||item.url);
    return refs.slice(0,8);
  };
  function analyze(nodesInput,edgesInput,previousRun){
    const nodes=(Array.isArray(nodesInput)?nodesInput:[]).filter(n=>n&&n.id),edges=(Array.isArray(edgesInput)?edgesInput:[]).filter(e=>e&&e.source&&e.target);
    const byId=new Map(nodes.map(n=>[String(n.id),n])),degree=new Map(nodes.map(n=>[String(n.id),0])),adjacency=new Map(nodes.map(n=>[String(n.id),new Set()]));
    const existing=new Set(),relationCounts={};
    for(const edge of edges){const a=String(edge.source),b=String(edge.target);existing.add(pairKey(a,b));if(degree.has(a))degree.set(a,degree.get(a)+1);if(degree.has(b))degree.set(b,degree.get(b)+1);if(adjacency.has(a)&&adjacency.has(b)){adjacency.get(a).add(b);adjacency.get(b).add(a);}const rel=String(edge.relation||"unspecified");relationCounts[rel]=(relationCounts[rel]||0)+1;}
    const layerCounts={},evidenceCounts={},kindCounts={},componentById=new Map();
    for(const node of nodes){const layer=layerOf(node),evidence=evidenceOf(node),kind=String(node.kind||"unspecified");layerCounts[layer]=(layerCounts[layer]||0)+1;evidenceCounts[evidence]=(evidenceCounts[evidence]||0)+1;kindCounts[kind]=(kindCounts[kind]||0)+1;}
    let components=0;
    for(const node of nodes){const id=String(node.id);if(componentById.has(id))continue;const component="component-"+(++components),queue=[id];componentById.set(id,component);for(let head=0;head<queue.length;head++)for(const next of adjacency.get(queue[head])||[])if(!componentById.has(next)){componentById.set(next,component);queue.push(next);}}
    const isolated=nodes.filter(n=>(degree.get(String(n.id))||0)===0);
    const prepared=nodes.map(node=>{const titleTokens=new Set(tokens(titleOf(node))),bodyTokens=new Set(tokens(nodeText(node))),weights=new Map();for(const term of bodyTokens)weights.set(term,1);for(const term of titleTokens)weights.set(term,5);return {node,id:String(node.id),titleTokens,weights,layer:layerOf(node),evidence:evidenceOf(node)};});
    const candidates=[];
    for(let i=0;i<prepared.length;i++)for(let j=i+1;j<prepared.length;j++){
      const a=prepared[i],b=prepared[j];if(existing.has(pairKey(a.id,b.id)))continue;
      const shared=[...a.weights.keys()].filter(term=>b.weights.has(term)),titleShared=shared.filter(term=>a.titleTokens.has(term)||b.titleTokens.has(term)),commonNeighbors=[...(adjacency.get(a.id)||[])].filter(id=>(adjacency.get(b.id)||new Set()).has(id));
      if(shared.length<2&&titleShared.length===0&&commonNeighbors.length===0)continue;
      const crossLayer=a.layer!==b.layer,separateComponents=componentById.get(a.id)!==componentById.get(b.id),weighted=shared.reduce((sum,term)=>sum+Math.min(a.weights.get(term),b.weights.get(term)),0),union=new Set([...a.weights.keys(),...b.weights.keys()]);
      const similarity=union.size?weighted/(5*titleShared.length+Math.max(1,union.size)):0,score=Number((weighted+(crossLayer?3:0)+(commonNeighbors.length*6)+(separateComponents?4:0)+titleShared.length*2).toFixed(2));
      const refs=[...sourceRefs(a.node),...sourceRefs(b.node)].filter((x,k,all)=>all.findIndex(y=>y.url===x.url)===k).slice(0,10);
      const neighborContext=commonNeighbors.map(id=>{const n=byId.get(id);return {id,title:titleOf(n),kind:String(n.kind||"unspecified"),layer:layerOf(n),evidence:evidenceOf(n),excerpt:excerpt(n),sourceReferences:sourceRefs(n)};}).slice(0,6);
      candidates.push({id:pairKey(a.id,b.id),sourceId:a.id,targetId:b.id,sourceTitle:titleOf(a.node),targetTitle:titleOf(b.node),sourceKind:String(a.node.kind||"unspecified"),targetKind:String(b.node.kind||"unspecified"),sourceLayer:a.layer,targetLayer:b.layer,sourceEvidence:a.evidence,targetEvidence:b.evidence,sourceComponent:componentById.get(a.id),targetComponent:componentById.get(b.id),sharedConcepts:shared.slice(0,8),titleMatches:titleShared.slice(0,5),sharedNeighbors:neighborContext.map(({id,title,layer})=>({id,title,layer})),evidenceDossier:{nodes:[{id:a.id,title:titleOf(a.node),kind:String(a.node.kind||"unspecified"),layer:a.layer,evidence:a.evidence,excerpt:excerpt(a.node),sourceReferences:sourceRefs(a.node)},{id:b.id,title:titleOf(b.node),kind:String(b.node.kind||"unspecified"),layer:b.layer,evidence:b.evidence,excerpt:excerpt(b.node),sourceReferences:sourceRefs(b.node)}],sharedContext:neighborContext,knownSourceCount:refs.length+neighborContext.reduce((n,x)=>n+x.sourceReferences.length,0),missingEvidence:[...(a.evidence==="not_recorded"?[a.id+": evidence status not recorded"]:[]),...(b.evidence==="not_recorded"?[b.id+": evidence status not recorded"]:[])]},crossLayer,separateComponents,sourceReferences:refs,score,similarity:Number(similarity.toFixed(3)),classification:"UNVERIFIED_RELATION_CANDIDATE",reasoning:[shared.length?"Istilah yang sama: "+shared.slice(0,5).join(", "):null,commonNeighbors.length?"Memiliki "+commonNeighbors.length+" tetangga graph yang sama.":null,crossLayer?"Berasal dari lapisan pengetahuan berbeda.":null,separateComponents?"Berada di komponen graph terpisah; relasi perlu diperiksa manual.":null].filter(Boolean),warning:"Ini kandidat hubungan untuk diteliti, bukan bukti sebab-akibat atau kebenaran ilmiah."});
    }
    candidates.sort((a,b)=>b.score-a.score||b.sharedConcepts.length-a.sharedConcepts.length||a.id.localeCompare(b.id));
    const top=candidates.slice(0,30),previous=Array.isArray(previousRun?.candidates)?previousRun.candidates:[],previousIds=new Set(previous.map(x=>x.id)),currentIds=new Set(top.map(x=>x.id));
    const resolved=previous.filter(x=>existing.has(pairKey(x.sourceId,x.targetId))),persistent=previous.filter(x=>currentIds.has(x.id)),fresh=top.filter(x=>!previousIds.has(x.id));
    return {schemaVersion:3,id:"bl-knowledge-cycle-"+Date.now(),createdAt:new Date().toISOString(),source:"mnemos-RLI:Knowledge",mode:"DETERMINISTIC_GRAPH_EXPLORATION",metrics:{nodes:nodes.length,edges:edges.length,connectedComponents:components,isolatedNodes:isolated.length,candidatePairs:candidates.length,crossLayerCandidates:candidates.filter(x=>x.crossLayer).length,structuralCandidates:candidates.filter(x=>x.sharedNeighbors.length>0).length,disconnectedBridgeCandidates:candidates.filter(x=>x.separateComponents).length,nodesWithSourceReferences:nodes.filter(n=>sourceRefs(n).length).length},layers:layerCounts,evidence:evidenceCounts,kinds:kindCounts,relations:relationCounts,isolated:isolated.map(n=>({id:String(n.id),title:titleOf(n),layer:layerOf(n)})),candidates:top,cycleComparison:{previousCandidates:previous.length,newCandidates:fresh.length,stillOpen:persistent.length,resolvedByNewGraphEdges:resolved.length,newItems:fresh.map(x=>x.id),resolvedItems:resolved.map(x=>x.id)},limitations:["Analisis memakai metadata, struktur graph, tetangga bersama, dan kemiripan istilah; bukan LLM atau semantic embedding.","Kandidat relasi belum ditulis ke Mnemos-RLI dan tidak boleh dianggap fakta.","Status bukti dan tautan sumber diwariskan dari node; sumber primer tidak otomatis dibaca ulang.","Riwayat siklus tersimpan lokal pada browser perangkat ini."]};
  }
  window.BeyondLightKnowledgeExplorer={analyze,pairKey,tokens,sourceRefs};
})();