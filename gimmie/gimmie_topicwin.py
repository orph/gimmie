
import datetime
import math
from xml.sax import saxutils
from gettext import gettext as _

import gobject
import gtk
import pango
import gconf

try:
    import iconentry
except ImportError:
    pass

try:
    import cairo
except ImportError:
    pass

from gimmie_base import ItemSource, gimmie_get_topic_for_uri
from gimmie_util import bookmarks, icon_factory, ToolMenuButton, gconf_bridge
from gimmie_globals import gimmie_is_panel_applet


#
#  Topic Window helpers
#

class SearchToolItem(gtk.ToolItem):
    __gsignals__ = {
        "clear" : (gobject.SIGNAL_RUN_FIRST,
                   gobject.TYPE_NONE,
                   ()),
        "search" : (gobject.SIGNAL_RUN_FIRST,
                    gobject.TYPE_NONE,
                    (gobject.TYPE_STRING,))
        }

    def __init__(self, accel_group = None):
        gtk.ToolItem.__init__(self)
        self.search_timeout = 0
        self.default_search_text = _("Search")

        box = gtk.HBox(False, 0)
        box.show()

        try:
            img = icon_factory.load_image(gtk.STOCK_FIND, 16)
            img.show()
            ev_box = gtk.EventBox()
            ev_box.set_property('visible-window', False)
            ev_box.add(img)
            ev_box.show()

            self.clearbtn = gtk.EventBox()
            self.clearbtn.set_property('visible-window', False)
            self.clearbtn.set_size_request(16, -1)
            self.clearbtn.show()
            self.clearbtn.connect("button-release-event", lambda w, ev: self.emit("clear"))

            self.iconentry = iconentry.IconEntry()
            self.iconentry.pack_widget(ev_box, True)
            self.iconentry.pack_widget(self.clearbtn, False)

            align = gtk.Alignment(0.5, 0.5)
            align.set_padding(0, 0, 0, 10)
            align.add(self.iconentry)
            align.show()

            box.pack_start(align, False, False, 0)
            self.entry = self.iconentry.get_entry()
        except NameError:
            self.clearbtn = None
            self.iconentry = None
            self.entry = gtk.Entry()
            box.pack_start(self.entry, False, False, 10)

        self.entry.set_width_chars(14)
        self.entry.set_text(self.default_search_text)
        self.entry.show()
        self.entry.connect("activate", lambda w: self._typing_timeout())
        self.entry.connect("focus-in-event", lambda w, x: self._entry_focus_in())
        self.entry.connect("key-press-event", self._entry_key_press)
        # Hold on to this id so we can block emission when initially clearing text
        self.change_handler_id = self.entry.connect("changed", lambda w: self._queue_search())

        if accel_group:
            # Focus on Ctrl-L
            self.entry.add_accelerator("grab-focus",
                                       accel_group,
                                       ord('l'),
                                       gtk.gdk.CONTROL_MASK,
                                       0)

        self.add(box)
        self.show_all()

    def do_clear(self):
        if self.clearbtn and self.clearbtn.child:
            self.clearbtn.remove(self.clearbtn.child)
        self._entry_clear_no_change_handler()

    def do_search(self, text):
        if self.clearbtn and not self.clearbtn.child:
            img = icon_factory.load_image(gtk.STOCK_CLOSE, 16)
            img.show()
            self.clearbtn.add(img)

    def _entry_clear_no_change_handler(self):
        '''Avoids sending \'changed\' signal when clearing text.'''
        self.entry.handler_block(self.change_handler_id)
        self.entry.set_text("")
        self.entry.handler_unblock(self.change_handler_id)

    def _entry_focus_in(self):
        '''Clear default search text'''
        if self.entry.get_text() == self.default_search_text:
            self._entry_clear_no_change_handler()

    def _typing_timeout(self):
        if len(self.entry.get_text()) > 0:
            self.emit("search", self.entry.get_text())
        self.search_timeout = 0
        return False

    def _queue_search(self):
        if self.search_timeout != 0:
            gobject.source_remove(self.search_timeout)
            self.search_timeout = 0

        if len(self.entry.get_text()) == 0:
            self.emit("clear")
        else:
            self.search_timeout = gobject.timeout_add(50, self._typing_timeout)

    def _entry_key_press(self, w, ev):
        if ev.keyval == gtk.gdk.keyval_from_name("Escape") \
               and len(self.entry.get_text()) > 0:
            self.emit("clear")
            return True

    def get_search_text(self):
        if self.entry.get_text() == self.default_search_text:
            return None
        return self.entry.get_text()

    def cancel(self):
        '''Cancel a pending/active search without sending the \'clear\' signal.'''
        if self.entry.get_text() != self.default_search_text:
            self.do_clear()


