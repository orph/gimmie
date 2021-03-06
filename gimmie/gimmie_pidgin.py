
import datetime
import re
import os
from gettext import gettext as _
from xml.dom.minidom import parse
from xml.sax import saxutils

import gobject
import dbus

from gimmie_base import Item, ItemSource
from gimmie_util import bookmarks, launcher, icon_factory, FileMonitor, DBusWrapper

#
# FIXME: This should be merged with gimmie_gaim.py.
#        This is just a copy with s/gaim/purple/ everywhere.
#

class PidginBuddy(Item):
    def __init__(self, node):
        self.account_name = node.getAttribute("account")
        self.proto = node.getAttribute("proto")

        # Getting the Screenname
        try:
            try:
                self.screenname = node.getElementsByTagName("component")[0].childNodes[0].data
            except IndexError:
                self.screenname = node.getElementsByTagName("name")[0].childNodes[0].data
        except IndexError:
            self.screenname = ""

        # Getting the Alias
        try:
            self.alias = node.getElementsByTagName("alias")[0].childNodes[0].data
        except IndexError:
            try:
                account = pidgin_dbus.PurpleAccountsFindAny(self.account_name, self.proto)
                buddy = pidgin_dbus.PurpleFindBuddy(account, self.screenname)
                self.alias = pidgin_dbus.PurpleBuddyGetAlias(buddy)
            except dbus.DBusException:
                self.alias = ""

        self.buddy_icon = None
        
        icondir = os.path.expanduser("~/.purple/icons")

        for setting in node.getElementsByTagName("setting"):
            if setting.getAttribute("name") == "buddy_icon":
                path = setting.childNodes[0].data
                if os.path.split(path)[0] == "":
                    path = os.path.join(icondir, path)
                if os.path.exists(path):
                    self.buddy_icon = path
                break

        Item.__init__(self,
                      uri="aim:goim?screenname=\"%s\"" % self.screenname,
                      mimetype="purple/buddy")

        self.idle_time = None

    def get_name(self):
        return self.get_displayname()

    def get_displayname(self):
        return self.get_alias() or self.get_screenname()

    def get_screenname(self):
        return self.screenname

    def get_alias(self):
        return self.alias

    def get_icon(self, icon_size):
        icon = None
        if self.buddy_icon:
            icon = icon_factory.load_icon(self.buddy_icon, icon_size)
            if icon:
                icon = icon_factory.make_icon_frame(icon, icon_size, True)
        if not icon:
            acct_type = self.get_account().get_nice_protocol()
            if acct_type == "aim" and self.get_screenname()[:1].isdigit():
                # ICQ screennames start with a number
                acct_type = "icq"
            icon = icon_factory.load_icon("im-" + acct_type, icon_size)
        if not icon:
            icon = icon_factory.load_icon("stock_person", icon_size)

        try:
            if not self.get_is_online():
                icon = icon_factory.greyscale(icon)
        except (dbus.DBusException, TypeError):
            icon = icon_factory.greyscale(icon)

        return icon

    def get_comment(self):
        comment = ""

        if pidgin_reader.get_buddy_has_name_clash(self):
            if self.get_alias():
                comment = self.get_screenname()
            else:
                comment = self.get_account_name()

        try:
            if self.get_is_online():
                status_id = pidgin_dbus.PurplePresenceGetActiveStatus(self.get_presence_dbus_obj())
                msg = pidgin_dbus.PurpleStatusGetAttrString(status_id, "message")
                if msg:
                    if comment: comment += "\n"
                    comment += re.sub('<.*?>', '', msg)
                elif not self.get_is_available():
                    if comment: comment += "\n"
                    if self.get_is_idle():
                        idle_time = self.get_idle_time()
                        if idle_time:
                            comment += _("Idle since %s") % \
                                       self.pretty_print_time_since(idle_time, include_today=False)
                        else:
                            comment += _("Idle")
                    else:
                        comment += _("Away")
            else:
                if comment: comment += "\n"
                comment += _("Offline")
        except (dbus.DBusException, TypeError):
            pass

        return comment

    def get_name_markup(self):
        # Reimplemented from Item to make <3 last
        markup = saxutils.escape(self.get_name() or "")
        online = "<span foreground='limegreen'>&#x25cf;</span>"
        heart = self.get_is_pinned() and " <span foreground='red'>&#x2665;</span>" or ""

        try:
            if self.get_is_online():
                if self.get_is_available():
                    return "%s %s%s" % (markup, online, heart)
                else:
                    return "<i>%s</i> %s%s" % (markup, online, heart)
        except (dbus.DBusException, TypeError):
            pass

        return "<span foreground='darkgrey'><i>%s</i></span>%s" % (markup, heart)

    def matches_text(self, text):
        '''
        Override Item.matches_text to avoid searching the comment, since it can
        be slow do fetch with D-BUS, and isn\'t reliable anyway.
        '''
        return (self.screenname.lower().find(text) > -1) or \
               (self.alias and self.alias.lower().find(text) > -1)

    def set_account(self, acct):
        self.account = acct

    def get_account(self):
        return self.account

    def get_account_name(self):
        return self.account_name

    def do_open(self):
        try:
            self.get_account().go_online() # Log in
            conv = pidgin_dbus.PurpleConversationNew(1, # Create IM conversation
                                                 self.get_account().get_dbus_obj(),
                                                 self.get_screenname())
            pidgin_dbus.PurpleConversationPresent(conv)
            print " *** Starting new Pidgin conversation with '%s'" % self.get_screenname()
        except (dbus.DBusException, TypeError):
            print " *** Calling purple-remote uri: %s" % self.get_uri()
            launcher.launch_command("purple-remote uri %s" % self.get_uri())

    def get_is_online(self):
        return pidgin_dbus.PurpleBuddyIsOnline(self.get_dbus_obj()) > 0

    def get_is_available(self):
        return pidgin_dbus.PurplePresenceIsAvailable(self.get_presence_dbus_obj())

    def get_is_idle(self):
        return pidgin_dbus.PurplePresenceIsIdle(self.get_presence_dbus_obj())

    def get_idle_time(self):
        return self.idle_time

    def reset_idle_time(self):
        self.idle_time = datetime.datetime.now()

    def clear_idle_time(self):
        self.idle_time = None

    def get_presence_dbus_obj(self):
        return pidgin_dbus.PurpleBuddyGetPresence(self.get_dbus_obj())

    def get_dbus_obj(self):
        return pidgin_dbus.PurpleFindBuddy(self.get_account().get_dbus_obj(),
                                       self.get_screenname())

    def get_log_path(self):
        return os.path.join(self.get_account().get_log_path(), self.get_screenname().lower())

    def get_timestamp(self):
        try:
            return os.path.getmtime(self.get_log_path())
        except OSError:
            return 0

    def get_is_opened(self):
        try:
            return pidgin_dbus.PurpleFindConversationWithAccount(1,
                                                             self.get_screenname(),
                                                             self.get_account().get_dbus_obj()) != 0
        except (dbus.DBusException, TypeError):
            return False

    def handle_drag_data_received(self, selection, target_type):
        for uri in selection.get_uris():
            if uri.lower().startswith("aim:goim?screenname="):
                bookmarks.add_bookmark(uri, "purple/buddy")

    def pin(self):
        # PidginBuddy needs an XML node with content from the pidgin config file, so
        # create a PidginBuddyUri which can be created from a URI and pin it
        # instead.
        PidginBuddyUri(self.get_uri()).pin()
        self.emit("reload")


