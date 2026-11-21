#  ActionGrooveNC

<p align="center">
  <img src="data/icons/hicolor/scalable/apps/actiongroove_NC.png"
       alt="Screenshot of ActionGrooveNC"
       title="Screenshot of ActionGrooveNC"
       width="30%">
</p>

This project is a fork of [NextGroove](https://gitlab.gnome.org/dean36963/nextgroove). Since the original project is no longer maintained, ActionGrooveNC aims to continue its development, improve the existing codebase, and introduce further enhancements.


![a](screenshots/screenshot1.png "Screenshot of ActionGrooveNC")

## Current Capabilities

 - Connects to a Nextcloud instance of your choice.
 - Can select music from an album view (most recent first), filtering by an artist first, or playlists.
 - Allows adding albums/playlists/songs to the queue, either at the end or after the current song.
 - Basic MPRIS support allowing to be controlled via common controls and shortcuts.
 - Drag&Drop to Queue 
 - Caches album art, and can optionally cache songs.
 - Can save current play queue as a playlist.
 - Uploads selected files or folders to the configured Nextcloud Music folder without overwriting existing files.
 - Scans new and modified music files after an upload.
 - Refreshes the collection from the main menu or with Ctrl+R.
 - Adaptive and works at mobile resolution.
 - Does *not* support other media like podcasts.

## Uploading music

1. Log in to Nextcloud and select **Upload** from the main menu or press Ctrl+U.
2. Choose individual local files or a local folder, then select **Start upload**.
3. Check the upload and scan results in the dialog. After the scan, select
   **Refresh** from the main menu or press Ctrl+R to update the collection.

Uploads preserve the selected folder and its subfolders, including non-audio
files such as cover art. Symbolic links are not uploaded. Before every upload,
the app retrieves the configured folder from Nextcloud Music and displays the
destination. If the configured path is `/`, files are uploaded to the root of
the user's Nextcloud files. If the settings or folder cannot be accessed, the
upload is stopped. Existing files are skipped, not overwritten.

After at least one successful upload, the app checks the entire Nextcloud Music
collection for new and modified music files and scans those that need it.
Scan failures are reported separately from upload failures.

When running from the source tree with `run-dev.py`, `msgfmt` from the gettext
package is required to compile the translations.

## Contributing and Issues

Haven't defined a contributing guide yet at such an early stage.
Pushing the project out there to see if anyone finds this useful.

Raising issues is welcome, but I don't devote much time to this project.

A lot of the current code needs a heavy refactor into something much tidier
and using preferred patterns of signal based connections.
