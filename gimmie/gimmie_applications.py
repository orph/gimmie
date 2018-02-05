
import os
import time
from gettext import gettext as _
from xml.sax import saxutils

import gobject
import gtk
import gnomedesktop

import wnck
import gmenu

from gimmie_globals import gimmie_is_panel_applet
from gimmie_base import ItemSource, Topic, gimmie_get_topic_for_uri
from gimmie_file import FileItem
from gimmie_recent import RecentlyUsed
from gimmie_util import bookmarks, icon_factory, icon_theme, launcher


#
#  Applications
#

class LauncherItem(FileItem):
    '''
    This is a FileItem because we want it\'s get_timestamp behavior.
    '''
    def __init__(self, uri):
        FileItem.__init__(self, uri=uri)

    def get_mimetype(self):
        return "application/x-desktop"

    def get_comment_markup(self):
        '''Return the comment if it exists, otherwise use the command in small monospace.'''
        if self.get_comment():
            return FileItem.get_comment_markup(self)
        else:
            return "<span size='small' font_family='monospace'>%s</span>" % \
                   saxutils.escape(self.get_command())

    def get_command(self):
        raise NotImplementedError

    def get_categories(self):
        raise NotImplementedError

    def do_open(self):
        print " *** Spawning app: %s" % self.get_command()
        ### See http://cvs.gnome.org/viewcvs/gnome-desktop/libgnome-desktop/gnome-desktop-item.c
        ### for the correct way to do this (ditem_execute()).

        self.timestamp = time.time()
        launcher.launch_command_with_uris(self.get_command(), [], self.get_uri())

    def matches_text(self, text):
        command = self.get_command()
        return FileItem.matches_text(self, text) or \
               (command and command.lower().find(text) > -1)

    def get_tooltip(self):
        return self.get_name()

    def handle_drag_data_received(self, selection, target_type):
        for uri in selection.get_uris():
            item = FileItem(uri)
            if item.get_mimetype() == "application/x-desktop":
                bookmarks.add_bookmark(uri, item.get_mimetype())
            else:
                launcher.launch_uri(uri)


class DesktopFileItem(LauncherItem):
    def __init__(self, uri):
        try:
            if os.path.dirname(uri):
                item = gnomedesktop.item_new_from_uri(uri, gnomedesktop.LOAD_ONLY_IF_EXISTS)
            else:
                item = gnomedesktop.item_new_from_basename(uri, gnomedesktop.LOAD_ONLY_IF_EXISTS)
        except gobject.GError:
            raise ValueError("File path not a .desktop file")

        if not item:
            raise ValueError("URI not found")

        LauncherItem.__init__(self, item.get_location())

        self.command = item.get_string(gnomedesktop.KEY_EXEC)
        if not self.command:
            raise ValueError("No Exec key in .desktop file")
        
        self.name = item.get_localestring(gnomedesktop.KEY_NAME)
        if not self.name:
            self.name = os.path.basename(uri)

        self.comment = item.get_localestring(gnomedesktop.KEY_COMMENT)
        if not self.comment:
            self.comment = item.get_localestring(gnomedesktop.KEY_GENERIC_NAME)

        self.command = item.get_string(gnomedesktop.KEY_EXEC)
        self.icon_name = item.get_string(gnomedesktop.KEY_ICON)

        catstr = item.get_string(gnomedesktop.KEY_CATEGORIES) or ""
        self.categories = catstr.split(";")

    def get_name(self):
        return self.name

    def get_comment(self):
        return self.comment

    def get_command(self):
        return self.command

    def get_icon(self, icon_size):
        if self.icon_name:
            try:
                found = gnomedesktop.find_icon(icon_theme, self.icon_name, icon_size, 0)
                return icon_factory.load_icon(found, icon_size)
            except IOError:
                print " !!! Unable to load icon_name:", self.icon_name
        return LauncherItem.get_icon(self, icon_size)

    def get_categories(self):
        return self.categories


class PanelLaunchers_NOTUSED(ItemSource):
    '''
    Loads all panel launchers from ~/.gnome2/panel2.d/default/launchers as bookmarks.
    '''
    def __init__(self, name, icon=None):
        ItemSource.__init__(self, name=name, icon=icon)

        recent_items = []

        logdirs = os.walk(os.path.expanduser("~/.gnome2/panel2.d/default/launchers"))
        for dir in logdirs:
            for file in dir[2]:
                path = os.path.join(dir[0], file)
                recent_items.append(DesktopFileItem(path))

        recent_items.sort(lambda x, y: y.get_timestamp() - x.get_timestamp())
        self.set_items(recent_items)


#
#  Menu-spec flattened tree
#

