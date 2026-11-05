package com.nexus.app

import android.os.Bundle
import android.content.Intent
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.*
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import com.nexus.app.data.*
import kotlinx.coroutines.launch
import kotlin.math.*

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState)
        val repo = NexusRepository(this, NexusDb.get(this).dao())
        setContent { NexusApp(repo) }
    }
}

private val ink = Color(0xFF17202A); private val muted = Color(0xFF77808B); private val blue = Color(0xFF526DFF); private val bg = Color(0xFFF6F7FA)

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun NexusApp(repo: NexusRepository) {
    val notes by repo.notes.collectAsStateWithLifecycle(initialValue = emptyList())
    val scope = rememberCoroutineScope()
    var page by remember { mutableStateOf("Notes") }; var query by remember { mutableStateOf("") }
    var editing by remember { mutableStateOf<Note?>(null) }; var create by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<Note?>(null) }; var message by remember { mutableStateOf("") }
    val pickFiles = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        val note = selected; if (uri != null && note != null) scope.launch { runCatching { repo.addAttachment(note.id, uri) }.onFailure { message = it.message ?: "Attachment failed" } }
    }
    val export = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri -> if (uri != null) scope.launch { runCatching { repo.export(uri); message="Backup exported" }.onFailure { message=it.message ?: "Export failed" } } }
    val import = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> if (uri != null) scope.launch { runCatching { repo.import(uri); message="Backup restored" }.onFailure { message=it.message ?: "Import failed" } } }
    MaterialTheme(colorScheme = lightColorScheme(primary = blue, background = bg, surface = Color.White)) {
        Scaffold(containerColor = bg, topBar = {
            Column(Modifier.fillMaxWidth().background(Color.White).statusBarsPadding()) {
                Row(Modifier.fillMaxWidth().padding(horizontal=20.dp, vertical=14.dp), verticalAlignment=Alignment.CenterVertically) {
                    Text("N", color=blue, fontSize=25.sp, fontWeight=FontWeight.Black); Spacer(Modifier.width(8.dp)); Text("NEXUS", fontSize=17.sp, fontWeight=FontWeight.Bold, letterSpacing=2.sp)
                    Spacer(Modifier.weight(1f)); TextButton(onClick={ export.launch("nexus-backup.zip") }) { Text("Export") }; TextButton(onClick={ import.launch(arrayOf("application/zip", "application/octet-stream")) }) { Text("Import") }
                }
                Row(Modifier.padding(horizontal=20.dp).fillMaxWidth().height(48.dp).background(bg, RoundedCornerShape(14.dp)).padding(horizontal=14.dp), verticalAlignment=Alignment.CenterVertically) {
                    Icon(Icons.Default.Search, null, tint=muted); Spacer(Modifier.width(8.dp)); BasicTextField(query, { query=it }, Modifier.weight(1f), singleLine=true, decorationBox={ inner -> if(query.isEmpty()) Text("Search your knowledge", color=muted); inner() }); if(query.isNotEmpty()) IconButton(onClick={query=""}, modifier=Modifier.size(28.dp)){ Icon(Icons.Default.Close,null,tint=muted) }
                }
                Row(Modifier.fillMaxWidth().padding(horizontal=18.dp, vertical=10.dp), horizontalArrangement=Arrangement.spacedBy(8.dp)) { listOf("Notes","Graph").forEach { label -> FilterChip(selected=page==label,onClick={page=label},label={Text(label)},) } }
            }
        }, floatingActionButton = { if(page=="Notes") FloatingActionButton(onClick={create=true}, containerColor=blue, contentColor=Color.White){ Icon(Icons.Default.Add,"New note") } }, snackbarHost={ SnackbarHost(remember { SnackbarHostState() }) }) { padding ->
            Column(Modifier.padding(padding).fillMaxSize()) {
                if(message.isNotBlank()) { LaunchedEffect(message){ kotlinx.coroutines.delay(2200); message="" }; Text(message, Modifier.fillMaxWidth().background(Color(0xFFE7ECFF)).padding(12.dp), color=ink) }
                if(page=="Notes") NoteList(notes.filter { query.isBlank() || (it.title+it.body+it.tags).contains(query, true) }, onOpen={editing=it}, onDelete={ n -> scope.launch { repo.delete(n.id) } })
                else GraphScreen(notes, query, repo, onOpen={editing=it})
            }
        }
        if(create || editing!=null) NoteEditor(repo, editing, onClose={ create=false; editing=null }, onSaved={ create=false; editing=null; message="Note saved" }, onAttach={ selected=it; pickFiles.launch(arrayOf("image/*","video/*","application/pdf","application/zip")) })
    }
}

