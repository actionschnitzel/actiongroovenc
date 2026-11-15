import os
from gettext import gettext as _
from urllib.parse import quote, urljoin, urlsplit
from xml.etree import ElementTree

import requests


class UploadError(Exception):
    pass


def upload_to_music(server, username, auth, paths, report, settings_headers=None):
    """Upload selected files and directories without replacing existing files."""
    root = f"{server.rstrip('/')}/remote.php/dav/files/{quote(username, safe='')}"
    api_base = f"{server.rstrip('/')}/index.php/apps/music/api"
    api_headers = dict(settings_headers or {})
    uploaded = 0
    failed = 0

    def url(parts):
        return root + "/" + "/".join(quote(part, safe="") for part in parts)

    def error(path, message):
        nonlocal failed
        failed += 1
        report(_("Failed: %(path)s — %(reason)s") % {"path": path, "reason": message})

    def request(method, parts, **kwargs):
        response = session.request(
            method, url(parts), auth=auth, timeout=(15, 120),
            allow_redirects=False, **kwargs
        )
        return response

    def get_settings():
        nonlocal api_headers
        settings_url = f"{api_base}/settings"

        def origin(url):
            try:
                parsed = urlsplit(url)
                if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                    return None
                port = parsed.port
                return parsed.scheme, parsed.hostname, port if port is not None else (443 if parsed.scheme == "https" else 80)
            except ValueError:
                return None

        initial_origin = origin(settings_url)
        if initial_origin is None:
            raise UploadError(_("Invalid Nextcloud server address"))
        for _attempt in range(6):
            try:
                response = session.get(
                    settings_url, headers=api_headers, auth=auth, timeout=(15, 120), allow_redirects=False,
                )
            except ValueError as exc:
                raise UploadError(_("Invalid redirect from Nextcloud")) from exc
            if response.status_code not in (301, 302, 303, 307, 308):
                return response
            location = response.headers.get("Location")
            if not location:
                raise UploadError(_("Nextcloud returned a redirect without a destination"))
            try:
                next_url = urljoin(settings_url, location)
            except ValueError as exc:
                raise UploadError(_("Invalid redirect from Nextcloud")) from exc
            if origin(next_url) != initial_origin:
                raise UploadError(_("Nextcloud redirected the settings request to a different server"))
            settings_url = next_url
            api_headers = {key: value for key, value in api_headers.items() if key.lower() != "cookie"}
        raise UploadError(_("Too many redirects while retrieving Nextcloud Music settings"))

    def scan_music():
        response = session.get(
            f"{api_base}/scanstate", headers=api_headers, auth=auth,
            timeout=(15, 120), allow_redirects=False,
        )
        if response.status_code != 200:
            raise UploadError(_("HTTP status %(status)s") % {"status": response.status_code})
        try:
            state = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise UploadError(_("Invalid music scan response")) from exc
        if not isinstance(state, dict):
            raise UploadError(_("Invalid music scan response"))
        unscanned = state.get("unscannedFiles")
        dirty = state.get("dirtyFiles")
        if not isinstance(unscanned, list) or not isinstance(dirty, list):
            raise UploadError(_("Invalid music scan response"))
        ids = unscanned + dirty
        if any(type(file_id) is not int or file_id <= 0 for file_id in ids):
            raise UploadError(_("Invalid music scan response"))
        ids = list(dict.fromkeys(ids))
        report(_("Scanning new and modified music files: %(count)d") % {"count": len(ids)})
        for offset in range(0, len(ids), 20):
            batch = ids[offset:offset + 20]
            response = session.post(
                f"{api_base}/scan", headers=api_headers, auth=auth,
                json={"files": ",".join(map(str, batch)), "finalize": offset + 20 >= len(ids)},
                timeout=(15, 120), allow_redirects=False,
            )
            if response.status_code != 200:
                raise UploadError(_("HTTP status %(status)s") % {"status": response.status_code})
            try:
                result = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                raise UploadError(_("Invalid music scan response")) from exc
            if not isinstance(result, dict) or type(result.get("filesScanned")) is not int:
                raise UploadError(_("Invalid music scan response"))
            if result["filesScanned"] != len(batch):
                raise UploadError(_("Not all music files could be scanned"))
        report(_("Music scan completed. Refresh the library to see the results."))

    def verify_directory(parts):
        response = request("PROPFIND", parts, headers={"Depth": "0"})
        if response.status_code != 207:
            raise UploadError(_("HTTP status %(status)s") % {"status": response.status_code})
        try:
            document = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as exc:
            raise UploadError(_("Invalid WebDAV response")) from exc
        if document.find(".//{DAV:}resourcetype/{DAV:}collection") is None:
            raise UploadError(_("The destination is not a folder"))

    def ensure_directory(parts):
        response = request("MKCOL", parts)
        if response.status_code == 405:
            verify_directory(parts)
        elif response.status_code != 201:
            raise UploadError(_("HTTP status %(status)s") % {"status": response.status_code})

    def upload_file(local_path, parts):
        nonlocal uploaded
        try:
            with open(local_path, "rb") as source:
                response = request("PUT", parts, data=source, headers={"If-None-Match": "*"})
            if response.status_code == 412:
                raise UploadError(_("File already exists"))
            if response.status_code not in (200, 201, 204):
                raise UploadError(_("HTTP status %(status)s") % {"status": response.status_code})
            uploaded += 1
            report(_("Uploaded: %(path)s") % {"path": "/".join(parts)})
        except (OSError, requests.RequestException, UploadError) as exc:
            error(local_path, str(exc))

    def upload_entry(local_path, parts):
        try:
            if os.path.islink(local_path):
                raise UploadError(_("Symbolic links are not uploaded"))
            if os.path.isfile(local_path):
                upload_file(local_path, parts)
                return
            if not os.path.isdir(local_path):
                raise UploadError(_("Not a regular file or directory"))
            ensure_directory(parts)
            with os.scandir(local_path) as entries:
                children = sorted((entry.name for entry in entries))
            for name in children:
                upload_entry(os.path.join(local_path, name), parts + [name])
        except (OSError, requests.RequestException, UploadError) as exc:
            error(local_path, str(exc))

    with requests.Session() as session:
        try:
            response = get_settings()
            if response.status_code != 200:
                raise UploadError(_("HTTP status %(status)s") % {"status": response.status_code})
            try:
                settings = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                raise UploadError(_("Invalid Nextcloud Music settings response")) from exc
            music_path = settings.get("path") if isinstance(settings, dict) else None
            if not isinstance(music_path, str) or not music_path.startswith("/") or "\0" in music_path:
                raise UploadError(_("Invalid music folder in Nextcloud Music settings"))
            destination = [part for part in music_path.split("/") if part]
            if any(part in (".", "..") for part in destination):
                raise UploadError(_("Invalid music folder in Nextcloud Music settings"))
            verify_directory(destination)
            report(_("Upload destination: %(path)s") % {"path": "/" + "/".join(destination)})
        except (requests.RequestException, UploadError) as exc:
            error(_("Nextcloud Music folder"), str(exc))
            return uploaded, failed, None
        for path in paths:
            path = os.path.normpath(path)
            name = os.path.basename(path)
            if not name or name in (".", ".."):
                error(path, _("Cannot upload this path"))
                continue
            upload_entry(path, destination + [name])
        scan_success = None
        if uploaded:
            try:
                scan_music()
                scan_success = True
            except (requests.RequestException, UploadError) as exc:
                report(_("Music scan failed: %(reason)s") % {"reason": str(exc)})
                scan_success = False
    return uploaded, failed, scan_success