class ZoomMenuToolItem(ToolMenuButton):
    __gsignals__ = {
        "zoom-changed" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_INT,)),
        "open-timeline" : (gobject.SIGNAL_RUN_FIRST,
                           gobject.TYPE_NONE,
                           ())
        }

    _zoomlist = [[_("Today"), 1],
                 [_("This week"), 7],
                 [_("Last 2 weeks"), 14],
                 [_("This month"), 30],
                 [_("Last 2 months"), 60],
                 [_("Last 3 months"), 90],
                 [_("Last 6 months"), 180]]
    _default_zoom = 7

    def __init__(self):
        img = gtk.Image()
        img.set_from_pixbuf(icon_factory.load_icon(gtk.STOCK_ZOOM_IN,
                                                   gtk.ICON_SIZE_SMALL_TOOLBAR))
        ToolMenuButton.__init__(self, img, "")

        self.zoom_level = self._default_zoom
        group = None
        menu = gtk.Menu()

        for name, days in self._zoomlist:
            group = self._make_menu_item(group, name, days)
            if days == self.zoom_level:
                group.set_active(True)
            menu.append(group)

        item = gtk.SeparatorMenuItem()
        menu.append(item)

        item = gtk.CheckMenuItem(_("Show timeline"))
        item.connect("activate", lambda w: self.emit("open-timeline"))
        menu.append(item)

        menu.show_all()

        self.set_menu(menu)
        self.show_all()

    def _item_toggled(self, w, name, num_days):
        if w.get_active():
            self.set_label(name)
            self.zoom_level = num_days
            self.emit("zoom-changed", num_days)

    def _make_menu_item(self, group, name, num_days):
        item = gtk.RadioMenuItem(group, name)
        item.connect("toggled", self._item_toggled, name, num_days)
        item.zoom_level = num_days
        return item

    def get_zoom_level(self):
        return self.zoom_level

    def get_zoom_level_list(self, floor = _default_zoom):
        return [days for name, days in self._zoomlist if days >= floor]

    def set_zoom_level(self, zoom_level):
        self.zoom_level = zoom_level
        for btn in self.get_menu().get_children():
            if hasattr(btn, "zoom_level") and btn.zoom_level == zoom_level:
                btn.set_active(True)


class SparkLine(gtk.EventBox):
    __gsignals__ = {
        "realize" : "override",
        "expose-event" : "override",
        "zoom-changed" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_INT,)),
        }

    def __init__(self, zoom_level_list):
        '''
        first_date is the oldest recorded item, not necessarily included in this
        sparkline.
        '''
        gtk.EventBox.__init__(self)
        self.set_redraw_on_allocate(True)

        self.zoom_level_list = zoom_level_list[:]
        self.zoom_level_list.sort()
        self.first_day = datetime.timedelta(self.zoom_level_list[-1])

        self.day_width = -1
        self.num_days_selected = -1
        self.set_dates([])

    def do_size_request(self, req):
        req.width = self.first_day.days
        req.height = 24

    def do_realize(self):
        self.chain()
        self.style.set_background(self.window, self.state)
        self.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND1))

    def do_button_press_event(self, ev):
        today_ordinal = datetime.date.today().toordinal()
        first_ordinal = (datetime.date.today() - self.first_day).toordinal()

        num_days = today_ordinal - first_ordinal
        if num_days == 0:
            # No data, nothing to click
            return True

        if self.day_width <= 0:
            # Too much data, nothing to click
            return True

        click_day = num_days - (ev.x / self.day_width)

        for i in self.zoom_level_list:
            if click_day <= i:
                print " *** SparkLine: Setting zoom level %d days." % i
                self.emit("zoom-changed", i)
                break

        return True

    def do_expose_event(self, ev):
        self.chain(ev)
        try:
            cr = self.window.cairo_create()
        except AttributeError:
            return self._paint_gdk()
        return self._paint_cairo(cr)

    def _paint_cairo(self, cr):
        today_ordinal = datetime.date.today().toordinal()
        first_ordinal = (datetime.date.today() - self.first_day).toordinal()

        num_days = len(self.date_cnts)
        if num_days == 0:
            # No data, nothing to draw
            return True

        # Width of individual day bars, and total of all bars
        # Store day_width for use in button-press handler
        self.day_width = float(self.allocation.width) / num_days
        print "day_width == ", self.day_width
        total_width = self.day_width * num_days

        # Get colors to draw from the theme
        bar_color = self.style.fg[gtk.STATE_INSENSITIVE]
        baseline_color = self.style.fg[gtk.STATE_NORMAL]
        selected_color = self.style.base[gtk.STATE_SELECTED]

        # Draw with slight upward offset
        base_height = self.allocation.height - 10

        cr.set_line_width(1.0)
        cr.scale(1.0, 1.0)

        cr.set_source_color(self.style.white)
        cr.rectangle(0, 0, self.allocation.width, self.allocation.height)
        cr.fill()

        # Draw the baseline for days which don't have any data
        cr.set_source_color(baseline_color)
        cr.move_to(0, base_height - 1)
        cr.line_to(total_width, base_height - 1)
        cr.stroke()

        # Draw the day segment separators for 0 days
        cr.rectangle(total_width, base_height, 1, 5)
        cr.fill()

        # Draw the data bars
        x_offset = 0
        dates = self.date_cnts.keys ()
        dates.sort()

        levels_list = self.zoom_level_list[:]
        
        for date in dates:
            if date.toordinal() < first_ordinal:
                continue

            cnt = self.date_cnts[date]

            height = math.log(base_height) * cnt
            height = min(height, base_height)

            color = bar_color
            if today_ordinal - date.toordinal() < self.num_days_selected:
                color = selected_color

            cr.set_line_width(0.2)

            cr.set_source_color(color)
            cr.rectangle(x_offset, base_height - height,
                         self.day_width, height)
            cr.fill()

            cr.set_source_color(baseline_color)
            cr.rectangle(x_offset, base_height - height,
                         self.day_width, height)
            cr.stroke ()

            # Fill selected region
            if today_ordinal - date.toordinal() < self.num_days_selected:
                cr.set_line_width(0.5)
                cr.set_source_color(selected_color)
                cr.rectangle(x_offset, base_height, self.day_width, 2.5)
                cr.fill()
                cr.set_source_color(baseline_color)
                cr.stroke()

            if levels_list and today_ordinal - date.toordinal() <= levels_list[-1]:
                cr.set_line_width(1.5)
                cr.set_source_color(baseline_color)
                cr.move_to(x_offset, base_height)
                cr.line_to(x_offset, base_height + 5)
                cr.stroke()
                levels_list.pop()

            x_offset += self.day_width

        return True

    def _paint_gdk(self):
        today_ordinal = datetime.date.today().toordinal()
        first_ordinal = (datetime.date.today() - self.first_day).toordinal()

        num_days = today_ordinal - first_ordinal
        if num_days == 0:
            # No data, nothing to draw
            return True

        # Width of individual day bars, and total of all bars
        self.day_width = self.allocation.width / num_days
        total_width = self.day_width * num_days

        # Get colors to draw from the theme
        bar_gc = self.get_style().fg_gc[gtk.STATE_INSENSITIVE]
        baseline_gc = self.get_style().fg_gc[gtk.STATE_NORMAL]
        selected_gc = self.get_style().base_gc[gtk.STATE_SELECTED]

        # Draw with slight upward offset
        base_height = self.allocation.height - 10

        # Draw the currently selected region indicator first
        selection_width = self.day_width * self.num_days_selected
        if selection_width < 0:
            selection_width = self.allocation.width

        self.window.draw_rectangle(selected_gc, True,
                                   total_width - selection_width, base_height,
                                   selection_width, 5)

        # Draw the baseline for days which don't have any data
        self.window.draw_rectangle(baseline_gc, True,
                                   0, base_height,
                                   total_width, 1)

        # Draw the day segment separators for each zoom level, including the
        # last possible day.
        levels_list = self.zoom_level_list
        levels_list.append(num_days)
        for i in levels_list:
            if i <= num_days:
                x_offset = (today_ordinal - first_ordinal - i) * self.day_width
                self.window.draw_rectangle(baseline_gc, True,
                                           x_offset, base_height,
                                           1, 5)

        # Draw the day segment separators for 0 days
        self.window.draw_rectangle(baseline_gc, True,
                                   total_width, base_height,
                                   1, 5)

        # Draw the data bars
        for date, cnt in self.date_cnts.iteritems():
            if date.toordinal() < first_ordinal:
                continue

            x_offset = (date.toordinal() - first_ordinal - 1) * self.day_width
            height = int(math.log(base_height) * cnt)
            height = min(height, base_height)

            gc = bar_gc
            if today_ordinal - date.toordinal() < self.num_days_selected:
                gc = selected_gc
            self.window.draw_rectangle(gc, True,
                                       x_offset, base_height - height,
                                       self.day_width, height)

            self.window.draw_rectangle(baseline_gc, False,
                                       x_offset, base_height - height,
                                       self.day_width, height)

        return True

    def set_dates(self, datetime_list):
        self.date_cnts = {}
        self.largest_cnt = 0

        for date in datetime_list:
            if isinstance(date, datetime.datetime):
                date = date.date()
            else:
                assert isinstance(date, datetime.date)

            new_cnt = self.date_cnts.get(date, 0) + 1
            self.date_cnts[date] = new_cnt

            if new_cnt > self.largest_cnt:
                self.largest_cnt = new_cnt

        self.queue_draw()

    def set_zoom_level(self, zoom_level):
        self.num_days_selected = zoom_level
        self.queue_draw()