class MenuLauncherItem(LauncherItem):
    def __init__(self, menu_entry):
        LauncherItem.__init__(self, "file://" + menu_entry.get_desktop_file_path())
        self.menu_entry = menu_entry

    def get_name(self):
        return self.menu_entry.get_name()

    def get_comment(self):
        return self.menu_entry.get_comment()

    def get_icon(self, icon_size):
        icon = self.menu_entry.get_icon()
        if icon:
            return icon_factory.load_icon(icon, icon_size)
        return None

    def get_command(self):
        return self.menu_entry.get_exec()

    def get_desktop_file_id(self):
        return self.menu_entry.get_desktop_file_id()

    def pin(self):
        # MenuLauncherItem needs a gmenu.Entry object, so create a
        # DesktopFileItem which can be created from a URI and pin it instead.
        DesktopFileItem(self.get_uri()).pin()
        self.emit("reload")


class MenuSource(ItemSource):
    def __init__(self, menu_directory):
        ItemSource.__init__(self,
                            name=menu_directory.get_name(),
                            icon=menu_directory.get_icon() or "gnome-fs-directory",
                            comment=menu_directory.get_comment(),
                            filter_by_date=False)
        self.menu_directory = menu_directory

    def get_items_uncached(self):
        file_ids = []
        for item in self._add_recurse(self.menu_directory.contents, file_ids):
            yield item

    def _add_recurse(self, dir_contents, file_ids):
        for child in dir_contents:
            if isinstance(child, gmenu.Directory):
                for item in self._add_recurse(child.contents, file_ids):
                    yield item
            elif isinstance(child, gmenu.Entry):
                id = child.get_desktop_file_id()
                if id not in file_ids:
                    file_ids.append(id)
                    yield MenuLauncherItem(child)


class MenuTree(gobject.GObject):
    __gsignals__ = {
        "reload" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
        }
    
    def __init__ (self, menu_file):
        gobject.GObject.__init__(self)
        
        self.tree = gmenu.lookup_tree(menu_file)
        if not self.tree.root:
            raise ValueError("The menu file %s could not be found." % menu_file)

        # NOTE: Re-enabled for 0.3.  See Gimmie bug #419271, and
        #       gnome-menus bug #442747.
        self.tree.add_monitor(lambda *args: self.emit("reload"))

    def get_toplevel_sources(self):
        sources = []

        for toplevel in self.tree.root.contents:
            if isinstance(toplevel, gmenu.Directory):
                sources.append(MenuSource(toplevel))

        return sources

    def get_toplevel_items(self):
        items = []

        for toplevel in self.tree.root.contents:
            if isinstance(toplevel, gmenu.Entry):
                items.append(MenuLauncherItem(toplevel))

        return items

    def get_toplevel_items_source(self):
        items = self.get_toplevel_items()
        if len(items) > 0:
            source = ItemSource(name=_("Other"),
                                uri="source://ApplicationsOther",
                                icon="gnome-fs-directory",
                                filter_by_date=False)
            source.set_items(items)
            return source
        else:
            return None

    def get_toplevel_flat_source(self):
        return MenuSource(self.tree.root)

    def lookup_system_menu_file (menu_file):
        conf_dirs = None
        if os.environ.has_key("XDG_CONFIG_DIRS"):
            conf_dirs = os.environ["XDG_CONFIG_DIRS"]
        if not conf_dirs:
            conf_dirs = "/etc/xdg"

        for conf_dir in conf_dirs.split(":"):
            menu_file_path = os.path.join(conf_dir, "menus", menu_file)
            if os.path.isfile(menu_file_path):
                return menu_file_path
    
        return None


#
# Recently used Launchers
#

class RecentLaunchers(RecentlyUsed):
    def __init__(self, name, icon = "stock_calendar"):
        RecentlyUsed.__init__(self, name, icon)
        
    def include_item(self, item):
        return item.has_tag("Launchers")

    def get_items_uncached(self):
        for item in RecentlyUsed.get_items_uncached(self):
            try:
                yield DesktopFileItem(item.get_uri())
            except ValueError:
                print " !!! Error reading recent launcher: %s" % item.get_uri()


class RecentApplicationLaunchers(RecentLaunchers):
    def get_items_uncached(self):
        for item in RecentLaunchers.get_items_uncached(self):
            if "Settings" not in item.get_categories():
                yield item


class RecentSettingsLaunchers(RecentLaunchers):
    def get_items_uncached(self):
        for item in RecentLaunchers.get_items_uncached(self):
            if "Settings" in item.get_categories():
                yield item


#
# Toolbar Items
#

