
from gettext import gettext as _
import os

import gobject
import gtk
import wnck

from gimmie_base import Item, ItemSource
from gimmie_util import bookmarks, icon_factory


class RunningItem(Item):
    '''
    A wrapper around an Item and a WnckClassGroup or WnckApplication.
    '''
    def __init__(self, app_group, item = None):
        assert app_group, "WnckClassGroup app_group cannot be None"
        
        if item:
            Item.__init__(self,
                          uri=item.get_uri(),
                          timestamp=item.get_timestamp(),
                          mimetype=item.get_mimetype())
        else:
            Item.__init__(self,
                          uri="win-group://%s" % app_group.get_name(),
                          mimetype="x-unknown")

        self.item = item
        self.app_group = app_group

        # Listen for hint changes.
        for win in app_group.get_windows():
            win.connect("state-changed", self._win_state_changed)

    def get_name(self):
        if self.item:
            return self.item.get_name()
        else:
            return self.app_group.get_name()

    def get_comment(self):
        if self.item:
            return self.item.get_comment()
        else:
            return ""

    def get_icon(self, icon_size):
        if self.item:
            return self.item.get_icon(icon_size)
        else:
            ### FIXME: Support appgroups and applications?
            
            ### FIXME: Gaim/Pidgin has a tendency to set the group leader icon
            ###        to the latest buddy icon.
            if self.app_group.get_res_class() == "Gaim":
                icon = "gaim"
            elif self.app_group.get_res_class() == "Pidgin":
                icon = "pidgin"
            else:
                icon = self.app_group.get_icon()
            return icon_factory.load_icon(icon, icon_size)
            
    def do_open(self):
        screen = wnck.screen_get(0)
        opened_one = False

        app_wins = self.app_group.get_windows()
        active_ws = screen.get_active_workspace()

        # Sorted by stacking order
        visible_wins = [win for win
                        in screen.get_windows_stacked()
                        if win in app_wins and win.is_on_workspace(active_ws)]
        if not visible_wins and self.item:
            self.item.open()
            return

        if screen.get_active_window() in visible_wins:
            # Already active
            if len(visible_wins) > 1:
                # This group has the active win, so cycle the topmost active window down
                print " *** Raising window: ", visible_wins[0].get_name()
                visible_wins[0].activate(gtk.get_current_event_time())
            return
        else:
            # Not currently active, so raise them all
            for win in visible_wins:
                win.activate(gtk.get_current_event_time())
            return

        raise Exception("No application windows on this desktop, and no Item to launch")

    def get_is_opened(self):
        if self.app_group and self.app_group.get_windows():
            return True
        return (self.item and self.item.get_is_opened()) or False

    def get_is_active(self):
        if self.app_group:
            for win in self.app_group.get_windows():
                if win.is_active():
                    return True
        return (self.item and self.item.get_is_active()) or False
 
    def get_can_pin(self):
        if self.item:
            return self.item.get_can_pin()
        return False

    def set_screen_position(self, x, y, w, h):
        '''
        Set the _NET_WM_ICON_GEOMETRY window manager hint on all the
        app-group\'s windows so that they will minimize onto this item\'s area.
        '''
        for win in self.app_group.get_windows():
            win.set_icon_geometry(x, y, w, h)

    def get_tooltip(self):
        if self.item:
            return self.item.get_tooltip()
        else:
            return self.app_group.get_name()

    def _win_state_changed(self, win, changemask, newstate):
        ### FIXME: We seem to miss events if we filter, so always emit
        # 1024 == WNCK_WINDOW_STATE_DEMANDS_ATTENTION
        #if changemask & 1024:
        self.emit("reload")

    def get_is_user_visible(self):
        workspace = wnck.screen_get_default().get_active_workspace()
        for win in self.app_group.get_windows():
            if win.is_visible_on_workspace(workspace) and \
                   win.get_window_type() in (0, 7, 8):
                # (Normal, Utility, Splashscreen) window
                return True
        else:
            if self.item:
                return self.item.get_is_user_visible()
            return False

    def get_demands_attention(self):
        for win in self.app_group.get_windows():
            if win.needs_attention():
                return True
        return False

    def handle_drag_data_received(self, selection, target_type):
        if self.item:
            self.item.handle_drag_data_received(selection, target_type)


