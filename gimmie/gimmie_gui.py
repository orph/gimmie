
import datetime
import os
from gettext import gettext as _

import gobject
import gtk
import wnck

import sexy

from gimmie_util import icon_factory, FocusRaiser, KillFocusPadding


#
# GimmieBar GUI Helpers
#

class RunningItemTile(gtk.EventBox):
    __gsignals__ = {
        'size-allocate' : 'override'
        }

    def __init__(self, item, target_height, gravity):
        gtk.EventBox.__init__(self)
        self.set_visible_window(False)
        self.item = item
        self.target_height = target_height

        # List of regular, highlight, and drag icons to use
        self.icons = (None, None, None)

        self.connect("button-press-event", self._button_press)
        self.connect_after("button-release-event", self._button_release)
        self.connect("enter-notify-event", lambda x, ev: self.img.set_from_pixbuf(self.icons[1]))
        self.connect("leave-notify-event", lambda x, ev: self.img.set_from_pixbuf(self.icons[0]))
        self.connect("drag-data-get", self._drag_data_get)
        self.connect("drag-data-received", self._drag_data_received)

        self.drag_source_set(gtk.gdk.BUTTON1_MASK,
                             [("text/uri-list", 0, 100)],
                             gtk.gdk.ACTION_LINK | gtk.gdk.ACTION_COPY)
            
        self.drag_dest_set(gtk.DEST_DEFAULT_DROP |
                           gtk.DEST_DEFAULT_HIGHLIGHT |
                           gtk.DEST_DEFAULT_MOTION,
                           [("text/uri-list", 0, 100)],
                           gtk.gdk.ACTION_COPY)

        ### FIXME: Need to make icon scale to the size allocation
        #img.set_size_request(48, 48)
        #img.connect("size-allocate", self._size_alloc, scaled)

        self.img = gtk.Image()

        # Add some edge-side padding
        if gravity == gtk.gdk.GRAVITY_NORTH:
            self.img.set_property("ypad", 2)
            self.img.set_property("yalign", 1.0)
        elif gravity == gtk.gdk.GRAVITY_SOUTH:
            self.img.set_property("ypad", 2)
            self.img.set_property("yalign", 0.0)
        elif gravity == gtk.gdk.GRAVITY_WEST:
            self.img.set_property("xpad", 2)
            self.img.set_property("xalign", 0.5)
        elif gravity == gtk.gdk.GRAVITY_EAST:
            self.img.set_property("xpad", 2)
            self.img.set_property("xalign", 0.5)

        self.img.show()
        self.add(self.img)

        reload_connect_id = item.connect_after("reload", self._reload)
        self.connect("destroy", lambda w: self.item.disconnect(reload_connect_id))
        self._reload(item)

        self.show()

    def _load_icons(self, item, target_height):
        '''Return a list of [regular, highlight, drag] icons for this item'''

        icon = item.get_icon(target_height)
        assert icon, "Running Item must have an icon"

        if target_height <= icon.get_height() <= target_height + 2:
            # Don't be so uptight.  Allow for a 1 pixel border.
            scaled = icon
        else:
            # Scale icon to target height, maintaining aspect ratio
            print " *** Scaling image of height %d to %d: %s" % (icon.get_height(),
                                                                 target_height,
                                                                 item.get_uri())
            scaled = icon.scale_simple(target_height * icon.get_width() / icon.get_height(),
                                       target_height,
                                       gtk.gdk.INTERP_BILINEAR)

        if item.get_demands_attention():
            # FIXME: Animate this to fade in and out
            # Put an alert icon at the bottom left.
            warning = self.render_icon(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_BUTTON)
            x = 0
            y = scaled.get_height() - warning.get_height()
            warning.composite(scaled,
                              x, y, warning.get_width(), warning.get_height(),
                              x, y,
                              1.0, 1.0,
                              gtk.gdk.INTERP_NEAREST,
                              255)

        # FIXME: Will a transparent icon work for people with crappy X drivers?
        if not item.get_is_opened():
            # Use a 70% transparent greyscale icon as the regular icon.
            # Use a greyscale icon as the highlight icon.
            # Use a 40% transparent icon as the drag icon.
            grey = icon_factory.greyscale(scaled)
            return (icon_factory.transparentize(grey, 70),
                    grey,
                    icon_factory.transparentize(scaled, 40))
        else:
            # Use a 40% transparent icon as the drag icon.
            # FIXME: use a highlighted icon for mouseover
            return (scaled,
                    icon_factory.colorshift(scaled, 30),
                    icon_factory.transparentize(scaled, 40))

    def _reload(self, item):
        del self.icons
        self.icons = self._load_icons(item, self.target_height)
        self.img.set_from_pixbuf(self.icons[0])
        self.drag_source_set_icon_pixbuf(self.icons[2])

    def _button_press(self, w, ev):
        if ev.button == 1:
            self.press_x = ev.x
            self.press_y = ev.y
        elif ev.button == 3:
            menu = gtk.Menu()
            menu.attach_to_widget(w, None)
            ### FIXME: Should highlight item, and restore in deactivate
            #menu.connect("deactivate", self._deactivate_item_popup, view, old_selected)

            self.item.populate_popup(menu)
            menu.popup(None, None, None, ev.button, ev.time)
            return True

    def _button_release(self, w, ev):
        if ev.button == 1:
            if not hasattr(self, "press_x") or \
               not self.drag_check_threshold(int(self.press_x),
                                             int(self.press_y),
                                             int(ev.x),
                                             int(ev.y)):
                self.item.open()
                return True

    def _drag_data_get(self, w, drag_context, selection_data, info, timestamp):
        # FIXME: Prefer ACTION_LINK if available
        if info == 100: # text/uri-list
            selection_data.set_uris([self.item.get_uri()])

    def _drag_data_received(self, widget, context, x, y, selection, target_type, time):
        self.item.handle_drag_data_received(selection, target_type)

    def get_tooltip(self):
        ### Uncomment for plain text
        #return self.item.get_tooltip()
        
        img = gtk.Image()
        img.set_from_pixbuf(self.item.get_icon(48))
        
        label = gtk.Label()
        label.set_markup("<span size='large'>%s</span>\n%s" % (self.item.get_name_markup(),
                                                               self.item.get_comment_markup()))

        box = gtk.HBox(False, 4)
        box.pack_start(img, False, False, 0)
        box.pack_start(label, False, False, 0)
        return box

    def do_size_allocate(self, alloc):
        if self.window:
            win_x, win_y = self.window.get_origin()
            self.item.set_screen_position(win_x + self.allocation.x,
                                          win_y + self.allocation.y,
                                          self.allocation.width,
                                          self.allocation.height)
            return self.chain(alloc)

    # Not used currently
    def _size_alloc(self, w, alloc, pixbuf):
        print " *** RunningItemTile size_alloc: width=%s, height=%s" % (alloc.width,
                                                                        alloc.height)
        scaled = pixbuf.scale_simple(alloc.width * pixbuf.get_width() / pixbuf.get_height(),
                                     alloc.width,
                                     gtk.gdk.INTERP_BILINEAR)
        w.set_from_pixbuf(scaled)
        return True

    def get_item(self):
        return self.item