@Composable private fun NoteList(notes: List<Note>, onOpen:(Note)->Unit, onDelete:(Note)->Unit) {
    if(notes.isEmpty()) { Column(Modifier.fillMaxSize().padding(32.dp), verticalArrangement=Arrangement.Center, horizontalAlignment=Alignment.CenterHorizontally) { Icon(Icons.Default.Favorite, null, tint=blue, modifier=Modifier.size(38.dp)); Spacer(Modifier.height(14.dp)); Text("Your knowledge starts here", fontWeight=FontWeight.SemiBold, fontSize=18.sp); Text("Create a note, connect ideas, and see them come together.", color=muted, modifier=Modifier.padding(top=6.dp)) }; return }
    LazyColumn(Modifier.fillMaxSize(), contentPadding=PaddingValues(start=18.dp,end=18.dp,top=6.dp,bottom=100.dp), verticalArrangement=Arrangement.spacedBy(10.dp)) {
        items(notes, key={it.id}) { n -> Card(Modifier.fillMaxWidth().clickable { onOpen(n) }, shape=RoundedCornerShape(17.dp), colors=CardDefaults.cardColors(containerColor=Color.White)) {
            Column(Modifier.padding(16.dp)) { Row(verticalAlignment=Alignment.CenterVertically) { Text(n.title, Modifier.weight(1f), fontWeight=FontWeight.SemiBold, fontSize=17.sp, color=ink, maxLines=1); IconButton(onClick={onDelete(n)}, modifier=Modifier.size(32.dp)){Icon(Icons.Default.Delete,null,tint=muted)} }
                Text(n.body.replace(Regex("[#*_`]"), "").take(140).ifBlank { "No content" }, color=muted, maxLines=2, fontSize=14.sp)
                if(n.tags.isNotBlank()) Row(Modifier.padding(top=12.dp), horizontalArrangement=Arrangement.spacedBy(6.dp)) { n.tags.split(",").take(4).forEach { AssistChip(onClick={}, label={Text(it.trim(),fontSize=11.sp)}, modifier=Modifier.height(30.dp)) } }
            }
        } }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun NoteEditor(repo:NexusRepository, note:Note?, onClose:()->Unit, onSaved:()->Unit, onAttach:(Note)->Unit) {
    val scope= rememberCoroutineScope(); val context=LocalContext.current; var title by remember(note?.id){ mutableStateOf(note?.title ?: "") }; var body by remember(note?.id){ mutableStateOf(note?.body ?: "") }; var tags by remember(note?.id){ mutableStateOf(note?.tags ?: "") }; var preview by remember { mutableStateOf(false) }
    var currentId by remember(note?.id) { mutableStateOf(note?.id) }; var attachments by remember { mutableStateOf(emptyList<Attachment>()) }; var backlinks by remember { mutableStateOf(emptyList<Note>()) }; var linked by remember { mutableStateOf(emptyList<Note>()) }; var suggestions by remember { mutableStateOf(emptyList<Pair<Note,Double>>()) }; var all by remember { mutableStateOf(emptyList<Note>()) }; var linkPick by remember { mutableStateOf("") }
    LaunchedEffect(currentId, note?.id) { if(currentId!=null) { attachments=repo.attachments(currentId!!); val ls=repo.linksFor(currentId!!); val allNotes=repo.search(""); all=allNotes; backlinks=ls.filter{it.toId==currentId}.mapNotNull{l->allNotes.find{it.id==l.fromId}}; linked=ls.filter{it.fromId==currentId}.mapNotNull{l->allNotes.find{it.id==l.toId}}; val n=repo.search("").find{it.id==currentId}; if(n!=null) suggestions=repo.suggestions(n) } else all=repo.search("") }
    ModalBottomSheet(onDismissRequest=onClose, containerColor=Color.White, sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true)) {
        Column(Modifier.fillMaxWidth().fillMaxHeight(.96f).padding(horizontal=20.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically) { Text(if(note==null) "NEW NOTE" else "EDIT NOTE", fontSize=12.sp, letterSpacing=1.5.sp, color=muted, fontWeight=FontWeight.Bold); Spacer(Modifier.weight(1f)); TextButton(onClick={preview=!preview}) { Text(if(preview) "Edit" else "Preview") }; TextButton(onClick={onClose}) { Text("Close") } }
            BasicTextField(title,{title=it},Modifier.fillMaxWidth().padding(top=8.dp,bottom=12.dp),textStyle= androidx.compose.ui.text.TextStyle(fontSize=25.sp,fontWeight=FontWeight.Bold,color=ink),decorationBox={inner->if(title.isEmpty()) Text("Untitled",fontSize=25.sp,color=muted);inner()})
            BasicTextField(tags,{tags=it},Modifier.fillMaxWidth().background(bg,RoundedCornerShape(10.dp)).padding(12.dp),singleLine=true,decorationBox={inner->if(tags.isEmpty())Text("Tags, comma separated",color=muted);inner()})
            Spacer(Modifier.height(12.dp)); if(preview) MarkdownPreview(body, Modifier.weight(1f).fillMaxWidth()) else BasicTextField(body,{body=it},Modifier.weight(1f).fillMaxWidth().background(bg,RoundedCornerShape(14.dp)).padding(14.dp),textStyle=androidx.compose.ui.text.TextStyle(fontSize=16.sp,color=ink,lineHeight=24.sp),decorationBox={inner->if(body.isEmpty())Text("Write in Markdown…",color=muted);inner()})
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp), modifier=Modifier.padding(top=10.dp)) { OutlinedButton(onClick={ if(currentId!=null) onAttach(Note(currentId!!,title,body,tags,System.currentTimeMillis(),System.currentTimeMillis())) else { scope.launch { currentId=repo.save(null,title,body,tags); onAttach(Note(currentId!!,title,body,tags,0,0)) } } }) { Icon(Icons.Default.Add,null); Text("Files") }; Spacer(Modifier.weight(1f)); Button(onClick={ scope.launch { currentId=repo.save(currentId,title,body,tags); onSaved() } }) { Text("Save") } }
            if(currentId!=null) Column(Modifier.heightIn(max=190.dp).verticalScroll(rememberScrollState()).padding(top=12.dp,bottom=20.dp)) {
                attachments.forEach { a -> Row(verticalAlignment=Alignment.CenterVertically) { Icon(Icons.Default.Add,null,tint=blue); Text(a.name,Modifier.weight(1f).clickable { runCatching { val uri=FileProvider.getUriForFile(context,"${context.packageName}.files",java.io.File(a.localPath)); context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri,a.mimeType).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)) }.onFailure { Toast.makeText(context,"No app can open this file",Toast.LENGTH_SHORT).show() } },maxLines=1); IconButton(onClick={scope.launch{repo.removeAttachment(a);attachments=repo.attachments(currentId!!)}}){Icon(Icons.Default.Close,null)} } }
                if(linked.isNotEmpty()) Text("LINKS TO", fontSize=10.sp,color=muted,fontWeight=FontWeight.Bold); linked.forEach{ Text("↗ ${it.title}",Modifier.clickable{linkPick=it.id}.padding(vertical=3.dp),color=blue) }
                if(backlinks.isNotEmpty()) Text("BACKLINKS", fontSize=10.sp,color=muted,fontWeight=FontWeight.Bold); backlinks.forEach{ Text("↙ ${it.title}",Modifier.padding(vertical=3.dp),color=ink) }
                if(suggestions.isNotEmpty()) Text("RELATED IDEAS", fontSize=10.sp,color=muted,fontWeight=FontWeight.Bold); suggestions.forEach { (s,score)-> Row(verticalAlignment=Alignment.CenterVertically){ Text(s.title,Modifier.weight(1f),color=ink); Text("${(score*100).toInt()}%",color=muted,fontSize=12.sp); TextButton(onClick={scope.launch{repo.link(currentId!!,s.id); linked=linked+s}}){Text("Link")} } }
                Text("ADD LINK", fontSize=10.sp,color=muted,fontWeight=FontWeight.Bold); all.filter{it.id!=currentId}.forEach { n -> if(linked.any{it.id==n.id}) Row(verticalAlignment=Alignment.CenterVertically){ Text("↗ ${n.title}",Modifier.weight(1f)); TextButton(onClick={scope.launch{repo.unlink(currentId!!,n.id);linked=linked.filterNot{it.id==n.id}}}){Text("Unlink")} } else TextButton(onClick={scope.launch{repo.link(currentId!!,n.id);linked=linked+n}}){Text("+ ${n.title}")} }
            }
        }
    }
}