class RunningItemSource(ItemSource):
    def __init__(self, name):
        ItemSource.__init__(self, name=name)

        self.screen = wnck.screen_get(0)
        self.timeout_id = None

        self.screen.connect("window-opened", lambda x, y: self.queue_reload_maybe(y))
        self.screen.connect("window-closed", lambda x, y: self.queue_reload_maybe(y))
        self.screen.connect("application-opened", self.queue_reload)
        self.screen.connect("application-closed", self.queue_reload)
        self.screen.connect("active-workspace-changed", self.queue_reload)

        bookmarks.connect("reload", lambda x: self.emit("reload"))
    
    def get_bookmark_items(self):
        raise NotImplementedError

    def get_item_for_uri(self, launch_uri):
        raise NotImplementedError

    def do_reload(self):
        raise NotImplementedError

    def queue_reload(self, *args):
        if self.timeout_id:
            gobject.source_remove(self.timeout_id)
        self.timeout_id = gobject.timeout_add(50, lambda: self.emit("reload"))

    def queue_reload_maybe(self, win):
        # ignore dock windows (wnck bindings are broken)
        if win.get_window_type() != 2:
            self.queue_reload()


#
#  Applications
#

from gimmie_applications import LauncherItem, DesktopFileItem
from gimmie_file import FileItem
from gimmie_util import launcher

class RunningApplications(RunningItemSource):
    def __init__(self):
        RunningItemSource.__init__(self, name="Running Applications")

    def munge_command_and_wmclass(self, cmd, app):
        split = cmd.split()
        cmd = os.path.basename(split[0]).lower()

        # FIXME: Hack around gksu commands
        if cmd in ("gksu", "gksudo", "gnomesu"):
            for i in split[1:]:
                if i[0] != '-': # Skip gksu options
                    cmd = os.path.basename(i.strip('"')).lower()
                    break

        return cmd == app.get_name().lower() or \
               cmd == app.get_res_class().lower() or \
               cmd + "-bin" == app.get_res_class().lower()

    def get_bookmark_items(self):
        items = []
        # Make DesktopFileItem for all launcher bookmarks
        for uri, mime in bookmarks.get_bookmarks(["application/x-desktop"]):
            app_item = self.get_item_for_uri(uri)
            if app_item:
                items.append(app_item)
        return items

    def get_item_for_uri(self, launch_uri):
        try:
            return DesktopFileItem(launch_uri)
        except ValueError:
            return None

    def do_reload(self):
        class_groups = {} # Key: WnckClassGroup, Value: [launcher_uri, ...]

        active_ws = self.screen.get_active_workspace()
        for win in self.screen.get_windows_stacked():
            if win.is_on_workspace(active_ws):
                # Only care about Normal, Utility, Splashscreen windows
                if win.get_window_type() not in (0, 7, 8):
                    continue

                class_group = win.get_class_group()
                if not class_group or class_group.get_name() == "gimmie":
                    continue

                # FIXME: Hack to avoid showing Gaim/Pidgin windows with the
                # "conversation" role.
                if class_group.get_name() in ("gaim", "Pidgin"):
                    gdk_win = gtk.gdk.window_foreign_new(win.get_xid())
                    if gdk_win:
                        role = gdk_win.property_get("WM_WINDOW_ROLE")
                        if role and role[2] == "conversation":
                            continue

                app = win.get_application()
                launch_uri, timestamp = launcher.parse_startup_id(app.get_startup_id())
                if launch_uri:
                    # FIXME: Hack to avoid showing application windows for
                    # non-launcher URIs opened through Gimmie.  Remove to always
                    # show application icons.
                    if not launch_uri.endswith(".desktop"):
                        continue

                # Store the class group
                if class_group not in class_groups:
                    class_groups[class_group] = []

                if launch_uri and launch_uri not in class_groups[class_group]:
                    class_groups[class_group].append(launch_uri)

        items = []

        # Make DesktopFileItems for all launcher bookmarks
        bookmark_items = self.get_bookmark_items()
        items.extend(bookmark_items) # Add all the bookmarks first

        ### Uncomment to append panel's launchers as bookmarks
        #bookmark_items.extend(PanelLaunchers(self.get_name()).get_items())

        # Append running apps (if no launcher exists already)
        for class_group, launcher_uris in class_groups.items():
            # Try matching with a bookmark
            for b in bookmark_items:
                # Match the class-group's startup_id with the launcher path
                if b.get_uri() in launcher_uris:
                    print " *** Window startup-id matches launcher path: %s" % b.get_uri()
                    items[items.index(b)] = RunningItem(class_group, b)
                    launcher_uris.remove(b.get_uri())
                    break

                # Otherwise, try munging the launcher's Exec with the class-group's WM_CLASS
                if self.munge_command_and_wmclass(b.get_command(), class_group):
                    print " *** Window class matches launcher command: %s == %s" % (
                        class_group.get_res_class().lower(),
                        b.get_command())
                    items[items.index(b)] = RunningItem(class_group, b)
                    break
            else:
                # No bookmark matches.  Try to create a DesktopFileItem for the
                # class-group's startup-id launchers.  Using a launcher gets us
                # good names and rich icons.
                for launcher_uri in launcher_uris:
                    item = self.get_item_for_uri(launcher_uri)
                    if item:
                        items.append(RunningItem(class_group, item))
                        break
                else:
                    items.append(RunningItem(class_group, None))

        self.set_items(items)
        return False

    def handle_drag_data_received(self, selection, target_type):
        for uri in selection.get_uris():
            item = FileItem(uri)
            if item.get_mimetype() == "application/x-desktop":
                bookmarks.add_bookmark(uri, item.get_mimetype())
            else:
                launcher.launch_uri(uri)


