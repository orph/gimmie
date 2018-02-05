
import datetime
import os
from gettext import gettext as _

import gtk
import dbus

from gimmie_base import Item, ItemSource, Topic
from gimmie_util import icon_factory, ToolMenuButton, ImplementMe
from gimmie_gaim import gaim_reader, gaim_dbus
from gimmie_pidgin import pidgin_reader, pidgin_dbus


#
# Sidebar ItemSources
#

class EverybodySource(ItemSource):
    '''
    A list of "everyone", possibly filtered by last chat date, making this a
    recently used list.  This uses the Gaim account reader so only chats with
    buddies in the buddy list will be displayed.
    '''
    def __init__(self, name, icon = None, filter_by_date=False):
        ItemSource.__init__(self,
                            name=name,
                            icon=icon,
                            uri="source://People/Everybody",
                            filter_by_date=filter_by_date)

        # Listen for changes in the Gaim files
        pidgin_reader.connect("reload", lambda x: self.emit("reload"))
        gaim_reader.connect("reload", lambda x: self.emit("reload"))

    def get_items_uncached(self):
        # Buddies in Pidgin/Gaim are mutually exclusive
        buddy_list = pidgin_reader.get_all_buddies()
        if not buddy_list:
            buddy_list = gaim_reader.get_all_buddies()

        for buddy in buddy_list:
            yield buddy


class OnlineBuddySource(ItemSource):
    '''
    A list of all currently online buddies.
    '''
    def __init__(self, name, icon = None):
        ItemSource.__init__(self,
                            name=name,
                            icon=icon,
                            uri="source://People/Online",
                            filter_by_date=False)

        # Listen for changes in the Gaim files.  This isn't a good indicator of
        # presence changes, but it works sometimes.
        pidgin_reader.connect("reload", lambda x: self.emit("reload"))
        gaim_reader.connect("reload", lambda x: self.emit("reload"))

    def get_items_uncached(self):
        try:
            for buddy in pidgin_reader.get_all_buddies():
                if buddy.get_is_online():
                    yield buddy
        except (dbus.DBusException, TypeError):
            print " !!! Error accessing Pidgin D-BUS interface.  Is Pidgin running?"
        try:
            for buddy in gaim_reader.get_all_buddies():
                if buddy.get_is_online():
                    yield buddy
        except (dbus.DBusException, TypeError):
            print " !!! Error accessing Gaim2 D-BUS interface.  Is Gaim2 running?"


#
# Toolbar Items
#

class AccountMenu(gtk.Menu):
    def __init__(self):
        gtk.Menu.__init__(self)

        self.item_available = gtk.ImageMenuItem(_("Available"))
        self.item_available.set_image(icon_factory.load_image(gtk.STOCK_YES, gtk.ICON_SIZE_MENU))
        self.item_available.connect("activate", lambda w: self._set_status("available"))
        self.item_available.show()
        self.append(self.item_available)

        self.item_offline = gtk.ImageMenuItem(_("Offline"))
        self.item_offline.set_image(icon_factory.load_image(gtk.STOCK_CANCEL, gtk.ICON_SIZE_MENU))
        self.item_offline.connect("activate", lambda w: self._set_status("offline"))
        self.item_offline.show()
        self.append(self.item_offline)
        
        self.item_away = gtk.ImageMenuItem(_("Away"))
        self.item_away.set_image(icon_factory.load_image(gtk.STOCK_NO, gtk.ICON_SIZE_MENU))
        self.item_away.connect("activate", lambda w: self._set_status("away"))
        self.item_away.show()
        self.append(self.item_away)
        
        self.item_invisible = gtk.ImageMenuItem(_("Invisible"))
        self.item_invisible.set_image(icon_factory.load_image("status-invisible",
                                                              gtk.ICON_SIZE_MENU))
        self.item_invisible.connect("activate", lambda w: self._set_status("invisible"))
        self.item_invisible.show()
        self.append(self.item_invisible)

        ### These don't work yet...
        #away_menu = gtk.Menu()
        #away_item = gtk.MenuItem(_("Away Messages..."))
        #away_item.show()
        #away_menu.append(away_item)

        #item = gtk.MenuItem(_("Away"))
        #item.show()
        #item.set_submenu(away_menu)
        #self.append(item)

        #item = gtk.SeparatorMenuItem()
        #item.show()
        #self.append(item)

        #item = gtk.MenuItem(_("Accounts..."))
        #item.connect("activate", lambda w: self._show_accounts_editor())
        #item.show()
        #self.append(item)

        #item = gtk.SeparatorMenuItem()
        #item.show()
        #self.append(item)

        #for acct in pidgin_reader.get_accounts():
        #    item = gtk.CheckMenuItem(acct.get_name())
        #    if acct.get_auto_login():
        #        item.set_active(True)
        #    item.show()
        #    self.append(item)

        #for acct in gaim_reader.get_accounts():
        #    item = gtk.CheckMenuItem(acct.get_name())
        #    if acct.get_auto_login():
        #        item.set_active(True)
        #    item.show()
        #    self.append(item)

    def _show_accounts_editor(self):
        ImplementMe()

    def _set_status(self, status):
        pidgin_reader.set_global_status(status)


