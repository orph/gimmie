
import datetime
import os
import pwd
from gettext import gettext as _

import gobject
import gtk
import gnomevfs

try:
    import gnomecups
except ImportError:
    gnomecups = None

import gdmclient

from gimmie_globals import gimmie_is_panel_applet
from gimmie_base import Item, ItemSource, Topic, IOrientationAware, gimmie_get_topic_for_uri
from gimmie_file import FileItem
from gimmie_logout import LogoutDialog
from gimmie_recent import RecentAggregate, recent_model
from gimmie_util import *

# FIXME: Move these to another file?
from gimmie_applications import MenuTree, RecentSettingsLaunchers, LauncherItem
from gimmie_trash import TrashItem


#
# Sidebar ItemSources
#

class FavoritesSource(ItemSource):
    '''
    Item source that lists all favorite items.
    '''
    def __init__(self):
        ItemSource.__init__(self,
                            name=_("All Favorites"),
                            icon="gnome-favorites",
                            uri="source://AllFavorites",
                            filter_by_date=False)
        bookmarks.connect("reload", lambda x: self.emit("reload"))

    def get_items_uncached(self):
        for uri, itemclass in bookmarks.get_bookmarks_and_class():
            try:
                mod, cls = itemclass.rsplit(".", 1)
                dynmod = __import__(mod, None, None, cls)
                dyncls = getattr(dynmod, cls)
                dynobj = dyncls(uri=uri)
                yield dynobj
            except (ValueError, TypeError, ImportError, AttributeError), err:
                # ValueError - thrown by Item constructor, or strange itemclass
                # TypeError - thrown by Item not accepting uri arg
                # ImportError - error importing mod
                # AttributeError - mod doesn't contain cls
                print "Error creating %s for URI \"%s\": %s" % (itemclass, uri, err)


class PlacesSource(ItemSource):
    '''
    Use the PlacesManager to list out the user\'s places, and watch for updates.
    '''
    
    def __init__(self):
        ItemSource.__init__(self,
                            name=_("Places"),
                            icon="gnome-fs-directory",
                            uri="source://Places",
                            filter_by_date=False)

        # Listen for changes in the ~/.gtk-bookmarks file
        places.connect("reload", lambda x: self.emit("reload"))

    def get_items_uncached(self):
        for uri, name, mime, icon in places.get_places():
            yield FileItem(uri=uri, icon=icon)

        # Add a trashcan so people can toggle it's pinned setting on the gimmie bar.
        yield TrashItem()