class TimeBar(gtk.EventBox):
    __gsignals__ = {
        "zoom-changed" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_INT,)),
        }

    _zoomlist = [[_("Today"), 1],
                 [_("This week"), 7],
                 [_("Last 2 weeks"), 14],
                 [_("This month"), 30],
                 [_("Last 2 months"), 60],
                 [_("Last 3 months"), 90],
                 [_("Last 6 months"), 180]]
    _default_zoom = 7

    def __init__(self):
        gtk.EventBox.__init__(self)
        self.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))
        
        box = gtk.HBox(False, 0)
        box.show()
        self.add(box)

        self._add_sparkline(box)

        self.label = gtk.Label()
        self.label.set_width_chars(max([len(x[0]) for x in self._zoomlist]))
        self.label.set_alignment(1.0, 0.5)
        box.pack_start(self.label, False, False, 6)

        self.in_btn = gtk.Button()
        self.in_btn.add(gtk.image_new_from_stock(gtk.STOCK_REMOVE, gtk.ICON_SIZE_SMALL_TOOLBAR))
        self.in_btn.set_relief(gtk.RELIEF_NONE)
        self.in_btn.connect("clicked", lambda btn: self._zoom_clicked(-1))
        box.pack_start(self.in_btn, False, False)

        self.out_btn = gtk.Button()
        self.out_btn.add(gtk.image_new_from_stock(gtk.STOCK_ADD, gtk.ICON_SIZE_SMALL_TOOLBAR))
        self.out_btn.set_relief(gtk.RELIEF_NONE)
        self.out_btn.connect("clicked", lambda btn: self._zoom_clicked(1))
        box.pack_start(self.out_btn, False, False)

        box.show_all()

        self.set_zoom_level(self._default_zoom)

    def _add_sparkline(self, box):
        self.spark = None
        
        ### Disabled due to bugginess for 0.2.8
        #self.spark = SparkLine(self.get_zoom_level_list(floor=0))
        #self.spark.connect("zoom-changed", lambda w, num_days: self.set_zoom_level(num_days))

        #align = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        #align.set_property("top-padding", 4)
        #align.add(self.spark)
        #box.pack_start(align, True, True, 6)

    def get_zoom_level(self):
        return self.zoom_level

    def get_zoom_level_list(self, floor = _default_zoom):
        return [days for name, days in self._zoomlist if days >= floor]

    def _zoom_clicked(self, dir):
        for i in range(len(self._zoomlist)):
            label, days = self._zoomlist[i]
            if days == self.zoom_level:
                try:
                    label, days = self._zoomlist[i + dir]
                except IndexError:
                    label, days = self._zoomlist[0]
                self.set_zoom_level(days, label)
                break

    def set_zoom_level(self, zoom_level, label=None):
        self.zoom_level = zoom_level

        if not label:
            for _label, days in self._zoomlist:
                if days == zoom_level:
                    label = _label
        self.label.set_text(label)
        if self.spark:
            self.spark.set_zoom_level(zoom_level)
        self.emit("zoom-changed", zoom_level)

    def set_items(self, items):
        dates = [x.get_timestamp() for x in items if x.get_timestamp() != 0]
        dates = [datetime.date.fromtimestamp(x) for x in dates]
        if self.spark:
            self.spark.set_dates(dates)


