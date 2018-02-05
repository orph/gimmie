
from gettext import ngettext, gettext as _

import dbus
import gobject
import gtk
import gnome.ui

import gdmclient
from gimmie_util import DBusWrapper, icon_factory


class LogoutDialog(gtk.MessageDialog):
    # Dialog types, passed in constructor
    (SHUTDOWN, LOGOUT) = range(2)

    # Dialog responses
    (RESPONSE_LOGOUT,
     RESPONSE_SWITCH_USER,
     RESPONSE_SHUTDOWN,
     RESPONSE_REBOOT,
     RESPONSE_SUSPEND_TO_DISK,
     RESPONSE_SUSPEND_TO_RAM) = range(6)

    # Time to wait before automatically responding to dialog.
    AUTOMATIC_ACTION_TIMEOUT = 60

    # Guard against multiple gnome session saves
    logout_reentrance = 0

    def __init__(self, type, screen=None, time=None):
        gtk.MessageDialog.__init__(self, type=gtk.MESSAGE_WARNING)

        if not time:
            time = gobject.get_current_time()

        self.dialog_type = type

        self.set_skip_pager_hint(True)
        self.set_skip_taskbar_hint(True)
        self.set_keep_above(True)
        self.stick()

        self.timeout_id = 0

        self.set_title("")

        self.connect("destroy", self._destroy)
        self.connect("response", self._response)

        if type is self.SHUTDOWN:
            icon_name = "gnome-shutdown"
            primary_text = _("Shut down this computer now?")

            try:
                if gpm_dbus.AllowedSuspend():
                    btn = self.add_button(_("_Sleep"), self.RESPONSE_SUSPEND_TO_RAM)
                    btn.set_image(icon_factory.load_image("gnome-session-suspend.png",
                                                          gtk.ICON_SIZE_BUTTON))

                if gpm_dbus.AllowedHibernate():
                    btn = self.add_button(_("_Hibernate"), self.RESPONSE_SUSPEND_TO_DISK)
                    btn.set_image(icon_factory.load_image("gnome-session-hibernate.png",
                                                          gtk.ICON_SIZE_BUTTON))
            except dbus.DBusException:
                pass

            btn = self.add_button(_("_Reboot"), self.RESPONSE_REBOOT)
            btn.set_image(icon_factory.load_image("gnome-session-reboot.png",
                                                  gtk.ICON_SIZE_BUTTON))

            self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)

            btn = self.add_button(_("Shut _Down"), self.RESPONSE_SHUTDOWN)
            btn.set_image(icon_factory.load_image("gnome-session-halt.png",
                                                  gtk.ICON_SIZE_BUTTON))

            self.timed_out_response = self.RESPONSE_SHUTDOWN
        elif type is self.LOGOUT:
            icon_name = "gnome-logout"
            primary_text = _("Log out of this computer now?")
            
            self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)

            btn = self.add_button(_("_Log Out"), self.RESPONSE_LOGOUT)
            btn.set_image(icon_factory.load_image("gnome-session-logout.png",
                                                  gtk.ICON_SIZE_BUTTON))

            self.timed_out_response = self.RESPONSE_LOGOUT
        else:
            assert False, "Not reached"

        # GTK before 2.10 crashes when setting a custom icon in message dialogs
	if gtk.gtk_version[2] >= 10:
            self.image.set_from_icon_name(icon_name, gtk.ICON_SIZE_DIALOG)

        self.set_markup("<span size=\"larger\" weight=\"bold\">%s</span>" % primary_text)
        self.set_default_response(gtk.RESPONSE_CANCEL)
        if screen:
            self.set_screen(screen)

        self.set_timeout()

    def _destroy(self, widget):
        if self.timeout_id != 0:
            gobject.source_remove(self.timeout_id)
            self.time_left = 0
        self.destroy()

    def _response(self, widget, response):
        if response == gtk.RESPONSE_CANCEL or \
               response == gtk.RESPONSE_NONE or \
               response == gtk.RESPONSE_DELETE_EVENT:
            self._destroy(widget)
        elif response == self.RESPONSE_LOGOUT:
            gdmclient.set_logout_action(gdmclient.LOGOUT_ACTION_NONE)
            self.request_logout()
        elif response == self.RESPONSE_SWITCH_USER:
            gdmclient.new_login()
        elif response == self.RESPONSE_SHUTDOWN:
            gdmclient.set_logout_action(gdmclient.LOGOUT_ACTION_SHUTDOWN)
            self.request_logout()
        elif response == self.RESPONSE_REBOOT:
            gdmclient.set_logout_action(gdmclient.LOGOUT_ACTION_REBOOT)
            self.request_logout()
        elif response == self.RESPONSE_SUSPEND_TO_DISK:
            self._destroy(widget)
            try:
                gpm_dbus.Hibernate()
            except dbus.DBusException:
                # NOTE: Gdm doesn't differentiate a hibernate from a suspend
                gdmclient.set_logout_action(gdmclient.LOGOUT_ACTION_SUSPEND)
                self.request_logout()
        elif response == self.RESPONSE_SUSPEND_TO_RAM:
            self._destroy(widget)
            try:
                gpm_dbus.Suspend()
            except dbus.DBusException:
                gdmclient.set_logout_action(gdmclient.LOGOUT_ACTION_SUSPEND)
                self.request_logout()
        else:
            assert False, "Not reached"

    def request_logout(self):
        if self.logout_reentrance == 0:
            self.logout_reentrance += 1

            client = gnome.ui.master_client()
            if client:
                client.request_save(gnome.ui.SAVE_GLOBAL,
                                    True, # Shutdown?
                                    gnome.ui.INTERACT_ANY,
                                    True, # Fast?
                                    True) # Global?

            self.logout_reentrance -= 1

    def set_timeout(self):
        self.time_left = self.AUTOMATIC_ACTION_TIMEOUT

        # Sets secondary timeout
        self.logout_timeout()

        if self.timeout_id != 0:
            gobject.source_remove(self.timeout_id)
        self.timeout_id = gobject.timeout_add(1000, self.logout_timeout)

    def logout_timeout(self):
        if self.time_left == 0:
            self.response(self.timed_out_response)
            return False

        if self.dialog_type is self.SHUTDOWN:
            secondary_text = \
                ngettext("This computer will be automatically shut down in %d second.",
                         "This computer will be automatically shut down in %d seconds.",
                         self.time_left)
        elif self.dialog_type is self.LOGOUT:
            secondary_text = ngettext("You will be automatically logged out in %d second.",
                                      "You will be automatically logged out in %d seconds.",
                                      self.time_left)

        if ((self.time_left%10 == 0) or (self.time_left <= 30)):
            self.format_secondary_text(secondary_text % self.time_left)
        self.time_left -= 1

        return True


#
# Globals
#

gpm_dbus = DBusWrapper("org.gnome.PowerManager", program_name="gnome-power-manager")