class DriveItem(Item):
    def __init__(self, drive = None, uri = None):
        assert drive or uri, "Invalid arguments passed to DriveItem.__init__"

        if not drive and uri:
            for drive in gnomevfs.VolumeMonitor().get_connected_drives():
                if drive.get_activation_uri() == uri:
                    break
            else:
                raise ValueError, "Cannot find drive to match URI '%s'" % uri

        uri = drive.get_activation_uri()
        if not uri:
            for volume in drive.get_mounted_volumes():
                if volume.is_user_visible():
                    # FIXME: Using the first volume URI for a device is
                    #        broken. There could be multiple, though I don't
                    #        know under what circumstances this would happen.
                    uri = volume.get_activation_uri()
                    break
            else:
                raise ValueError, "Cannot find URI to open for drive '%s'" % \
                      drive.get_display_name()

        Item.__init__(self,
                      uri=uri,
                      timestamp=0,
                      mimetype="x-gimmie/drive",
                      icon=drive.get_icon())
        self.drive = drive

    def get_name(self):
        return self.drive.get_display_name()

    def get_comment(self):
        if not self.get_is_mounted():
            # FIXME: Check if drive is set to auto-mount, and if not show "Not Mounted"
            return _("No disk inserted")
        else:
            comment = ""

            volumes = self.drive.get_mounted_volumes()
            if len(volumes) == 1:
                vol_name = volumes[0].get_display_name()
                if vol_name != self.get_name():
                    comment += volumes[0].get_display_name()

            # FIXME: If read-only drive, show allocated size instead
            try:
                space = gnomevfs.get_volume_free_space(gnomevfs.URI(self.get_uri()))
            except (TypeError, gnomevfs.Error):
                # When the URI or free space is unknown
                space = 0

            if space:
                if comment: comment += "\n"
                comment += _("Free space: %s") % gnomevfs.format_file_size_for_display(space)

            return comment

    def get_icon(self, icon_size):
        volumes = self.drive.get_mounted_volumes()
        if len(volumes) == 1:
            return icon_factory.load_icon(volumes[0].get_icon(), icon_size)
        else:
            icon = icon_factory.load_icon(self.drive.get_icon(), icon_size)
            if not volumes:
                # Not mounted, shade the icon
                return icon_factory.transparentize(icon, 70)
            return icon

    def get_is_mounted(self):
        return self.drive.is_mounted()

    def eject(self):
        try:
            self.drive.eject(lambda x, y, z: self.emit("reload"))
        except SystemError, err:
            # FIXME: Some PyGtk versions are broken.  See bug #418667.
            print " !!! Error ejecting:", err

    def populate_popup(self, menu):
        Item.populate_popup(self, menu)

        # FIXME: Add mount/unmount toggle?  Need to track nautilus.

        eject = gtk.MenuItem(_("_Eject"), use_underline=True)
        if hasattr(self.drive, "needs_eject"):
            # NOTE: PyGTK doesn't bind this yet.  See bug #419225.
            eject.set_sensitive(self.drive.needs_eject())
        eject.connect("activate", lambda w: self.eject())
        eject.show()
        menu.append(eject)


class DevicesSource(ItemSource):
    '''
    Use the gnome-vfs VolumeMonitor to list the currently connected devices.
    '''
    def __init__(self):
        ItemSource.__init__(self,
                            name=_("Devices & Media"),
                            icon="gnome-dev-removable-usb",
                            uri="source://Devices",
                            filter_by_date=False)
        
        self.add_bluetooth = Item(name=_("Add Bluetooth..."),
                                  comment=_("Access a wireless device"),
                                  icon="stock_bluetooth",
                                  special=True)
        self.add_bluetooth.do_open = lambda: self._add_bluetooth()

        self.cd_burner = Item(name=_("Create CD/DVD..."),
                              comment=_("Burn files onto a CD or DVD disk"),
                              icon="gnome-dev-cdrom",
                              special=True)
        self.cd_burner.do_open = \
            lambda: launcher.launch_command("nautilus --no-desktop burn:///")

        self.vol_monitor = gnomevfs.VolumeMonitor()
        self.vol_monitor.connect("drive_connected", lambda v, d: self.emit("reload"))
        self.vol_monitor.connect("drive_disconnected", lambda v, d: self.emit("reload"))
        self.vol_monitor.connect("volume_mounted", lambda v, d: self.emit("reload"))
        self.vol_monitor.connect("volume_unmounted", lambda v, d: self.emit("reload"))

    def _add_bluetooth(self):
        ImplementMe()

    def get_items_uncached(self):
        yield self.add_bluetooth
        yield self.cd_burner

        for drive in self.vol_monitor.get_connected_drives():
            try:
                yield DriveItem(drive)
            except ValueError:
                pass