class HideOnDeleteWindow(gtk.Window):
    __gsignals__ = {
        'hide' : 'override',
        'delete-event' : 'override',
        'key-press-event' : 'override',
        }

    def __init__(self):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        # Act the same as hidden when iconified by hiding from the task list.
        self.connect("map-event", lambda w, ev: self.set_skip_taskbar_hint(False))
        self.connect("unmap-event", lambda w, ev: self.set_skip_taskbar_hint(True))

    def do_hide(self):
        self.chain()

        # Workaround Gtk bug, where adding or changing Widgets
        # while the Window is hidden causes it to be reshown at
        # 0,0...
        self_x, self_y = self.get_position()
        self.move(self_x, self_y)
        return True

    def do_delete_event(self, ev):
        self.hide()
        return True

    def do_key_press_event(self, ev):
        if not gtk.Window.do_key_press_event(self, ev) \
               and ev.keyval == gtk.gdk.keyval_from_name("Escape"):
            self.iconify()
            return True


class ItemIconView(gtk.IconView):
    '''
    Icon view which displays Items in the style of the Nautilus horizontal mode,
    where icons are right aligned and each column is of a uniform width.  Also
    handles opening an item and displaying the item context menu.
    '''
    def __init__(self):
        gtk.IconView.__init__(self)
        self.set_orientation(gtk.ORIENTATION_HORIZONTAL)

        self.idle_load_id = None
        self.reload_handlers = {}

        # PyGtk before 2.8.4 doesn't expose GtkIconView's CellLayout interface
        self.use_cells = isinstance(self, gtk.CellLayout)
	if self.use_cells:
            # Pack the renderers manually, since GtkIconView layout is very buggy.
            self.icon_cell = gtk.CellRendererPixbuf()
            self.icon_cell.set_property("yalign", 0.0)
            self.icon_cell.set_property("xalign", 1.0)
            self.pack_start(self.icon_cell, expand=False)
            self.add_attribute(self.icon_cell, "pixbuf", 1)

            self.text_cell = gtk.CellRendererText()
            self.text_cell.set_property("wrap-mode", pango.WRAP_WORD_CHAR)
            self.text_cell.set_property("yalign", 0.0)
            self.pack_start(self.text_cell, expand=False)
            self.add_attribute(self.text_cell, "markup", 0)
        else:
            self.set_markup_column(0)
            self.set_pixbuf_column(1)
            self.set_item_width(230)

        self.set_margin(12)
        self.set_spacing(4)
        self.set_selection_mode(gtk.SELECTION_MULTIPLE)
        self.connect("item-activated", self._open_item)
        self.connect("button-press-event", self._show_item_popup)
        self.connect("button-release-event", self._button_release)
        self.connect("drag-data-get", self._item_drag_data_get)
        self.connect("motion-notify-event", self._motion_notify)
        self.enable_model_drag_source(0,
                                      [("text/uri-list", 0, 100)],
                                      gtk.gdk.ACTION_LINK | gtk.gdk.ACTION_COPY)

        self.click_policy = gconf_bridge.get("click_policy")
        gconf_bridge.connect("changed::click_policy", lambda gb: self._click_policy_changed())

        self.nautilus_gconf_notify_id = None
        if self.click_policy == "nautilus":
            self._connect_nautilus_click_policy()

        bookmarks.connect("reload", lambda b: self._reload_visible_items())

        self.highlight_path = None
        self.highlight_normal_icon = None
        self.highlight_timeout = 0

    def _connect_nautilus_click_policy(self):
        nautilus_dir = "/apps/nautilus/preferences/"
        self.nautilus_click_policy_key = nautilus_dir + "click_policy"

        self.gconf_client = gconf.client_get_default()
        self.gconf_client.add_dir(nautilus_dir[:-1], gconf.CLIENT_PRELOAD_NONE)
        self.nautilus_gconf_notify_id = \
               self.gconf_client.notify_add(self.nautilus_click_policy_key,
                                            self._nautilus_click_policy_changed)

        value = self.gconf_client.get(self.nautilus_click_policy_key)
        if value:
            self.click_policy = value.get_string()
        else:
            self.click_policy = "double"

    def _disconnect_nautilus_click_policy(self):
        if self.nautilus_gconf_notify_id:
            self.gconf_client.notify_remove(self.nautilus_gconf_notify_id)
            self.nautilus_gconf_notify_id = None

    def _nautilus_click_policy_changed(self, client, cnxn_id, entry, data=None):
        value = self.gconf_client.get(self.nautilus_click_policy_key)
        if value:
            self.click_policy = value.get_string()

    def _compare_item_name(self, model, iter1, iter2, user_data = None):
        '''
        Item comparison: special items come first, followed by case insensitive
        name comparison.
        '''
        item1 = model.get_value(iter1, 2)
        item2 = model.get_value(iter2, 2)
        return not item1 and 1 or \
               not item2 and -1 or \
               cmp(not item1.is_special(), not item2.is_special()) or \
               cmp((item1.get_name() or "").lower(), (item2.get_name() or "").lower())

    def load_items(self, items, ondone_cb = None):
        '''
        Creates a new list store to load with item data, then sets up an idle
        timeout generator to fill it.
        '''
        
        # Clean up existing item reload connections
        for item, handler in self.reload_handlers.iteritems():
            item.handler_disconnect(handler)
        self.reload_handlers.clear()

        store = gtk.ListStore(gobject.TYPE_STRING,    # 0: Markup text
                              gtk.gdk.Pixbuf,         # 1: Pixbuf
                              gobject.TYPE_PYOBJECT,  # 2: Item
                              gobject.TYPE_BOOLEAN)   # 3: Visible
        store.set_sort_func(2, self._compare_item_name)
        store.set_sort_column_id(2, gtk.SORT_ASCENDING)
        store.icon_width = -1
        store.wrap_width = -1

        filterstore = store.filter_new()
        filterstore.set_visible_column(3)

        # IconView bug doesn't send selection-changed on set_model
        self.unselect_all()
        self.set_model(filterstore) # Set the model

        # Clear highlight state
        self.highlight_path = None
        self.highlight_normal_icon = None
        if self.highlight_timeout != 0:
            gobject.source_remove(self.highlight_timeout)
        
        if self.idle_load_id:
            gobject.source_remove(self.idle_load_id) # Cancel pending load
        self.idle_load_id = \
            gobject.timeout_add(0, self._idle_load_items(items, store, ondone_cb).next)

    def _idle_load_items(self, items, store, ondone_cb):
        '''
        Loads one item at a time, yielding True if there is more to load, and
        setting the IconView model and yielding False when finished.
        '''
        for i in items:
            iter = store.append((None, None, i, i.get_is_user_visible()))
            self.reload_handlers[i] = i.connect("reload", self._reload_item, iter, store)
            yield True # Keep going

        self._reload_visible_items()

        if ondone_cb:
            ondone_cb()

        yield False # All done

    def _update_sizing(self, icon_width):
        if self.use_cells and icon_width > self.icon_cell.get_fixed_size()[0]:
            self.icon_cell.set_fixed_size(icon_width, -1) # Reset icon sizing
            wrap_width = 230 - icon_width - 4
            self.text_cell.set_property("wrap-width", wrap_width)

    def _reload_item(self, item, iter, store):
        if store.iter_is_valid(iter):
            icon_size = self._set_item(item, iter, store)
            self._update_sizing(icon_size)

    def _reload_visible_items(self):
        store = self.get_model()
        if isinstance(store, gtk.TreeModelFilter):
            # Get a writable model if a filter model is set
            store = store.get_model()

        max_size = 0
        for row in store:
            icon_size = self._set_item(row[2], row.iter, store)
            max_size = max(icon_size, max_size)
        self._update_sizing(max_size)

    def _set_item(self, item, iter, store):
        if not item.get_is_user_visible():
            store.set(iter, 3, False) # Hide the item
            return 0

        name = item.get_name_markup()
        largename = "<span size='large'>%s</span>" % name
        smallname = "<span size='small'>%s</span>" % name
        comment = "<span size='small'>%s</span>" % item.get_comment_markup()

        # Size based on number of visible items
        item_cnt = len(store)
        if item_cnt > 40:
            text = smallname
            icon_size = 16
        elif item_cnt > 30:
            text = name
            icon_size = 24
        elif item_cnt > 15:
            text = name + "\n" + comment
            icon_size = 24
        else:
            text = largename + "\n" + comment
            icon_size = 32

        # Show pinned items and those opened today with a larger icon
        if datetime.date.fromtimestamp(item.get_timestamp()) == datetime.date.today() or \
               item.get_is_pinned():
            icon_size = min(icon_size * 2, 48)

        try:
            icon = item.get_icon(icon_size)
            # Bound returned width to height * 2
            icon_width = min(icon.get_width(), icon.get_height() * 2)
        except (AssertionError, AttributeError):
            icon = None
            icon_width = 0

        # Update text, icon, and visibility
        store.set(iter, 0, text, 1, icon, 3, True)

        # Return the icon width used for sizing other records
        return icon_width

    def _open_item(self, view, path):
        model = view.get_model()
        model.get_value(model.get_iter(path), 2).open()

    def _deactivate_item_popup(self, menu, view, old_selected):
        view.unselect_all()
        print " *** Restoring previous selection"
        for path in old_selected:
            view.select_path(path)

    def _show_item_popup(self, view, ev):
        if ev.button == 3:
            path = view.get_path_at_pos(int(ev.x), int(ev.y))
            if path:
                model = view.get_model()
                item = model.get_value(model.get_iter(path), 2)
                if item:
                    old_selected = view.get_selected_items()

                    view.unselect_all()
                    view.select_path(path)

                    menu = gtk.Menu()
                    menu.attach_to_widget(view, None)
                    menu.connect("deactivate", self._deactivate_item_popup, view, old_selected)

                    print " *** Showing item popup"
                    item.populate_popup(menu)
                    menu.popup(None, None, None, ev.button, ev.time)
                    return True

    def _item_drag_data_get(self, view, drag_context, selection_data, info, timestamp):
        # FIXME: Prefer ACTION_LINK if available
        if info == 100: # text/uri-list
            selected = view.get_selected_items()
            if not selected:
                return

            model = view.get_model()
            uris = []
            for path in selected:
                item = model.get_value(model.get_iter(path), 2)
                if not item:
                    continue
                uris.append(item.get_uri())

            print " *** Dropping URIs:", uris
            selection_data.set_uris(uris)

    def _button_release(self, view, ev):
        if ev.button == 1 and self.click_policy == 'single':
            path = view.get_path_at_pos(int(ev.x), int(ev.y))
            if path:
                self.item_activated(path)

    def _undo_highlight(self):
        model = self.get_model()
        iter = model.convert_iter_to_child_iter(model.get_iter(self.highlight_path))

        # Reset the normal icon
        model.get_model().set_value(iter, 1, self.highlight_normal_icon)

        self.highlight_path = None
        self.highlight_normal_icon = None

    def _do_highlight(self, path):
        model = self.get_model()
        iter = model.convert_iter_to_child_iter(model.get_iter(path))

        pixbuf = model.get_model().get_value(iter, 1)
        if pixbuf:
            # Set highlight icon
            model.get_model().set_value(iter, 1, icon_factory.colorshift(pixbuf, 30))

            # Store the path and regular icon for later
            self.highlight_path = path
            self.highlight_normal_icon = pixbuf

    def _motion_notify_timeout(self):
        x, y = self.get_pointer()
        path = self.get_path_at_pos(x, y)

        if path != self.highlight_path:
            if self.highlight_path:
                self._undo_highlight()
            if path:
                self._do_highlight(path)

        if self.click_policy == "single":
            cursor = None
            if path:
                # Set hand cursor
                cursor = gtk.gdk.Cursor(gtk.gdk.HAND2)
            self.window.set_cursor(cursor)

        self.highlight_timeout = 0
        return False

    def _motion_notify(self, view, ev):
        if self.highlight_timeout != 0:
            gobject.source_remove(self.highlight_timeout)

        # Avoid highlighting while rubberbanding
        if not ev.state & gtk.gdk.BUTTON1_MASK:
            ### FIXME: IconView flickers if we replace the icon too quickly, so use
            ###        a short timeout.
            self.highlight_timeout = gobject.timeout_add(5, self._motion_notify_timeout)

    def _click_policy_changed(self):
        self.click_policy = gconf_bridge.get("click_policy")

        if self.click_policy == "nautilus":
            self._connect_nautilus_click_policy()
        else:
            self._disconnect_nautilus_click_policy()


