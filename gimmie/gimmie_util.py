
import datetime
import gc
import os
import urllib
from gettext import gettext as _

import sys     # for ImplementMe
import inspect # for ImplementMe

import dbus
import gobject
import gtk
import gnome.ui
import gnomevfs
import gconf

import gimmie_globals


#
#  Utilities
#

class FileMonitor(gobject.GObject):
    '''
    A simple wrapper around Gnome VFS file monitors.  Emits created, deleted,
    and changed events.  Incoming events are queued, with the latest event
    cancelling prior undelivered events.
    '''
    
    __gsignals__ = {
        "event" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
                   (gobject.TYPE_STRING, gobject.TYPE_INT)),
        "created" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        "deleted" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        "changed" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,))
    }

    def __init__(self, path):
        gobject.GObject.__init__(self)

        if os.path.isabs(path):
            self.path = "file://" + path
        else:
            self.path = path
        try:
            self.type = gnomevfs.get_file_info(path).type
        except gnomevfs.Error:
            self.type = gnomevfs.MONITOR_FILE

        self.monitor = None
        self.pending_timeouts = {}

    def open(self):
        if not self.monitor:
            if self.type == gnomevfs.FILE_TYPE_DIRECTORY:
                monitor_type = gnomevfs.MONITOR_DIRECTORY
            else:
                monitor_type = gnomevfs.MONITOR_FILE
            self.monitor = gnomevfs.monitor_add(self.path, monitor_type, self._queue_event)

    def _clear_timeout(self, info_uri):
        try:
            gobject.source_remove(self.pending_timeouts[info_uri])
            del self.pending_timeouts[info_uri]
        except KeyError:
            pass

    def _queue_event(self, monitor_uri, info_uri, event):
        self._clear_timeout(info_uri)
        self.pending_timeouts[info_uri] = \
            gobject.timeout_add(250, self._timeout_cb, monitor_uri, info_uri, event)

    def queue_changed(self, info_uri):
        self._queue_event(self.path, info_uri, gnomevfs.MONITOR_EVENT_CHANGED)

    def close(self):
        gnomevfs.monitor_cancel(self.monitor)
        self.monitor = None

    def _timeout_cb(self, monitor_uri, info_uri, event):
        if event in (gnomevfs.MONITOR_EVENT_METADATA_CHANGED,
                     gnomevfs.MONITOR_EVENT_CHANGED):
            self.emit("changed", info_uri)
        elif event == gnomevfs.MONITOR_EVENT_CREATED:
            self.emit("created", info_uri)
        elif event == gnomevfs.MONITOR_EVENT_DELETED:
            self.emit("deleted", info_uri)
        self.emit("event", info_uri, event)

        self._clear_timeout(info_uri)
        return False


