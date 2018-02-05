
import datetime
import sys
from gettext import bindtextdomain, textdomain, gettext as _

import gtk
import gnomeapplet
import gobject
import pango

### Running in panel applet mode.
import gimmie_globals
gimmie_globals.gimmie_is_panel_applet = lambda: True

from gimmie_base import Topic, ItemSource, Item
from gimmie_applications import ApplicationsTopic
from gimmie_computer import ComputerTopic
from gimmie_library import DocumentsTopic
from gimmie_people import PeopleTopic
from gimmie_prefs import Preferences
from gimmie_topicwin import TopicView, TimeBar
from gimmie_util import bookmarks, icon_factory, launcher, GConfBridge, KillFocusPadding, ToolMenuButton


def color_average(col1, col2, colormap):
    if not col1 or not col2:
        return col1 or col2
    new = gtk.gdk.Color()
    new.red = int((col1.red + col2.red) / 2)
    new.green = int((col1.green + col2.green) / 2)
    new.blue = int((col1.blue + col2.blue) / 2)
    return colormap.alloc_color(new)


def color_average_widget_state(col1, widget, state):
    state_col = widget.get_style().bg[state]
    return color_average(col1, state_col, widget.get_colormap())


class GrabOnShowWindow(gtk.Window):
    __gsignals__ = {
        'grab-broken-event': 'override',
        'map-event' : 'override',
        'unmap-event' : 'override',
        'button-press-event' : 'override',
        'key-press-event' : 'override',
        }

    def __init__(self):
        gtk.Window.__init__(self)
        self.grabbed = False

    def _grab_window_event(self, win, ev):
        if ev.type in (gtk.gdk.UNMAP, gtk.gdk.SELECTION_CLEAR):
            self.do_map_event(ev) 
        return False

    def do_grab_broken_event(self, ev):
        if ev.grab_window and self.grabbed:
            ev_widget = ev.grab_window.get_user_data()
            if isinstance(ev_widget, gtk.Widget):
                ev_widget.connect("event", self._grab_window_event)

            self.grabbed = False # No longer grabbed
        return True

    def do_map_event(self, ev):
        if not self.grabbed:
            self.grab_focus()
            self.grab_add()

            time = gtk.get_current_event_time()
            gtk.gdk.pointer_grab(self.window, True, gtk.gdk.BUTTON_PRESS_MASK, None, None, time)
            gtk.gdk.keyboard_grab(self.window, True, time)
        self.grabbed = True

    def do_unmap_event(self, ev):
        if self.grabbed:
            time = gtk.get_current_event_time()
            gtk.gdk.pointer_ungrab(time)
            gtk.gdk.keyboard_ungrab(time)
            self.grab_remove()
        self.grabbed = False

    def do_button_press_event(self, ev):
        win_tuple = gtk.gdk.window_at_pointer()
        ev_win = (win_tuple and win_tuple[0]) or None

        if not ev_win:
            # External application, hide and give up grab
            self.hide()
        elif ev_win.get_toplevel() != self.window:
            # Other toplevel window, hide and forward the event
            ev_widget = ev_win.get_user_data()
            if ev_widget.event(ev):
                self.hide()
            else:
                return False

        return True

    def do_key_press_event(self, ev):
        if not gtk.Window.do_key_press_event(self, ev) \
               and ev.keyval == gtk.gdk.keyval_from_name("Escape"):
            self.hide()
            return True