class PrinterItem(Item):
    '''
    Wraps a GnomeCupsPrinter.
    '''
    def __init__(self, printer):
        Item.__init__(self, mimetype="x-gimmie/printer")
        
        printer.connect("is_default_changed", lambda *args: self.emit("reload"))
        printer.connect("attributes_changed", lambda *args: self.emit("reload"))
        
        self.printer = printer
        self.add_tag("Printer")

    def do_reload(self):
        print " *** Reloading Printer: %s (state: %s, jobs: %s, location: %s, " \
              "make/model: %s, info: %s)" \
              % (self.get_name(),
                 self.printer.get_state_name(),
                 self.printer.get_job_count(),
                 self.printer.get_location(),
                 self.printer.get_make_and_model(),
                 self.printer.get_info())

    def get_uri(self):
        if self.printer.get_attributes_initialized():
            return self.printer.get_uri()
        return None

    def get_name(self):
        return self.printer.get_name()

    def get_comment(self):
        jobcnt = self.printer.get_job_count()
        state = self.printer.get_state_name()
        loc = self.printer.get_location().strip()

        comment = ""
        if loc and loc.lower() != "location unknown" and loc != self.printer.get_name():
            comment = loc + "\n"

        if jobcnt:
            #return "<span color=\"#337F33\">%s - %d Jobs</span>" % (state, jobcnt)
            return comment + "%s - %d Jobs" % (state, jobcnt)
        else:
            #return "<span color=\"#33337F\">%s</span>" % state
            return comment + state

    def get_timestamp(self):
        uri = self.get_uri()
        if uri:
            try:
                return recent_model.get_item(uri).get_timestamp()
            except KeyError:
                pass
        return 0

    def do_open(self):
        launcher.launch_command("gnome-cups-manager --view \"%s\"" % self.printer.get_name())
        recent_model.add_item(self)

    def _open_properties(self):
        launcher.launch_command("gnome-cups-manager --properties \"%s\"" % self.printer.get_name())

    def get_icon(self, icon_size):
        icon_name, emblems = self.printer.get_icon()
        icon = icon_factory.load_icon(icon_name, icon_size) or \
               icon_factory.load_icon(gtk.STOCK_PRINT, icon_size) # Backup
        if icon_size >= 32:
            for emblem_name in emblems:
                emblem = icon_factory.load_icon(emblem_name, icon_size)
                if emblem:
                    icon = icon.copy() # NOTE: The composite can crash if we don't copy first.
                                       # gnome-cups-manager does this too.
                    emblem.composite(icon,
                                     0, 0,
                                     icon.get_width(), icon.get_height(),
                                     0, 0,
                                     1.0, 1.0,
                                     gtk.gdk.INTERP_NEAREST,
                                     255)
                else:
                    print " !!! Unable to load printer emblem '%s'" % emblem_name
        return icon

    def populate_popup(self, menu):
        Item.populate_popup(self, menu)
        
        props = gtk.ImageMenuItem (gtk.STOCK_PROPERTIES)
        props.connect("activate", lambda w: self._open_properties())
        props.show()
        menu.append(props)


class PrinterSource(ItemSource):
    '''
    Use libgnomecups to list out printers.
    '''
    def __init__(self):
        ItemSource.__init__(self,
                            name=_("Printers"),
                            icon=gtk.STOCK_PRINT,
                            uri="source://Printers",
                            filter_by_date=False)

        self.add_printer = Item(name=_("Add Printer..."),
                                comment=_("Setup attached or networked printer"),
                                icon="gnome-dev-printer-new",
                                special=True)
        self.add_printer.do_open = lambda: launcher.launch_command("gnome-cups-add")

        if gnomecups:
            gnomecups.new_printer_notify_add(lambda *args: self.emit("reload"))
            gnomecups.printer_removed_notify_add(lambda *args: self.emit("reload"))

    def get_enabled(self):
        return gnomecups != None

    def get_items_uncached(self):
        yield self.add_printer

        if gnomecups:
            for printer_name in gnomecups.get_printers():
                printer = gnomecups.printer_get(printer_name)
                yield PrinterItem(printer)


class RemoteMountItem(Item):
    def __init__(self, volume):
        Item.__init__(self,
                      name=volume.get_display_name(),
                      uri=volume.get_activation_uri(),
                      mimetype="x-directory/normal",
                      icon=volume.get_icon())

    def get_timestamp(self):
        try:
            return recent_model.get_item(self.get_uri()).get_timestamp()
        except KeyError:
            return 0

    def get_comment(self):
        seen = self.get_timestamp()
        if seen:
            return self.pretty_print_time_since(seen)
        return None

    def do_open(self):
        launcher.launch_command("nautilus %s" % self.get_uri())
        recent_model.add_item(self)


