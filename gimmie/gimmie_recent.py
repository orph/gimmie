
import datetime
import os
import urllib
import time
from gettext import gettext as _

import gobject
import gtk

from gimmie_base import Item, ItemSource


#
# egg.Recent and gtk.RecentManager integration.
#

class RecentlyUsedManager(ItemSource):
    def __init__(self):
        ItemSource.__init__(self)

    def add(self, uri, mimetype, groups = None, timestamp = None):
        assert uri, "Must specify recent URI"
        assert mimetype, "Must specify recent URI's mimetype"

        if not timestamp:
            timestamp = int(time.time())
        recent_item = Item(uri=uri, mimetype=mimetype, tags=groups, timestamp=timestamp)
        self.add_item(recent_item)

    def add_item(self, item):
        raise NotImplementedError

    def get_item(self, uri):
        raise NotImplementedError


class RecentlyUsedManagerGtk(RecentlyUsedManager):
    def __init__(self):
        RecentlyUsedManager.__init__(self)
        self.recent_manager = gtk.recent_manager_get_default()
        self.recent_manager.set_limit(-1)

        self.recent_manager.connect("changed", lambda m: self.emit("reload"))

    def get_items_uncached(self):
        for info in self.recent_manager.get_items():
            if not info.get_private_hint():
                yield Item(name=info.get_display_name(),
                           uri=info.get_uri(),
                           mimetype=info.get_mime_type(),
                           timestamp=info.get_modified(),
                           tags=info.get_groups())

    def add_item(self, item):
        assert isinstance(item, Item), "argument must be an Item instance"

        recent_dict = { "app_name" : "gimmie",
                        "app_exec" : "gimmie",
                        "mime_type" : item.get_mimetype(),
                        "groups" : item.get_tags() + ["GimmieWasHere"],
                        "visited" : item.get_timestamp()
                       }
        self.recent_manager.add_full(item.get_uri(), recent_dict)

    def get_item(self, uri):
        # Usually, we're given a file path, but maybe not always
        if uri[0] == '/':
            uri = 'file://' + uri

        try:
            info = self.recent_manager.lookup_item(uri)
            return Item(name=info.get_display_name(),
                        uri=info.get_uri(),
                        mimetype=info.get_mime_type(),
                        timestamp=info.get_modified(),
                        tags=info.get_groups())
        except gobject.GError:
            raise KeyError, uri


class RecentlyUsedManagerEgg(RecentlyUsedManager):
    def __init__(self):
        RecentlyUsedManager.__init__(self)
        self.recent_model = egg.recent.RecentModel()
        # FIXME: EggRecentModel only sends changes if item limit is set
        self.recent_model.set_limit(1000000)

        self.recent_items = {}
        self.recent_model.connect("changed", lambda m, list: self.emit("reload"))

    def get_items_uncached(self):
        self.recent_items = {}
        for info in self.recent_model.get_list():
            item = Item(uri=info.get_uri(),
                        mimetype=info.get_mime_type(),
                        timestamp=info.get_timestamp(),
                        tags=info.get_groups())
            self.recent_items[item.get_uri()] = item
            yield item

    def get_item(self, uri):
        # Usually, we're given a file path, but maybe not always
        if uri[0] == '/':
            uri = 'file://' + uri
        return self.recent_items[uri]

    def add_item(self, item):
        # FIXME: Work around egg recent not signalling for in-process adds.
        self.recent_items[item.get_uri()] = item

        recent_item = egg.recent.RecentItem(item.get_uri())
        recent_item.set_mime_type(item.get_mimetype())
        recent_item.set_timestamp(item.get_timestamp() or int(time.time()))
        recent_item.add_group("GimmieWasHere")
        for tag in item.get_tags():
            recent_item.add_group(tag)
        
        self.recent_model.add_full(self, recent_item)


class RecentlyUsed(ItemSource):
    '''
    Recently-used documents, log stored in ~/.recently-used.
    '''
    def __init__(self, name, icon = "stock_calendar"):
        ItemSource.__init__(self, name=name, icon=icon)
        recent_model.connect("reload", lambda m: self.emit("reload"))

    def get_items_uncached(self):
        for item in recent_model.get_items():
            # Check whether to include this item
            if self.include_item(item):
                yield item

    def include_item(self, item):
        return True


class RecentlyUsedOfMimeType(RecentlyUsed):
    '''
    Recently-used items filtered by a set of mimetypes.
    '''
    def __init__(self, name, icon, mimetype_list):
        RecentlyUsed.__init__(self, name, icon)
        self.mimetype_list = mimetype_list

    def include_item(self, item):
        item_mime = item.get_mimetype()
        for mimetype in self.mimetype_list:
            if hasattr(mimetype, "match") and mimetype.match(item_mime) \
                   or item_mime == mimetype:
                return True
        return False


class RecentAggregate(ItemSource):
    '''
    This ItemSource subclass aggregates all the items from a list of
    ItemSources, by including the first Item encountered of a URI and
    filtering duplicates.
    '''
    def __init__(self, sources, name = _("Recently Used"), icon = "stock_calendar"):
        ItemSource.__init__(self, name=name, icon=icon)

        # Sources provide the real items we will display
        self.sources = sources
        for source in self.sources:
            self._listen_to_source(source)

    def _listen_to_source(self, source):
        source.connect("reload", lambda x: self.emit("reload"))

    def get_items_uncached(self):
        item_uris = {}

        # Find items matching recent uris
        for source in self.sources:
            for item in source.get_items_uncached():
                uri = item.get_uri()
                # Block special items the source might include like "Create
                # New Note" and avoid duplicate items for the same URI.
                if not item.is_special() and uri and uri not in item_uris:
                    item_uris[uri] = item
                    yield item


#
# Globals
#

if gtk.gtk_version[1] >= 10:
    ### gtk.RecentManager is only available in >= GTK+ 2.10.
    recent_model = RecentlyUsedManagerGtk()
else:
    ### GTK isn't new enough, go with the libegg code.
    import egg.recent
    recent_model = RecentlyUsedManagerEgg()