class AppletOrientationHelper:
    def __init__(self, widget, applet, track_widget):
        update_cb = lambda: self.update_position(widget, track_widget, applet)

        widget.connect("size-allocate", lambda w, a: update_cb())
        track_widget.connect("size-allocate", lambda w, a: update_cb())
        track_widget.connect("screen-changed",
                             lambda w, screen: widget.set_screen(screen))

    def update_position(self, widget, track_widget, applet):
        '''
        Calculates position and moves window to it.
        '''
        if not track_widget.flags() & gtk.REALIZED:
            return

        # Get our own dimensions & position
        track_x, track_y = track_widget.window.get_origin()
        track_x += track_widget.allocation.x
        track_y += track_widget.allocation.y

        if widget.flags() & gtk.REALIZED:
            width = widget.allocation.width
            height = widget.allocation.height
        else:
            width, height = widget.size_request()

        screen = track_widget.get_screen()
        monitor = screen.get_monitor_geometry(screen.get_monitor_at_window(track_widget.window))

        orient = applet.get_orient()

        if orient in (gnomeapplet.ORIENT_LEFT, gnomeapplet.ORIENT_RIGHT):
            if orient == gnomeapplet.ORIENT_LEFT:
                x = track_x + track_widget.allocation.width + 1
                y = track_y + 1
                north = gtk.gdk.GRAVITY_NORTH_WEST
                south = gtk.gdk.GRAVITY_SOUTH_WEST
            elif orient == gnomeapplet.ORIENT_RIGHT:
                x = track_x - width - 1
                y = track_y + 1
                north = gtk.gdk.GRAVITY_NORTH_EAST
                south = gtk.gdk.GRAVITY_SOUTH_EAST

            if y + height > monitor.y + monitor.height:
                y = monitor.y + monitor.height - height
            if y < 0:
                y = 0

            if y + height > monitor.height / 2:
                gravity = south
            else:
                gravity = north
        else:
            if orient == gnomeapplet.ORIENT_DOWN:
                x = track_x + 1
                y = track_y + track_widget.allocation.height - 1
                gravity = gtk.gdk.GRAVITY_NORTH_WEST
            elif orient == gnomeapplet.ORIENT_UP:
                x = track_x + 1
                y = track_y - height + 1
                gravity = gtk.gdk.GRAVITY_SOUTH_WEST

            if x + width > monitor.x + monitor.width:
                x = monitor.x + monitor.width - width
            if x < 0:
                x = 0

        if (gravity != widget.get_gravity()):
            widget.set_gravity(gravity)
        widget.move(x, y)