class PidginBuddyUri(Item):
    def __init__(self, uri):
        assert uri.startswith("aim:"), "Pidgin buddy URI does not begin with aim:"
        Item.__init__(self, uri=uri, mimetype="purple/buddy")

        pidgin_reader.connect("reload", lambda r, u: self._find_buddy(u), uri)
        self._find_buddy(uri)

    def _find_buddy(self, uri):
        for buddy in pidgin_reader.get_all_buddies():
            if buddy.get_uri() == uri:
                self.pidgin_buddy = buddy
                buddy.connect("reload", lambda b: self.emit("reload"))
                self.emit("reload")
                break
        else:
            raise ValueError("Buddy for URI '%s' not found" % uri)

    def __getattribute__(self, name):
        try:
            if hasattr(gobject.GObject, name) or name == "pin":
                # Allow connect et al. to reach this gobject
                return Item.__getattribute__(self, name)
            else:
                # Avoid infinite recursion accessing pidgin_buddy
                pidgin_buddy = Item.__getattribute__(self, "pidgin_buddy")
                return getattr(pidgin_buddy, name)
        except AttributeError:
            return Item.__getattribute__(self, name)


class PidginGroup:
    def __init__(self, node):
        self.name = node.getAttribute("name")
        self.buddy_list = []

        for chat in node.getElementsByTagName("chat"):
            buddy = PidginBuddy(chat)
            self.buddy_list.append(buddy)

        for contact in node.getElementsByTagName("contact"):
            for node in node.getElementsByTagName("buddy"):
                buddy = PidginBuddy(node)
                self.buddy_list.append(buddy)

    def get_name(self):
        return self.name

    def get_buddies(self):
        return self.buddy_list

    def get_dbus_obj(self):
        return pidgin_dbus.PurpleindGroup(self.get_name())