@Composable private fun MarkdownPreview(markdown:String, modifier:Modifier=Modifier) { Column(modifier.verticalScroll(rememberScrollState()).padding(14.dp)) { markdown.lines().forEach { line -> when { line.startsWith("### ")->Text(line.drop(4),fontSize=18.sp,fontWeight=FontWeight.Bold,color=ink); line.startsWith("## ")->Text(line.drop(3),fontSize=21.sp,fontWeight=FontWeight.Bold,color=ink); line.startsWith("# ")->Text(line.drop(2),fontSize=25.sp,fontWeight=FontWeight.Bold,color=ink); line.startsWith("- ")->Text("• ${line.drop(2)}",fontSize=16.sp,color=ink); line.isBlank()->Spacer(Modifier.height(8.dp)); else->Text(line.replace(Regex("\\*\\*(.*?)\\*\\*"),"$1").replace("`",""),fontSize=16.sp,color=ink,lineHeight=24.sp) } } } }

@Composable private fun GraphScreen(notes:List<Note>, query:String, repo:NexusRepository, onOpen:(Note)->Unit) {
    val scope= rememberCoroutineScope(); var links by remember{mutableStateOf(emptyList<Link>())}; var activeTags by remember{mutableStateOf(setOf<String>())}; var picked by remember{mutableStateOf<Note?>(null)}
    LaunchedEffect(notes) { links=repo.links() }
    val tags=notes.flatMap{it.tags.split(",").map(String::trim)}.filter{it.isNotBlank()}.distinct().take(12)
    Column(Modifier.fillMaxSize()) {
        if(tags.isNotEmpty()) LazyRow(contentPadding=PaddingValues(horizontal=16.dp), horizontalArrangement=Arrangement.spacedBy(6.dp)) { items(tags){tag->FilterChip(selected=tag in activeTags,onClick={activeTags=if(tag in activeTags) activeTags-tag else activeTags+tag},label={Text(tag)})} }
        Box(Modifier.weight(1f).fillMaxWidth().padding(12.dp).background(Color(0xFF101827),RoundedCornerShape(20.dp))) {
            GraphCanvas(notes.filter { (query.isBlank() || (it.title+it.tags).contains(query,true)) && (activeTags.isEmpty() || it.tags.split(",").any{t->t.trim() in activeTags}) },links, onOpen={picked=it;onOpen(it)})
            Text("DRAG TO ROTATE  ·  PINCH TO ZOOM",Modifier.align(Alignment.BottomCenter).padding(14.dp),fontSize=10.sp,color=Color(0xFF8592A8),letterSpacing=1.sp)
        }
        picked?.let { n -> Card(Modifier.fillMaxWidth().padding(12.dp).clickable{onOpen(n)}) { Column(Modifier.padding(14.dp)){Text(n.title,fontWeight=FontWeight.Bold);Text(n.body.take(90),color=muted,maxLines=2)} } }
    }
}

