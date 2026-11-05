/* Beyond-Light -> Mnemos-RLI Knowledge
 * Static browser integration. No application server, API proxy, Node runtime or secrets.
 * The Knowledge branch is the canonical read-only source of truth.
 */
(() => {
  "use strict";
  const ROOT = "https://raw.githubusercontent.com/rllibo833-sudo/mnemos-RLI/Knowledge/knowledge/";
  const CATALOG_URL = "https://raw.githubusercontent.com/rllibo833-sudo/Beyond-Light/main/docs/catalog.json";
  const state = { status: "idle", manifest: null, nodes: [], edges: [], catalog: null, errors: [] };
  const stopWords = new Set(["yang","dan","atau","dari","dengan","untuk","pada","dalam","ini","itu","apa","bagaimana","kenapa","mengapa","bisa","tolong","bantu","gw","gue","aku","saya","the","and","for","with","from","that","this","are","was","how","what","why"]);
  const tokenize = value => String(value || "").toLowerCase().normalize("NFKD").replace(/[^\p{L}\p{N}]+/gu," ").trim().split(/\s+/).filter(x=>x.length>1&&!stopWords.has(x));
  async function getJSON(url) {
    const response = await fetch(url, { mode: "cors", credentials: "omit", cache: "no-cache" });
    if (!response.ok) throw new Error("HTTP " + response.status + " saat membaca " + url);
    return response.json();
  }
  async function pool(items, concurrency, worker) {
    const output = new Array(items.length); let cursor = 0;
    async function run() {
      while (cursor < items.length) {
        const index = cursor++;
        try { output[index] = await worker(items[index], index); }
        catch (error) { output[index] = { __loadError: String(error), file: items[index] }; }
      }
    }
    await Promise.all(Array.from({length: Math.min(concurrency, items.length)}, run));
    return output;
  }
  async function initialize() {
    state.status = "loading";
    const manifest = await getJSON(ROOT + "manifest.json");
    if (manifest.source_of_truth !== "mnemos-RLI:Knowledge") throw new Error("Manifest bukan Knowledge canonical.");
    state.manifest = manifest;
    const [nodeResults, edgeResults, catalog] = await Promise.all([
      pool((manifest.node_files || []).map(file => "nodes/" + file), 4, file => getJSON(ROOT + file)),
      pool((manifest.edge_files || []).map(file => "edges/" + file), 4, file => getJSON(ROOT + file)),
      getJSON(CATALOG_URL).catch(error => ({ __loadError: String(error) }))
    ]);
    state.nodes = nodeResults.filter(x => x && !x.__loadError);
    state.edges = edgeResults.filter(x => Array.isArray(x)).flat();
    state.errors = [...nodeResults, ...edgeResults].filter(x => x && x.__loadError);
    state.catalog = catalog && !catalog.__loadError ? catalog : null;
    state.status = state.errors.length ? "partial" : "ready";
    return getStatus();
  }
  function getStatus() {
    return {
      status: state.status,
      source: "mnemos-RLI:Knowledge",
      generatedAt: state.manifest && state.manifest.generated_at,
      expectedNodes: state.manifest && state.manifest.nodes_count,
      loadedNodes: state.nodes.length,
      expectedEdges: state.manifest && state.manifest.edges_count,
      loadedEdges: state.edges.length,
      failedFiles: state.errors.map(x => x.file),
      engines: listEngines()
    };
  }
  function searchableText(node) {
    return [node.title,node.content,node.kind,node.id,node.metadata && JSON.stringify(node.metadata),node.source && JSON.stringify(node.source)].filter(Boolean).join(" ");
  }
  function search(query, options) {
    const terms = tokenize(query);
    if (!terms.length) return [];
    const limit = Math.max(1, Math.min(12, Number(options && options.limit) || 6));
    const ranked = state.nodes.map(node => {
      const title = tokenize(node.title).join(" ");
      const hay = tokenize(searchableText(node));
      let score = 0;
      for (const term of terms) {
        const count = hay.reduce((n, word) => n + (word === term ? 1 : 0), 0);
        if (title.split(" ").includes(term)) score += 8;
        score += Math.min(6, count) * 2;
      }
      const normalizedTitle = String(node.title || "").toLowerCase();
      if (normalizedTitle.includes(String(query).toLowerCase())) score += 10;
      return { node, score };
    }).filter(x=>x.score>0).sort((a,b)=>b.score-a.score);
    return ranked.slice(0,limit).map(x=>({
      id:x.node.id, title:x.node.title, kind:x.node.kind, content:x.node.content,
      layer:x.node.metadata && x.node.metadata.knowledge_layer,
      evidenceStatus:x.node.metadata && x.node.metadata.knowledge && x.node.metadata.knowledge.evidence_status,
      sources:(x.node.metadata && x.node.metadata.knowledge && x.node.metadata.knowledge.sources) || (x.node.source ? [x.node.source] : []),
      score:x.score
    }));
  }
  function relatedTo(ids) {
    const wanted = new Set(ids);
    const linked = [];
    for (const edge of state.edges) {
      if (wanted.has(edge.source) || wanted.has(edge.target)) {
        const id = wanted.has(edge.source) ? edge.target : edge.source;
        const node = state.nodes.find(n=>n.id===id);
        if (node && !wanted.has(id) && !linked.some(x=>x.id===id)) linked.push({id,title:node.title,relation:edge.relation});
      }
    }
    return linked.slice(0,8);
  }
  function answer(query) {
    if (state.status === "idle" || state.status === "loading") throw new Error("Knowledge graph masih dimuat.");
    const hits = search(query,{limit:5});
    if (!hits.length) return {
      text:"Belum ada node Knowledge yang cukup cocok dengan pertanyaan itu. Coba gunakan istilah yang lebih spesifik. Pencarian dilakukan langsung di browser terhadap branch mnemos-RLI/Knowledge.",
      hits:[], related:[], source:"mnemos-RLI:Knowledge"
    };
    const lines = hits.map((hit,index)=>{
      const snippet = String(hit.content || "").replace(/\s+/g," ").slice(0,620);
      const status = hit.evidenceStatus ? " · status bukti: " + hit.evidenceStatus : "";
      const layer = hit.layer ? " · lapisan: " + hit.layer : "";
      return (index+1)+". "+(hit.title || hit.id)+layer+status+"\n"+snippet;
    });
    const related = relatedTo(hits.map(x=>x.id));
    const sources = [];
    for (const hit of hits) for (const source of hit.sources || []) {
      const url = source.ref || source.uri;
      if (url && /^https?:\/\//i.test(url) && !sources.some(x=>x.url===url)) sources.push({title:source.title || hit.title,url});
    }
    const sourceLines = sources.slice(0,8).map(x=>"- "+x.title+": "+x.url);
    const relatedLines = related.map(x=>"- "+x.title+" ("+x.relation+")");
    return {
      text:"Hasil penelusuran Knowledge (bukan jawaban LLM):\n\n"+lines.join("\n\n")+
        (relatedLines.length?"\n\nRelasi graf:\n"+relatedLines.join("\n"):"")+
        (sourceLines.length?"\n\nSumber:\n"+sourceLines.join("\n"):"")+
        "\n\nSumber utama: mnemos-RLI / branch Knowledge. Hasil dibatasi pada data yang berhasil dimuat; status bukti tiap node harus tetap diperhatikan.",
      hits, related, sources, source:"mnemos-RLI:Knowledge"
    };
  }
  function listEngines() {
    const found = [];
    if (window.BeyondLightSymbolic) found.push({id:"symbolic",name:"Symbolic mathematics",methods:["analyze","evaluate","derivative","integrate","substitute","isolate"]});
    if (window.BeyondLightResearch) found.push({id:"research",name:"Research registry, dimensions and benchmarks",methods:["validateEquation","benchmark","benchmarkAll","listEquations"]});
    if (window.BeyondLightFeasibility) found.push({id:"feasibility",name:"Physics and engineering primitives",methods:["evaluate","stress","eulerBucklingLoad","energyBalance"]});
    if (window.BeyondLightFeasibilityAssessment) found.push({id:"assessment",name:"Staged feasibility and machine assembly",methods:["assess","assemble"]});
    if (window.BeyondLightTechnologyDesign) found.push({id:"technology",name:"Technology design domains",methods:["explore"]});
    if (window.BeyondLightDecision) found.push({id:"decision",name:"Evidence classification and Pareto ranking",methods:["classify","rankCandidates"]});
    if (window.BeyondLightResearchCore) found.push({id:"research-core",name:"Unified static research planner and orchestration",methods:["plan","dispatch","listEngines"]});
    return found;
  }
  function runEngine(engine, operation, payload) {
    const p = payload || {};
    switch (engine + "." + operation) {
      case "symbolic.analyze": return window.BeyondLightSymbolic.analyze(p.expression,p.variable || "x",p.value);
      case "symbolic.evaluate": return window.BeyondLightSymbolic.evaluate(window.BeyondLightSymbolic.parse(p.expression),p.variables || {});
      case "symbolic.derivative": return window.BeyondLightSymbolic.print(window.BeyondLightSymbolic.simplify(window.BeyondLightSymbolic.derivative(window.BeyondLightSymbolic.parse(p.expression),p.variable || "x")));
      case "symbolic.integrate": return window.BeyondLightSymbolic.print(window.BeyondLightSymbolic.simplify(window.BeyondLightSymbolic.integrate(window.BeyondLightSymbolic.parse(p.expression),p.variable || "x"))) + " + C";
      case "symbolic.substitute": return window.BeyondLightSymbolic.substitute(p.expression,p.variable,p.replacement);
      case "symbolic.isolate": return window.BeyondLightSymbolic.isolate(p.lhs,p.rhs,p.variable);
      case "research.validateEquation": return window.BeyondLightResearch.dimensions.validateEquation(p.expression,p.variables || "");
      case "research.benchmark": return window.BeyondLightResearch.benchmarks.run(p.id,p.inputs || {},p.tolerance);
      case "research.benchmarkAll": return window.BeyondLightResearch.benchmarks.runAll();
      case "research.listEquations": return window.BeyondLightResearch.equations.load();
      case "feasibility.evaluate": return window.BeyondLightFeasibility.evaluate(p);
      case "assessment.assess": return window.BeyondLightFeasibilityAssessment.assess(p);
      case "assessment.assemble": return window.BeyondLightFeasibilityAssessment.assemble(p);
      case "technology.explore": return window.BeyondLightTechnologyDesign.explore(p.domainId,p.inputs || {});
      case "decision.classify": return window.BeyondLightDecision.classify(p);
      case "decision.rankCandidates": return window.BeyondLightDecision.rankCandidates(p);
      case "research-core.plan": return window.BeyondLightResearchCore.plan(window.BeyondLightResearchCore.createRequest(p));
      case "research-core.dispatch": return window.BeyondLightResearchCore.dispatch(p);
      case "research-core.listEngines": return window.BeyondLightResearchCore.listEngines();
      case "research-core.importDatasetCsv": return window.BeyondLightResearchCore.importDatasetCsv(p.filename,p.csv,p.metadata || {});
      case "research-core.listDatasets": return window.BeyondLightResearchCore.listDatasets();
      default: throw new Error("Mesin/operasi tidak tersedia di browser: " + engine + "." + operation);
    }
  }
  function engineInventory() {
    const modules = state.catalog && Array.isArray(state.catalog.modules) ? state.catalog.modules : [];
    return {
      browserEngines:listEngines(),
      catalogModules:modules.map(m=>({file:m.file,functionality:m.functionality,browserStatus:m.browserStatus,runtime:m.runtime,layer:m.layer})),
      summary:state.catalog && state.catalog.summary,
      researchWorkflows:window.BeyondLightResearchCore ? window.BeyondLightResearchCore.listEngines() : []
    };
  }
  window.BeyondLightMnemos = {
    ready:null, initialize, getStatus, search, answer, runEngine, listEngines, engineInventory,
    getGraph:()=>({manifest:state.manifest,nodes:state.nodes,edges:state.edges})
  };
  window.BeyondLightMnemos.ready = initialize();
  window.BeyondLightMnemos.ready.catch(error=>{state.status="error";state.errors.push({file:"manifest/initialization",error:String(error)});});
})();