class TopicMenu(GrabOnShowWindow, TopicView):
    '''
    Panel applet menu version of topic window.
    '''
    def __init__(self, topic):
        GrabOnShowWindow.__init__(self)
        TopicView.__init__(self, topic)

        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_POPUP_MENU)
        self.set_decorated(False)

        self.add_accel_group(self.accel_group)

        ### Merge the topic's color with the style as a border
        new = color_average_widget_state(topic.get_hint_color(), self, gtk.STATE_NORMAL)
        self.modify_bg(gtk.STATE_NORMAL, new)

        frame = gtk.Frame()
        frame.show()
        frame.set_shadow_type(gtk.SHADOW_OUT)
        self.add(frame)

        ev_box = gtk.EventBox()
        ev_box.show()
        frame.add(ev_box)

        ### Merge the topic's color with the style as a border
        new = color_average_widget_state(topic.get_hint_color(), ev_box, gtk.STATE_ACTIVE)
        ev_box.modify_bg(gtk.STATE_NORMAL, new)

        ev_box2 = gtk.EventBox()
        ev_box2.show()
        ev_box2.set_border_width(4)
        ev_box.add(ev_box2)
        ev_box = ev_box2

        frame = gtk.Frame()
        frame.show()
        frame.set_shadow_type(gtk.SHADOW_OUT)
        ev_box.add(frame)

        # Contains the visual frame, giving it some space
        self._content = gtk.VBox(False, 0)
        self._content.set_border_width(0)
        self._content.show()
        frame.add(self._content)

        # Toolbar
        self._content.pack_start(self.toolbar, False, False, 0)

        # Hbox containing the sidebar buttons and the toolbar/iconview
        body = gtk.HBox(False, 12)
        body.set_border_width(12)
        body.show()
        self._content.pack_start(body, True, True, 0)

        # Load up the sidebar
        self._sidebar_align = gtk.Alignment(0.5, 0.0, 0.0, 0.0)
        self._sidebar_align.add(self.sidebar)
        self._sidebar_align.show()
        body.pack_start(self._sidebar_align, False, True, 0)

        # Horizontal time line bar with plus/minus buttons above icon view
        self.timebar = TimeBar()
        self.timebar.connect("zoom-changed", lambda w, num_days: self.zoom_changed(num_days))
        align = gtk.Alignment(1.0, 0.0, 0.0, 0.0)
        align.add(self.timebar)
        align.show()
        evbox = gtk.EventBox()
        evbox.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))
        evbox.show()
        timebox = gtk.HBox(False, 0)
        timebox.pack_start(evbox, True, True)
        timebox.pack_start(align, False, True)
        timebox.show()
        self.content_vbox.pack_start(timebox, False, False)

        # Frame containing timebar and iconview inside scrolled window
        body.pack_start(self.content_frame, True, True, 0)

        # Bound the height request of the scrolled window and icon view
        self.scroll.connect("size-request", self._scroll_get_best_size)
        self.scroll.get_vadjustment().connect("changed",
                                              lambda adj: self.scroll.queue_resize_no_redraw())

        self.view.set_size_request(500, -1)
        self.view.connect("item-activated", lambda v, p: self.hide()) # Iconify on item open

        # Setup the toolbar
        self._add_toolbar_items()

        # Select an initial sidebar button
        self.find_first_button()

    def set_gravity(self, gravity):
        # Override GtkWindow::set_gravity
        assert self.toolbar.parent == self._content

        self._content.remove(self.toolbar)
        if gravity in (gtk.gdk.GRAVITY_SOUTH,
                       gtk.gdk.GRAVITY_SOUTH_WEST,
                       gtk.gdk.GRAVITY_SOUTH_EAST):
            # Toolbar & sidebar at the bottom
            self._content.pack_end(self.toolbar, False, False, 0)
            self._sidebar_align.set_property("yalign", 1.0)
        else:
            # Toolbar & sidebar at the top
            self._content.pack_start(self.toolbar, False, False, 0)
            self._sidebar_align.set_property("yalign", 0.0)

        gtk.Window.set_gravity(self, gravity)

    def get_zoom_level(self):
        return self.timebar.get_zoom_level()

    def get_zoom_level_list(self):
        return self.timebar.get_zoom_level_list()

    def set_zoom_level(self, zoom):
        self.timebar.set_zoom_level(zoom)

    def show_hide_zoomer(self, show):
        if show:
            if self.active_source:
                self.timebar.set_items(self.active_source.get_items())
            self.timebar.show()
        else:
            self.timebar.hide()

    def _scroll_get_best_size(self, scroll, req):
        '''
        Sets the height request of the scrolled window to either the upper bound
        of the scrollbar or 70% of the screen height, whichever is smaller.
        '''
        vadj = scroll.get_property("vadjustment")
        upper = int(vadj.get_property("upper"))
        upper = min(upper, int(self.get_screen().get_height() * 0.7))

        if upper == 0 or upper == scroll.allocation.height:
            # Avoid unneeded or bogus resize
            return False

        req.height = upper
        return True

    def _load_items_done(self, ondone_cb):
        '''
        Do some magic to get a decent size request out of an iconview.  Reset
        the scrolled window upper bound to 0, and resize the window.
        '''
        if ondone_cb:
            ondone_cb()

        vadj = self.scroll.get_property("vadjustment")
        vadj.set_property("upper", 0)

        w, h = self.child.size_request()
        self.resize(w, h)

    def load_items(self, items, ondone_cb = None):
        '''
        Wrap the ondone callback to resize the scrolled window after reloading
        the iconview.
        '''
        self.view.load_items(items, lambda: self._load_items_done(ondone_cb))

    def _favorite_selection_changed(self, view, fav, block_id, img):
        # Block the toggled handler from triggering
        fav.handler_block(block_id)
        selected = view.get_selected_items()
        if len(selected) == 1:
            model = view.get_model()
            item = model.get_value(model.get_iter(selected[0]), 2)

            pix = icon_factory.load_icon("gnome-favorites", gtk.ICON_SIZE_LARGE_TOOLBAR)
            if not item.get_is_pinned():
               pix = icon_factory.greyscale(pix)
            img.set_from_pixbuf(pix)

            fav.set_active(item.get_is_pinned())
            fav.set_sensitive(item.get_can_pin())
        else:
            fav.set_active(False)
            fav.set_sensitive(False)
        fav.handler_unblock(block_id)

    def _favorite_toggled(self, fav):
        selected = self.view.get_selected_items()
        if len(selected) == 1:
            model = self.view.get_model()
            item = model.get_value(model.get_iter(selected[0]), 2)
            if fav.get_active():
                item.pin()
            else:
                item.unpin()

    def add_favorite_toolitem(self):
        img = icon_factory.load_image("gnome-favorites", gtk.ICON_SIZE_LARGE_TOOLBAR)
        
        i = gtk.ToggleToolButton()
        i.set_label(_("Favorite"))
        i.set_icon_widget(img)
        i.set_is_important(True)
        i.set_sensitive(False)
        i.set_tooltip(self.tooltips, _("Add to Favorites"))
        i.show_all()
        self.toolbar.insert(i, -1)
        
        block_id = i.connect("toggled", self._favorite_toggled)
        
        sel_changed_cb = lambda: self._favorite_selection_changed(self.view, i, block_id, img)
        self.view.connect("selection-changed", lambda view: sel_changed_cb())
        bookmarks.connect("reload", lambda b: sel_changed_cb())

        self.fav = i

    def _make_toolbar_expander(self, expand = True):
        sep = gtk.SeparatorToolItem()
        sep.set_draw(False)
        sep.set_expand(expand)
        sep.show()
        return sep

    def _add_toolbar_items(self):
        # Right-align the zoom and search tool items
        self.toolbar.insert(self._make_toolbar_expander(), -1)

        for i in self.topic.get_toolbar_items(self.tooltips):
            ### Uncomment to pack space between elements
            #self.toolbar.insert(self._make_toolbar_expander(), -1)
            if i:
                i.show_all()
                if isinstance(i, ToolMenuButton):
                    for menu_item in i.get_menu() or []:
                        menu_item.connect("activate", lambda menu_item: self.hide())
                elif isinstance(i, gtk.ToolButton):
                    i.connect("clicked", lambda btn: self.hide())
                self.toolbar.insert(i, -1)

        self.add_favorite_toolitem()

        # Try to disassociate the Favorite button from the search box
        self.toolbar.insert(self._make_toolbar_expander(False), -1)

        self.add_search_toolitem()

        # Right-align the zoom and search tool items
        self.toolbar.insert(self._make_toolbar_expander(), -1)