class RunningNoSettingsApplications(RunningApplications):
    def __init__(self):
        RunningApplications.__init__(self)

    def get_items(self):
        items = []
        for item in RunningApplications.get_items(self):
            launcher = item
            if isinstance(item, RunningItem):
                if not item.item:
                    items.append(item)
                    continue
                launcher = item.item
            if isinstance(launcher, LauncherItem):
                if "Settings" not in launcher.get_categories():
                    items.append(item)
        return items


class RunningSettingsApplications(RunningApplications):
    def __init__(self):
        RunningApplications.__init__(self)

    def get_items(self):
        items = []
        for item in RunningApplications.get_items(self):
            launcher = item
            if isinstance(item, RunningItem):
                launcher = item.item
            if isinstance(launcher, LauncherItem):
                if "Settings" in launcher.get_categories():
                    items.append(item)
        return items


#
#  Computer
#

from gimmie_base import IOrientationAware
from gimmie_gui import FriendlyClock, FriendlyPager, TrayManagerBox
from gimmie_trash import TrashItem
from gimmie_util import gconf_bridge

class ComputerRunningSource(ItemSource, IOrientationAware):
    def __init__(self):
        ItemSource.__init__(self, name="Computer Running Source")
        self.pager = None
        self.orientation = None

        try:
            # This might not exist, so be careful
            self.tray_mgr = TrayManagerBox()
            self.tray_mgr.show()
        except AttributeError:
            self.tray_mgr = None

        self.pager = FriendlyPager(wnck.screen_get_default())
        self.pager.show()
        self.pager_align = gtk.Alignment()
        self.pager_align.add(self.pager)
        self.pager_align.show()

        self.clock = FriendlyClock()
        self.clock.show()

        self.settings_apps = RunningSettingsApplications()
        self.settings_apps.connect_after("reload", lambda x: self.emit("reload"))

        gconf_bridge.connect("changed::clockapplet", lambda gb: self.emit("reload"))

    def set_orientation(self, orientation):
        self.orientation = orientation
        if self.pager:
            self.pager.set_orientation(orientation)
            if self.orientation == gtk.ORIENTATION_VERTICAL:
                self.pager_align.set_property("top-padding", 2)
                self.pager_align.set_property("bottom-padding", 2)
            else:
                self.pager_align.set_property("left-padding", 2)
                self.pager_align.set_property("right-padding", 2)

    def get_orientation(self, orientation):
        return self.orientation

    def do_reload(self):
        items = []

        # Add workspace switcher first.
        items.append(self.pager_align)

        # Add running/bookmarked settings apps
        items += self.settings_apps.get_items()

        # Add box containing tray icons
        if self.tray_mgr:
            items.append(self.tray_mgr)

        # Add a clock if /apps/gimmie/clockapplet is True
        if gconf_bridge.get('clockapplet'):
            items.append(self.clock)

        # Add a trashcan, put it at the end to make it a stable drop target
        items.append(TrashItem())

        self.set_items(items)