class FocusRaiser:
    '''
    A focus monitor which monitors mouse pointer entry/exit on a watched window,
    and raises another window in response.
    '''
    _RAISE_THRESHOLD_PIXELS = 2
    _RAISE_TIMEOUT_FAST_MILLIS = 100
    _RAISE_TIMEOUT_MILLIS = 500
    _LOWER_TIMEOUT_MILLIS = 500
    
    def __init__(self,
                 watch_win,
                 raise_win,
                 gravity = gtk.gdk.GRAVITY_SOUTH,
                 hide_on_lower = False,
                 lower_timeout = _LOWER_TIMEOUT_MILLIS):
        self.gravity = gravity
        self.hide_on_lower = hide_on_lower
        self.raise_timeout_id = None
        self.lower_timeout = lower_timeout

        # Immediately raise the raise_win when dragging over either window
        self._connect_drag(watch_win, raise_win)  # watch_win raises raise_win
        self._connect_drag(raise_win, raise_win)  # raise_win raises itself

        # Lower after leaving either window
        watch_win.connect("leave-notify-event", lambda w, ev: self.queue_lower(raise_win))
        raise_win.connect("leave-notify-event", lambda w, ev: self.queue_lower(raise_win))

        # Raise on enter or motion of the watched window.  
        watch_win.add_events(gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.POINTER_MOTION_HINT_MASK)
        watch_win.connect("motion-notify-event", lambda w, ev: self.queue_raise(raise_win, w, ev))
        watch_win.connect("enter-notify-event", lambda w, ev: self.queue_raise(raise_win, w, ev))

        raise_win.set_keep_below(True)

    def set_gravity(self, gravity):
        self.gravity = gravity

    def set_hide_on_lower(self, hide_on_lower):
        self.hide_on_lower = hide_on_lower

    def _connect_drag(self, watch_win, raise_win):
        # FIXME: Use gtk_drag_dest_set_track_motion once we can depend on GTK 2.10
        watch_win.connect("drag-motion", self._drag_motion, raise_win)
        watch_win.connect("drag-leave", lambda w, ctx, timestamp: self.queue_lower(raise_win))

    def _drag_motion(self, w, ctx, x, y, timestamp, raise_win):
        self.do_raise(raise_win)
        return True

    def do_lower(self, items_win):
        # Lower if mouse cursor not within window bounds
        x, y = items_win.get_pointer()
        if items_win.window and not \
               (0 < x < items_win.allocation.width and \
                0 < y < items_win.allocation.height):
            items_win.set_keep_below(True)
            if self.hide_on_lower:
                items_win.hide()
            else:
                items_win.window.lower()
                
        self.raise_timeout_id = None
        return False

    def do_raise(self, items_win):        
        items_win.set_keep_below(False)
        if self.hide_on_lower:
            items_win.show()
        elif items_win.window:
            items_win.window.raise_()

        if self.raise_timeout_id:
            gobject.source_remove(self.raise_timeout_id)
            self.raise_timeout_id = None

    def queue_lower(self, items_win):
        if self.raise_timeout_id:
            gobject.source_remove(self.raise_timeout_id)
        self.raise_timeout_id = gobject.timeout_add(self.lower_timeout, self.do_lower, items_win)

    def queue_raise(self, items_win, w, ev):
        if self.raise_timeout_id:
            gobject.source_remove(self.raise_timeout_id)

        x, y = w.get_pointer()
        height = w.allocation.height
        width = w.allocation.width

        # Queue fast raise if pointer within _RAISE_THRESHOLD_PIXELS of outside
        # edge of watched window.
        fast_raise = False

        if self.gravity == gtk.gdk.GRAVITY_NORTH \
               and 0 <= y <= self._RAISE_THRESHOLD_PIXELS:
            fast_raise = True
        if self.gravity == gtk.gdk.GRAVITY_SOUTH \
               and height - self._RAISE_THRESHOLD_PIXELS <= y <= height:
            fast_raise = True
        if self.gravity == gtk.gdk.GRAVITY_EAST \
               and width - self._RAISE_THRESHOLD_PIXELS <= x <= width:
            fast_raise = True
        if self.gravity == gtk.gdk.GRAVITY_WEST \
               and 0 <= x <= self._RAISE_THRESHOLD_PIXELS:
            fast_raise = True

        if fast_raise:
            self.raise_timeout_id = gobject.timeout_add(self._RAISE_TIMEOUT_FAST_MILLIS,
                                                        self.do_raise,
                                                        items_win)
        else:
            self.raise_timeout_id = gobject.timeout_add(self._RAISE_TIMEOUT_MILLIS,
                                                        self.do_raise,
                                                        items_win)


class KillFocusPadding:
    _PARSED_STYLE_NAMES = []
    
    def __init__(self, widget, style_name):
        if style_name not in KillFocusPadding._PARSED_STYLE_NAMES:
            gtk.rc_parse_string(
                '''
                style "gimmie-%s-style" {
                   GtkWidget::focus-line-width=0
                   GtkWidget::focus-padding=0
                }
                widget "*.gimmie-%s" style "gimmie-%s-style"
                ''' % (style_name, style_name, style_name))
            KillFocusPadding._PARSED_STYLE_NAMES.append(style_name)
        widget.set_name("gimmie-%s" % style_name)


class NoWindowButton(gtk.Button):
    '''
    A Gtk button which does not handle clicks itself.
    '''
    __gsignals__ = {
        'realize' : 'override'
        }
    
    def __init__(self):
        gtk.Button.__init__(self)
        KillFocusPadding(self, "no-window-button")

    def do_realize(self):
        # Don't let GtkButton create an event window overlay
        gtk.Widget.do_realize(self)