class TooltipRaiser(FocusRaiser):
    def __init__(self, widget, content, gravity):
        self.widget = widget
        self.content = content
        self.gravity = gravity

        # FIXME: Bindings for initally-empty label do not work
        self.tooltip = sexy.sexy_tooltip_new_with_label("")

        # Tooltip still reappears after a second
        #widget.connect("button-press-event", lambda w, ev: self.do_lower(self.tooltip))
        #widget.connect("button-release-event", lambda w, ev: self.do_lower(self.tooltip))
        widget.connect("destroy", lambda w: self.tooltip.destroy())

        FocusRaiser.__init__(self,
                             widget,
                             self.tooltip,
                             gravity,
                             hide_on_lower=True,
                             lower_timeout=0)

    def do_raise(self, tooltip):
        if not self.widget.window:
            return
        
        # Clear old content
        if self.tooltip.child:
            self.tooltip.remove(self.tooltip.child)

        # Content can be a string, a widget, or a lambda returning either
        content = self.content
        if callable(content):
            content = content()
        if not isinstance(content, gtk.Widget):
            content = gtk.Label(content)
            content.set_use_markup(True)
        content.show_all()
        self.tooltip.add(content)

        x, y = self.widget.window.get_origin()
        rect = self.widget.allocation
        rect.x += x
        rect.y += y

        # Space to avoid topic buttons
        if self.gravity == gtk.gdk.GRAVITY_EAST:
            rect.x -= 20
        elif self.gravity == gtk.gdk.GRAVITY_WEST:
            rect.x += 20
        elif self.gravity == gtk.gdk.GRAVITY_SOUTH:
            rect.y -= 20
        elif self.gravity == gtk.gdk.GRAVITY_NORTH:
            rect.y += 20

	self.tooltip.position_to_rect(rect, self.widget.get_screen())

        # Show the tooltip
        FocusRaiser.do_raise(self, tooltip)


