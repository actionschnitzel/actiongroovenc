import logging
import threading
from gettext import gettext as _

from gi.repository import Adw, GLib, Gtk

from .upload import upload_to_music


class UploadDialog(Adw.Dialog):
    def __init__(self, client):
        super().__init__(title=_("Upload to Nextcloud"), content_width=520, content_height=480)
        self.client = client
        self.paths = []

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)
        toolbar.set_content(box)
        self.set_child(toolbar)

        description = Gtk.Label(label=_("Files are uploaded to the folder configured in Nextcloud Music. Existing files are not overwritten."))
        description.set_wrap(True)
        description.set_xalign(0)
        box.append(description)

        buttons = Gtk.Box(spacing=6)
        self.files_button = Gtk.Button(label=_("Choose files"))
        self.folder_button = Gtk.Button(label=_("Choose folder"))
        self.files_button.connect("clicked", self._choose_files)
        self.folder_button.connect("clicked", self._choose_folder)
        buttons.append(self.files_button)
        buttons.append(self.folder_button)
        box.append(buttons)

        self.selection = Gtk.Label(label=_("No files selected"))
        self.selection.set_xalign(0)
        self.selection.set_wrap(True)
        box.append(self.selection)

        self.upload_button = Gtk.Button(label=_("Start upload"))
        self.upload_button.add_css_class("suggested-action")
        self.upload_button.set_sensitive(False)
        self.upload_button.connect("clicked", self._start_upload)
        box.append(self.upload_button)

        self.status = Gtk.Label(label="")
        self.status.set_xalign(0)
        self.status.set_wrap(True)
        box.append(self.status)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.details = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll.set_child(self.details)
        box.append(scroll)

    def _choose_files(self, _button):
        chooser = Gtk.FileDialog(title=_("Choose files"))
        chooser.open_multiple(self.get_root(), None, self._files_selected)

    def _choose_folder(self, _button):
        chooser = Gtk.FileDialog(title=_("Choose folder"))
        chooser.select_folder(self.get_root(), None, self._folder_selected)

    def _files_selected(self, chooser, result):
        try:
            files = chooser.open_multiple_finish(result)
            self._set_selection([files.get_item(i) for i in range(files.get_n_items())])
        except GLib.Error as exc:
            self._selection_error(exc)

    def _folder_selected(self, chooser, result):
        try:
            self._set_selection([chooser.select_folder_finish(result)])
        except GLib.Error as exc:
            self._selection_error(exc)

    def _selection_error(self, exc):
        if not exc.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED) and not exc.matches(
            Gtk.DialogError.quark(), Gtk.DialogError.CANCELLED
        ):
            logging.error("File selection failed: %s", exc)
            self.status.set_text(_("File selection failed: %(reason)s") % {"reason": str(exc)})

    def _set_selection(self, files):
        paths = [file.get_path() for file in files]
        if any(path is None for path in paths):
            self.paths = []
            self.selection.set_text(_("No files selected"))
            self.upload_button.set_sensitive(False)
            self.status.set_text(_("Only local files and folders can be uploaded."))
            return
        self.paths = paths
        if len(paths) > 1:
            self.selection.set_text(_("%(count)d files selected") % {"count": len(paths)})
        else:
            self.selection.set_text(paths[0] if paths else _("No files selected"))
        self.status.set_text("")
        self.upload_button.set_sensitive(bool(paths))

    def _start_upload(self, _button):
        try:
            server, username, auth = self.client.upload_credentials()
            settings_headers = self.client.cookie_headers
        except GLib.Error as exc:
            logging.error("Unable to retrieve upload credentials: %s", exc)
            self.status.set_text(_("Unable to retrieve login credentials."))
            return
        self.files_button.set_sensitive(False)
        self.folder_button.set_sensitive(False)
        self.upload_button.set_sensitive(False)
        self.set_can_close(False)
        self.details.get_buffer().set_text("")
        self.status.set_text(_("Finding the Nextcloud Music folder and uploading…"))

        def report(message):
            GLib.idle_add(self._append_detail, message)

        def worker():
            try:
                uploaded, failed, scan_success = upload_to_music(server, username, auth, self.paths, report, settings_headers)
                GLib.idle_add(self._finished, uploaded, failed, scan_success)
            except Exception:
                logging.exception("Unexpected upload failure")
                GLib.idle_add(self._unexpected_error)

        threading.Thread(target=worker, daemon=True).start()

    def _append_detail(self, message):
        buffer = self.details.get_buffer()
        buffer.insert(buffer.get_end_iter(), message + "\n")
        return False

    def _finished(self, uploaded, failed, scan_success):
        if scan_success is False:
            message = _("Upload finished: %(uploaded)d uploaded, %(failed)d failed or skipped. Music scan failed; see details.")
        else:
            message = _("Upload finished: %(uploaded)d uploaded, %(failed)d failed or skipped.")
        self.status.set_text(message % {"uploaded": uploaded, "failed": failed})
        self._enable_controls()
        return False

    def _unexpected_error(self):
        self.status.set_text(_("Upload failed unexpectedly. See the application log for details."))
        self._enable_controls()
        return False

    def _enable_controls(self):
        self.set_can_close(True)
        self.files_button.set_sensitive(True)
        self.folder_button.set_sensitive(True)
        self.upload_button.set_sensitive(bool(self.paths))