class BonjourSource(ItemSource):
    '''
    Use Avahi to list out computers on the network.  Show a dialog on opening a
    computer listing the available services each with a button to open them in
    an appropriate way: web, ftp, smb, nfs, etc.

    This doesn\'t do anything yet.
    '''
    def __init__(self):
        ItemSource.__init__(self,
                            name=_("Nearby Computers"),
                            icon=gtk.STOCK_NETWORK,
                            uri="source://Network",
                            filter_by_date=False)

        self.connect_to = Item(name=_("Connect to..."),
                               comment=_("Access a computer on the network"),
                               icon=gtk.STOCK_CONNECT,
                               special=True)
        self.connect_to.do_open = lambda: self._connect_to()

        self.smb = Item(name=_("Windows Network"),
                        comment=_("Browse nearby Windows computers"),
                        icon=gtk.STOCK_NETWORK,
                        special=True)
        self.smb.do_open = lambda: launcher.launch_command("nautilus smb://")

        self.vol_monitor = gnomevfs.VolumeMonitor()
        self.vol_monitor.connect("volume_mounted", lambda v, d: self.emit("reload"))
        self.vol_monitor.connect("volume_unmounted", lambda v, d: self.emit("reload"))

    def get_items_uncached(self):
        yield self.connect_to
        yield self.smb

        # FIXME: List avahi-discovered hosts

        for vol in self.vol_monitor.get_mounted_volumes():
            if vol.get_volume_type() == gnomevfs.VOLUME_TYPE_CONNECTED_SERVER:
                yield RemoteMountItem(vol)

    def _connect_to(self):
        launcher.launch_command("nautilus-connect-server")


class SettingsSource(ItemSource):
    def __init__(self):
        ItemSource.__init__(self,
                            name=_("Settings"),
                            uri="source://Settings",
                            filter_by_date=False)

        self.inline_administration_items = True
        self.settings_menu_tree = None
        try:
            # Gnome 2.17.91+ changed the file name arbitrarily.  Yay.
            self.settings_menu_tree = MenuTree("gnomecc.menu")
            # Administration items are not included in the new gnomecc.menu
            self.inline_administration_items = False
        except ValueError:
            try:
                # This is the file panel menu-based gnomecc uses.  It generally
                # includes preferences.menu and system-settings.menu.
                self.settings_menu_tree = MenuTree("settings.menu")
            except ValueError:
                try:
                    # Some distros rename settings.menu.
                    self.settings_menu_tree = MenuTree("gnome-settings.menu")
                except ValueError:
                    pass

        if self.settings_menu_tree:
            self.settings_menu_tree.connect_after("reload", lambda x: self.emit("reload"))

        self.settings_menu_source = None
        self.do_reload()

    def do_reload(self):
        self.settings_menu_source = self.settings_menu_tree.get_toplevel_flat_source()

    def always_show_descriptions(self):
        return True

    def get_enabled(self):
        return self.settings_menu_tree != None

    def get_icon(self, size):
        return self.settings_menu_source.get_icon(size)

    def get_comment(self):
        return self.settings_menu_source.get_comment()

    def get_items_uncached(self):
        if self.settings_menu_source:
            for item in self.settings_menu_source.get_items_uncached():
                yield item

    def get_settings_menu_tree(self):
        return self.settings_menu_tree

    def has_administration(self):
        return self.inline_administration_items