class ToolMenuButton(gtk.ToggleToolButton):
    '''
    A tool item which when clicked reveals a menu.
    '''
    
    __gsignals__ = {
        'mnemonic-activate' : 'override',
        }

    def __init__(self, img, label):
        gtk.ToggleToolButton.__init__(self, None)
        
        self.set_property("can-focus", True)
        self.set_is_important(True)
        
        self.label = gtk.Label(label)
        arrow = gtk.Arrow(gtk.ARROW_DOWN, gtk.SHADOW_IN)
        box = gtk.HBox(False, 0)
        box.pack_start(self.label, True, True, 0)
        box.pack_end(arrow, False, False, 0)
        box.show_all()

        self.set_label_widget(box)
        self.set_icon_widget(img)

        self.menu = None

        self.child.connect("button-press-event", self.button_press)

    def set_label(self, label):
        self.label.set_text(label)

    def get_label(self):
        return self.label.get_text()

    def set_menu(self, menu):
        self.menu = menu
        menu.attach_to_widget(self, None)
        menu.connect("deactivate", self._release_button)

    def get_menu(self):
        return self.menu

    def button_press(self, w, ev):
        self.popup_menu(self.menu, ev)
        self.set_active(True)
        return True

    def do_activate(self):
        self.menu.select_first(True)
        self.popup_menu(self.menu)
        self.set_active(True)

    def do_mnemonic_activate(self, group_cycling):
        if not group_cycling:
            self.activate()
        elif self.can_focus():
            self.grab_focus()
        return True

    def _get_menu_position(self, menu):
        parent = menu.get_attach_widget()
        if parent:
            x, y = parent.window.get_origin()

            parent_alloc = parent.get_allocation()
            x += parent_alloc.x + 1
            y += parent_alloc.y

            width, height = menu.size_request()
            if y + height >= parent.get_screen().get_height():
                y -= height - 1
            else:
                y += parent_alloc.height - 1

            return x, y, True
        return 0, 0, False

    def _menu_deactivate(self, menu):
        menu.popdown()
        parent = menu.get_attach_widget()
        if parent:
            parent.set_state(gtk.STATE_NORMAL)

    def popup_menu(self, menu, ev = None):
        menu.connect("deactivate", self._menu_deactivate)
        if ev:
            menu.popup(None, None, self._get_menu_position, ev.button, ev.time)
        else:
            menu.popup(None, None, self._get_menu_position, 0, gtk.get_current_event_time())

        # Highlight the parent
        parent = menu.get_attach_widget()
        if parent:
            parent.set_state(gtk.STATE_SELECTED)

    def _release_button(self, menu):
        self.set_active(False)
        #self.child.release()

    def unused__do_toolbar_reconfigured(self):
        style = self.get_toolbar_style()
        if style == gtk.TOOLBAR_ICONS:
            self.label_horiz.hide()
            self.label_vert.hide()
            self.img.show()
        elif style == gtk.TOOLBAR_TEXT:
            self.label_vert.hide()
            self.img.hide()
            self.label_horiz.show()
        elif style == gtk.TOOLBAR_BOTH:
            self.label_horiz.hide()
            self.img.show()
            self.label_vert.show()
        elif style == gtk.TOOLBAR_BOTH_HORIZ:
            self.label_vert.hide()
            self.img.show()
            self.label_horiz.show()