class SidebarButton(gtk.ToggleButton):
    '''
    A ToggleButton that represents an ItemSource.  Emits a "reload" signal when
    the button is toggled as active or if it\'s ItemSource emits "reload".
    The button contents will be the source\'s icon (large toolbar sized) and
    name, and the button cannot be untoggled by the user.
    '''
    __gsignals__ = {
        "reload" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
        }

    def __init__(self, source):
        gtk.ToggleButton.__init__(self)
        self.source = source

        self.img = gtk.Image()
        self.img.set_from_pixbuf(source.get_icon(gtk.ICON_SIZE_LARGE_TOOLBAR))
        self.img.show()
        ### Uncomment to show the number of items in label
        #name = "%s (%d)" % (source.get_name(), len(source.get_items()))
        self.label = gtk.Label(source.get_name())
        self.label.show()

        self._reload_button_content()

        hbox = gtk.HBox(False, 4)
        hbox.pack_start(self.img, False, False, 0)
        hbox.pack_start(self.label, False, False, 0)
        hbox.show()

        self.add(hbox)
        self.set_focus_on_click(False)
        self.set_active(False)

        source.connect_after("reload", lambda s: self._reload_if_active())
        self.connect("toggled", lambda w: self._reload_if_active())

        self.connect("button-press-event", self._ignore_untoggle)

    def _reload_button_content(self):
        self.set_sensitive(self.source.get_enabled())
        self.img.set_from_pixbuf(self.source.get_icon(gtk.ICON_SIZE_LARGE_TOOLBAR))
        self.label.set_text(self.source.get_name())

    def _reload_if_active(self):
        self._reload_button_content()
        if self.get_active():
            self.emit("reload")

    def _ignore_untoggle(self, btn, ev):
        if ev.button == 3:
            # FIXME: Allow removing categories from sidebar
            # FIXME: Allow pinning sidebar categories when in standalone mode

            ### Context menu disabled for now
            #menu = gtk.Menu()
            #menu.attach_to_widget(btn, None)
            #
            #print " *** Showing sidebar popup"
            #self.source.populate_popup(menu)
            #menu.popup(None, None, None, ev.button, ev.time)

            return True
        elif btn.get_active():
            # Block untoggle if we are the active button
            return True

    def get_source(self):
        return self.source


