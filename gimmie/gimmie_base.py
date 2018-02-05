
import datetime
import time
from gettext import ngettext, gettext as _
from xml.sax import saxutils

import gobject
import gtk

from gimmie_util import Thumbnailer, bookmarks, icon_factory, launcher


#
# Base classes used by all topics
#

class Item(gobject.GObject):
    __gsignals__ = {
        "reload" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        "open" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        }

    def __init__(self,
                 uri = None,
                 name = None,
                 comment = None,
                 timestamp = 0,
                 mimetype = None,
                 icon = None,
                 special = False,
                 tags = None):
        gobject.GObject.__init__(self)
        self.uri = uri
        self.name = name
        self.comment = comment
        self.timestamp = timestamp
        self.mimetype = mimetype
        self.icon = icon
        self.special = special
        self.tags = tags or []
        self.thumbnailer = None

    def get_demands_attention(self):
        return False

    def get_icon(self, icon_size):
        if self.icon:
            return icon_factory.load_icon(self.icon, icon_size)

        if not self.thumbnailer:
            self.thumbnailer = Thumbnailer(self.get_uri(), self.get_mimetype())
        return self.thumbnailer.get_icon(icon_size, self.get_timestamp())

    def get_timestamp(self):
        return self.timestamp

    def get_mimetype(self):
        return self.mimetype

    def get_uri(self):
        return self.uri

    def get_name(self):
        return self.name or self.get_uri()

    def get_comment(self):
        return self.comment

    def get_name_markup(self):
        name = saxutils.escape(self.get_name() or "")
        if self.get_is_pinned():
            name += " <span foreground='red'>&#x2665;</span>"
        return name

    def get_comment_markup(self):
        return "<span foreground='darkgrey'>%s</span>" % \
               saxutils.escape(self.get_comment() or "")

    def do_open(self):
        uri_to_open = self.get_uri()
        if uri_to_open:
            self.timestamp = time.time()
            launcher.launch_uri(uri_to_open, self.get_mimetype())
        else:
            print " !!! Item has no URI to open: %s" % self

    def open(self):
        self.emit("open")

    def get_is_user_visible(self):
        return True

    def get_is_opened(self):
        return False

    def get_is_active(self):
        return False

    def get_can_pin(self):
        return self.get_uri() != None

    def get_is_pinned(self):
        return bookmarks.is_bookmark(self.get_uri())

    def pin(self):
        bookmarks.add_bookmark_item(self)
        self.emit("reload")

    def unpin(self):
        bookmarks.remove_bookmark(self.get_uri())
        self.emit("reload")

    def set_screen_position(self, x, y, w, h):
        pass

    def matches_text(self, text):
        name = self.get_name()
        comment = self.get_comment()
        return (name and name.lower().find(text) > -1) or \
               (comment and comment.lower().find(text) > -1)

    def populate_popup(self, menu):
        open = gtk.ImageMenuItem (gtk.STOCK_OPEN)
        open.connect("activate", lambda w: self.open())
        open.show()
        menu.append(open)

        fav = gtk.CheckMenuItem (_("Add to Favorites"))
        fav.set_sensitive(self.get_can_pin())
        fav.set_active(self.get_is_pinned())
        fav.connect("toggled", self._add_to_favorites_toggled)
        fav.show()
        menu.append(fav)

    def _add_to_favorites_toggled(self, fav):
        if fav.get_active():
            self.pin()
        else:
            self.unpin()

    def get_tooltip(self):
        return self.get_name()

    def pretty_print_time_since(self, timestamp, include_today = True):
        '''
        Format a timestamp in a readable way (for English).
        '''
        now = datetime.datetime.now()
        then = datetime.datetime.fromtimestamp(timestamp)
        if then.year == now.year:
            then_ord = then.toordinal()
            now_ord = now.toordinal()
            time_str = then.strftime(_("%l:%M %p"))
            if then_ord == now_ord:
                if include_today:
                    return _("Today, %s") % time_str
                else:
                    return time_str
            elif then_ord == now_ord - 1:
                return _("Yesterday, %s") % time_str
            elif then_ord > now_ord - 4:
                return ngettext("%d day ago, %s",
                                "%d days ago, %s",
                                now_ord - then_ord) % (now_ord - then_ord, time_str)
            elif then_ord > now_ord - 6:
                return ngettext("%d day ago",
                                "%d days ago",
                                now_ord - then_ord) % (now_ord - then_ord)
            else:
                return then.strftime(_("%B %e"))
        else:
            return then.strftime(_("%B %e, %G"))

    def handle_drag_data_received(self, selection, target_type):
        pass

    def is_special(self):
        '''
        Special items are always displayed when browsing an ItemSource,
        regardless of the active date filter.  Usually special items denote
        meta-tasks such as configuring or creating other items.
        '''
        return self.special

    def get_tags(self):
        '''Returns a dictionary of tags for this Item.'''
        return self.tags

    def add_tag(self, tag):
        '''Adds a tag for this Item.  Emits "reload".'''
        assert isinstance(tag, str), "Tag must be a string"

        if tag not in self.tags:
            self.tags.append(tag)
            self.emit("reload")

    def has_tag(self, tag):
        assert isinstance(tag, str), "Tag must be a string"
        return tag in self.tags

    def remove_tag(self, tag):
        '''Removes a tag for this Item.  Emits "reload".'''
        assert isinstance(tag, str), "Tag must be a string"

        if tag in self.tags:
            self.tags.remove(tag)
            self.emit("reload")


