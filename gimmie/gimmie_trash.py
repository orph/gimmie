
from gettext import ngettext, gettext as _

import gobject
import gtk
import gnomevfs
import gnomevfs.async
try:
    import gconf
except ImportError:
    pass

from gimmie_base import Item
from gimmie_util import FileMonitor


class TrashDirectory(gobject.GObject):
    __gsignals__ = {
        "count-changed" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
        }

    def __init__(self, trash_uri):
        gobject.GObject.__init__(self)
        
        self.trash_uri = trash_uri
        self.trash_cnt = 0
        self.monitor = FileMonitor(trash_uri)
        self.monitor.connect("created", lambda mon, info: self._trash_dir_changed())
        self.monitor.connect("deleted", lambda mon, info: self._trash_dir_changed())
        self.monitor.open()

        self._trash_dir_changed()

    def get_uri(self):
        return self.trash_uri

    def get_count(self):
        return self.trash_cnt

    def cleanup(self):
        self.monitor.close()

    def _trash_dir_changed(self):
        count = 0
        try:
            for file in gnomevfs.open_directory(self.trash_uri):
                if file.name not in (".", ".."):
                    count += 1
        except gnomevfs.Error:
            pass
        self.trash_cnt = count
        self.emit("count-changed")


class TrashMonitor(gobject.GObject):
    '''
    Object which monitors the trash can.  This was mostly ported from
    trashapplet.
    '''

    __gsignals__ = {
        "count-changed" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
        }

    def __init__(self):
        gobject.GObject.__init__(self)
        
        self.volume_monitor = gnomevfs.VolumeMonitor()
        self.trash_dirs = {} # volume_uri : TrashDirectory
        self.notify_id = None

        self.volume_monitor.connect("volume_mounted", lambda m, v: self.add_volume(v))
        self.volume_monitor.connect("volume_pre_unmount", lambda m, v: self.remove_volume(v))

        self.recheck_trash_dirs()

    def recheck_trash_dirs(self):
        for volume in self.volume_monitor.get_mounted_volumes():
            self.add_volume(volume)

    def add_volume(self, volume):
        uri = volume.get_activation_uri()
        if volume.handles_trash() and uri not in self.trash_dirs:
            gnomevfs.async.find_directory(near_uri_list = [gnomevfs.URI(uri)],
                                          kind = gnomevfs.DIRECTORY_KIND_TRASH,
                                          create_if_needed = False,
                                          find_if_needed = True,
                                          permissions = 0777,
                                          callback = self._find_directory,
                                          user_data = uri)

    def remove_volume(self, volume):
        volume_uri = volume.get_activation_uri()
        try:
            trashdir = self.trash_dirs[volume_uri]
            trashdir.cleanup()
            del self.trash_dirs[volume_uri]
        except KeyError:
            return

        self.emit("count-changed")

    def _find_directory(self, handle, results, volume_uri):
        # FIXME: Support multiple trash directories per volume?
        for uri, error in results:
            # error is None if Trash directory is successfully found
            if error != None:
                continue

            trash_uri = str(uri)
            if trash_uri in [x.get_uri() for x in self.trash_dirs.values()]:
                continue

            trashdir = TrashDirectory(trash_uri)
            trashdir.connect("count-changed", lambda cnt: self.emit("count-changed"))
            self.trash_dirs[volume_uri] = trashdir

            # simulate a change to update item count
            self.emit("count-changed")
            break

    def empty(self):
        source_uris = [gnomevfs.URI(dir.get_uri()) for dir in self.trash_dirs.values()]
        gnomevfs.async.xfer(source_uri_list = source_uris,
                            target_uri_list = [],
                            xfer_options = gnomevfs.XFER_EMPTY_DIRECTORIES,
                            error_mode = gnomevfs.XFER_ERROR_MODE_ABORT,
                            overwrite_mode = gnomevfs.XFER_OVERWRITE_MODE_REPLACE,
                            progress_update_callback = self._empty_progress,
                            update_callback_data = None)

    def _empty_progress(self, handle, info, data=None):
        # FIXME: show progress/cancellation?
        return 1

    def is_empty(self):
        return self.get_count() == 0

    def get_count(self):
        count = 0
        for trashdir in self.trash_dirs.values():
            count += trashdir.get_count()
        return count