class AdministrationSource(ItemSource):
    def __init__(self):
        ItemSource.__init__(self,
                             name=_("Administration"),
                             uri="source://Administration",
                             filter_by_date=False)

        self.system_settings_menu_tree = MenuTree("system-settings.menu")
        self.system_settings_menu_tree.connect("reload", lambda x: self.emit("reload"))

        self.system_settings_menu_source = None
        self.do_reload()

    def do_reload(self):
        self.system_settings_menu_source = self.system_settings_menu_tree.get_toplevel_flat_source()

    def always_show_descriptions(self):
        return True

    def get_enabled(self):
        return self.system_settings_menu_tree != None

    def get_icon(self, size):
        return self.system_settings_menu_source.get_icon(size)

    def get_comment(self):
        return self.system_settings_menu_source.get_comment()

    def get_items_uncached(self):
        if self.system_settings_menu_source:
            for item in self.system_settings_menu_source.get_items_uncached():
                yield item


#
# Toolbar Items
#

class UserMenu(gtk.Menu):
    def __init__(self):
        gtk.Menu.__init__(self)

        btn = gtk.ImageMenuItem(_("About Me"))
        btn.set_image(icon_factory.load_image("user-info", gtk.ICON_SIZE_LARGE_TOOLBAR))
        btn.connect("activate", lambda b: launcher.launch_command("gnome-about-me"))
        btn.show()
        self.append(btn)

        btn = gtk.ImageMenuItem(_("Switch User"))
        btn.set_image(icon_factory.load_image("gnome-lockscreen", gtk.ICON_SIZE_LARGE_TOOLBAR))
        btn.connect("activate", self._switch_user)
        btn.show()
        self.append(btn)

        btn = gtk.ImageMenuItem(_("Log Out..."))
        btn.set_image(icon_factory.load_image("gnome-logout", gtk.ICON_SIZE_LARGE_TOOLBAR))
        btn.connect("activate", self._logout, LogoutDialog.LOGOUT)
        btn.show()
        self.append(btn)

    def _logout(self, btn, method):
        dialog = LogoutDialog(method)
        dialog.show()

    def _switch_user(self, button):
        gdmclient.new_login()


class UserToolMenuButton(ToolMenuButton):
    def __init__(self, tooltips):
        # Get the user's real name from /etc/passwd
        pwent = pwd.getpwuid(os.getuid())
        self.username = pwent.pw_gecos.split(",")[0] or pwent.pw_name

        self.face_monitor = FileMonitor(os.path.expanduser("~/.face"))
        self.face_monitor.open()

        img = gtk.Image()
        self.face_monitor.connect("event", lambda m, u, ev, img: self._dot_face_changed, img)
        self._dot_face_changed(img)
        
        ToolMenuButton.__init__(self, img, self.username)
        self.set_tooltip(tooltips, _("Switch to another user"))
        self.set_menu(UserMenu())

    def _dot_face_changed(self, img):
        face = os.path.expanduser("~/.face")
        if not os.path.exists(face):
            face = "stock_person"
        img.set_from_pixbuf(icon_factory.load_icon(face, gtk.ICON_SIZE_LARGE_TOOLBAR))


class ShutdownToolButton(gtk.ToolButton):
    __gsignals__ = {
        "clicked" : "override"
        }

    def __init__(self, tooltips):
        img = icon_factory.load_image("gnome-shutdown", gtk.ICON_SIZE_LARGE_TOOLBAR)
        gtk.ToolButton.__init__(self, img, _("Shutdown..."))
        self.set_tooltip(tooltips, _("Shutdown or suspend this computer"))

    def do_clicked(self):
        dialog = LogoutDialog(LogoutDialog.SHUTDOWN)
        dialog.show()


class HelpToolMenuButton(ToolMenuButton):
    def __init__(self, tooltips):
        img = icon_factory.load_image(gtk.STOCK_HELP, gtk.ICON_SIZE_LARGE_TOOLBAR)
        ToolMenuButton.__init__(self, img, _("Help"))

        menu = gtk.Menu()
        self.set_menu(menu)

        about = gtk.ImageMenuItem(_("About Gnome"))
        about.set_image(icon_factory.load_image(gtk.STOCK_ABOUT, gtk.ICON_SIZE_LARGE_TOOLBAR))
        about.connect("activate", lambda w: launcher.launch_command("gnome-about"))
        about.show()
        menu.append(about)
        