class AddPersonToolButton(gtk.ToolButton):
    __gsignals__ = {
        "clicked" : "override"
        }

    def __init__(self, tooltips):
        img = icon_factory.load_image("stock_person", gtk.ICON_SIZE_LARGE_TOOLBAR)
        gtk.ToolButton.__init__(self, img, _("New Person"))
        self.set_tooltip(tooltips, _("Add a new contact person"))

    def _pidgin_get_default_account_obj(self):
        acct = pidgin_dbus.PurpleAccountsFindConnected("", "")
        if not acct:
            acct = pidgin_dbus.PurpleAccountsFindAny("", "")
        return acct

    def _gaim_get_default_account_obj(self):
        acct = gaim_dbus.GaimAccountsFindConnected("", "")
        if not acct:
            acct = gaim_dbus.GaimAccountsFindAny("", "")
        return acct

    def do_clicked(self):
        try:
            acct = self._pidgin_get_default_account_obj()
            pidgin_dbus.PurpleBlistRequestAddBuddy(acct, "", "", "")
        except:
                try:
                    acct = self._gaim_get_default_account_obj()
                    gaim_dbus.GaimBlistRequestAddBuddy(acct, "", "", "")
                except dbus.DBusException:
                    print " !!! Pidgin or Gaim2 D-BUS interface not available.  Is either Pidgin or Gaim2 running?"


class AvailableToolMenuButton(ToolMenuButton):
    def __init__(self, tooltips):
        ToolMenuButton.__init__(self, gtk.Image(), _("Status"))

        self.set_tooltip(tooltips, _("Set your online status"))
        self.set_menu(AccountMenu())
    
        # Connect to dbus signals to notify us of buddy status changes
        # NOTE: When going to 'invisible' there won't be an accountStatusChanged
        #       signal (tested with an xmpp account might be different on
        #       others)
        try:
            pidgin_reader.connect("status-changed", lambda x: self._status_changed())
            self._status_changed()
        except dbus.DBusException:
            print " !!! Pidgin D-BUS interface not available.  Is Pidgin running?"

    def _status_changed(self):
        status_str = pidgin_reader.get_global_status()

        icon = None
        if status_str == _("Available"):
            icon = gtk.STOCK_YES
        elif status_str == _("Offline"):
            icon = gtk.STOCK_CANCEL
        elif status_str == _("Away"):
            icon = gtk.STOCK_NO
        elif status_str == _("Invisible"):
            # FIXME: Need icon for invisible
            icon = "status-invisible"
        else:
            print " !!! Unknown Pidgin status:", status_str

        if icon:
            self.get_icon_widget().set_from_pixbuf(
                icon_factory.load_icon(icon, gtk.ICON_SIZE_BUTTON))
        self.set_label(status_str.capitalize())


#
# Topic Implementation
#

class PeopleTopic(Topic):
    '''
    Lists recently talked to people, people online now, and all contacts, as
    well as listing out Gaim groups.  Placeholders for future
    Gmail/Friendster/LinkedIn contact integration.
    '''
    def __init__(self):
        Topic.__init__(self,
                       _("People"),
                       uri="topic://People",
                       icon="stock_people")

        from gimmie_running import RunningChats
        self.set_running_source_factory(lambda: RunningChats())

        # Reload the sidebar when Pidgin's files change
        pidgin_reader.connect("reload", lambda x: self.emit("reload"))

        # Reload the sidebar when Gaim's files change
        gaim_reader.connect("reload", lambda x: self.emit("reload"))

    def do_reload(self):
        source_list = [EverybodySource(_("Recent People"), "stock_calendar", filter_by_date=True),
                       OnlineBuddySource(_("Online Now"), "im"),
                       EverybodySource(_("Everybody"), "gnome-globe"),
                       None]

        source_list += [None]

        # Accounts in Pidgin/Gaim are mutually exclusive
        acct_list = pidgin_reader.get_accounts()
        if not acct_list:
            acct_list = gaim_reader.get_accounts()

        for acct in acct_list:
            source_list.append(acct)

        self.set_sidebar_source_list(source_list)

    def get_hint_color(self):
        return gtk.gdk.color_parse("pink")

    def get_toolbar_items(self, tooltips):
        tools = []

        btn = AddPersonToolButton(tooltips)
        btn.set_is_important(True)
        tools.append(btn)

        btn = AvailableToolMenuButton(tooltips)
        btn.set_is_important(True)
        tools.append(btn)

        return tools