class TopicRunningList(gtk.EventBox):    
    def __init__(self, source, gravity):
        gtk.EventBox.__init__(self)
        self.set_visible_window(False)
        self.gravity = gravity

        if gravity in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
            self.content = gtk.VBox(False, 4)
        else:
            self.content = gtk.HBox(False, 4)
        self.content.show()
        self.add(self.content)

        source.connect_after("reload", self._reload)
        self._reload(source)

        ### FIXME: should grow to multiple rows when too many documents to keep
        ### scaling down.

    def get_best_icon_size_for_screen(self):
        if self.get_screen().get_monitor_geometry(0).height > 768:
            return 48
        return 32

    def add_widget(self, i, target_height):
        if self.gravity in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
            i.set_size_request(target_height, -1)
        else:
            i.set_size_request(-1, target_height)
        self.content.pack_start(i, True, True, 0)

        if hasattr(i, "get_tooltip"):
            TooltipRaiser(i, i.get_tooltip, self.gravity)

    def add_item(self, i, target_height):
        running = RunningItemTile(i, target_height, self.gravity)
        running.show()
        self.content.pack_start(running, True, True, 0)

        TooltipRaiser(running, running.get_tooltip, self.gravity)

    def _reload(self, source):
        '''
        Reload the ItemSource\'s items from get_items() which can be a mix of
        Widgets or Items.  RunningItemTiles are created to represent Items as
        needed.  We only add/remove children added/missing since the last reload
        in order to minimize RunningItemTile creation, and to avoid reparenting
        widgets (which can adversely effect e.g. TrayIconManager).
        '''
        print " *** Reloading TopicRunningList:", source.get_name()

        target_height = self.get_best_icon_size_for_screen()
        new_items = list(source.get_items())
        
        for i in self.content:
            if i in new_items:
                new_items.remove(i)
            elif isinstance(i, RunningItemTile) and i.get_item() in new_items:
                new_items.remove(i.get_item())
            else:
                self.content.remove(i)
                i.destroy()

        for i in new_items:
            if isinstance(i, gtk.Widget):
                self.add_widget(i, target_height)
            else:
                self.add_item(i, target_height)

        if len(self.content.get_children()) == 0:
            self.hide()
        else:
            self.show()


class TopicButton(gtk.Button):
    __gsignals__ = {
        'size-allocate' : 'override',
        'button-press-event' : 'override'
        }

    def __init__(self, topic, edge_gravity):
        gtk.Button.__init__(self)
        self.modify_bg(gtk.STATE_NORMAL, topic.get_hint_color())
        self.set_property("can-default", False)
        self.set_property("can-focus", False)
        self.set_border_width(0)
        
        KillFocusPadding(self, "topic-button")
        
        label = topic.get_button_content(edge_gravity)
        label.show()
        self.add(label)

        ### FIXME: Figure out why button adds 2px of padding
        #self.set_size_request(-1, 24)
        
        self.topic = topic
        self.topic_win = None

    def do_set_wm_icon_geometry(self):
        '''
        Set the _NET_WM_ICON_GEOMETRY window manager hint, so that the topic
        window will minimize onto this button\'s allocatied area.  See
        http://standards.freedesktop.org/wm-spec/latest for details.
        '''
        if self.window and self.topic_win and self.topic_win.window:
            win_x, win_y = self.window.get_origin()

            # values are left, right, width, height
            propvals = [win_x + self.allocation.x,
                        win_y + self.allocation.y,
                        self.allocation.width,
                        self.allocation.height]

            # tell window manager where to animate minimizing this app
            self.topic_win.window.property_change("_NET_WM_ICON_GEOMETRY",
                                                  "CARDINAL",
                                                  32,
                                                  gtk.gdk.PROP_MODE_REPLACE,
                                                  propvals)

    def do_clicked(self):
        if not self.topic_win:
            self.topic_win = self.topic.get_topic_window()
            self.topic_win.realize()
            self.do_set_wm_icon_geometry()
        self.topic_win.deiconify()
        self.topic_win.present()

    def do_size_allocate(self, alloc):
        ret = self.chain(alloc)
        self.do_set_wm_icon_geometry()
        return ret

    def do_button_press_event(self, ev):
        if ev.button == 3:
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
            return self.chain(ev)