#
#  Documents
#

class RunningDocuments(RunningItemSource):
    '''
    A quick hack to look for DESKTOP_STARTUP_IDs containing URIs
    on Gimmie-launched running windows.  This only works for
    documents opened via the Documents window.
    '''
    def __init__(self):
        RunningItemSource.__init__(self, name="Opened Documents")

    def get_bookmark_items(self):
        items = []
        # Make FileItem for all document bookmarks
        for uri, mime in bookmarks.get_bookmarks():
            if mime not in ("application/x-desktop",
                            "purple/buddy", "gaim/buddy"):
                try:
                    items.append(FileItem(uri))
                except ValueError:
                    pass
        return items

    def get_item_for_uri(self, launch_uri):
        item = FileItem(launch_uri)
        if item.get_mimetype() in ("application/x-desktop",
                                   "purple/buddy", "gaim/buddy",
                                   "purple/log", "gaim/log",
                                   None):
            # Avoid showing launchers or conversations as running documents
            return None
        return item

    def do_reload(self):
        apps = []
        items = []
        bookmark_items = []

        # Make DesktopFileItems for all launcher bookmarks
        bookmark_items = self.get_bookmark_items()
        items.extend(bookmark_items)

        active_ws = self.screen.get_active_workspace()
        for win in self.screen.get_windows():
            if not win.is_on_workspace(active_ws):
                continue
            
            app = win.get_application()
            if not app or app in apps:
                continue
            apps.append(app)
            
            id = app.get_startup_id()
            if id and id.startswith("GIMMIE:"):
                try:
                    uri = id[len("GIMMIE:"):id.rfind("_TIME")]
                    timestamp = id[id.rfind("_TIME") + len("_TIME"):]

                    for b in bookmark_items:
                        if uri and (uri == b.get_uri() or uri == b.get_local_path()):
                            items[items.index(b)] = RunningItem(app, b)
                            break
                    else:
                        if uri:
                            item = self.get_item_for_uri(uri)
                            if item:
                                items.append(RunningItem(app, item))
                        #else:
                        #    items.append(RunningItem(app, None))
                except IndexError:
                    continue

        self.set_items(items)
        return False

    def handle_drag_data_received(self, selection, target_type):
        for uri in selection.get_uris():
            item = self.get_item_for_uri(uri)
            if item:
                bookmarks.add_bookmark(uri, item.get_mimetype())


#
# People
#

from gimmie_gaim import gaim_reader, gaim_dbus
from gimmie_pidgin import pidgin_reader, pidgin_dbus

class RunningChat(Item):
    '''
    A simple Item subclass that focuses the window passed to init on open.
    '''
    def __init__(self, buddy, win):
        Item.__init__(self,
                      uri=buddy.get_uri(),
                      timestamp=buddy.get_timestamp(),
                      icon=None)
        self.buddy = buddy
        self.win = win

        # Listen for hint changes.
        self.win.connect("state-changed", self._win_state_changed)

    def get_mimetype(self):
        return self._get_mime_prefix() + "/conversation"

    def _get_mime_prefix(self):
        if self.win.get_class_group().get_name() == "pidgin":
            return "purple"
        else:
            return "gaim"

    def _win_state_changed(self, win, changemask, newstate):
        ### FIXME: We seem to miss events if we filter, so always emit
        # 1024 == WNCK_WINDOW_STATE_DEMANDS_ATTENTION
        #if changemask & 1024:
        self.emit("reload")

    def get_icon(self, icon_size):
        return self.buddy.get_icon(icon_size)

    def get_name(self):
        return self.buddy.get_name()

    def get_is_opened(self):
        return True

    def get_demands_attention(self):
        return self.win.needs_attention()

    def do_open(self):
        self.win.activate(gtk.get_current_event_time())

    def handle_drag_data_received(self, selection, target_type):
        for uri in selection.get_uris():
            if uri.lower().startswith("aim:goim?screenname="):
                bookmarks.add_bookmark(uri, self._get_mime_prefix() + "/buddy")