class IconFactory:
    '''
    Icon lookup swiss-army knife (from menutreemodel.py)
    '''

    def load_icon_from_path(self, icon_path, icon_size = None):
        if os.path.isfile(icon_path):
            try:
                if icon_size:
                    # constrain height, not width
                    return gtk.gdk.pixbuf_new_from_file_at_size(icon_path, -1, int(icon_size))
                else:
                    return gtk.gdk.pixbuf_new_from_file(icon_path)
            except:
                pass
        return None

    def load_icon_from_data_dirs(self, icon_value, icon_size = None):
        data_dirs = None
        if os.environ.has_key("XDG_DATA_DIRS"):
            data_dirs = os.environ["XDG_DATA_DIRS"]
        if not data_dirs:
            data_dirs = "/usr/local/share/:/usr/share/"

        for data_dir in data_dirs.split(":"):
            retval = self.load_icon_from_path(os.path.join(data_dir, "pixmaps", icon_value),
                                              icon_size)
            if retval:
                return retval
            
            retval = self.load_icon_from_path(os.path.join(data_dir, "icons", icon_value),
                                              icon_size)
            if retval:
                return retval

        return None

    def scale_to_bounded(self, icon, size):
        if icon:
            if icon.get_height() > size:
                return icon.scale_simple(size * icon.get_width() / icon.get_height(),
                                         size,
                                         gtk.gdk.INTERP_BILINEAR)
            else:
                return icon
        else:
            return None

    def load_icon(self, icon_value, icon_size, force_size = True):
        assert icon_value, "No icon to load!"

        if isinstance(icon_size, gtk.IconSize):
            icon_size = gtk.icon_size_lookup(icon_size)[0]
            force_size = True

        if isinstance(icon_value, gtk.gdk.Pixbuf):
            if force_size:
                return self.scale_to_bounded(icon_value, icon_size)
            return icon_value

        if os.path.isabs(icon_value):
            icon = self.load_icon_from_path(icon_value, icon_size)
            if icon:
                if force_size:
                    return self.scale_to_bounded(icon, icon_size)
                return icon
            icon_name = os.path.basename(icon_value)
        else:
            icon_name = icon_value
    
        if icon_name.endswith(".png"):
            icon_name = icon_name[:-len(".png")]
        elif icon_name.endswith(".xpm"):
            icon_name = icon_name[:-len(".xpm")]
        elif icon_name.endswith(".svg"):
            icon_name = icon_name[:-len(".svg")]
    
        icon = None
        info = icon_theme.lookup_icon(icon_name, icon_size, gtk.ICON_LOOKUP_USE_BUILTIN)
        if info:
            if icon_name.startswith("gtk-"):
                # NOTE: IconInfo/IconTheme.load_icon leaks a ref to the icon, so
                #       load it manually.
                # NOTE: The bindings are also broken for Gtk's builtin pixbufs:
                #       IconInfo.get_builtin_pixbuf always returns None.
                icon = info.load_icon()
            elif info.get_filename():
                icon = self.load_icon_from_path(info.get_filename())
        else:
            icon = self.load_icon_from_data_dirs(icon_value, icon_size) # Fallback

        if icon and force_size:
            return self.scale_to_bounded(icon, icon_size)
        return icon

    def load_image(self, icon_value, icon_size, force_size = True):
        pixbuf = self.load_icon(icon_value, icon_size, force_size)
        img = gtk.Image()
        img.set_from_pixbuf(pixbuf)
        img.show()
        return img

    def make_icon_frame(self, thumb, icon_size = None, blend = False):
        border = 1

        mythumb = gtk.gdk.Pixbuf(thumb.get_colorspace(),
                                 True,
                                 thumb.get_bits_per_sample(),
                                 thumb.get_width(),
                                 thumb.get_height())
        mythumb.fill(0x00000080) # black, 50% transparent
        if blend:
            thumb.composite(mythumb, 0, 0,
                            thumb.get_width(), thumb.get_height(),
                            0, 0,
                            1.0, 1.0,
                            gtk.gdk.INTERP_NEAREST,
                            128)
        thumb.copy_area(border, border,
                        thumb.get_width() - (border * 2), thumb.get_height() - (border * 2),
                        mythumb,
                        border, border)
        return mythumb

    def transparentize(self, pixbuf, percent):
        pixbuf = pixbuf.add_alpha(False, '0', '0', '0')
        for row in pixbuf.get_pixels_array():
            for pix in row:
                pix[3] = min(int(pix[3]), 255 - (percent * 0.01 * 255))
        return pixbuf

    def colorshift(self, pixbuf, shift):
        pixbuf = pixbuf.copy()
        for row in pixbuf.get_pixels_array():
            for pix in row:
                pix[0] = min(255, int(pix[0]) + shift)
                pix[1] = min(255, int(pix[1]) + shift)
                pix[2] = min(255, int(pix[2]) + shift)
        return pixbuf

    def greyscale(self, pixbuf):
        pixbuf = pixbuf.copy()
        for row in pixbuf.get_pixels_array():
            for pix in row:
                pix[0] = pix[1] = pix[2] = (int(pix[0]) + int(pix[1]) + int(pix[2])) / 3
        return pixbuf


class Thumbnailer:
    def __init__(self, uri, mimetype):
        self.uri = uri or ""
        self.mimetype = mimetype or ""
        self.cached_icon = None
        self.cached_timestamp = None
        self.cached_size = None

    def get_icon(self, icon_size, timestamp = 0):
        if not self.cached_icon or \
               icon_size != self.cached_size or \
               timestamp != self.cached_timestamp:
            self.cached_icon = self._lookup_or_make_thumb(icon_size, timestamp)
            self.cached_size = icon_size
            self.cached_timestamp = timestamp
        return self.cached_icon

    def _lookup_or_make_thumb(self, icon_size, timestamp):
        ### FIXME: Trash URIs crash older libgnomeui's icon lookup, so we avoid it
        if self.uri.startswith("trash:"):
            return self._get_trash_icon()

        icon_name, icon_type = \
                   gnome.ui.icon_lookup(icon_theme, thumb_factory, self.uri, self.mimetype, 0)
        try:
            if icon_type == gnome.ui.ICON_LOOKUP_RESULT_FLAGS_THUMBNAIL or \
                   thumb_factory.has_valid_failed_thumbnail(self.uri, timestamp):
                # Use existing thumbnail
                thumb = icon_factory.load_icon(icon_name, icon_size)
            elif self._is_local_uri(self.uri):
                # Generate a thumbnail for local files only
                print " *** Calling generate_thumbnail for", self.uri
                thumb = thumb_factory.generate_thumbnail(self.uri, self.mimetype)
                thumb_factory.save_thumbnail(thumb, self.uri, timestamp)

            if thumb:
                # Fixup the thumbnail a bit
                thumb = self._nicer_dimensions(thumb)
                thumb = icon_factory.make_icon_frame(thumb, icon_size)

                return thumb
        except:
            pass

        # Fallback to mime-type icon on failure
        return icon_factory.load_icon(icon_name, icon_size)

    def _get_trash_icon(self, uri):
        trash_icon = "gnome-fs-trash-full"
        import gimmie_trash
        if gimmie_trash.trash_monitor.is_empty():
            trash_icon = "gnome-fs-trash-empty"
        return icon_factory.load_icon(trash_icon, icon_size)

    def _is_local_uri(self, uri):
        # NOTE: gnomevfs.URI.is_local seems to hang for some URIs (e.g. ssh
        #       or http).  So look in a list of local schemes which comes
        #       directly from gnome_vfs_uri_is_local_scheme.
        scheme, path = urllib.splittype(self.get_uri() or "")
        return not scheme or scheme in ("file", "help", "ghelp", "gnome-help", "trash",
                                        "man", "info", "hardware", "search", "pipe",
                                        "gnome-trash")

    def _nicer_dimensions(self, icon):
        ### Constrain thumb dimensions to 1:1.2
        if float(icon.get_height()) / float(icon.get_width()) > 1.2:
            return icon.subpixbuf(0, 0,
                                  icon.get_width(), int(icon.get_width() * 1.2))
        return icon


