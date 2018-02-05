
from gettext import gettext as _

import gtk
import gconf
import gobject

from gimmie_base import gimmie_get_topic_for_uri


class Preferences(gtk.Dialog):
    def __init__(self, prefs):
        gtk.Dialog.__init__(self)
        self.set_title(_("Gimmie Preferences"))
        self.set_has_separator(False)

        self.prefs = prefs

        btn = self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        btn.connect("clicked", self.close)

        self.style_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING);
        self.style_store.append((_("Text only"), "text"))
        self.style_store.append((_("Icons only"), "icon"))
        self.style_store.append((_("Text and icons"), "both"))

        self.combo_style = gtk.ComboBox(self.style_store)

        cell = gtk.CellRendererText()
        self.combo_style.pack_start(cell, True)
        self.combo_style.add_attribute(cell, "text", 0)
        self.combo_style.set_active(0)
        self.combo_style.connect("changed", self._button_style_combo_changed)

        self.prefs.connect("changed::button_style", self._button_style_pref_changed)
        self._button_style_pref_changed(self.prefs)

        combo_label = gtk.Label(_("Topic _button labels:"))
        combo_label.set_use_underline(True)

        hbox_style = gtk.HBox(False, 6)
        hbox_style.pack_start(combo_label)
        hbox_style.pack_start(self.combo_style)

        self.color_check = gtk.CheckButton("Show topic _colors")
        self.color_check.connect("toggled", self._use_colors_toggled)

        self.prefs.connect("changed::use_colors", self._use_colors_pref_changed)
        self._use_colors_pref_changed(self.prefs)

        vbox = gtk.VBox(False, 6)
        vbox.pack_start(hbox_style, False, False)
        vbox.pack_start(self.color_check, False, False)

        align = gtk.Alignment()
        align.set_padding(12, 0, 24, 0)
        align.add(vbox)
        align.show()

        frame_style = self.make_frame(_("Appearance"))
        frame_style.add(align)

        table = gtk.Table(2, 2, True)
        table.set_row_spacings(6)
        table.set_col_spacings(12)

        # Try to get the Computer topic name (i.e. the platform name)
        computer = gimmie_get_topic_for_uri("topic://Computer")
        computer_name = computer and computer.get_name() or _("Computer")
        
        table.attach(self.make_btn(computer_name, "show_computer"), 0,1, 0,1)
        table.attach(self.make_btn(_("Programs"), "show_programs"), 1,2, 0,1)
        table.attach(self.make_btn(_("Library"),  "show_library"),  0,1, 1,2)
        table.attach(self.make_btn(_("People"),   "show_people"),   1,2, 1,2)

        align = gtk.Alignment()
        align.set_padding(12, 0, 24, 0)
        align.add(table)
        align.show()

        frame_cat = self.make_frame(_("Topics"))
        frame_cat.add(align)

        vbox = gtk.VBox(False, 12)
        vbox.set_border_width(12)
        vbox.pack_start(frame_cat, False, False, 0)
        vbox.pack_start(frame_style, False, False, 0)

        self.vbox.add(vbox)
        
        self.show_all()

    def make_frame(self, label_text):
        label = gtk.Label()
        label.set_markup("<b>%s</b>" % label_text)
        label.show()

        frame = gtk.Frame();
        frame.set_label_widget(label)
        frame.set_shadow_type(gtk.SHADOW_NONE)
        return frame

    def make_btn(self, label, pref_key):
        btn = gtk.CheckButton(label)
        btn.connect("toggled", self._show_topic_toggled, pref_key)

        self.prefs.connect("changed::" + pref_key, self._show_topic_pref_changed, btn, pref_key)
        self._show_topic_pref_changed(self.prefs, btn, pref_key)

        return btn

    def _show_topic_toggled(self, btn, key):
        self.prefs.set(key, btn.get_active())

    def _show_topic_pref_changed(self, prefs, btn, pref_key=None):
        btn.set_active(self.prefs.get(pref_key, default=True) == True)

    def _button_style_combo_changed(self, combobox):
        state = self.style_store.get_value(self.combo_style.get_active_iter(), 1)
        self.prefs.set("button_style", state)

    def _button_style_pref_changed(self, prefs):
        new_setting = self.prefs.get("button_style", default="both")
        for row in self.style_store:
            if row[1] == new_setting:
                self.combo_style.set_active_iter(row.iter)
                break

    def _use_colors_toggled(self, btn):
        self.prefs.set("use_colors", self.color_check.get_active())

    def _use_colors_pref_changed(self, prefs):
        self.color_check.set_active(self.prefs.get("use_colors", default=True) == True)

    def close(self, button):
        self.destroy()