def get_topic_window_mod(self):
    if not self.topic_window:
        self.topic_window = TopicMenu(self)
    return self.topic_window

### Override Topic to use the applet menu version.
Topic.get_topic_window = get_topic_window_mod


class TopicButtonMod(gtk.ToggleButton):
    __gsignals__ = {
        'button-press-event' : 'override',
        'activate' : 'override',
        'realize' : 'override',
        }

    def __init__(self, topic, applet, prefs):
        gtk.Button.__init__(self)
        self.set_property("can-default", False)
        self.set_property("can-focus", False)
        self.set_border_width(0)

        KillFocusPadding(self, "topic-button")

        self.topic = topic
        self.applet = applet
        self.prefs = prefs

        # TopicMenu is created on demand
        self.topic_win = None

        prefs.connect("changed::button_style", self._button_style_pref_changed)
        self._button_style_pref_changed(prefs)

        prefs.connect("changed::use_colors", self._use_colors_pref_changed)
        self._use_colors_pref_changed(prefs)

    def _use_colors_pref_changed(self, prefs):
        if self.prefs.get("use_colors", default=True) == True:
            self.set_relief(gtk.RELIEF_NORMAL)
        else:
            self.set_relief(gtk.RELIEF_NONE)

    def _button_style_pref_changed(self, prefs):
        style = self.prefs.get("button_style", default="both")

        # FIXME: Don't hardcode 18!
        icon = self.topic.get_icon(18)
        icon = icon_factory.load_image (icon, 18)

        orient = self.applet.get_orient()
        if orient in (gnomeapplet.ORIENT_UP, gnomeapplet.ORIENT_DOWN):
            if style == "text":
                self.set_image(gtk.Image())
                self.set_label(self.topic.get_name())
            elif style == "icon":
                self.set_image(icon)
                self.set_label("")
            elif style == "both":
                self.set_image(icon)
                self.set_label(self.topic.get_name())
        else:
            if style == "text":
                icon = gtk.Image() # No image
                label = gtk.Label(self.topic.get_name())
            elif style == "icon":
                label = gtk.Label("")
            elif style == "both":
                label = gtk.Label(self.topic.get_name())

            if self.applet.get_orient() == gnomeapplet.ORIENT_LEFT:
                label.set_property("angle", 270)
            else:
                label.set_property("angle", 90)
            label.show()

            vbox = gtk.VBox(False, 2)
            if orient == gnomeapplet.ORIENT_LEFT:
                vbox.pack_start(icon, False, False, 0)
                vbox.pack_start(label, False, False, 0)
            else: 
                vbox.pack_start(label, False, False, 0)
                vbox.pack_start(icon, False, False, 0)
            vbox.show()

            if self.child:
                self.remove(self.child)
            align = gtk.Alignment(0.5, 0.5, 0.0, 0.0)
            align.add(vbox)
            align.show()
            self.add(align)

    def do_realize(self):
        self.chain()

        color = self.topic.get_hint_color()

        new = color_average_widget_state(color, self, gtk.STATE_NORMAL)
        self.modify_bg(gtk.STATE_NORMAL, new)

        new = color_average_widget_state(color, self, gtk.STATE_ACTIVE)
        self.modify_bg(gtk.STATE_ACTIVE, new)

        new = color_average_widget_state(color, self, gtk.STATE_PRELIGHT)
        self.modify_bg(gtk.STATE_PRELIGHT, new)

    def do_button_press_event(self, ev):
        if ev.button == 3:
            # FIXME: Add items to panel right-click menu
            return False
        
            menu = gtk.Menu()

            for mi in self.topic.get_context_menu_items():
                if not mi:
                    mi = gtk.SeparatorMenuItem()
                    mi.show()
                menu.append(mi)

            menu.connect('selection-done', lambda x: menu.destroy())

            menu.attach_to_widget(self, None)
            menu.popup(None, None, None, ev.button, ev.time)

            return True
        else:
            if not self.get_active():
                self._show()
            return True

    def _show(self):
        if not self.topic_win:
            self.topic_win = self.topic.get_topic_window()
            self.topic_win.connect("map-event", self._map)
            self.topic_win.connect("unmap-event", self._unmap)
            #self.topic_win.realize()
            #self.do_set_wm_icon_geometry()

            AppletOrientationHelper(self.topic_win, self.applet, self)

        self.topic_win.search_tool_item.entry.grab_focus()
        self.topic_win.present()

    def _map(self, win, ev):
        self.set_active(True)

    def _unmap(self, win, ev):
        self.set_active(False)


