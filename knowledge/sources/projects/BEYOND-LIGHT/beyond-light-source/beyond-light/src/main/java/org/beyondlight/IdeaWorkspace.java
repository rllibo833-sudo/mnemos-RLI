package org.beyondlight;

/**
 * Preserved local research entry point; the public knowledge site is served from GitHub Pages.
 * Idea-first entry point. The scientific workbench remains available at /tools;
 * this page turns a plain-language goal into a guided research request.
 */
public final class IdeaWorkspace {
    private IdeaWorkspace() {}

    public static String page() {
        return """
<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#101a20">
<title>Beyond-Light — Ruang Ide</title>
<style>
:root{color-scheme:dark;--bg:#101a20;--panel:#19282f;--panel2:#20343b;--ink:#edf5f2;--muted:#a9bfba;--line:#36514f;--accent:#9bd8bd}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,sans-serif}
main{max-width:920px;margin:auto;padding:24px 18px 64px}.brand{font-size:13px;letter-spacing:.18em;color:var(--accent);font-weight:700}
h1{font-size:clamp(32px,6vw,54px);line-height:1.05;margin:14px 0}h2{font-size:21px;margin:0 0 12px}
p{color:var(--muted)}.intro{font-size:18px;max-width:680px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:20px;margin:18px 0}
textarea{width:100%;min-height:140px;background:#0d171b;color:var(--ink);border:1px solid var(--line);border-radius:12px;padding:15px;font:inherit;resize:vertical}
button,.linkbtn{background:var(--accent);color:#10231e;border:0;border-radius:11px;padding:12px 18px;font:inherit;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}
button:disabled{opacity:.55;cursor:wait}.secondary{background:var(--panel2);color:var(--ink);border:1px solid var(--line)}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}.hint{font-size:13px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.step{background:var(--panel2);border-radius:12px;padding:14px}.step b{display:block;color:var(--accent);margin-bottom:4px}
.hidden{display:none}.result h3{font-size:16px;margin:18px 0 6px;color:var(--accent)}.result ul{padding-left:20px}.result li{margin:6px 0}
details{border-top:1px solid var(--line);padding:12px 0}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0d171b;padding:12px;border-radius:10px;color:#d5e5df;font-size:12px}
.card{border:1px solid var(--line);border-radius:12px;padding:12px;margin:9px 0}.card a{color:var(--accent)}.status{color:var(--accent);font-weight:650}.layer-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}.layer-field{min-width:0;background:var(--panel2);padding:12px;border-radius:12px}.layer-field label{display:block;font-size:13px;font-weight:650;margin:8px 0 5px}.layer-field input,.layer-field select,.layer-field textarea{width:100%;background:#0d171b;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:9px;font:inherit}.layer-field textarea{min-height:74px}.layer-note{font-size:12px;margin:6px 0 0}@media(max-width:600px){.layer-grid{grid-template-columns:1fr}}
footer{margin-top:28px;border-top:1px solid var(--line);padding-top:18px;font-size:13px}
@media(max-width:600px){main{padding:20px 14px 48px}.steps{grid-template-columns:1fr}.panel{padding:16px}}
</style>
</head>
<body><main>
<div class="brand">BEYOND-LIGHT</div>
<h1>Ide dulu.<br>Rumus belakangan.</h1>
<p class="intro">Ceritakan apa yang ingin lu wujudkan. Beyond-Light akan membantu membuka jalur pengetahuan, penelitian, eksperimen, dan perhitungan yang relevan—tanpa mengharuskan lu mulai dari angka.</p>
<section class="panel">
<label for="goal"><strong>Apa yang lagi lu pikirkan?</strong></label>
<textarea id="goal" placeholder="Contoh: gw pengen bikin kendaraan yang bisa terbang berbulan-bulan tanpa isi bahan bakar terus..."></textarea>
<div class="actions"><button id="explore">Jelajahi ide</button><button class="secondary" id="example">Pakai contoh Mars</button></div>
<p class="hint">Tulis seperti ngobrol. Jangan masukkan angka teknis kecuali memang lu mau.</p>
</section>
<section class="panel">
<details id="knowledgeLayers">
<summary>Lapisan pengetahuan lanjutan (opsional)</summary>
<p class="hint">Isi hanya bagian yang punya dasar. Sumber riset yang ditemukan akan dipakai sebagai rujukan otomatis bila tersedia. Lapisan kosong tidak dikirim.</p>
<div class="layer-grid">
<div class="layer-field">
<strong>Scientific Knowledge</strong>
<p class="layer-note">Dibentuk otomatis dari research run, evidence report, dan sumber yang ditemukan. Status bukti default tetap unknown sampai ada bukti yang benar-benar mendukung.</p>
</div>
<div class="layer-field">
<strong>Historical Knowledge</strong>
<label for="historyTitle">Peristiwa / penemuan / perkembangan</label><input id="historyTitle" maxlength="512" placeholder="Nama peristiwa atau penemuan">
<label for="historyContent">Konteks sejarah</label><textarea id="historyContent" placeholder="Apa yang terjadi, siapa yang terlibat, dan mengapa penting?"></textarea>
<label for="historyDate">Tanggal</label><input id="historyDate" placeholder="YYYY-MM-DD atau tahun">
<label for="historyPeriod">Periode</label><input id="historyPeriod" placeholder="Contoh: Revolusi Industri">
<label for="historyPeople">Tokoh (pisahkan dengan koma)</label><input id="historyPeople">
<label for="historyInstitutions">Institusi (pisahkan dengan koma)</label><input id="historyInstitutions">
<label for="historySources">Sumber (satu URL / referensi per baris)</label><textarea id="historySources" placeholder="https://..."></textarea>
<p class="layer-note">Catatan sejarah hanya diterbitkan bila ada sumber yang diisi di sini atau ditemukan oleh riset.</p>
</div>
<div class="layer-field">
<strong>Philosophical Knowledge</strong>
<label for="philoQuestions">Pertanyaan filosofis (satu per baris)</label><textarea id="philoQuestions"></textarea>
<label for="philoAssumptions">Asumsi (satu per baris)</label><textarea id="philoAssumptions"></textarea>
<label for="philoPrinciples">Prinsip (satu per baris)</label><textarea id="philoPrinciples"></textarea>
<label for="philoArguments">Argumen (satu per baris)</label><textarea id="philoArguments"></textarea>
<label for="philoEthics">Pertimbangan etika (satu per baris)</label><textarea id="philoEthics"></textarea>
<label for="philoConsequences">Konsekuensi (satu per baris)</label><textarea id="philoConsequences"></textarea>
</div>
<div class="layer-field">
<strong>Experimental Knowledge</strong>
<label for="experimentHypothesis">Hipotesis</label><textarea id="experimentHypothesis" placeholder="Pernyataan yang dapat diuji"></textarea>
<label for="experimentMethod">Metode / simulasi</label><textarea id="experimentMethod" placeholder="Prosedur yang dapat diulang"></textarea>
<label for="experimentStatus">Status hasil</label><select id="experimentStatus"><option value="planned">planned</option><option value="in_progress">in_progress</option><option value="supported">supported</option><option value="not_supported">not_supported</option><option value="inconclusive">inconclusive</option><option value="failed">failed</option><option value="replicated">replicated</option></select>
<label for="experimentConditions">Kondisi (satu per baris)</label><textarea id="experimentConditions"></textarea>
<label for="experimentVariables">Variabel (satu per baris)</label><textarea id="experimentVariables"></textarea>
<label for="experimentResults">Hasil (satu per baris)</label><textarea id="experimentResults"></textarea>
<label for="experimentRawDataRefs">Referensi data mentah (satu ID / URL per baris)</label><textarea id="experimentRawDataRefs"></textarea>
<label for="experimentReplicationOf">ID eksperimen yang direplikasi</label><input id="experimentReplicationOf">
<label for="experimentFailures">Kegagalan / batas (satu per baris)</label><textarea id="experimentFailures"></textarea>
<p class="layer-note">Status supported perlu hasil dan referensi data atau sumber; replicated juga perlu ID eksperimen asal.</p>
</div>
<div class="layer-field">
<strong>Cross-Disciplinary Relations</strong>
<label for="crossDisciplines">Disiplin ilmu (pisahkan dengan koma)</label><input id="crossDisciplines" placeholder="physics, materials">
<label for="crossRationale">Alasan hubungan konsep</label><textarea id="crossRationale" placeholder="Jelaskan hubungan yang benar-benar didukung, bukan sekadar kemiripan kata."></textarea>
<label for="crossSourceNode">Konsep asal di Knowledge Graph</label><select id="crossSourceNode"><option value="">Muat graph untuk memilih node</option></select>
<label for="crossTargetNode">Konsep tujuan di Knowledge Graph</label><select id="crossTargetNode"><option value="">Muat graph untuk memilih node</option></select>
<p class="layer-note">Pilih dua node yang sudah ada. Relasi hanya dikirim jika kedua node tersedia dan berbeda.</p>
</div>
</div>
</details>
</section>
<section class="panel">
<h2>Perjalanan ide</h2>
<div class="steps">
<div class="step"><b>01 · Ide</b><span>Tujuan dan hal yang ingin diwujudkan.</span></div>
<div class="step"><b>02 · Gambaran</b><span>Kebutuhan, teknologi terkait, dan pertanyaan yang perlu dijawab.</span></div>
<div class="step"><b>03 · Peta kenyataan</b><span>Penelitian dan data yang sudah tersedia, berikut batasnya.</span></div>
</div>
</section>
<section id="working" class="panel hidden" aria-live="polite"><h2 id="workingTitle">Sedang membuka jalur penelitian…</h2><p id="workingText">Mencari rekaman penelitian terbuka dan memeriksa apakah ada data numerik yang dapat dianalisis.</p></section>
<section id="result" class="panel result hidden">
<h2>Hasil penjelajahan</h2><p id="resultStatus" class="status"></p>
<div id="ideaSummary"></div>
<div id="sources"></div>
<div id="downloads"></div>
<div id="analysis"></div>
<details><summary>Lihat catatan teknis, model, dan keterbatasan</summary><pre id="raw"></pre></details>
</section>
<section class="panel">
<h2>Perpustakaan pengetahuan</h2>
<p>Materi ilmiah dan teknis yang sudah tersimpan di aplikasi tetap bisa dipakai dari sini.</p>
<div class="actions"><button class="secondary" id="loadLibrary">Buka isi perpustakaan</button><a class="linkbtn secondary" href="/tools">Buka alat ilmiah lengkap</a></div>
<div id="library" class="hidden"></div>
</section>
<footer>Beyond-Light adalah ruang eksplorasi dan penyaringan awal. Hasil model bukan bukti eksperimen, bukan validasi independen, dan bukan sertifikasi desain. Semua sumber, asumsi, dan batas perlu diperiksa sebelum dipakai untuk keputusan nyata.</footer>
</main>
<script>
const $=id=>document.getElementById(id);
const goal=$('goal');
function lines(id){return $(id).value.split(/\\r?\\n/).map(x=>x.trim()).filter(Boolean)}
function words(id){return $(id).value.split(',').map(x=>x.trim()).filter(Boolean)}
async function loadCrossNodes(){
 const source=$('crossSourceNode'),target=$('crossTargetNode');
 if(source.dataset.loaded==='true')return;
 source.replaceChildren();target.replaceChildren();
 try{
  const response=await fetch('/knowledge/graph');if(!response.ok)throw new Error('Graph tidak dapat dimuat');
  const graph=await response.json(),nodes=Array.isArray(graph.nodes)?graph.nodes:[];
  const addOptions=(select)=>{const empty=document.createElement('option');empty.value='';empty.textContent='Pilih konsep';select.append(empty);nodes.forEach(node=>{const option=document.createElement('option');option.value=node.id;option.textContent=(node.title||node.id)+' · '+node.kind;select.append(option)})};
  addOptions(source);addOptions(target);source.dataset.loaded='true';target.dataset.loaded='true';
 }catch(error){source.replaceChildren();target.replaceChildren();const option=document.createElement('option');option.value='';option.textContent='Graph belum tersedia: '+error.message;source.append(option);target.append(option)}
}
$('knowledgeLayers').addEventListener('toggle',()=>{if($('knowledgeLayers').open)loadCrossNodes()});
function readKnowledgeLayers(){
 const layers={};
 const historical={title:$('historyTitle').value.trim(),content:$('historyContent').value.trim(),date:$('historyDate').value.trim(),timePeriod:$('historyPeriod').value.trim(),people:words('historyPeople'),institutions:words('historyInstitutions'),sources:lines('historySources').map(ref=>({ref}))};
 if(historical.title||historical.content||historical.date||historical.timePeriod||historical.people.length||historical.institutions.length||historical.sources.length)layers.historical=historical;
 const philosophical={questions:lines('philoQuestions'),assumptions:lines('philoAssumptions'),principles:lines('philoPrinciples'),arguments:lines('philoArguments'),ethicalConsiderations:lines('philoEthics'),consequences:lines('philoConsequences')};
 if(Object.values(philosophical).some(values=>values.length))layers.philosophical=philosophical;
 const experiment={hypothesis:$('experimentHypothesis').value.trim(),method:$('experimentMethod').value.trim(),outcomeStatus:$('experimentStatus').value,conditions:lines('experimentConditions'),variables:lines('experimentVariables'),results:lines('experimentResults'),rawDataRefs:lines('experimentRawDataRefs'),replicationOf:$('experimentReplicationOf').value.trim(),failureModes:lines('experimentFailures')};
 if(experiment.hypothesis||experiment.method||experiment.conditions.length||experiment.variables.length||experiment.results.length||experiment.failureModes.length){
  if(!experiment.hypothesis||!experiment.method)throw new Error('Experimental Knowledge memerlukan hipotesis dan metode.');
  if(experiment.outcomeStatus==='supported'&&!experiment.results.length)throw new Error('Status supported memerlukan hasil yang tercatat.');
  if(experiment.outcomeStatus==='replicated'&&(!experiment.results.length||!experiment.replicationOf))throw new Error('Status replicated memerlukan hasil dan ID eksperimen asal.');
  if(['not_supported','inconclusive'].includes(experiment.outcomeStatus)&&!experiment.results.length&&!experiment.failureModes.length)throw new Error('Status not_supported/inconclusive memerlukan hasil atau catatan kegagalan.');
  if(experiment.outcomeStatus==='failed'&&!experiment.results.length&&!experiment.failureModes.length)throw new Error('Status failed memerlukan hasil atau catatan kegagalan.');
  layers.experimental=experiment;
 }
 const disciplines=words('crossDisciplines'),mappingRationale=$('crossRationale').value.trim(),sourceNodeId=$('crossSourceNode').value,targetNodeId=$('crossTargetNode').value;
 if(disciplines.length||mappingRationale||sourceNodeId||targetNodeId){
  if(new Set(disciplines.map(x=>x.toLowerCase())).size<2||!mappingRationale||!sourceNodeId||!targetNodeId||sourceNodeId===targetNodeId)throw new Error('Cross-Disciplinary memerlukan dua disiplin, alasan hubungan, dan dua node berbeda.');
  layers['cross-disciplinary']={disciplines,mappingRationale,sourceNodeId,targetNodeId,relation:'bridges'};
 }
 if(layers.historical&&!layers.historical.sources.length)layers.historical.sources=[];
 return layers;
}
$('example').onclick=()=>{goal.value='Gw ingin membawa manusia dan 100 kg barang ke Mars dalam 30 hari. Teknologi apa yang paling mendekati, apa saja yang dibutuhkan, dan batas terbesar yang harus dilewati?';goal.focus()};
function addCard(parent,title,body,url){const el=document.createElement('div');el.className='card';const h=document.createElement('strong');h.textContent=title||'Tanpa judul';el.append(h);if(body){const p=document.createElement('p');p.textContent=body;el.append(p)}if(url&&(url.startsWith('https://')||url.startsWith('http://'))){const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Buka sumber';el.append(a)}parent.append(el)}
function list(parent,title,items,render){const h=document.createElement('h3');h.textContent=title;parent.append(h);if(!items||!items.length){const p=document.createElement('p');p.textContent='Belum ada rekaman yang tersedia dari pencarian ini.';parent.append(p);return}items.forEach(x=>render(x))}
$('explore').onclick=async()=>{
 const q=goal.value.trim();if(q.length<3){goal.focus();return}
 $('explore').disabled=true;$('working').classList.remove('hidden');$('result').classList.add('hidden');$('workingTitle').textContent='Membuka jalur untuk ide lu…';$('workingText').textContent='Mencari penelitian terbuka, memeriksa file data yang tersedia, lalu menjalankan analisis lokal jika ada dataset yang cocok.';
 try{
  const knowledgeLayers=readKnowledgeLayers();
  const request={question:q};if(Object.keys(knowledgeLayers).length)request.context={knowledgeLayers};
  const response=await fetch('/research/dispatch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});
  const payload=await response.json();if(!response.ok)throw new Error(payload.error||'Penjelajahan tidak berhasil');
  const analysis=payload.analysis||{},output=analysis.output||{},rows=output.records||[],rec=rows[rows.length-1]||{},inputs=rec.inputs||{},res=rec.result||{},plan=payload.plan||{},evidence=payload.evidence||{};
  const discovery=(output.executionOrder||[]).includes('research.open-data-discovery');
  const found=discovery?(output.records||[]):(rec.searchResults||[]);
  $('resultStatus').textContent=evidence.classification||analysis.status||rec.status||'Selesai';
  $('ideaSummary').replaceChildren();
  const p=document.createElement('p');p.textContent='Ide yang dijelajahi: '+q;$('ideaSummary').append(p);
  const intro=document.createElement('p');
  intro.textContent=discovery
   ?'Rencana: '+(plan.primaryDiscipline||'general')+'. Ditemukan '+(output.recordCount||found.length)+' metadata rekaman terbuka dari Zenodo. Mode ini hanya menemukan metadata; tidak mengunduh CSV atau menjalankan screening numerik. '+(evidence.summary||'Periksa sumber asli sebelum memakai hasil.')
   :'Rencana: '+(plan.primaryDiscipline||'general')+'. Pencarian menemukan '+(inputs.openRecordsFound||0)+' rekaman terbuka. Sebanyak '+(inputs.datasetsImported||0)+' file CSV numerik berhasil diimpor untuk pemeriksaan. '+(evidence.summary||'Hasil harus dibaca bersama sumber dan keterbatasannya.');
  $('ideaSummary').append(intro);
  $('sources').replaceChildren();list($('sources'),'Penelitian yang ditemukan',found,x=>addCard($('sources'),x.title,'DOI: '+(x.doi||'tidak dicantumkan')+(x.year?' · '+x.year:'')+(x.authors?' · '+x.authors:'')+(x.description?' · '+x.description:''),x.url||x.recordUrl));
  $('downloads').replaceChildren();list($('downloads'),'Data yang berhasil dibuka',rec.downloads||[],x=>{const d=x.dataset||{},s=x.source||{};addCard($('downloads'),d.filename||x.filename||'Dataset',String(d.rows||0)+' baris data · '+(s.doi||'DOI tidak tersedia'),s.url||s.recordUrl)});
  $('analysis').replaceChildren();const h=document.createElement('h3');h.textContent='Apa yang berhasil diperiksa';$('analysis').append(h);
  const a=document.createElement('p');
  a.textContent=discovery
   ?'Belum ada analisis isi paper atau dataset. Hasil yang tersedia adalah metadata, identitas rekaman, DOI, deskripsi dan tautan sumber. Tidak ada kesimpulan ilmiah yang dibuat dari metadata saja.'
   :'Kandidat pola yang mengungguli pembanding dalam dataset: '+(res.patternCandidatesOutperformingBaselineInternally||0)+'. Pencarian model otomatis: '+(res.autonomousModelSearches||0)+'. Analisis gagal: '+(res.failedAnalyses||0)+'. Ini penyaringan internal, bukan replikasi independen atau penemuan hukum alam.';
  $('analysis').append(a);
  const checks=evidence.checks||{};const ev=document.createElement('p');ev.textContent='Status validasi: replikasi independen '+(checks.independentReplication||'belum dilakukan')+'; validasi eksperimen '+(checks.experimentalValidation||'belum dilakukan')+'.';$('analysis').append(ev);
  const sync=payload.knowledgeSync||{};const syncLine=document.createElement('p');syncLine.textContent='Mnemos Knowledge Graph: '+(sync.status||'DISABLED')+' · '+(sync.nodeCount||0)+' node · '+(sync.edgeCount||0)+' relasi. Tujuan permanen: mnemos-RLI / Knowledge.';$('analysis').append(syncLine);const syncError=(sync.error||(sync.outbox||{}).lastError||'').toString();if(syncError){const warning=document.createElement('p');warning.textContent='Catatan sinkronisasi: '+syncError;$('analysis').append(warning)}
  const limits=document.createElement('p');limits.textContent=(analysis.limitations||rec.limitations||[]).join(' ');$('analysis').append(limits);
  $('raw').textContent=JSON.stringify(payload,null,2);$('result').classList.remove('hidden');
 }catch(e){$('resultStatus').textContent='Penjelajahan gagal';$('ideaSummary').textContent=e.message;$('result').classList.remove('hidden')}
 finally{$('working').classList.add('hidden');$('explore').disabled=false}
};
$('loadLibrary').onclick=async()=>{
 const box=$('library');box.classList.remove('hidden');box.textContent='Membaca katalog lokal…';
 try{
  const [science,materials,experiments,datasets]=await Promise.all([
   fetch('/science').then(r=>r.json()),fetch('/materials').then(r=>r.json()),fetch('/published-experiments').then(r=>r.json()),fetch('/datasets').then(r=>r.json())
  ]);
  box.replaceChildren();
  const section=(title,arr,label)=>{const h=document.createElement('h3');h.textContent=title+' ('+(Array.isArray(arr)?arr.length:0)+')';box.append(h);(Array.isArray(arr)?arr:[]).slice(0,12).forEach(x=>{const m=typeof x==='object'?x:{};addCard(box,m.name||m.title||m.id||label,JSON.stringify(m).slice(0,420),m.url||m.sourceUrl)})};
  section('Konstanta, persamaan, dan model',science.equations||science.models||science,'Item katalog');
  section('Material',materials,'Material');
  section('Ringkasan eksperimen terbit',experiments,'Eksperimen');
  section('Dataset lokal',datasets,'Dataset');
 }catch(e){box.textContent='Perpustakaan belum dapat dibaca: '+e.message}
};
</script></body></html>
""";
    }
}