class InstallUpdateToolButton(gtk.ToolButton):
    __gsignals__ = {
        "clicked" : "override"
        }

    def __init__(self, tooltips):
        img = icon_factory.load_image("gnome-settings-default-applications",
                                      gtk.ICON_SIZE_LARGE_TOOLBAR)
        gtk.ToolButton.__init__(self, img, _("Install & Update"))
        self.set_tooltip(tooltips, _("Manage software on this computer"))

        # Find the installer command to run
        if os.path.isfile("/usr/bin/gnome-app-install"):
            cmd = "/usr/bin/gnome-app-install"
        elif os.path.isfile("/sbin/yast2"):
            # OpenSuSE specific
            cmd = "/sbin/yast2 sw_single"
        else:
            raise NotImplementedError, "No software manager found"

        # Try to run via sudo helper, either gksudo or gnomesu
        if os.path.isfile("/usr/bin/gksudo"):
            cmd = "/usr/bin/gksudo %s" % cmd
        elif os.path.isfile("/usr/bin/gnomesu"):
            cmd = "/usr/bin/gnomesu %s" % cmd
        elif os.path.isfile("/opt/gnome/bin/gnomesu"):
            # OpenSuSE specific
            cmd = "/opt/gnome/bin/gnomesu %s" % cmd

        self.cmd = cmd

    def do_clicked(self):
        launcher.launch_command(self.cmd)


class SettingsToolButton(gtk.ToolButton):
    __gsignals__ = {
        "clicked" : "override"
        }

    def __init__(self, tooltips):
        img = icon_factory.load_image("gnome-settings", gtk.ICON_SIZE_LARGE_TOOLBAR)
        gtk.ToolButton.__init__(self, img, _("Settings"))
        self.set_tooltip(tooltips, _("Manage settings and preferences"))

    def do_clicked(self):
        topic = gimmie_get_topic_for_uri("topic://Computer")
        topicwin = topic.get_topic_window()
        topicwin.set_source_by_uri("source://Settings")
        topicwin.present()


class ShowDesktopToolButton(gtk.ToolButton):
    __gsignals__ = {
        "clicked" : "override"
        }

    def __init__(self, tooltips):
        img = icon_factory.load_image("gnome-fs-desktop", gtk.ICON_SIZE_LARGE_TOOLBAR)
        gtk.ToolButton.__init__(self, img, _("Show Desktop"))
        self.set_tooltip(tooltips, "Hide all windows and show the desktop")

    def do_clicked(self):
        screen = wnck.screen_get(0)
        screen.toggle_showing_desktop(not screen.get_showing_desktop())


#
# Topic Implementation
#

class ApplicationsTopic(Topic):
    '''
    Lists recently opened launchers, and uses libgmenu to list application menu
    categories.
    '''
    def __init__(self):
        Topic.__init__(self,
                       _("Programs"),
                       uri="topic://Applications",
                       icon="gnome-main-menu")

        from gimmie_running import RunningNoSettingsApplications
        self.set_running_source_factory(lambda: RunningNoSettingsApplications())

        self.apps_menu_tree = None
        try:
            self.apps_menu_tree = MenuTree("applications.menu")
        except ValueError:
            try:
                # Some distros rename applications.menu.
                self.apps_menu_tree = MenuTree("gnome-applications.menu")
            except ValueError:
                pass
        if self.apps_menu_tree:
            self.apps_menu_tree.connect("reload", lambda x: self.emit("reload"))

    def do_reload(self):
        source_list = []

        source_list.append(RecentApplicationLaunchers(_("Recently Used")))

        if self.apps_menu_tree:
            source_list.append(None)
            source_list.extend(self.apps_menu_tree.get_toplevel_sources())
            other_apps = self.apps_menu_tree.get_toplevel_items_source()
            if other_apps:
                source_list.append(other_apps)

        self.set_sidebar_source_list(source_list)

    def get_hint_color(self):
        return gtk.gdk.color_parse("lightblue")

    def get_toolbar_items(self, tooltips):
        tools = []

        try:
            btn = InstallUpdateToolButton(tooltips)
            btn.set_is_important(True)
            tools.append(btn)
        except NotImplementedError:
            pass

        # Panel applet mode has easy access to Computer menu, so don't show this
        if not gimmie_is_panel_applet:
            btn = SettingsToolButton(tooltips)
            btn.set_is_important(True)
            tools.append(btn)

        ### Uncomment to add hide/show desktop button
        #btn = ShowDesktopToolButton(tooltips)
        #btn.set_is_important(True)
        #tools.append(btn)

        ### Uncomment to show F2-style Run dialog
        #img = icon_factory.load_image("gnome-run", gtk.ICON_SIZE_LARGE_TOOLBAR)
        #btn = gtk.ToolButton(img, _("Run"))
        #btn.set_tooltip(tooltips, _("Run a command"))
        #btn.set_is_important(True)
        #tools.append(btn)

        return tools