class GimmieApplet:
    __INSTANCE = None

    def __init__(self, applet, iid):
        if GimmieApplet.__INSTANCE == None:
            GimmieApplet.__INSTANCE = self

        KillFocusPadding(applet, "applet")

        self.applet = applet
        self.applet.add_preferences("/schemas/apps/gimmie/prefs")
        self.prefs = GConfBridge(self.applet.get_preferences_key())

        if applet.get_orient() in (gnomeapplet.ORIENT_UP, gnomeapplet.ORIENT_DOWN):
            self.content = gtk.HBox(True, 0)
        else:
            self.content = gtk.VBox(True, 0)
        self.content.show()

        if applet.child:
            applet.remove(applet.child)
        applet.add(self.content)
        applet.show()
        applet.set_background_widget(applet)
        
        applet.setup_menu_from_file(None,
                                    "GNOME_GimmieApplet.xml",
                                    None,
                                    (("About", self._show_about),
                                     ("EditMenus", self._run_menu_editor),
                                     ("Prefs", self._show_preferences)))

        topic_and_pref = ((ComputerTopic(),     "show_computer"),
                          (ApplicationsTopic(), "show_programs"),
                          (DocumentsTopic(),    "show_library"),
                          (PeopleTopic(),       "show_people"))
        
        for topic, pref_key in topic_and_pref:
            btn = TopicButtonMod(topic, applet, self.prefs)
            btn.show()
            self.content.pack_start(btn, True, True, 0)

            self.prefs.connect("changed::" + pref_key,
                               self._show_topic_pref_changed, btn,
                               pref_key)
            self._show_topic_pref_changed(self.prefs, btn, pref_key)

        self.prefs.connect("changed::use_colors", self._use_colors_pref_changed)
        self._use_colors_pref_changed(self.prefs)

    def _show_about(self, component, verb):
        # TODO: Complete this
        about = gtk.AboutDialog()
        about.set_name("Gimmie")
        about.set_authors(("Alex Graveley <alex@beatniksoftware.com>",
                           "David Trowbridge <trowbrds@gmail.com>",
                           "Tony Tsui <tsui.tony@gmail.com"))
        about.run()
        about.destroy()
        return

    def _show_preferences(self, component, verb):
        Preferences(self.prefs).show()

    def _run_menu_editor(self, component, verb):
        launcher.launch_command("alacarte")

    def _show_topic_pref_changed(self, prefs, btn, pref_key):
        if self.prefs.get(pref_key, default=True) == True:
            btn.show()
        else:
            btn.hide()

    def _use_colors_pref_changed(self, prefs):
        # When showing colors, buttons looks weird if they are are different sizes.
        # So make the packing box homogenous if use_colors is True.
        if self.applet.get_orient() in (gnomeapplet.ORIENT_UP, gnomeapplet.ORIENT_DOWN):
            self.content.set_homogeneous(self.prefs.get("use_colors", default=True))


