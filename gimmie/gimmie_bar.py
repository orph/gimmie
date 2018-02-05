#!/usr/bin/env python

import gtk

from gimmie_base import IOrientationAware
from gimmie_gui import EdgeWindow, AnchoredWindow, TopicRunningList, TopicButton
from gimmie_util import FocusRaiser, NoWindowButton


class GimmieBar:
    '''
    Abstract baseclass for different layout implementations.  Subclasses must
    implement the layout() call.
    '''
    def __init__(self, topic_list, edge_gravity, autohide_anchors, swapbar):
        self.topic_list = topic_list
        self.autohide_anchors = autohide_anchors

        self.edge_window = EdgeWindow(edge_gravity)
        self.layout(edge_gravity, self.edge_window, swapbar)

    def make_spacer(self, edge_gravity, size = 24):
        sep = gtk.EventBox()
        if edge_gravity in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
            sep.set_size_request(-1, size)
        else:
            sep.set_size_request(size, -1)
        sep.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("black"))
        sep.show()
        return sep

    def make_topic_button(self, edge_gravity, topic):
        btn = TopicButton(topic, edge_gravity)
        btn.show()
        return btn

    def make_running_list(self, edge_gravity, topic):
        running_source = topic.get_running_source()
        if isinstance(running_source, IOrientationAware):
            if edge_gravity in (gtk.gdk.GRAVITY_WEST, gtk.gdk.GRAVITY_EAST):
                orientation = gtk.ORIENTATION_VERTICAL
            else:
                orientation = gtk.ORIENTATION_HORIZONTAL
            running_source.set_orientation(orientation)
        running = TopicRunningList(running_source, edge_gravity)
        running.show()
        return running

    def destroy(self):
        self.edge_window.destroy()

    def layout(self, edge_gravity, edge_window, swapbar):
        raise NotImplementedError