class ItemSource(Item):
    # Clear cached items after 4 minutes of inactivity
    CACHE_CLEAR_TIMEOUT_MS = 1000 * 60 * 4
    
    def __init__(self,
                 name = None,
                 icon = None,
                 comment = None,
                 uri = None,
                 filter_by_date = True):
        Item.__init__(self,
                      name=name,
                      icon=icon,
                      comment=comment,
                      uri=uri,
                      mimetype="gimmie/item-source")
        self.filter_by_date = filter_by_date
        self.items = None
        self.clear_cache_timeout_id = None

        # Clear cached items on reload
        self.connect("reload", lambda x: self.set_items(None))

    def get_items(self):
        '''
        Return cached items if available, otherwise get_items_uncached() is
        called to create a new cache, yielding each result along the way.  A
        timeout is set to invalidate the cached items to free memory.
        '''
        if self.clear_cache_timeout_id:
            gobject.source_remove(self.clear_cache_timeout_id)
        self.clear_cache_timeout_id = gobject.timeout_add(ItemSource.CACHE_CLEAR_TIMEOUT_MS,
                                                          lambda: self.set_items(None))

        if self.items:
            for i in self.items:
                yield i
        else:
            items = []
            for i in self.get_items_uncached():
                items.append(i)
                yield i

            # Only cache results once we've successfully yielded all items
            self.set_items(items)

    def get_items_uncached(self):
        '''Subclasses should override this to return/yield Items. The results
        will be cached.'''
        return []

    def set_items(self, items):
        '''Set the cached items.  Pass None for items to reset the cache.'''
        self.items = items

    def get_enabled(self):
        return True

    def get_filter_by_date(self):
        '''False if consumers should avoid using timestamps to filter items, True otherwise.'''
        return self.filter_by_date


class DisabledItemSource(ItemSource):
    def __init__(self, name, icon=None, uri=None):
        ItemSource.__init__(self, name=name, icon=icon, uri=uri)

    def get_enabled(self):
        return False


class IOrientationAware:
    def get_orientation(self):
        raise NotImplementedError

    def set_orientation(self, orientation):
        raise NotImplementedError


class Topic(gobject.GObject):
    __gsignals__ = {
        "reload" : (gobject.SIGNAL_RUN_FIRST,
                    gobject.TYPE_NONE,
                    ())
        }
    
    def __init__(self, name, uri = None, icon = None):
        gobject.GObject.__init__(self)
        self.name = name
        self.label = None
        self.uri = uri
        self.icon = icon
        self.topic_window = None
        
        self.running_source = None
        self.sidebar_sources = None

        if uri:
            # Add to the global Topic list
            gimmie_topics.append(self)

    def do_reload(self):
        pass # Do nothing

    def accept_drops(self):
        return True
    
    def get_name(self):
        return self.name

    def get_uri(self):
        return self.uri

    def get_icon(self, icon_size):
        if self.icon:
            return icon_factory.load_icon(self.icon, icon_size)
        return None

    def get_button_content(self, edge_gravity):
	self.label = gtk.Label(self.get_name())

        if edge_gravity == gtk.gdk.GRAVITY_EAST:
            self.label.set_property("angle", 90)
            self.label.set_padding(0, 12)
        elif edge_gravity == gtk.gdk.GRAVITY_WEST:
            self.label.set_property("angle", 270)
            self.label.set_padding(0, 12)
        else:
            self.label.set_padding(12, 0)

	return self.label

    def get_hint_color(self):
        raise NotImplementedError

    def get_sidebar_source_list(self):
        if not self.sidebar_sources:
            self.do_reload()
        return self.sidebar_sources or []

    def set_sidebar_source_list(self, sources):
        # FIXME: Emit reload on source reload?
        self.sidebar_sources = sources

    def get_running_source(self):
        if callable(self.running_source):
            self.running_source = self.running_source()

            ### Uncomment to show topic label as bold/italic if a running item
            ### needs attention.
            #self.running_source.connect("reload", lambda x: self._on_source_reload())
        return self.running_source

    def set_running_source_factory(self, factory_cb):
        assert callable(factory_cb)
        self.running_source = factory_cb

    def _on_source_reload(self, item = None):
        # Look for an item with urgency, update the label widget text
        if self.label:
            for item in self.running_source.get_items():
                if isinstance(item, Item) and item.get_demands_attention():
                    text = self.label.get_text() # Strips existing markup
                    text = "<b><i>%s</i></b>" % text # Make the label bold/italic
                    self.label.set_markup(text)
                    break

    def get_toolbar_items(self, tooltips):
        raise NotImplementedError

    def get_context_menu_items(self):
        return []
 
    def find_items(self, text):
        '''This does an AND search of all the words in the text arg'''
        words = text.lower().strip().split()
        if not words:
            return

        matches = []
        match_uris = []

        for source in self.get_sidebar_source_list():
            if isinstance(source, ItemSource): # Skip spacer elements
                for item in source.get_items():
                    uri = item.get_uri()
                    if item in matches or (uri and uri in match_uris):
                        continue

                    # Match all words
                    for word in words:
                        if not item.matches_text(word):
                            break
                    else:
                        matches.append(item)
                        match_uris.append(uri)
                        yield item

    def get_topic_window(self):
        # FIXME: Hack around rescursive import
        from gimmie_topicwin import TopicWindow
        
        if not self.topic_window:
            self.topic_window = TopicWindow(self)
        return self.topic_window

    def get_source_for_uri(self, uri):
        for source in self.get_sidebar_source_list():
            if isinstance(source, Item) and source.get_uri() == uri:
                return source
        return None



#
# Globals
#

gimmie_topics = []

def gimmie_get_topic_for_uri(uri):
    for topic in gimmie_topics:
        if topic.get_uri() == uri:
            return topic
    return None