class PidginAccount(ItemSource):
    def __init__(self, node):
        self.protocol = node.getElementsByTagName("protocol")[0].childNodes[0].data
        self.screenname = node.getElementsByTagName("name")[0].childNodes[0].data

        self.alias = None
        try:
            self.alias = node.getElementsByTagName("alias")[0].childNodes[0].data
        except IndexError:
            if self.protocol == "prpl-jabber":
                # Strip the trailing /resource from the screenname
                try:
                    self.alias = self.screenname[:self.screenname.rindex("/")]
                except ValueError:
                    pass

        uri = "source://Purple/%s/%s" % (self.get_nice_protocol(), self.screenname)
        comment = self.alias and self.screenname or None
        ItemSource.__init__(self, uri=uri, comment=comment, filter_by_date=False)

        self.buddyicon = None
        buddyicon = node.getElementsByTagName("buddyicon")
        if buddyicon:
            self.buddyicon = buddyicon[0].childNodes[0].data

        for setting in node.getElementsByTagName("setting"):
            if setting.getAttribute("name") == "auto-login":
                if setting.childNodes[0].data == "1":
                    self.auto_login = True
                    break
        else:
            self.auto_login = False

        self.buddy_list = []
        self.group_list = []

    def get_name(self):
        # Try to use the shorter alias if it's set.
        return self.get_alias() or self.get_screenname()

    def get_screenname(self):
        return self.screenname

    def get_alias(self):
        return self.alias

    def get_auto_login(self):
        return self.auto_login

    def get_protocol(self):
        return self.protocol

    def get_nice_protocol(self):
        if self.protocol == "prpl-oscar":
            return "aim"
        if self.protocol.startswith("prpl-"):
            return self.protocol[len("prpl-"):]
        return self.protocol

    def get_icon(self, icon_size):
        icon = None
        if self.buddyicon:
            icon = icon_factory.load_icon(self.buddyicon, icon_size)
            if icon:
                icon = icon_factory.make_icon_frame(icon, icon_size, True)
        if not icon:
            acct_type = self.get_nice_protocol()
            if acct_type == "aim" and self.get_name()[:1].isdigit():
                # ICQ screennames start with a number
                acct_type = "icq"
            icon = icon_factory.load_icon("im-" + acct_type, icon_size)
        if not icon:
            icon = icon_factory.load_icon("stock_person", icon_size)

        return icon

    def get_items(self):
        return self.buddy_list

    def add_buddy(self, buddy):
        self.buddy_list.append(buddy)

    def is_online(self, _account = None):
        return pidgin_dbus.PurpleAccountIsConnected(_account or self.get_dbus_obj())

    def go_online(self):
        account = self.get_dbus_obj()
        if not self.is_online(account):
            pidgin_dbus.PurpleAccountSetStatusVargs(account, "online", 1)
            pidgin_dbus.PurpleAccountConnect(account)

    def go_offline(self):
        account = self.get_dbus_obj()
        if self.is_online(account):
            pidgin_dbus.PurpleAccountSetStatusVargs(account, "online", 0)
            pidgin_dbus.PurpleAccountDisconnect(account)

    def get_dbus_obj(self, connect = False):
        return pidgin_dbus.PurpleAccountsFindAny(self.get_screenname(), self.get_protocol())

    def get_log_path(self):
        # Pidgin does not include Jabber's account resource in the logdir name
        logdir = self.get_name().lower().rsplit("/", 1)[0]
        return os.path.join(os.path.expanduser("~/.purple/logs"),
                            self.get_nice_protocol(),
                            logdir)