class LaunchManager:
    '''
    A program lauching utility which handles opening a URI or executing a
    program or .desktop launcher, handling variable expansion in the Exec
    string.

    Adds the launched URI or launcher to the ~/.recently-used log.  Sets a
    DESKTOP_STARTUP_ID environment variable containing useful information such
    as the URI which caused the program execution and a timestamp.

    See the startup notification spec for more information on
    DESKTOP_STARTUP_IDs.
    '''
    def __init__(self):
        self.recent_model = None

    def _get_recent_model(self):
        # FIXME: This avoids import cycles
        if not self.recent_model:
            import gimmie_recent
            self.recent_model = gimmie_recent.recent_model
        return self.recent_model

    def launch_uri(self, uri, mimetype = None):
        assert uri, "Must specify URI to launch"
        
        child = os.fork()
        if not child:
            # Inside forked child
            os.setsid()
            os.environ['GIMMIE_LAUNCHER'] = uri
            os.environ['DESKTOP_STARTUP_ID'] = self.make_startup_id(uri)
            os.spawnlp(os.P_NOWAIT, "gnome-open", "gnome-open", uri)
            os._exit(0)
        else:
            os.wait()

            if not mimetype:
                mimetype = "application/octet-stream"
                try:
                    # Use XDG to lookup mime type based on file name.
                    # gtk_recent_manager_add_full requires it.
                    import xdg.Mime
                    mimetype = xdg.Mime.get_type_by_name(uri)
                    if mimetype:
                        mimetype = str(mimetype)
                    return mimetype
                except (ImportError, NameError):
                    print " !!! No mimetype found for URI: %s" % uri

            self._get_recent_model().add(uri=uri, mimetype=mimetype)
        return child

    def get_local_path(self, uri):
        scheme, path = urllib.splittype(uri)
        if scheme == None:
            return uri
        elif scheme == "file":
            path = urllib.url2pathname(path)
            if path[:3] == "///":
                path = path[2:]
            return path
        return None

    def launch_command_with_uris(self, command, uri_list, launcher_uri = None):
        if command.rfind("%U") > -1:
            uri_str = ""
            for uri in uri_list:
                uri_str = uri_str + " " + uri
            return self.launch_command(command.replace("%U", uri_str), launcher_uri)
        elif command.rfind("%F") > -1:
            file_str = ""
            for uri in uri_list:
                uri = self.get_local_path(self, uri)
                if uri:
                    file_str = file_str + " " + uri
                else:
                    print " !!! Command does not support non-file URLs: ", command
            return self.launch_command(command.replace("%F", file_str), launcher_uri)
        elif command.rfind("%u") > -1:
            startup_ids = []
            for uri in uri_list:
                startup_ids.append(self.launch_command(command.replace("%u", uri), launcher_uri))
            else:
                return self.launch_command(command.replace("%u", ""), launcher_uri)
            return startup_ids
        elif command.rfind("%f") > -1:
            startup_ids = []
            for uri in uri_list:
                uri = self.get_local_path(self, uri)
                if uri:
                    startup_ids.append(self.launch_command(command.replace("%f", uri),
                                                           launcher_uri))
                else:
                    print " !!! Command does not support non-file URLs: ", command
            else:
                return self.launch_command(command.replace("%f", ""), launcher_uri)
            return startup_ids
        else:
            return self.launch_command(command, launcher_uri)

    def make_startup_id(self, key, ev_time = None):
        if not ev_time:
            ev_time = gtk.get_current_event_time()
        if not key:
            return "GIMMIE_TIME%d" % ev_time
        else:
            return "GIMMIE:%s_TIME%d" % (key, ev_time)

    def parse_startup_id(self, id):
        if id and id.startswith("GIMMIE:"):
            try:
                uri = id[len("GIMMIE:"):id.rfind("_TIME")]
                timestamp = id[id.rfind("_TIME") + len("_TIME"):]
                return (uri, timestamp)
            except IndexError:
                pass
        return (None, None)

    def launch_command(self, command, launcher_uri = None):
        startup_id = self.make_startup_id(launcher_uri)
        child = os.fork()
        if not child:
            # Inside forked child
            os.setsid()
            os.environ['DESKTOP_STARTUP_ID'] = startup_id
            if launcher_uri:
                os.environ['GIMMIE_LAUNCHER'] = launcher_uri
            os.popen2(command)
            os._exit(0)
        else:
            os.wait()
            if launcher_uri:
                self._get_recent_model().add(uri=launcher_uri,
                                            mimetype="application/x-desktop",
                                            groups=["Launchers"])
            return (child, startup_id)