class TrashItem(Item):
    '''
    An item which monitors the trash can state
    '''
    def __init__(self, uri="trash:///"):
        Item.__init__(self,
                      name=_("Trash"),
                      uri=uri,
                      icon="gnome-fs-trash-full",
                      mimetype="x-directory/normal")
        trash_monitor.connect("count-changed", lambda mon: self.emit("reload"))

    def get_icon(self, icon_size):
        # FIXME: accept icon?
        if trash_monitor.is_empty():
            self.icon = "gnome-fs-trash-empty"
        else:
            self.icon = "gnome-fs-trash-full"
        return Item.get_icon(self, icon_size)

    def populate_popup(self, menu):
        Item.populate_popup(self, menu)

        sep = gtk.SeparatorMenuItem()
        sep.show()
        menu.append(sep)

        empty = gtk.MenuItem(_("_Empty Trash"), use_underline=True)
        empty.set_sensitive(not trash_monitor.is_empty())
        empty.connect("activate", lambda w: self.do_empty())
        empty.show()
        menu.append(empty)

    def get_comment(self):
        return ngettext("%d item", "%d items", trash_monitor.get_count()) \
               % trash_monitor.get_count()

    def get_tooltip(self):
        ### FIXME: Tooltips are cached currently, so displaying the count always shows 0
        #return _("%s (%s)") % (self.get_name(), self.get_comment())
        return self.get_name()

    def get_is_opened(self):
        return True

    def get_can_pin(self):
        ### FIXME: Pinning the trash can cause a crash, so disable for now.
        return False

    def do_empty(self):
	try:
            client = gconf.client_get_default()
            if not client.get_bool("/apps/nautilus/preferences/confirm_trash"):
                return True
	except NameError:
            pass

        dialog = gtk.MessageDialog(type = gtk.MESSAGE_WARNING,
                                   flags = gtk.DIALOG_MODAL,
                                   message_format = _("Empty all of the items from the trash?"))
        dialog.format_secondary_text(_("If you choose to empty the trash, all items in it will be permanently lost.  Please note that you can also delete them separately."))
        dialog.set_wmclass("empty_trash", "Nautilus");
        # FIXME: Set transient
        dialog.realize()

        dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)

        button = gtk.Button(label=_("_Empty Trash"), use_underline=True)
        button.set_property("can-default", True)
        button.show()
        dialog.add_action_widget(button, gtk.RESPONSE_ACCEPT)
        dialog.set_default_response(gtk.RESPONSE_ACCEPT)

        if dialog.run() == gtk.RESPONSE_ACCEPT:
            trash_monitor.empty()

        dialog.destroy()

    def _async_progress(self, handle, info, xfer_opts):
        if info.status == gnomevfs.XFER_PROGRESS_STATUS_VFSERROR:
            uri = gnomevfs.URI(info.source_name)

            if xfer_opts & gnomevfs.XFER_REMOVESOURCE:
                msg = _("Error while moving.")
                msg2 = _('Cannot move "%s" to the trash because you do not have permissions to change it or its parent folder.' % uri.short_name)
            elif xfer_opts & gnomevfs.XFER_DELETE_ITEMS:
                msg = _("Error while deleting.")
                msg2 = _('"%s" cannot be deleted because you do not have permissions to modify its parent folder.') % uri.short_name
            else:
                msg = _("Error while performing file operation.")
                msg2 = _('Cannot perform file operation %d on "%s".')  % (xfer_opts, uri.short_name)

            dialog = gtk.MessageDialog(type = gtk.MESSAGE_ERROR,
                                       message_format = msg)
            dialog.format_secondary_text(msg2)

            if info.files_total > 1:
                button = gtk.Button(label=_("_Skip"))
                button.show()
                dialog.add_action_widget(button, gtk.RESPONSE_REJECT)

            dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)

            button = gtk.Button(label=_("_Retry"))
            button.set_property("can-default", True)
            button.show()
            dialog.add_action_widget(button, gtk.RESPONSE_ACCEPT)
            dialog.set_default_response(gtk.RESPONSE_ACCEPT)

            response = dialog.run()
            dialog.destroy()

            if response == gtk.RESPONSE_ACCEPT:
                return gnomevfs.XFER_ERROR_ACTION_RETRY
            elif response == gtk.RESPONSE_REJECT:
                return gnomevfs.XFER_ERROR_ACTION_SKIP

            return gnomevfs.XFER_ERROR_ACTION_ABORT

        return 1

    def _async_progress_sync(self, info, data=None):
        # Dummy function. All code to handle error conditions is in
        # self._async_progress()
        return 1

    def _find_directory(self, handle, results, uri_list):
        # Recheck for any Trash dirs we may have added
        trash_monitor.recheck_trash_dirs()

        source_uri_list = []
        target_uri_list = []
        unmovable_uri_list = []
        for i in xrange(len(results)):
            trash_uri, error = results[i]
            source_uri = uri_list[i]

            # error is None if Trash directory is successfully found
            if error == None:
                source_uri_list.append(source_uri)
                target_uri_list.append(trash_uri.append_file_name(source_uri.short_name))
            else:
                unmovable_uri_list.append(source_uri)

        if len(source_uri_list) > 0:
            gnomevfs.async.xfer(source_uri_list, target_uri_list,
                                xfer_options = gnomevfs.XFER_REMOVESOURCE |
                                               gnomevfs.XFER_RECURSIVE,
                                error_mode = gnomevfs.XFER_ERROR_MODE_QUERY,
                                overwrite_mode = gnomevfs.XFER_OVERWRITE_MODE_REPLACE,
                                progress_update_callback = self._async_progress,
                                update_callback_data = gnomevfs.XFER_REMOVESOURCE,
                                progress_sync_callback = self._async_progress_sync)

        num_files = len(unmovable_uri_list)
        if (num_files > 0):
            if len(source_uri_list) == 0:
                msg = _("Cannot move items to trash, do you want to delete them immediately?")
                msg2 = _("None of the %d selected items can be moved to the Trash") % num_files
            else:
                msg = _("Cannot move some items to trash, do you want to delete these immediately?")
                msg2 = _("%d of the selected items cannot be moved to the Trash") % num_files

            dialog = gtk.MessageDialog(type = gtk.MESSAGE_QUESTION,
                                       flags = gtk.DIALOG_MODAL,
                                       message_format = msg)

            dialog.format_secondary_text(msg2)

            dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)

            button = gtk.Button(label=_("_Delete"), use_underline=True)
            button.set_property("can-default", True)
            button.show()
            dialog.add_action_widget(button, gtk.RESPONSE_ACCEPT)
            dialog.set_default_response(gtk.RESPONSE_ACCEPT)

            if dialog.run() == gtk.RESPONSE_ACCEPT:
                gnomevfs.async.xfer(source_uri_list = unmovable_uri_list,
                                    target_uri_list = [],
                                    xfer_options = gnomevfs.XFER_DELETE_ITEMS,
                                    error_mode = gnomevfs.XFER_ERROR_MODE_QUERY,
                                    overwrite_mode = gnomevfs.XFER_OVERWRITE_MODE_REPLACE,
                                    progress_update_callback = self._async_progress,
                                    update_callback_data = gnomevfs.XFER_DELETE_ITEMS,
                                    progress_sync_callback = self._async_progress_sync)
            dialog.destroy()

    def handle_drag_data_received(self, selection, target_type):
        uri_list = []
        for uri in selection.get_uris():
            uri_list.append(gnomevfs.URI(uri))

        gnomevfs.async.find_directory(near_uri_list = uri_list,
                                      kind = gnomevfs.DIRECTORY_KIND_TRASH,
                                      create_if_needed = True,
                                      find_if_needed = False,
                                      permissions = 0777,
                                      callback = self._find_directory,
                                      user_data = uri_list)

#
# Globals
#

trash_monitor = TrashMonitor()
