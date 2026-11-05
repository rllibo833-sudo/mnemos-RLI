package com.nexus.app.data

import androidx.room.*

@Entity(tableName = "notes", indices = [Index("updatedAt")])
data class Note(@PrimaryKey val id: String, val title: String, val body: String, val tags: String = "", val createdAt: Long, val updatedAt: Long)

@Entity(tableName = "links", primaryKeys = ["fromId", "toId"])
data class Link(@ColumnInfo(index = true) val fromId: String, @ColumnInfo(index = true) val toId: String, val kind: String = "manual")

@Entity(tableName = "attachments")
data class Attachment(@PrimaryKey val id: String, @ColumnInfo(index = true) val noteId: String, val name: String, val mimeType: String, val localPath: String, val addedAt: Long)

data class NoteWithAttachments(@Embedded val note: Note, @Relation(parentColumn = "id", entityColumn = "noteId") val attachments: List<Attachment>)

@Dao interface NexusDao {
    @Query("SELECT * FROM notes ORDER BY updatedAt DESC") fun observeNotes(): kotlinx.coroutines.flow.Flow<List<Note>>
    @Query("SELECT * FROM notes ORDER BY updatedAt DESC") suspend fun allNotes(): List<Note>
    @Query("SELECT * FROM notes WHERE id = :id") suspend fun note(id: String): Note?
    @Query("SELECT * FROM notes WHERE title LIKE '%' || :q || '%' OR body LIKE '%' || :q || '%' OR tags LIKE '%' || :q || '%' ORDER BY updatedAt DESC") suspend fun search(q: String): List<Note>
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun putNote(note: Note)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun putNotes(notes: List<Note>)
    @Query("DELETE FROM notes WHERE id = :id") suspend fun deleteNote(id: String)
    @Query("SELECT * FROM links") suspend fun allLinks(): List<Link>
    @Query("SELECT * FROM links WHERE fromId = :id OR toId = :id") suspend fun linksFor(id: String): List<Link>
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun putLink(link: Link)
    @Query("DELETE FROM links WHERE fromId = :a AND toId = :b") suspend fun deleteLink(a: String, b: String)
    @Query("DELETE FROM links WHERE fromId = :id OR toId = :id") suspend fun deleteLinksFor(id: String)
    @Query("DELETE FROM links") suspend fun clearLinks()
    @Query("DELETE FROM notes") suspend fun clearNotes()
    @Query("SELECT * FROM attachments WHERE noteId = :id ORDER BY addedAt") suspend fun attachments(id: String): List<Attachment>
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun putAttachment(a: Attachment)
    @Query("DELETE FROM attachments WHERE id = :id") suspend fun deleteAttachment(id: String)
    @Query("DELETE FROM attachments WHERE noteId = :id") suspend fun deleteAttachmentsFor(id: String)
    @Query("SELECT * FROM attachments") suspend fun allAttachments(): List<Attachment>
}

@Database(entities = [Note::class, Link::class, Attachment::class], version = 1, exportSchema = false)
abstract class NexusDb : RoomDatabase() {
    abstract fun dao(): NexusDao
    companion object {
        @Volatile private var INSTANCE: NexusDb? = null
        fun get(context: android.content.Context): NexusDb = INSTANCE ?: synchronized(this) {
            INSTANCE ?: Room.databaseBuilder(context.applicationContext, NexusDb::class.java, "nexus.db").build().also { INSTANCE = it }
        }
    }
}