class Sidebar(gtk.VBox):
    '''
    A VBox containing SidebarButtons or spacers (empty-string labels).  Handles
    ensuring only one button is toggled at a time, and emits a "set-source"
    signal when a button toggled passing it\'s associated ItemSource.
    '''
    __gsignals__ = {
        "set-source" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))
        }

    def __init__(self, topic):
        gtk.VBox.__init__(self, False)

        # FIXME: Not passed to __init__ to avoid binding bug #419107.
        self.set_spacing(4)

        self.topic = topic
        self.in_set_source = False

        # Listen for topic changes and reload the sidebar
        topic.connect_after("reload", lambda t: self.add_sources())
        self.add_sources()

    def add_sources(self):
        active_source = None
        active_source_uri = None

        for child in self.get_children():
            if isinstance(child, SidebarButton) and child.get_active():
                active_source = child.get_source()
                active_source_uri = active_source.get_uri()
            self.remove(child)
            child.destroy()

        for source in self.topic.get_sidebar_source_list():
            if not source:
                btn = gtk.Label("") # spacer
                btn.set_size_request(-1, 8)
                btn.show()
            elif source == "---":
                btn = gtk.HSeparator() # separator
                btn.set_size_request(-1, 22)
                btn.show()
            else:
                btn = SidebarButton(source)
                btn.connect("reload", self._button_reload)
                if source == active_source or \
                   (active_source_uri and source.get_uri() == active_source_uri):
                    btn.set_active(True)
                btn.show()

            self.pack_start(btn, False, False, 0)

    def _button_reload(self, btn):
        if not self.in_set_source: # Reentrance guard
            self.set_source(btn.get_source())

    def do_set_source(self, source):
        for btn in self:
            if isinstance(btn, SidebarButton):
                # Setting the button active will cause a reload signal which
                # will emit a set-source signal.
                btn.set_active(btn.get_source() == source)

    def set_source(self, source):
        self.in_set_source = True # Reentrance guard
        self.emit("set-source", source)
        self.in_set_source = False