class DockWindow(gtk.Window):
    __gsignals__ = {
        'realize' : 'override',
        'size-allocate' : 'override',
        }

    def __init__(self, edge_gravity):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.set_wmclass("gnome-panel", "Gnome-panel")
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DOCK)
        self.set_skip_pager_hint(True)
        self.set_skip_taskbar_hint(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.stick()

        ### Uncomment to have icons grow upwards.
        ### FIXME: This trips metacity bugs and makes the window actually move position
        #self.set_gravity(gtk.gdk.GRAVITY_SOUTH_EAST)

        self.edge_gravity = edge_gravity
        self.set_strut = False
        
        if edge_gravity in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
            self.content = gtk.VBox (False, 0)
        else:
            self.content = gtk.HBox (False, 0)
        self.content.show()

        self.content_align = gtk.Alignment(xscale=1.0, yscale=1.0)
        self.content_align.add(self.content)
        self.content_align.show()
        self.add(self.content_align)

    def get_content(self):
        return self.content

    def get_content_alignment(self):
        return self.content_align

    def get_edge_gravity(self):
        return self.edge_gravity

    def get_win_placement(self):
        '''This will place the window on the edge corresponding to the edge gravity'''
        
        width, height = self.size_request()
        geom = self.get_screen().get_monitor_geometry(0)
        eg = self.edge_gravity
            
        if eg in (gtk.gdk.GRAVITY_SOUTH, gtk.gdk.GRAVITY_NORTH):
            x = (geom.width / 2) - (width / 2)
        elif eg == gtk.gdk.GRAVITY_EAST:
            x = geom.width - width
        elif eg == gtk.gdk.GRAVITY_WEST:
            x = 0

        if eg in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
            y = (geom.height / 2) - (height / 2)
        elif eg == gtk.gdk.GRAVITY_SOUTH:
            y = geom.height - height
        elif eg == gtk.gdk.GRAVITY_NORTH:
            y = 0

        return [geom.x + x, geom.y + y] # Compensate for multiple monitors

    def move_to_position(self):
        if self.window:
            ### FIXME: Apparantly other people who are not me don't need this
            self.window.set_override_redirect(True)
            apply(self.move, self.get_win_placement())
            self.window.set_override_redirect(False)

    def do_realize(self):
        # FIXME: chain fails for some reason
        #ret = self.chain()
        ret = gtk.Window.do_realize(self)
        self.move_to_position()
        return ret

    def set_wm_strut(self, val):
        self.set_strut = val
        self.queue_resize_no_redraw()

    def do_set_wm_strut(self):
        '''
        Set the _NET_WM_STRUT window manager hint, so that maximized windows
        and/or desktop icons will not overlap this window\'s allocatied area.
        See http://standards.freedesktop.org/wm-spec/latest for details.
        '''
        if self.window:
            if self.set_strut:
                # values are left, right, top, bottom
                propvals = [0, 0, 0, 0]

                geom = self.get_screen().get_monitor_geometry(0)
                eg = self.get_edge_gravity()
                x, y = self.window.get_origin()
                alloc = self.allocation

                if eg == gtk.gdk.GRAVITY_WEST:
                    propvals[0] = alloc.width + x
                elif eg == gtk.gdk.GRAVITY_EAST and x != 0:
                    propvals[1] = geom.width - x
                elif eg == gtk.gdk.GRAVITY_NORTH:
                    propvals[2] = alloc.height + y
                elif eg == gtk.gdk.GRAVITY_SOUTH and y != 0:
                    propvals[3] = geom.height - y

                # tell window manager to not overlap buttons with maximized window
                self.window.property_change("_NET_WM_STRUT",
                                            "CARDINAL",
                                            32,
                                            gtk.gdk.PROP_MODE_REPLACE,
                                            propvals)
            else:
                self.window.property_delete("_NET_WM_STRUT")

        return False

    def do_size_allocate(self, alloc):
        # FIXME: chain fails for some reason
        #ret = self.chain(alloc)
        ret = gtk.Window.do_size_allocate(self, alloc)
        self.move_to_position()

        # Setting _NET_WM_STRUT too early can confuse the WM if the window is
        # still located at 0,0, so do it in an idle.
        gobject.idle_add(self.do_set_wm_strut)
        
        return ret


class EdgeWindow(DockWindow):
    __gsignals__ = {
        'size-request' : 'override'
        }

    def __init__(self, edge_gravity):
        DockWindow.__init__(self, edge_gravity)
        self.set_keep_above(True)
        self.set_wm_strut(True)

    def do_size_request(self, req):
        ret = self.chain(req)

        # Give some whitespace
        geom = self.get_screen().get_monitor_geometry(0)

        # If centered to a side, take at least 50% of available size
        if self.get_edge_gravity() in [gtk.gdk.GRAVITY_SOUTH, gtk.gdk.GRAVITY_NORTH]:
            req.width = max(geom.width / 2, req.width)
        elif self.get_edge_gravity() in [gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST]:
            req.height = max(geom.height / 2, req.height)

        # Never take more than available size
        req.width = min(geom.width, req.width)
        req.height = min(geom.height, req.height)

        ### Uncomment for a more stable bar size
        # If centered to a side, take 85% of available size
        #if self.get_edge_gravity() in (gtk.gdk.GRAVITY_SOUTH, gtk.gdk.GRAVITY_NORTH):
        #    req.width = geom.width * 0.85
        #elif self.get_edge_gravity() in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
        #    req.height = geom.height * 0.85

        return ret


class AnchoredWindow(DockWindow):
    '''
    A DockWindow that track the location of the widget passed to __init__ and
    displays itself in relation to it, using the gravity specified.  Uses a
    gtk.SizeGroup to keep the width/height equal to the tracked widget.
    '''

    __gsignals__ = {
        'size-request' : 'override',
        }

    def __init__(self, edge_gravity, track_widget):
        DockWindow.__init__(self, edge_gravity)
        self.set_transient_for(track_widget.get_toplevel())
        self.track_widget = track_widget

        ### Avoids desktop icons.  Any better way?
        #if edge_gravity in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
        #    self.set_wm_strut(True)

        track_widget.connect_after("size-allocate", lambda w, alloc: self.queue_resize_no_redraw())

    def do_size_request(self, req):
        track_alloc = self.track_widget.get_allocation()

        if self.get_edge_gravity() in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
            self.content.set_size_request(-1, track_alloc.height)
        else:
            self.content.set_size_request(track_alloc.width, -1)

        return self.chain(req)

    def get_win_placement(self):
        self.track_widget.realize()
        
        track_alloc = self.track_widget.allocation
        track_x, track_y = self.track_widget.window.get_origin()
        self_x, self_y = DockWindow.get_win_placement(self)

        eg = self.get_edge_gravity()
        if eg in (gtk.gdk.GRAVITY_WEST, gtk.gdk.GRAVITY_EAST):
            y = track_y + track_alloc.y - self.content.allocation.y

            if eg == gtk.gdk.GRAVITY_WEST:
                x = track_x + track_alloc.x + track_alloc.width - self.content.allocation.x
            elif eg == gtk.gdk.GRAVITY_EAST:
                x = track_x - self.allocation.width + self.content.allocation.x
        else:
            x = track_x + track_alloc.x - self.content.allocation.x

            if eg == gtk.gdk.GRAVITY_NORTH:
                y = self_y + track_alloc.height - self.content.allocation.y
            else:
                y = self_y - track_alloc.height + self.content.allocation.y

        return [x, y]


#
# GimmieBar Computer widgets: clock, pager, and tray icon manager
#

class FriendlyClock(gtk.ToggleButton):
    __gsignals__ = {
        'toggled' : 'override'
        }
    
    def __init__(self):
        gtk.ToggleButton.__init__(self)
        self.set_relief(gtk.RELIEF_NONE)
        self.set_resize_mode(gtk.RESIZE_IMMEDIATE)

        KillFocusPadding(self, "clock-applet-button")

        self.label = gtk.Label("XXX")
        self.label.set_use_markup(True)
        self.label.set_justify(gtk.JUSTIFY_CENTER)
        self.label.show()
        self.add(self.label)

        gobject.timeout_add(1000, self._update_time)
        self._update_time()

        self.popup = None

    def _update_time(self):
        now = datetime.datetime.now()
        day = now.strftime("<span size='small'>%A</span>")
        time = now.strftime("%l:%M<span size='small'> %p</span>").strip()
        now_str = "<span font_family='monospace'>%s\n%s</span>" % (day, time)
        if self.label.get_text() != now_str:
            self.label.set_markup(now_str)
        return True

    class CalendarPopup(gtk.Window):
        def __init__(self):
            gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
            self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_UTILITY)
            self.set_wmclass("gimmie", "Gimmie")
            self.set_decorated(False)
            self.set_resizable(False)
            self.set_keep_above(True)
            self.stick()
            self.set_title(_("Calendar"))

            frame = gtk.Frame()
            frame.set_shadow_type(gtk.SHADOW_OUT)
            frame.show()
            self.add(frame)

            vbox = gtk.VBox(False, 6)
            vbox.set_border_width(6)
            vbox.show()
            frame.add(vbox)

            self.cal = gtk.Calendar()
            self.cal.set_display_options(self.cal.get_display_options() |
                                         gtk.CALENDAR_SHOW_WEEK_NUMBERS)
            self.cal.show()
            vbox.pack_start(self.cal, True, False, 0)

    def _close_on_escape(self, w, ev):
        if ev.keyval == gtk.gdk.keyval_from_name("Escape"):
            self.set_active(False)
            return True
        return False

    def _position_popup(self, popup):
        x, y = self.window.get_origin()
        x += self.allocation.x
        y += self.allocation.y
        w, h = popup.size_request()
        geom = self.get_screen().get_monitor_geometry(0)

        y -= h
        if (x + w) > geom.x + geom.width:
            x -= (x + w) - (geom.x + geom.width)

        popup.move(x, y)
        popup.set_gravity(gtk.gdk.GRAVITY_SOUTH_WEST)

    def do_toggled(self):
        if self.get_active():
            self.popup = FriendlyClock.CalendarPopup()
            self.popup.connect("delete-event", lambda w, ev: self.set_active(False))
            self.popup.connect("key-press-event", self._close_on_escape)

            self._position_popup(self.popup)
            self.popup.present()
        elif self.popup:
            self.popup.destroy()
            self.popup = None

    def get_tooltip(self):
        now = datetime.datetime.now()
        day = now.strftime("%A %B %e, %Y")
        return "%s\n<span size='smaller'>No Appointments</span>" % (day)