class VolumeToolMenuButton(ToolMenuButton):
    '''Dummy placeholder until this implements a volume control'''
    def __init__(self, tooltips):
        img = icon_factory.load_image("gnome-audio", gtk.ICON_SIZE_LARGE_TOOLBAR)
        ToolMenuButton.__init__(self, img, "")
        self.set_tooltip(tooltips, _("Volume: 75%"))

        menu = gtk.Menu()
        self.set_menu(menu)

        mi = gtk.MenuItem(_("Not Implemented"))
        mi.set_sensitive(False)
        mi.show()
        menu.append(mi)


class NetworkLocationToolMenuButton(ToolMenuButton):
    '''Dummy placeholder until this implements NetworkManager-applet behavior'''
    def __init__(self, tooltips):
        img = icon_factory.load_image(gtk.STOCK_NETWORK, gtk.ICON_SIZE_LARGE_TOOLBAR)
        ToolMenuButton.__init__(self, img, "")
        self.set_tooltip(tooltips, _("Change the network location"))

        menu = gtk.Menu()
        self.set_menu(menu)

        mi = gtk.MenuItem(_("Not Implemented"))
        mi.set_sensitive(False)
        mi.show()
        menu.append(mi)


class SettingsMenu(gtk.Menu):
    '''
    Lists the Settings items split into columns by toplevel categorization,
    i.e. Preferences and Administration.
    '''
    def __init__(self):
        gtk.Menu.__init__(self)

        column = 0
        row_max = 14

        settings_source = SettingsSource()
        for source in settings_source.get_settings_menu_tree().get_toplevel_source_list():
            menu_items = []

            for item in source.get_items():
                img = gtk.Image()
                img.set_from_pixbuf(item.get_icon(gtk.ICON_SIZE_LARGE_TOOLBAR))
                menu_item = gtk.ImageMenuItem(item.get_name())
                menu_item.set_image(img)
                menu_item.connect("activate", lambda mi, i: i.open(), item)
                menu_item.show()
                menu_items.append(menu_item)

            for idx in range(len(menu_items)):
                mi_column = column + int(idx / row_max)
                mi_row = idx % row_max

                # Offset 2 rows for header and separator menu item
                self.attach(menu_items[idx],
                            mi_column, mi_column + 1,
                            mi_row + 2, mi_row + 3)

            col_cnt = idx / row_max
            if idx % row_max > 0:
                col_cnt = col_cnt + 1

            img = gtk.Image()
            img.set_from_pixbuf(source.get_icon(gtk.ICON_SIZE_LARGE_TOOLBAR))
            heading_item = gtk.ImageMenuItem(source.get_name())
            heading_item.set_image(img)
            heading_item.set_sensitive(False)
            heading_item.show()
            self.attach(heading_item, column, column + col_cnt, 0, 1);

            sep = gtk.SeparatorMenuItem()
            sep.show()
            self.attach(sep, column, column + col_cnt, 1, 2);

            column = column + col_cnt


class SettingsToolMenuButton(ToolMenuButton):
    def __init__(self, tooltips):
        img = icon_factory.load_image(gtk.STOCK_PREFERENCES, gtk.ICON_SIZE_LARGE_TOOLBAR)
        ToolMenuButton.__init__(self, img, _("Settings"))
        self.set_tooltip(tooltips, _("Preferences & Administration"))
        self.set_menu(SettingsMenu())


#
# Topic Implementation
#