def gimmie_run_standalone():
    main_window = gtk.Window(gtk.WINDOW_TOPLEVEL)
    main_window.set_title("Gimmie")
    main_window.connect("destroy", gtk.main_quit)

    app = gnomeapplet.Applet()

    # NOTE: Change this to test different panel orientations
    app.get_orient = lambda: gnomeapplet.ORIENT_DOWN
    
    gimmie_applet_factory(app, None)
    app.reparent(main_window)

    main_window.show()
    gtk.main()


def gimmie_applet_factory(applet, iid):
    print "Running gimmie instance:", applet, iid

    applet.connect("change-orient", lambda applet, orient: gimmie_applet_factory(applet, iid))
    applet.connect("change-size", lambda applet, size: gimmie_applet_factory(applet, iid))
    GimmieApplet(applet, iid)
    
    return True


def main(args):
    bindtextdomain('gimmie', gimmie_globals.localedir)
    textdomain('gimmie')

    # Tell gobject/gtk we are threaded
    gtk.gdk.threads_init()

    if "--window" in args:
        gimmie_run_standalone()
        sys.exit()
    elif "--prefs" in args:
        Preferences(GConfBridge()).run()
        sys.exit()

    gnomeapplet.bonobo_factory("OAFIID:GNOME_Gimmie_Factory", 
                               gnomeapplet.Applet.__gtype__, 
                               "gimmie", "0", gimmie_applet_factory)


if __name__ == "__main__":
    main(["--window"])
