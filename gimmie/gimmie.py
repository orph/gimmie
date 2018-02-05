
import gc
import os
import signal
from gettext import bindtextdomain, textdomain

import gtk
import gnome

import gimmie_globals
from gimmie_bar import GimmieBarDock
from gimmie_applications import ApplicationsTopic
from gimmie_computer import ComputerTopic
from gimmie_library import DocumentsTopic
from gimmie_people import PeopleTopic
from gimmie_util import gconf_bridge


#
# Globals
#

gimmie_bar = None


def _load_gimmie_bar(topics):
    '''Create a new GimmieBar, and destroy the existing one if it exists.'''
    global gimmie_bar

    swapbar = gconf_bridge.get("swapbar")
    autohide = gconf_bridge.get("autohide")
    vertical = gconf_bridge.get("vertical")

    # Use a single bottom bar by default.
    gravity = (vertical and gtk.gdk.GRAVITY_WEST) or gtk.gdk.GRAVITY_SOUTH

    if gimmie_bar:
        gimmie_bar.destroy()
    gimmie_bar = GimmieBarDock(topics, gravity, autohide_anchors=autohide, swapbar=swapbar)


def _setup_session_manager():
    '''Enables session manager auto-restart on login, and after a crash.'''
    session_mgr = gnome.ui.master_client()
    argv = [__file__]
    try:
        session_mgr.set_restart_command(argv)
    except TypeError:
        # Fedora systems have a broken gnome-python wrapper for this function.
        session_mgr.set_restart_command(len(argv), argv)
    session_mgr.set_restart_style(gnome.ui.RESTART_IF_RUNNING | gnome.ui.RESTART_IMMEDIATELY)
    session_mgr.connect("die", lambda x: gtk.main_quit())


def _cancel_session_manager():
    '''Resets session manager to avoid immediate restart.'''
    session_mgr = gnome.ui.master_client()
    session_mgr.set_restart_style(gnome.ui.RESTART_IF_RUNNING) 
    session_mgr.flush()


def main(args):
    bindtextdomain('gimmie', gimmie_globals.localedir)
    textdomain('gimmie')

    ### Uncomment to spew leak debug info
    #gc.set_debug(gc.DEBUG_LEAK)

    # Tell gobject/gtk we are threaded
    gtk.gdk.threads_init()

    gnome.program_init("gimmie", gimmie_globals.version)

    _setup_session_manager()
    signal.signal(signal.SIGTERM, lambda x: _cancel_session_manager()) # Don't restart after kill

    try:
        topics = [ApplicationsTopic(), DocumentsTopic(), PeopleTopic(), ComputerTopic()]
        load_it = lambda: _load_gimmie_bar(topics)

        gconf_bridge.connect("changed::swapbar", lambda gb: load_it())
        gconf_bridge.connect("changed::autohide", lambda gb: load_it())
        gconf_bridge.connect("changed::vertical", lambda gb: load_it())
        load_it()

        gtk.main()
    except (KeyboardInterrupt, SystemExit):
        # Don't restart if user pressed Ctrl-C, or sys.exit called
        _cancel_session_manager()


if __name__ == "__main__":
    main(None)