class ComputerTopic(Topic):
    '''
    Lists a heterogeneous set of browsable system items, such as devices/drives,
    printers, and nearby computers (using Avahi).  Also lists control panel
    launchers in a flat list.
    '''
    def __init__(self):
        import platform
        system_alias_name = platform.system_alias(platform.system(),
                                                  platform.release(),
                                                  platform.version())[0] or _("Computer")
        Topic.__init__(self,
                       system_alias_name,
                       uri="topic://Computer",
                       icon="computer")

        from gimmie_running import ComputerRunningSource
        self.set_running_source_factory(lambda: ComputerRunningSource())

        self.update_time_timeout_id = None
        self.current_time = 0

    def do_reload(self):
        if gimmie_is_panel_applet():
            ### Show the Favorites source if in applet mode.  This is because
            ### applet mode doesn't have a dock for favorites.
            fav = [FavoritesSource(),
                   "---"] # separator
        else:
            fav = []

        source_list = [PlacesSource(),
                       DevicesSource(),
                       BonjourSource()]

        printers = PrinterSource()
        if printers.get_enabled():
            source_list.append(printers)

        settings = SettingsSource()
        source_list += [None, settings]

        if not settings.has_administration():
            try:
                source_list.append(AdministrationSource())
            except ValueError, err:
                print " !!! Error loading Administration items:", err
        
        ### Uncomment to list settings inside their toplevel folders in the sidebar
        #source_list += SettingsSource().get_toplevel_source_list()
        #source_list.append(None)

        recent = RecentAggregate(sources=[x for x in source_list if x])
        source_list = fav + [recent, None] + source_list

        self.set_sidebar_source_list(source_list)

    def accept_drops(self):
        return False
    
    def get_hint_color(self):
        return None

    def get_button_content(self, edge_gravity):
        if edge_gravity in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
            box = gtk.VBox(False, 0)
        else:
            box = gtk.HBox(False, 0)

        time_btn = Topic.get_button_content(self, edge_gravity)
        time_btn.show()
        box.pack_start(time_btn, True, True, 0)

        ### Uncomment to show Find button in corner
        #sep = gtk.VSeparator()
        #find = icon_factory.load_image(gtk.STOCK_FIND, 12)
        #find.show_all()
        #box.pack_start(sep, False, False, 0)
        #box.pack_start(find, False, False, 6)

        gconf_bridge.connect("changed::clockapplet",
                             lambda gb: self._clockapplet_changed(time_btn))
        self._clockapplet_changed(time_btn)

        return box

    def _clockapplet_changed(self, time_btn):
        if self.update_time_timeout_id:
            gobject.source_remove(self.update_time_timeout_id)
            self.update_time_timeout_id = None

        if gconf_bridge.get('clockapplet'):
            # Using the clock applet, just show the topic name
            time_btn.set_text(self.get_name())
        else:
            # Not using the clock applet, show the time in the topic button.
            # FIXME: Is updating ~every second acceptable?
            self.update_time_timeout_id = gobject.timeout_add(1000, self._update_time, time_btn)
            self._update_time(time_btn)

    def _update_time(self, time_btn):
        now_str = datetime.datetime.now().strftime(_("Computer, %l:%M %p"))
        if time_btn.get_text() != now_str:
            time_btn.set_text(now_str)
        return True

    def get_toolbar_items(self, tooltips):
        tools = []

        btn = UserToolMenuButton(tooltips)
        btn.set_is_important(True)
        tools.append(btn)

        ### Uncomment to show settings in a columned menu
        #btn = SettingsToolMenuButton(tooltips)
        #btn.set_is_important(True)
        #tools.append(btn)

        ### Uncomment to show network location chooser (unimplemeneted)
        #btn = NetworkLocationToolMenuButton(tooltips)
        #btn.set_is_important(True)
        #tools.append(btn)

        ### Uncomment to show volume selector in toolbar (unimplemented)
        #btn = VolumeToolMenuButton(tooltips)
        #btn.set_is_important(True)
        #tools.append(btn)

        tools.append(None)

        btn = ShutdownToolButton(tooltips)
        btn.set_is_important(True)
        tools.append(btn)

        tools.append(None)

        btn = HelpToolMenuButton(tooltips)
        btn.set_is_important(True)
        tools.append(btn)    

        return tools