class BookmarkManager(gobject.GObject):
    '''
    Maintains a list of bookmarks in ~/.gimmie-bookmarks.
    Each line of which is of the format: URI\tMIMETYPE
    '''
    
    __gsignals__ = {
        "reload" : (gobject.SIGNAL_RUN_FIRST,
                    gobject.TYPE_NONE,
                    ())
        }

    DEFAULT_BOOKMARKS = [
        ("firefox.desktop", "application/x-desktop", "gimmie.gimmie_applications.DesktopFileItem"),
        ("nautilus.desktop", "application/x-desktop", "gimmie.gimmie_applications.DesktopFileItem"),
        (os.path.abspath("README"), "text/plain", "gimmie.gimmie_file.FileItem"),
        ("aim:goim?screenname=\"orphennui\"", "gaim/buddy", "gimmie.gimmie_gaim.GaimBuddy"),
        ]
    
    def __init__(self):
        gobject.GObject.__init__(self)
        self.bookmarks_path = os.path.expanduser("~/.gimmie-bookmarks")

        self.monitor = FileMonitor(self.bookmarks_path)
        self.monitor.connect("event", lambda a, b, ev: self.emit("reload"))
        self.monitor.open()

        self.emit("reload")

    def do_reload(self):
        self.bookmarks = []
        try:
            f = file(self.bookmarks_path, "r")
            for line in f:
                line = line.strip()
                args = line.split("\t")
                try: 
                    uri, mimetype, classname = args
                except ValueError:
                    uri, mimetype = args
                    classname = "gimmie_file.FileItem"
                self.bookmarks.append([uri, mimetype, classname])
            f.close()
        except (IOError, EOFError):
            self.bookmarks = BookmarkManager.DEFAULT_BOOKMARKS

    def _write(self):
        try:
            f = file(self.bookmarks_path, "w")
            f.writelines(["%s\t%s\t%s\n" % (u, m, c) for u, m, c in self.bookmarks])
            f.close()

            # Let the file monitor event signal the change to avoid reloading twice
            self.monitor.queue_changed(self.bookmarks_path)
        except (IOError, EOFError):
            pass # Doesn't exist, or no access

    def add_bookmark(self, uri, mimetype, classname = "gimmie_file.FileItem"):
        assert uri, "Must specify URI to bookmark"
        assert mimetype, "Must specify MimeType for URI"

        if not [uri, mimetype, classname] in self.bookmarks:
            self.bookmarks.append([uri, mimetype, classname])
            self._write()

    def add_bookmark_item(self, item):
        classname = "%s.%s" % (item.__class__.__module__, item.__class__.__name__)
        self.add_bookmark(item.get_uri(), item.get_mimetype(), classname)

    def remove_bookmark(self, uri):
        assert uri, "Must specify URI to unbookmark"
        
        self.bookmarks = [x for x in self.bookmarks if x[0] != uri]
        self._write()

    def is_bookmark(self, check_uri):
        return len([x for x in self.bookmarks if x[0] == check_uri]) > 0

    def get_bookmarks(self, mime_type_list = None):
        '''
        Returns the current list of bookmarks as uri and mimetype pairs.  Can be
        filtered by mimetype.
        '''
        if mime_type_list:
            return [[x, y] for x, y, z in self.bookmarks if y in mime_type_list]
        return [[x, y] for x, y, z in self.bookmarks]

    def get_bookmarks_and_class(self):
        '''
        Returns the current list of bookmarks as uri and mimetype pairs.  Can be
        filtered by mimetype.
        '''
        return [[x, z] for x, y, z in self.bookmarks]