class RunningChats(RunningItemSource):
    '''
    A quick hack to use Gaim/Pidgin window titles to determine currently active
    chats.  This only works if you turn off tabbed chat mode and enable the
    remote control plugin.
    '''
    def __init__(self):
        RunningItemSource.__init__(self, name="Active Conversations")

        # Listen for changes in the Gaim/Pidgin files
        gaim_reader.connect("reload", lambda x: self.emit("reload"))
        pidgin_reader.connect("reload", lambda x: self.emit("reload"))

        ### Gaim2 D-BUS interface has no way to signal changes, so just poll
        #gobject.timeout_add(1000, lambda: self.emit("reload") or True)

    def _get_screenname_from_uri(self, uri):
        if uri.lower().startswith("aim:goim?screenname="):
            return uri[len("aim:goim?screenname="):].strip("\"'") # Trim quotemarks
        return None

    def _get_buddy_for_screenname(self, screenname):
        screenname = screenname.lower()
        all_buddies = pidgin_reader.get_all_buddies() + gaim_reader.get_all_buddies()
        buddies = [x for x \
                   in all_buddies \
                   if screenname in (x.get_screenname().lower(), x.get_alias().lower())]
        if not buddies:
            return None

        # FIXME: Filter for online accounts.  Just use auto-login for now.
        if len(buddies) > 1:
            auto_buddies = [x for x in buddies if x.get_account().get_auto_login()]
            if auto_buddies:
                buddies = auto_buddies

        # FIXME: This arbitrarily picks the first one
        return buddies[0]

    def get_bookmark_items(self):
        items = []
        for uri, mime in bookmarks.get_bookmarks(["purple/buddy", "gaim/buddy"]):
            buddy = self.get_item_for_uri(uri)
            if buddy:
                items.append(buddy)
        return items

    def get_item_for_uri(self, launch_uri):
        try:
            screenname = self._get_screenname_from_uri(launch_uri)
            if screenname == None:
                return None
            buddy = self._get_buddy_for_screenname(screenname)
            return buddy
        except (ValueError, IndexError):
            return None

    def do_reload(self):
        items = []

        # Get Gaim/PidginBuddy items for all people bookmarks
        bookmark_items = self.get_bookmark_items()
        items.extend(bookmark_items)

        ### FIXME: Use Gaim2 D-BUS to list open conversations.  More work needed here.
        #try:
        #    convs = gaim_dbus.GaimGetConversations()
        #    conv_names = [gaim_dbus.GaimConversationGetName(x) for x in convs]
        #    conv_buddies = [self._get_buddy_for_screenname(x) for x in conv_names]
        #
        #    items += [b for b in conv_buddies if b not in bookmark_items]
        #    if items == self.items:
        #        print "HALTING EMISSION!"
        #        self.emit_stop_by_name("reload")
        #    else:
        #        self.set_items(items)
        #    return True
        #except (dbus.DBusException, TypeError):
        #    pass

        active_ws = self.screen.get_active_workspace()
        for win in self.screen.get_windows():
            if not win.is_on_workspace(active_ws):
                continue

            if win.get_class_group().get_name() not in ("gaim", "Pidgin"):
                continue

            screenname = win.get_name().lower()
            if screenname[0] == '(' and screenname[-1] == ')': # Strip offline indicator
                screenname = screenname[1:-1]

            for b in bookmark_items:
                if screenname in (b.get_screenname().lower(), b.get_alias().lower()):
                    items[items.index(b)] = RunningChat(b, win)
                    break
            else:
                buddy = self._get_buddy_for_screenname(screenname)
                if buddy:
                    items.append(RunningChat(buddy, win))

            # FIXME: Figure out proper tabbed conversation support.
            # Look for a new buddy match when the window title changes.
            if not hasattr(win, "gimmie_name_changed_slot"):
                win.gimmie_name_changed_slot = win.connect("name-changed",
                                                           lambda x: self.emit("reload"))

        self.set_items(items)
        return False

    def handle_drag_data_received(self, selection, target_type):
        for uri in selection.get_uris():
            item = self.get_item_for_uri(uri)
            if item:
                bookmarks.add_bookmark(uri, item.get_mimetype())