class FriendlyPager(gtk.VBox):
    def __init__(self, screen):
        gtk.VBox.__init__(self, False, 0)
        self.use_compact_pager = False
        self.orientation = None
        self.viewport_geom = None

        self.labels = gtk.HBox(True, 0)
        self.labels.show()
        self.pack_start(self.labels, False, True, 0)

        # FIXME: This crashes for some people.
        self.pager = wnck.Pager(screen)
        self.pager.set_shadow_type(gtk.SHADOW_NONE)
        self.pager.connect("button-press-event", self._pager_button_press)
        self.pager.connect("scroll-event", self._pager_scroll_event, screen)
        self.pager.show()
        self.pack_start(self.pager, True, True, 0)

        screen.connect("active-workspace-changed", self._workspace_changed)
        screen.connect("workspace-created", self._reload_workspaces)
        screen.connect("workspace-destroyed", self._reload_workspaces)

    def set_orientation(self, orientation):
        self.orientation = orientation
        self.pager.set_orientation(orientation)
        if orientation != gtk.ORIENTATION_HORIZONTAL or self.use_compact_pager:
            self.labels.hide()
        else:
            self.labels.show()

    def _toggle_compact(self, compact):
        self.use_compact_pager = compact
        if self.use_compact_pager:
            self.pager.set_n_rows(2)
            self.labels.hide()
        else:
            self.pager.set_n_rows(1)
            if self.orientation == gtk.ORIENTATION_HORIZONTAL:
                self.labels.show()

    def _workspace_changed(self, screen, *args):
        active = screen.get_active_workspace()
        idx = 0
        for l in self.labels.get_children():
            name = _("Desk %d") % (idx + 1)
            if active and active.get_number() == idx:
                l.set_markup("<span size='small'><b>%s</b></span>" % name)
            else:
                l.set_markup("<span size='small'>%s</span>" % name)
            idx += 1

    def _reload_workspaces(self, screen, *args):
        cnt = screen.get_workspace_count()
        labels = self.labels.get_children()

        if len(labels) != cnt:
            for l in labels:
                self.labels.remove(l)

            for idx in range(0, cnt):
                l = gtk.Label("")
                l.set_alignment(0.5, 0.5)
                l.set_padding(2, 0)
                l.set_use_markup(True)
                l.show()
                self.labels.pack_start(l, True, True, 0)

            self._toggle_compact(screen.get_workspace_count() > 4)
            
            self.viewport_geom = None
            hide_pager = False
            if (cnt == 1):
                # Only hide the pager if viewports aren't used.
                window = gtk.gdk.get_default_root_window()
                type, format, self.viewport_geom = \
                      window.property_get("_NET_DESKTOP_GEOMETRY", "CARDINAL")
                if (self.viewport_geom[0] <= screen.get_width()) and \
                   (self.viewport_geom[1] <= screen.get_height()):
                    hide_pager = True
            
            if hide_pager:
                self.hide()
            else:
                self.show()
                
            self._workspace_changed(screen)

    def _pager_scroll_event(self, pager, ev, screen):
        workspace = screen.get_active_workspace()
        if not workspace:
            return
        
        if screen.get_workspace_count() == 1:
            screen_width = screen.get_width()
            if self.viewport_geom and (self.viewport_geom[0] > screen_width):
                workspace = screen.get_active_workspace()
    
                if ev.direction == gtk.gdk.SCROLL_DOWN:
                    x = workspace.get_viewport_x() + screen_width;
                else:
                    x = workspace.get_viewport_x() - screen_width
                    if x < 0:
                        x = self.viewport_geom[0] - screen_width
                
                screen.move_viewport(x, screen.get_height())
        else:
            idx = workspace.get_number()
            max_idx = screen.get_workspace_count() - 1
            if ev.direction == gtk.gdk.SCROLL_DOWN:
                d = 1
            else:
                d = -1

            workspace = screen.get_workspace(idx + d)
            if not workspace:
                if d == 1:
                    workspace = screen.get_workspace(0)
                else:
                    workspace = screen.get_workspace(max_idx)

            workspace.activate(ev.time)

    def _pager_button_press(self, pager, ev):
        if ev.button == 3:
            menu = gtk.Menu()
            menu.attach_to_widget(pager, None)

            item = gtk.CheckMenuItem(_("Use Compact Layout"))
            item.set_active(self.use_compact_pager)
            item.connect("toggled", lambda x: self._toggle_compact(x.get_active()))
            item.show()
            menu.append(item)
            
            menu.popup(None, None, None, ev.button, ev.time)
            return True


class TrayManagerBox(gtk.HBox):
    __gsignals__ = {
        'realize' : 'override'
        }

    def __init__(self):
        gtk.HBox.__init__(self, False, 0)

        from traymanager import TrayManager
        self.tray_mgr = TrayManager()
        self.tray_mgr.connect("tray_icon_added", self._add_tray_icon)
        self.tray_mgr.connect("tray_icon_removed", self._remove_tray_icon)

    def do_realize(self):
        self.chain()
        self.tray_mgr.manage_screen(gtk.gdk.screen_get_default())

    def _add_tray_icon(self, traymgr, icon):
        self.pack_start(icon, False, True, 0)

    def _remove_tray_icon(self, traymgr, icon):
        self.remove(icon)