class TopicView:
    '''
    Simple base class for the applet menu and standalone window versions a Topic
    visualizations.  Allows for filtering based on timestamp for sources that
    support it, and searching for items in all sources of the Topic.
    '''
    def __init__(self, topic):
        self.topic = topic
        self.active_source = None

        self.tooltips = gtk.Tooltips()
        self.accel_group = gtk.AccelGroup()

        self.toolbar = gtk.Toolbar()
        self.toolbar.set_show_arrow(False)
        self.toolbar.show()

        self.sidebar = Sidebar(topic)
        self.sidebar.connect("set-source", lambda sb, source: self._set_source(source))
        self.sidebar.show()

        # Frame containing content_vbox.  Subclasses should pack this.
        self.content_frame = gtk.Frame()
        self.content_frame.show()
        self.content_frame.set_shadow_type(gtk.SHADOW_IN)

        # VBox containing the icon view inside scrolled window
        self.content_vbox = gtk.VBox(False, 0)
        self.content_vbox.show()
        self.content_frame.add(self.content_vbox)

        # Scrolled window containing the icon view
        self.scroll = gtk.ScrolledWindow()
        self.scroll.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.scroll.set_shadow_type(gtk.SHADOW_NONE)
        self.scroll.show()
        self.content_vbox.pack_end(self.scroll, True, True)

        # Iconview for the current sidebar selection
        self.view = ItemIconView()
        self.view.show()
        self.scroll.add(self.view)

    def set_source_by_uri(self, uri):
        for source in self.topic.get_sidebar_source_list():
            if isinstance(source, ItemSource) and source.get_uri() == uri:
                self.sidebar.set_source(source)

    def get_zoom_level(self):
        return -1

    def set_zoom_level(self, zoom):
        pass

    def show_hide_zoomer(self, show):
        pass

    def load_items(self, items, ondone_cb = None):
        self.view.load_items(items, ondone_cb)

    def zoom_changed(self, num_days):
        if self.active_source:
            filtered = self._filter_items_num_days_ago(self.active_source.get_items(), num_days)
            # FIXME: This loses the focused item
            self.load_items(filtered)

    def _set_source(self, source):
        print " *** Setting source:", source

        self.active_source = source
        if source:
            # Clear any search text
            self.search_tool_item.cancel()

            # FIXME: This loses the focused item
            if source.get_filter_by_date():
                filtered = self._filter_items_num_days_ago(source.get_items(),
                                                           self.get_zoom_level())
                self.load_items(filtered, lambda: self.show_hide_zoomer(True))
            else:
                self.load_items(source.get_items(), lambda: self.show_hide_zoomer(False))
        else:
            self.show_hide_zoomer(False)
            self.load_items([])

    def find_first_button(self):
        '''
        Activates the first sidebar button which is not insensitive, and sets
        the zoom level (if possible) so at least two items are displayed.
        FIXME: Populate with default items if first button is empty?
        '''
        if self.active_source:
            return

        min_items = 5

        for source in self.topic.get_sidebar_source_list():
            if isinstance(source, ItemSource) and source.get_enabled():
                from gimmie_computer import FavoritesSource
                if isinstance(source, FavoritesSource):
                    # Always prefer FavoritesSource
                    self.sidebar.set_source(source)
                    break

                cnt = 0
                while source.get_items():
                    cnt += 1
                    if cnt == min_items:
                        break
                else:    
                    if cnt < min_items:
                        continue # Skip to the next sidebar button

                items = source.get_items()

                if source.get_filter_by_date():
                    for zoom in self.get_zoom_level_list():
                        filtered = self._filter_items_num_days_ago(items, zoom)
                        if len(filtered) >= min_items:
                            self.set_zoom_level(zoom)
                            break
                    else:
                        continue # Skip to the next sidebar button

                # FIXME: We're filtering to get an item count, and then
                # refiltering to show the items in _source_set.
                self.sidebar.set_source(source)
                break

        # When run inside an idle handler, don't run again
        return False

    def _filter_compare(self, i, days_ago):
        return i.is_special() or datetime.date.fromtimestamp(i.get_timestamp()) > days_ago

    def _filter_items_num_days_ago(self, items, num_days):
        if num_days < 0:
            days_ago = datetime.date.min
        else:
            days_ago = datetime.date.today() - datetime.timedelta(days = num_days)

        return [x for x in items if self._filter_compare(x, days_ago)]

    def _search(self, w, text):
        self.sidebar.set_source(None)

        matches = self.topic.find_items(text)
        self.load_items(matches)

    def _search_clear(self, w):
        self.find_first_button()

    def add_search_toolitem(self):
        item = SearchToolItem(self.accel_group)
        item.set_tooltip(self.tooltips, _("Search"))
        item.connect("search", self._search)
        item.connect("clear", self._search_clear)
        self.toolbar.insert(item, -1)
        self.search_tool_item = item


