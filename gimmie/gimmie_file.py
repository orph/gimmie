
import os
import sys
import urllib
import urlparse
from gettext import gettext as _

import gobject
import gtk
import gnome.ui
import gnomevfs
import gnomevfs.async

from gimmie_base import Item
from gimmie_util import bookmarks, icon_factory, icon_theme, thumb_factory
from gimmie_recent import recent_model
from gimmie_trash import trash_monitor


class FileItem(Item):
    '''
    An Item subclass wrapping a filesystem file or URI.  Handles generating
    thumbnails, and showing nice names and tooltips.
    '''
    def __init__(self, uri, timestamp=0, icon=None):
        Item.__init__(self, uri=uri, timestamp=timestamp, icon=icon)
        self.vfs_info = None
        self.vfs_info_job_id = None

    def get_is_user_visible(self):
        return self.ensure_file_info() != None

    def _file_info_callback(self, handle, results, data = None):
        if results:
            uri, error, info = results[0]
            if not error:
                self.vfs_info = info
                self.emit("reload")
        self.vfs_info_job_id = None

    def ensure_file_info(self):
        if not self.vfs_info and not self.vfs_info_job_id:
            try:
                vfs_uri = gnomevfs.URI(self.get_uri())
                self.vfs_info_job_id = \
                        gnomevfs.async.get_file_info(vfs_uri,
                                                     self._file_info_callback,
                                                     gnomevfs.FILE_INFO_GET_MIME_TYPE)
            except (TypeError, gnomevfs.Error):
                # GnomeVFS cannot handle the URI, or it doesn't exist
                return None
        return self.vfs_info

    def get_seen_timestamp(self):
        try:
            return recent_model.get_item(self.get_uri()).get_timestamp()
        except KeyError:
            return 0

    def get_modified_timestamp(self):
        try:
            return self.ensure_file_info().mtime
        except (ValueError, AttributeError):
            return 0

    def get_timestamp(self):
        return max(self.get_seen_timestamp(),
                   self.get_modified_timestamp(),
                   Item.get_timestamp(self))

    def get_mimetype(self):
        try:
            return self.ensure_file_info().mime_type
        except (ValueError, AttributeError):
            try:
                # Fallback to using XDG to lookup mime type based on file name.
                import xdg.Mime
                mimetype = xdg.Mime.get_type_by_name(self.get_uri())
                if mimetype != None:
                    mimetype = str(mimetype)
                return mimetype
            except (ImportError, NameError):
                print " !!! No mimetype found for URI: %s" % self.get_uri()
                return "application/octet-stream"

    def get_name(self):
        try:
            if self.is_local_path():
                return self.ensure_file_info().name.decode(sys.getfilesystemencoding(), "replace")
            else:
                return self.ensure_file_info().name
        except (ValueError, AttributeError), e:
            return urllib.unquote(os.path.basename(self.get_uri())) or self.get_uri()

    def get_location_comment(self):
        comment = ""
        scheme, path = urllib.splittype(self.get_uri())

        # Show hostname if remote file
        if scheme not in (None, "file"):
            # NOTE: urlparse is broken and requires a known URL scheme to parse
            #       the host segment.
            fake_url = "http:" + path
            parsed = urlparse.urlparse(fake_url)
            if parsed[1]:
                netloc = parsed[1]
                netloc = netloc[netloc.find("@")+1:]
                comment += "%s " % netloc

        # Show parent directory or "Home"
        local_path = self.get_local_path()
        if local_path:
            dirname = os.path.dirname(local_path)
            homedir = os.path.expanduser("~")
            if dirname == homedir:
                dirname = "Home"
        else:
            dirname = os.path.dirname(path)
        comment += "in %s" % os.path.basename(dirname)

        return comment

    def get_comment(self):
        comment = self.get_location_comment()

        # Show last modified or seen timestamp, whichever is more recent
        seen = self.get_seen_timestamp()
        changed = self.get_modified_timestamp()
        if not seen or changed > seen:
            if comment: comment += "\n"
            comment += self.pretty_print_time_since(changed)
        elif seen:
            if comment: comment += "\n"
            comment += self.pretty_print_time_since(seen)

        return comment

    def is_local_path(self):
        urllib.splittype(self.get_uri() or "")[0] in (None, "file")

    def get_local_path(self):
        scheme, path = urllib.splittype(self.get_uri())
        if scheme == None:
            return self.get_uri()
        elif scheme == "file":
            path = urllib.url2pathname(path)
            if path[:3] == "///":
                path = path[2:]
            return path
        return None

    def get_tooltip(self):
        local_path = self.get_local_path()
        if local_path:
            dirname = os.path.split(local_path)[0]
            homedir = os.path.expanduser("~")
            if dirname == homedir:
                dirname = "Home"
            elif dirname[:len(homedir)] == homedir:
                dirname = "~" + dirname[len(homedir):]
            return "%s in %s" % (self.get_name(), dirname)
        else:
            return self.get_name()

    def handle_drag_data_received(self, selection, target_type):
        for uri in selection.get_uris():
            item = FileItem(uri)
            if not item.get_mimetype() in ("application/x-desktop",
                                           "gaim/buddy",
                                           "gaim/log"):
                bookmarks.add_bookmark(uri, item.get_mimetype())