class PidginAccountReader(gobject.GObject):
    __gsignals__ = {
        "reload" : (gobject.SIGNAL_RUN_FIRST,
                    gobject.TYPE_NONE,
                    ()),
        "status-changed" : (gobject.SIGNAL_RUN_FIRST,
                            gobject.TYPE_NONE,
                            ())
        }

    def __init__(self):
        gobject.GObject.__init__(self)

        self.accounts_path = os.path.expanduser("~/.purple/accounts.xml")
        self.blist_path = os.path.expanduser("~/.purple/blist.xml")

        # Listen for changes to user's Pidgin accounts
        self.accounts_monitor = FileMonitor(self.accounts_path)
        self.accounts_monitor.connect("created", lambda a, b: self.emit("reload"))
        self.accounts_monitor.connect("changed", lambda a, b: self.emit("reload"))
        self.accounts_monitor.open()

        # Connect to dbus signals to notify us of buddy status changes
        try:
            # Update to a single buddy
            pidgin_dbus.connect_to_signal("BuddyStatusChanged", self._status_changed)
            pidgin_dbus.connect_to_signal("BuddyIdleChanged", self._idle_changed)
            pidgin_dbus.connect_to_signal("BuddySignedOn", self._signed_on)
            pidgin_dbus.connect_to_signal("BuddySignedOff", self._signed_off)
            pidgin_dbus.connect_to_signal("BuddyIconChanged", self._icon_changed)

            # Need to reread the blist.xml file
            pidgin_dbus.connect_to_signal("BuddyAdded", self._added)
            pidgin_dbus.connect_to_signal("BuddyRemoved", self._removed)

            # Update to user's account status
            pidgin_dbus.connect_to_signal("AccountStatusChanged", self._status_changed)
        except dbus.DBusException:
            # Fallback to listing for blist.xml writes
            self.blist_monitor = FileMonitor(self.blist_path)
            self.blist_monitor.connect("created", lambda a, b: self.emit("reload"))
            self.blist_monitor.connect("changed", lambda a, b: self.emit("reload"))
            self.blist_monitor.open()

        self.emit("reload")

    def _get_buddy_by_dbus_obj(self, dbus_obj):
        for buddy in self.buddy_list:
            try:
                if buddy.get_dbus_obj() == dbus_obj:
                    return buddy
            except dbus.DBusException:
                pass
        return None

    def _update_buddy(self, dbus_obj):
        buddy = self._get_buddy_by_dbus_obj(dbus_obj)
        if buddy:
            buddy.emit("reload")
        else:
            print " !!! Can't find Pidgin buddy %s to update." % dbus_obj

    def _status_changed(self, buddy, old_status, new_status):
        if old_status != new_status:
            self._update_buddy(buddy)

    def _idle_changed(self, buddy, is_idle, idle_time):
        buddy = self._get_buddy_by_dbus_obj(buddy)
        if buddy:
            if is_idle:
                buddy.reset_idle_time()
            else:
                buddy.clear_idle_time()
            buddy.emit("reload")

    def _signed_on(self, buddy):
        self._update_buddy(buddy)

    def _signed_off(self, buddy):
        self._update_buddy(buddy)

    def _icon_changed(self, buddy):
        self._update_buddy(buddy)

    def _added(self, buddy):
        self.emit("reload")

    def _removed(self, buddy):
        self.emit("reload")

    def _status_changed(self, account, old_status, new_status):
        self.emit("status-changed")

    def do_reload(self):
        self.account_list = {}
        self.group_list = []
        self.buddy_list = []

	try:
            acct_doc = parse(self.accounts_path)
	except IOError, (errno, strerror):
            print " !!! Error parsing ~/.purple/accounts.xml: %s" % (strerror)
            return

        for node in acct_doc.getElementsByTagName("account"):
            if node.getElementsByTagName("protocol"):
                try:
                    acct = PidginAccount(node)
                    self.account_list[acct.get_screenname()] = acct
                except NotImplementedError:
                    pass

        acct_doc.unlink()

        try:
            blist_doc = parse(self.blist_path)
	except IOError, (errno, strerror):
            print " !!! Error parsing ~/.purple/blist.xml: %s" % (strerror)
            return

        for node in blist_doc.getElementsByTagName("group"):
            group = PidginGroup(node)
            self.group_list.append(group)

            for buddy in group.get_buddies():
                if self.account_list.has_key(buddy.account_name):
                    # Add buddy to it's account, and set the account of the buddy
                    self.account_list[buddy.get_account_name()].add_buddy(buddy)
                    buddy.set_account(self.account_list[buddy.get_account_name()])
                    self.buddy_list.append(buddy)
                else:
                    print " !!! Pidgin buddy '%s' has unknown account '%s'." % \
                          (buddy.get_name(), buddy.get_account_name())

        blist_doc.unlink()

        self.buddy_name_clashes = set()
        names = set()
        for name in [x.get_displayname() for x in self.buddy_list]:
            if name in names:
                self.buddy_name_clashes.add(name)
            else:
                names.add(name)

    def get_accounts(self):
        return self.account_list.values()

    def get_groups(self):
        return self.group_list

    def get_all_buddies(self):
        return self.buddy_list

    def get_buddy_has_name_clash(self, buddy):
        # FIXME: Hack so that PidginBuddy can show the screenname if there is a
        #        name clash.
        return buddy.get_displayname() in self.buddy_name_clashes

    def set_global_status(self, status):
        try:
            accounts = pidgin_dbus.PurpleAccountsGetAllActive()
            status_id = pidgin_dbus.PurplePrimitiveGetTypeFromId(status)
            saved = pidgin_dbus.PurpleSavedstatusNew("", status_id)
            pidgin_dbus.PurpleSavedstatusSetMessage(saved, "")
            pidgin_dbus.PurpleSavedstatusActivate(saved)
        except (dbus.DBusException, TypeError):
            pass

    def get_global_status(self):
        try:
            status = pidgin_dbus.PurpleSavedstatusGetCurrent()
            return str(pidgin_dbus.PurpleSavedstatusGetTitle(status))
        except (dbus.DBusException, TypeError):
            return _("Offline")


#
# Globals
#

pidgin_dbus = DBusWrapper("im.pidgin.purple.PurpleService",
                          path="/im/pidgin/purple/PurpleObject",
                          interface="im.pidgin.purple.PurpleInterface",
                          program_name="Pidgin")

pidgin_reader = PidginAccountReader()