@Composable private fun GraphCanvas(notes:List<Note>, links:List<Link>, onOpen:(Note)->Unit) {
    var rotation by remember { mutableStateOf(Offset(.25f,.16f)) }; var zoom by remember{mutableFloatStateOf(1f)}; val drawn = remember { mutableMapOf<String, Offset>() }
    Canvas(Modifier.fillMaxSize().pointerInput(notes,zoom) {
        detectTransformGestures { _, pan, scale, _ -> rotation += Offset(pan.x/size.width,pan.y/size.height); zoom=(zoom*scale).coerceIn(.55f,2.6f) }
    }.pointerInput(notes,rotation,zoom) { detectTapGestures { tap -> drawn.minByOrNull { (it.value-tap).getDistance() }?.let { hit -> if ((hit.value-tap).getDistance()<45f) notes.find { it.id==hit.key }?.let(onOpen) } } }) {
        val center=Offset(size.width/2,size.height/2); val radius=min(size.width,size.height)*.36f*zoom
        val points=notes.mapIndexed { i,n -> val seed=n.id.hashCode().toLong().ushr(1); val theta=(i*2.399963+rotation.x*5).toFloat(); val zz=(((seed%1000)/1000f)-.5f)*.8f; val y=(1f-2f*(i+.5f)/max(notes.size,1)); val r=sqrt(max(0f,1-y*y)); val x=r*cos(theta); val z=r*sin(theta); val ry=y*cos(rotation.y*2)-z*sin(rotation.y*2); val rz=y*sin(rotation.y*2)+z*cos(rotation.y*2)+zz; val perspective=1f/(1f+rz*.24f); Triple(Offset(center.x+x*radius*perspective,center.y+ry*radius*perspective),perspective,n) }
        val positions=points.associateBy{it.third.id}; drawn.clear(); points.forEach { drawn[it.third.id]=it.first }; links.forEach { l -> val a=positions[l.fromId]?.first; val b=positions[l.toId]?.first; if(a!=null&&b!=null) drawLine(Color(0x665F79FF),a,b,1.4f) }
        for(i in points.indices) for(j in i+1 until points.size) { val a=points[i].third; val b=points[j].third; if(links.any{it.fromId==a.id&&it.toId==b.id||it.fromId==b.id&&it.toId==a.id}) continue; val ta=(a.title+" "+a.tags+" "+a.body).lowercase().split(Regex("[^\\p{L}\\p{N}]+" )).filter{it.length>3}.toSet(); val tb=(b.title+" "+b.tags+" "+b.body).lowercase().split(Regex("[^\\p{L}\\p{N}]+" )).filter{it.length>3}.toSet(); val score=ta.intersect(tb).size.toFloat()/max(1,ta.union(tb).size); if(score>.15f) drawLine(Color(0x334ABBC8),points[i].first,points[j].first,1f) }
        points.sortedBy{it.second}.forEach { (p,depth,n) -> val rad=(5f+3f*depth).coerceAtMost(9f); drawCircle(Color(0x445B76FF),rad*2.2f,p); drawCircle(if(n.tags.isNotBlank()) Color(0xFF69D6CB) else Color(0xFF7893FF),rad,p); drawContext.canvas.nativeCanvas.apply { val paint=android.graphics.Paint().apply { color=android.graphics.Color.WHITE; textSize=11f; textAlign=android.graphics.Paint.Align.CENTER; isAntiAlias=true }; drawText(n.title.take(16),p.x,p.y+rad+14,paint) } }
    }
}