class TopicWindow(HideOnDeleteWindow, TopicView):
    '''
    The toplevel window representing a Topic\'s ItemSources, allowing one to be
    active at a time and displaying it\'s item contents using an ItemIconView.
    '''
    def __init__(self, topic):
        HideOnDeleteWindow.__init__(self)
        TopicView.__init__(self, topic)

        self.set_title(topic.get_name())
        self.set_position(gtk.WIN_POS_CENTER)
        self.set_default_size(730, -1)

        self.add_accel_group(self.accel_group)

        ### Uncomment to use the topic's color as a border
        #self.modify_bg(gtk.STATE_NORMAL, topic.get_hint_color())

        # Vbox containing the toolbar and content
        vbox = gtk.VBox(False, 0)
        vbox.show()
        self.add(vbox)

        # Toolbar
        vbox.pack_start(self.toolbar, False, False, 0)

        # Contains the visual frame, giving it some space
        content = gtk.HBox(False, 0)
        content.set_border_width(12)
        content.show()
        vbox.add(content)

        # Hbox containing the sidebar buttons and the iconview
        body = gtk.HBox(False, 12)
        body.show()
        content.pack_start(body, True, True, 0)

        # Load up the sidebar
        body.pack_start(self.sidebar, False, False, 0)

        # Add frame containing the icon view
        body.pack_start(self.content_frame, True, True, 0)

        # Iconview for the current sidebar selection
        self.view.connect("item-activated", lambda v, p: self.iconify()) # Iconify on item open

        # Zoom drop down list
        self.zoom_menu = ZoomMenuToolItem()
        self.zoom_menu.set_tooltip(self.tooltips, _("Set the zoom level"))
        self.zoom_menu.set_is_important(True)
        self.zoom_menu.connect("zoom-changed", lambda w, num_days: self.zoom_changed(num_days))
        self.zoom_menu.connect("open-timeline", lambda w: self._open_timeline())

        ### Uncomment to make parts of the window draggable (only toolbar currently)
        #self.connect_after("button-press-event",
        #                   lambda w, ev: self.begin_move_drag(ev.button,
        #                                                      int(ev.x_root),
        #                                                      int(ev.y_root),
        #                                                      ev.time))

        # Setup the toolbar
        self._add_toolbar_items()

        # Select an initial sidebar button
        self.find_first_button()

    def get_zoom_level(self):
        return self.zoom_menu.get_zoom_level()

    def get_zoom_level_list(self):
        return self.zoom_menu.get_zoom_level_list()

    def set_zoom_level(self, zoom):
        self.zoom_menu.set_zoom_level(zoom)

    def show_hide_zoomer(self, show):
        self.zoom_menu.set_sensitive(show)

    def _open_timeline(self):
        topic = gimmie_get_topic_for_uri("topic://Computer")
        topicwin = topic.get_topic_window()
        topicwin.set_source_by_uri("source://Timeline")
        topicwin.present()

    def _add_toolbar_items(self):
        for i in self.topic.get_toolbar_items(self.tooltips):
            if not i:
                i = gtk.SeparatorToolItem()
            i.show_all()
            self.toolbar.insert(i, -1)

        # Right-align the zoom and search tool items
        sep = gtk.SeparatorToolItem()
        sep.set_draw(False)
        sep.set_expand(True)
        sep.show()
        self.toolbar.insert(sep, -1)

        self.toolbar.insert(self.zoom_menu, -1)

        self.add_search_toolitem()