class GimmieBarDock(GimmieBar):
    '''
    A GimmieBar with topic\'s running icons or topic buttons arranged on the
    screen edge, with the topic buttons or running icons hovering next to,
    below, or above.
    '''
    def layout(self, edge_gravity, edge_window, swapbar):
        if edge_gravity in [gtk.gdk.GRAVITY_WEST, gtk.gdk.GRAVITY_EAST]:
            # Keep the running items lists all the same width
            anchor_size_group = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)
        else:
            # Keep the running items lists all the same height
            anchor_size_group = gtk.SizeGroup(gtk.SIZE_GROUP_VERTICAL)

        first = True

        for topic in self.topic_list:
            if topic == None:
                edge_window.content.pack_start(self.make_spacer(edge_gravity), False, False, 0)
            else:
                if not first and not swapbar:
                    edge_window.content.pack_start(self.make_spacer(edge_gravity, 1),
                                                   False, False, 0)
                first = False

                # Give some space between topics
                align = gtk.Alignment(xscale=1.0, yscale=1.0)
                if edge_gravity in (gtk.gdk.GRAVITY_WEST, gtk.gdk.GRAVITY_EAST):
                    align.set_property("top-padding", 4)
                    align.set_property("bottom-padding", 4)
                else:
                    align.set_property("top-padding", 1)
                    align.set_property("left-padding", 4)
                    align.set_property("right-padding", 4)

                running_list = self.make_running_list(edge_gravity, topic)
                align.add(running_list)
                align.show()

                if swapbar:
                    running_btn = NoWindowButton()
                else:
                    running_btn = gtk.EventBox()
                running_btn.modify_bg(gtk.STATE_NORMAL, topic.get_hint_color())
                running_btn.add(align)
                running_btn.show()

                drag_flags = gtk.DEST_DEFAULT_DROP | gtk.DEST_DEFAULT_MOTION
                
                if topic.accept_drops():
                    drag_flags |= gtk.DEST_DEFAULT_HIGHLIGHT

                running_btn.drag_dest_set(drag_flags,
                                          [("text/uri-list", 0, 100)],
                                          gtk.gdk.ACTION_COPY)
                           
                running_btn.connect("drag-data-received",
                                    self._drag_data_received,
                                    topic.get_running_source())
                
                if not swapbar:
                    ev_box = gtk.EventBox()
                    ev_box.add(running_btn)
                    ev_box.show()

                # Topic button, opens the topic window
                topic_btn = self.make_topic_button(edge_gravity, topic)
                if swapbar:
                    edge_window.content.pack_start(topic_btn, True, True, 0)
                else:
                    edge_window.content.pack_start(ev_box, True, True, 0)

                if swapbar:
                    anchor_win = AnchoredWindow(edge_gravity, topic_btn)
                    anchor_win.content.pack_start(running_btn, True, True, 0)
                else:
                    anchor_win = self.make_anchor_win(topic_btn, running_btn, edge_gravity)
                # Keep the running items lists all the same height or width
                anchor_size_group.add_widget(anchor_win)

                sizing_type = gtk.SIZE_GROUP_HORIZONTAL # Manage widths
                if edge_gravity in (gtk.gdk.GRAVITY_WEST, gtk.gdk.GRAVITY_EAST):
                    sizing_type = gtk.SIZE_GROUP_VERTICAL # Manage heights

                # Using a sizing group to ensure the edge buttons will be as
                # large as possible.
                self.size_group = gtk.SizeGroup(sizing_type)
                self.size_group.add_widget(running_btn)
                self.size_group.add_widget(topic_btn)

                # Avoid showing anchored window too early
                if not self.autohide_anchors:
                    edge_window.connect_after("show", lambda x, aw: aw.show(), anchor_win)
                edge_window.connect("destroy", lambda x, aw: aw.destroy(), anchor_win)

                if swapbar:
                    raiser = FocusRaiser(topic_btn, anchor_win)
                else:
                    raiser = FocusRaiser(running_btn, anchor_win)
                raiser.set_gravity(edge_gravity)
                raiser.set_hide_on_lower(self.autohide_anchors)

	if not swapbar:
            self.setup_edge_win(edge_window, edge_gravity)

        # Shows everything (including anchor windows)
        edge_window.show()

    def setup_edge_win(self, edge_window, edge_gravity):
        align = edge_window.get_content_alignment()
        # 1px on either non-edge side
        if edge_gravity in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
            if self.autohide_anchors:
                if edge_gravity == gtk.gdk.GRAVITY_EAST:
                    align.set_property("left-padding", 1)
                elif edge_gravity == gtk.gdk.GRAVITY_WEST:
                    align.set_property("right-padding", 1)
            align.set_property("top-padding", 1)
            align.set_property("bottom-padding", 1)
        else:
            if self.autohide_anchors:
                if edge_gravity == gtk.gdk.GRAVITY_NORTH:
                    align.set_property("bottom-padding", 1)
                elif edge_gravity == gtk.gdk.GRAVITY_SOUTH:
                    align.set_property("top-padding", 1)
            align.set_property("left-padding", 1)
            align.set_property("right-padding", 1)

        # Use a black border
        edge_window.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("black"))

    def make_anchor_win(self, topic_btn, running_btn, edge_gravity):
        # Protect the topic button from the black window bg
        ev_box = gtk.EventBox()
        ev_box.add(topic_btn)
        ev_box.show()

        anchor_win = AnchoredWindow(edge_gravity, running_btn)
        anchor_win.content.pack_start(ev_box, True, True, 0)
        # Use a black border
        anchor_win.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("black"))

        align = anchor_win.get_content_alignment()
        # 1px on either non-edge side
        if edge_gravity in (gtk.gdk.GRAVITY_EAST, gtk.gdk.GRAVITY_WEST):
            if edge_gravity == gtk.gdk.GRAVITY_EAST:
                align.set_property("left-padding", 1)
            elif edge_gravity == gtk.gdk.GRAVITY_WEST:
                align.set_property("right-padding", 1)
            align.set_property("top-padding", 1)
            align.set_property("bottom-padding", 1)
        else:
            if edge_gravity == gtk.gdk.GRAVITY_NORTH:
                align.set_property("bottom-padding", 1)
            elif edge_gravity == gtk.gdk.GRAVITY_SOUTH:
                align.set_property("top-padding", 1)
            align.set_property("left-padding", 1)
            align.set_property("right-padding", 1)

        return anchor_win

    def _drag_data_received(self, widget, context, x, y, selection, target_type, time,
                            running_source):
        running_source.handle_drag_data_received(selection, target_type)
