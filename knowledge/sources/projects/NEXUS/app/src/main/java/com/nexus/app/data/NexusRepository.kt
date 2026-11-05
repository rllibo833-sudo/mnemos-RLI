package com.nexus.app.data

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.flow.Flow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

class NexusRepository(private val context: Context, private val dao: NexusDao) {
    val notes: Flow<List<Note>> = dao.observeNotes()
    suspend fun save(id: String?, title: String, body: String, tags: String): String {
        val now = System.currentTimeMillis(); val old = id?.let { dao.note(it) }
        val key = old?.id ?: UUID.randomUUID().toString()
        dao.putNote(Note(key, title.trim().ifBlank { "Untitled" }, body, tags.split(',').map { it.trim() }.filter { it.isNotBlank() }.distinct().joinToString(", "), old?.createdAt ?: now, now))
        return key
    }
    suspend fun delete(id: String) { dao.deleteLinksFor(id); dao.attachments(id).forEach { File(it.localPath).delete() }; dao.deleteAttachmentsFor(id); dao.deleteNote(id) }
    suspend fun search(q: String) = if (q.isBlank()) dao.allNotes() else dao.search(q.trim())
    suspend fun links() = dao.allLinks()
    suspend fun linksFor(id: String) = dao.linksFor(id)
    suspend fun link(a: String, b: String) { if (a != b) dao.putLink(Link(a, b)) }
    suspend fun unlink(a: String, b: String) = dao.deleteLink(a, b)
    suspend fun attachments(id: String) = dao.attachments(id)
    suspend fun addAttachment(noteId: String, uri: Uri): Attachment {
        val resolver = context.contentResolver
        val name = resolver.query(uri, null, null, null, null)?.use { c -> if (c.moveToFirst()) c.getString(c.getColumnIndexOrThrow(OpenableColumns.DISPLAY_NAME)) else null } ?: "attachment"
        val type = resolver.getType(uri) ?: "application/octet-stream"
        val dir = File(context.filesDir, "attachments").apply { mkdirs() }
        val file = File(dir, "${UUID.randomUUID()}_${name.replace(Regex("[^A-Za-z0-9._-]"), "_")}")
        resolver.openInputStream(uri)?.use { input -> file.outputStream().use(input::copyTo) } ?: error("Could not read selected file")
        val a = Attachment(UUID.randomUUID().toString(), noteId, name, type, file.absolutePath, System.currentTimeMillis()); dao.putAttachment(a); return a
    }
    suspend fun removeAttachment(a: Attachment) { File(a.localPath).delete(); dao.deleteAttachment(a.id) }

    // Cosine similarity over normalized terms provides offline semantic-style suggestions.
    suspend fun suggestions(note: Note, limit: Int = 5): List<Pair<Note, Double>> = dao.allNotes().asSequence().filter { it.id != note.id }
        .map { it to cosine(tokens(note.title + " " + note.tags + " " + note.body), tokens(it.title + " " + it.tags + " " + it.body)) }
        .filter { it.second >= .12 }.sortedByDescending { it.second }.take(limit).toList()
    private fun tokens(s: String) = s.lowercase().split(Regex("[^\\p{L}\\p{N}]+" )).filter { it.length > 2 }.groupingBy { it }.eachCount()
    private fun cosine(a: Map<String, Int>, b: Map<String, Int>): Double {
        if (a.isEmpty() || b.isEmpty()) return 0.0
        val dot = a.entries.sumOf { (k, v) -> v * (b[k] ?: 0) }.toDouble()
        return dot / (kotlin.math.sqrt(a.values.sumOf { it * it }.toDouble()) * kotlin.math.sqrt(b.values.sumOf { it * it }.toDouble()))
    }

    suspend fun export(uri: Uri) {
        val notes = dao.allNotes(); val links = dao.allLinks(); val attachments = dao.allAttachments()
        val json = JSONObject().put("version", 1).put("notes", JSONArray().also { arr -> notes.forEach { n -> arr.put(JSONObject().put("id", n.id).put("title", n.title).put("body", n.body).put("tags", n.tags).put("createdAt", n.createdAt).put("updatedAt", n.updatedAt)) } })
            .put("links", JSONArray().also { arr -> links.forEach { arr.put(JSONObject().put("from", it.fromId).put("to", it.toId).put("kind", it.kind)) } })
        context.contentResolver.openOutputStream(uri)?.use { out -> ZipOutputStream(out).use { zip ->
            zip.putNextEntry(ZipEntry("nexus.json")); zip.write(json.toString(2).toByteArray()); zip.closeEntry()
            attachments.forEach { a -> val f = File(a.localPath); if (f.exists()) { zip.putNextEntry(ZipEntry("attachments/${a.id}/${a.name}")); f.inputStream().use { it.copyTo(zip) }; zip.closeEntry() } }
            zip.putNextEntry(ZipEntry("attachments.json")); zip.write(JSONArray().also { ar -> attachments.forEach { a -> ar.put(JSONObject().put("id",a.id).put("noteId",a.noteId).put("name",a.name).put("mime",a.mimeType).put("path","attachments/${a.id}/${a.name}").put("addedAt",a.addedAt)) } }.toString(2).toByteArray()); zip.closeEntry()
        } } ?: error("Cannot create backup")
    }
    suspend fun import(uri: Uri) {
        val entries = linkedMapOf<String, ByteArray>()
        context.contentResolver.openInputStream(uri)?.use { input -> ZipInputStream(input).use { zip -> var e = zip.nextEntry; while (e != null) { if (!e.isDirectory) entries[e.name] = zip.readBytes(); e = zip.nextEntry } } } ?: error("Cannot open backup")
        val root = JSONObject(entries["nexus.json"]?.decodeToString() ?: error("Invalid NEXUS backup"))
        val ns = mutableListOf<Note>(); val arr = root.getJSONArray("notes")
        for (i in 0 until arr.length()) { val n = arr.getJSONObject(i); ns += Note(n.getString("id"), n.getString("title"), n.optString("body"), n.optString("tags"), n.optLong("createdAt"), n.optLong("updatedAt")) }
        val ls = mutableListOf<Link>(); val la = root.getJSONArray("links")
        for (i in 0 until la.length()) { val l = la.getJSONObject(i); ls += Link(l.getString("from"), l.getString("to"), l.optString("kind", "manual")) }
        val aa = mutableListOf<Attachment>(); val af = entries["attachments.json"]
        if (af != null) { val ja = JSONArray(af.decodeToString()); for (i in 0 until ja.length()) { val x=ja.getJSONObject(i); val path=x.getString("path"); val data=entries[path] ?: continue; val attachmentId=x.getString("id"); require(attachmentId.matches(Regex("[A-Za-z0-9_-]{1,128}"))) { "Invalid attachment ID" }; val safeName=File(path).name.replace(Regex("[^A-Za-z0-9._-]"), "_"); val file=File(context.filesDir,"attachments/${attachmentId}_$safeName").apply { parentFile?.mkdirs(); writeBytes(data) }; aa += Attachment(attachmentId,x.getString("noteId"),x.getString("name"),x.getString("mime"),file.absolutePath,x.optLong("addedAt")) } }
        ns.forEach { dao.putNote(it) }; ls.forEach { dao.putLink(it) }; aa.forEach { dao.putAttachment(it) }
    }
}
