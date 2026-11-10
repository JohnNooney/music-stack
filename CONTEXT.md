# Home music stack

A self-hosted music setup where Deemix downloads music into a single on-disk library that Jellyfin serves, organised so every song is browsable by its real artist and album while playlists remain playable.

## Language

### Library

**Library root**:
The single directory that Deemix downloads into and Jellyfin scans as its music library.
_Avoid_: media folder, downloads folder

**Album folder**:
A folder at the library root, named `<Album artist> - <Album>`, that holds tracks from exactly one album and nothing else.
_Avoid_: release folder, artist folder

**Partial album**:
An album folder holding only some of the album's tracks, often just one, because only those songs were wanted.
_Avoid_: single, orphan track

**Pseudo-album**:
A folder Jellyfin treats as one album even though it holds tracks from many albums; the defect this project removes.
_Avoid_: fake album, merged album

### Songs

**Song**:
One recording, identified by its ISRC (or by artist + title when no ISRC exists), regardless of how many files hold it.
_Avoid_: track (when meaning the recording), file

**Canonical copy**:
The single file kept for a song; every playlist that includes the song points to it.
_Avoid_: master, original

**Duplicate copy**:
Any other file holding the same song as a canonical copy; it is removed from the library to the trash, never deleted outright.
_Avoid_: dupe, loser

**Album artist**:
The artist credited for the whole album (may be "Various Artists" for a compilation); decides which album folder a song lives in.
_Avoid_: band, main artist

**Track artist**:
The artist credited on an individual song; decides which artist pages the song appears on, independent of its album artist.
_Avoid_: performer, featured artist

### Playlists

**Playlist**:
An ordered list of songs owned by a Jellyfin user and edited in Jellyfin; it never owns or contains audio.
_Avoid_: playlist folder, mix

**Playlist file**:
A `.m3u`/`.m3u8` file listing canonical copies by path relative to the library root; only ever an import source or an export, never the live playlist.
_Avoid_: m3u (as a synonym for playlist)

**Playlist import**:
Bringing a playlist file written by Deemix (or a pre-migration playlist file) into the matching Jellyfin playlist, after which the file leaves the scanned library.
_Avoid_: playlist sync (when meaning the one direction only)

**Playlist export**:
A playlist file written from a Jellyfin playlist so its contents are backed up and its history is reviewable in git.
_Avoid_: backup playlist

**Legacy playlist folder**:
A `Playlists/<Name>/` folder from before the migration that held a playlist's audio directly; a source of pseudo-albums, never recreated.
_Avoid_: playlist directory

**Playlist artifacts**:
Non-audio leftovers from a playlist download (failed-download log, playlist cover), kept per playlist in a hidden part of the library that Jellyfin does not scan.
_Avoid_: extras, junk

### Operations

**Migration**:
The one-off move of every song out of the legacy playlist folders into album folders, with playlist files rewritten to point at the canonical copies.
_Avoid_: reorganisation, cleanup

**Deemix path**:
The exact path Deemix would generate for a song; migrated songs are placed at their Deemix path so later downloads recognise them as already present.
_Avoid_: target path, expected path

**Trash**:
A holding area outside the library root where duplicate copies and stale files go, recoverable until emptied by hand.
_Avoid_: recycle bin, deleted files

**Inventory**:
A text listing of every audio file in the library (path, ISRC, size, artist, album, title), tracked in git as the reviewable record of layout changes.
_Avoid_: manifest (that is a per-run undo log), index