class PlacesManager(gobject.GObject):
    '''
    Maintains a list of places, including the home directory, desktop
    and locations stored in ~/.gtk-bookmarks
    '''

    __gsignals__ = {
        "reload" : (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ())
        }

    static_places = [
        ("file://" + os.path.expanduser("~"),
         _("Home"),
         "x-directory/normal",
         "gnome-fs-home"),
        ("file://" + os.path.expanduser("~/Desktop"),
         _("Desktop"),
         "x-directory/normal",
         "gnome-fs-desktop")
        ]

    def __init__(self):
        gobject.GObject.__init__(self)
        self._bookmarks_path = os.path.expanduser("~/.gtk-bookmarks")
        self._places = []

        self.monitor = FileMonitor(self._bookmarks_path)
        self.monitor.connect("event", lambda a, b, ev: self.emit("reload"))
        self.monitor.open()

        self.emit("reload")

    def do_reload(self):
        self._places = PlacesManager.static_places[:]
        try:
            for line in file(self._bookmarks_path):
                line = line.strip()

                if " " in line:
                    uri, name = line.split(" ", 1)
                else:
                    uri = line
                    path = urllib.splittype(uri)[1]
                    name = urllib.unquote(os.path.split(path)[1])

                try:
                    if not gnomevfs.exists(uri):
                        continue
                # Protect against a broken bookmarks file
                except TypeError:
                    continue

                mime = gnomevfs.get_mime_type(uri) or ""
                icon = gnome.ui.icon_lookup(icon_theme, thumb_factory, uri, mime, 0)[0]

                self._places.append((uri, name, mime, icon))
        except IOError, err:
            print "Error loading GTK bookmarks:", err

    def get_places(self):
        return self._places


class ImplementMe(gtk.MessageDialog):
    '''
    A fun helper that will pop up a "Not Implemented" dialog, and point towards
    the file and line where the ImplementMe() call originated, and allow opening
    the the file for editing.
    '''
    def __init__(self, parent=None):
        gtk.MessageDialog.__init__(self,
                                   type = gtk.MESSAGE_INFO,
                                   parent = parent,
                                   message_format = _("Not Implemented..."))

        caller = sys._getframe(1)
        file = inspect.getsourcefile(caller)
        line = inspect.getsourcelines(caller)
        self.format_secondary_text(_("Help us to write this feature by editing the file "
                                     "\"%s\" at line number %d." % (file, line[1])))

        self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)

        button = gtk.Button(label=_("_Fix It!"), use_underline=True)
        button.set_property("can-default", True)
        button.show()
        self.add_action_widget(button, gtk.RESPONSE_ACCEPT)
        self.set_default_response(gtk.RESPONSE_ACCEPT)

        if self.run() == gtk.RESPONSE_ACCEPT:
            if os.environ.has_key("GNOME_DESKTOP_SESSION_ID"):
                # Assume gedit is present if running GNOME
                launcher.launch_command("gedit +%d %s" % (line[1], file))
            else:
                launcher.launch_uri(file, "text/x-python")
        self.destroy()


class GConfBridge(gobject.GObject):
    DEFAULTS = {
        'swapbar'      : False, # Show the topic buttons on the screen
                               # edge and hide the clock applet
        'autohide'     : False, # Auto-hide anchored windows
        'vertical'     : False, # Show the bar on the screen's left edge
        'clockapplet'  : True,  # Show the clock applet
        'click_policy' : 'nautilus', # Number of clicks to launch items in
                                     # TopicWindows. Possible values are:
                                     # single, double, and nautilus to use
                                     # the Nautilus click_policy value.
        'gmail_keyring_token' : 0, # GMail account GNOME Keyring authentication token.
    }

    GIMMIE_PREFIX = "/apps/gimmie/"

    __gsignals__ = {
        'changed' : (gobject.SIGNAL_RUN_LAST | gobject.SIGNAL_DETAILED, gobject.TYPE_NONE, ()),
    }

    def __init__(self, prefix = None):
        gobject.GObject.__init__(self)

        if not prefix:
            prefix = self.GIMMIE_PREFIX
        if prefix[-1] != "/":
            prefix = prefix + "/"
        self.prefix = prefix
        
        self.gconf_client = gconf.client_get_default()
        self.gconf_client.add_dir(prefix[:-1], gconf.CLIENT_PRELOAD_RECURSIVE)

        self.notify_keys = { }

    def connect(self, detailed_signal, handler, *args):
        # Ensure we are watching the GConf key
        if detailed_signal.startswith("changed::"):
            key = detailed_signal[len("changed::"):]
            if not key.startswith(self.prefix):
                key = self.prefix + key
            if key not in self.notify_keys:
                self.notify_keys[key] = self.gconf_client.notify_add(key, self._key_changed)

        return gobject.GObject.connect(self, detailed_signal, handler, *args)

    def get(self, key, default=None):
        if not default:
            if key in self.DEFAULTS:
                default = self.DEFAULTS[key]
                vtype = type(default)
            else:
                assert "Unknown GConf key '%s', and no default value" % key

        vtype = type(default)
        if vtype not in (bool, str, int):
            assert "Invalid GConf key type '%s'" % vtype

        if not key.startswith(self.prefix):
            key = self.prefix + key

        value = self.gconf_client.get(key)
        if not value:
            self.set(key, default)
            return default

        if vtype is bool:
            return value.get_bool()
        elif vtype is str:
            return value.get_string()
        elif vtype is int:
            return value.get_int()
        else:
            return value

    def set(self, key, value):
        vtype = type(value)
        if vtype not in (bool, str, int):
            assert "Invalid GConf key type '%s'" % vtype

        if not key.startswith(self.prefix):
            key = self.prefix + key

        if vtype is bool:
            self.gconf_client.set_bool(key, value)
        elif vtype is str:
            self.gconf_client.set_string(key, value)
        elif vtype is int:
            self.gconf_client.set_int(key, value)

    def _key_changed(self, client, cnxn_id, entry, data=None):
        if entry.key.startswith(self.prefix):
            key = entry.key[len(self.prefix):]
        else:
            key = entry.key
        detailed_signal = "changed::%s" % key
        self.emit(detailed_signal)


class DBusWrapper:
    '''
    Simple wrapper around DBUS object creation.  This works around older DBUS
    bindings which did not create proxy objects if the service/interface is not
    available.  If there is no proxy object, all member access will raise a
    dbus.DBusException.
    '''

    def __init__(self, service, path = None, interface = None, program_name = None, bus = None):
        assert service, "D-BUS Service name not valid"
        self.__service = service
        self.__obj = None

        # NOTE: Some services use the same name for the path
        self.__path = path or "/%s" % service.replace(".", "/")
        self.__interface = interface or service

        self.__program_name = program_name
        self.__bus = bus

    def __get_bus(self):
        if not self.__bus:
            try:
                try:
                    # pthon-dbus 0.80.x requires a mainloop to connect signals
                    from dbus.mainloop.glib import DBusGMainLoop
                    self.__bus = dbus.SessionBus(mainloop=DBusGMainLoop())
                except ImportError:
                    self.__bus = dbus.SessionBus()
            except dbus.DBusException:
                print " !!! D-BUS Session bus is not running"
                raise 
        return self.__bus

    def __get_obj(self):
        if not self.__obj:
            try:
                svc = self.__get_bus().get_object(self.__service, self.__path)
                self.__obj = dbus.Interface(svc, self.__interface)
            except dbus.DBusException:
                print " !!! %s D-BUS service not available." % self.__service
                raise
        return self.__obj

    def __getattr__(self, name):
        try:
            return getattr(self.__get_obj(), name)
        except AttributeError:
            raise dbus.DBusException


class DebugHelper:
    LAST_TYPE_CNTS = {}

    @classmethod
    def count_running_objects(self, type_list):
        type_cnts = {}
        gc.collect()
        for obj in gc.get_objects():
            obj_type = type(obj)
            if obj_type in type_list:
                try:
                    type_cnts[obj_type] += 1
                except KeyError:
                    type_cnts[obj_type] = 1
        for k, v in type_cnts.iteritems():
            print "%d LIVING OBJECTS OF TYPE %s" % (v, k)

    @classmethod
    def diff_running_objects(self):
        type_cnts = {}
        gc.collect()
        for obj in gc.get_objects():
            obj_type = type(obj)
            try:
                type_cnts[obj_type] += 1
            except KeyError:
                type_cnts[obj_type] = 1
        for k, v in type_cnts.iteritems():
            try:
                existing_cnt = DebugHelper.LAST_TYPE_CNTS[k]
                if existing_cnt != v:
                    print "OBJ COUNT:\t%d\tDIFF:\t%d\t\tTYPE: %s" % (v, v - existing_cnt, k)
            except KeyError:
                print "INITIAL OBJ COUNT:\t%d\t\t\tTYPE: %s" % (v, k)
        DebugHelper.LAST_TYPE_CNTS = type_cnts

    @classmethod
    def idle_diff_running_objects(self):
        print
        print "========================== MEMDUMP", datetime.datetime.now()
        DebugHelper.diff_running_objects()
        print "========================== MEMDUMP"
        print
        return True


#
# Globals
#

icon_factory = IconFactory()
icon_theme = gtk.icon_theme_get_default()
icon_theme.append_search_path(gimmie_globals.image_dir)
thumb_factory = gnome.ui.ThumbnailFactory("normal")

launcher = LaunchManager()
bookmarks = BookmarkManager()
places = PlacesManager()
gconf_bridge = GConfBridge()

# Print running object diffs every 15 seconds
if "-memdump" in sys.argv or "--memdump" in sys.argv:
    gobject.timeout_add(30 * 1000, DebugHelper.idle_diff_running_objects)

