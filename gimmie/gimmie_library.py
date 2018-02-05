
import glob
import os
import re
import shutil
import sys
from gettext import gettext as _
from xml.dom.minidom import parse
from xml.parsers.expat import ExpatError

import gtk

from gimmie_globals import gimmie_is_panel_applet
from gimmie_base import Item, ItemSource, Topic, gimmie_get_topic_for_uri
from gimmie_file import FileItem
from gimmie_recent import RecentlyUsedOfMimeType, RecentAggregate
from gimmie_util import *
from gimmie_trash import trash_monitor
from gimmie_computer import DriveItem
from gimmie_tomboy import tomboy_source


#
# Sidebar ItemSources
#

class DirectorySource(ItemSource):
    def __init__(self, path, name = None, icon = "stock_folder"):
        self.path = os.path.expanduser(path)

        if not name:
            name = os.path.basename(self.path).decode(sys.getfilesystemencoding(), "replace")
        ItemSource.__init__(self, name=name, icon=icon)

        self.monitor = FileMonitor(self.path)
        self.monitor.connect("event", lambda m, uri, ev: self.emit("reload"))
        self.monitor.open()

    def get_enabled(self):
        return os.path.exists(self.path)

    def _add_name(self, paths, dirname, names):
        for name in names:
            paths.append(os.path.join(dirname, name))

    def get_items_uncached(self):
        paths = []
        os.path.walk(self.path, self._add_name, paths)
        for path in paths:
            yield FileItem(path)


class EpiphanyDownloadsSource(ItemSource):
    def __init__(self, name = "Epiphany Downloads"):
        ItemSource.__init__(self, name=name)

        self.ephy_directory_source = None
        self.ephy_gconf_bridge = GConfBridge("/apps/epiphany/directories/")
        self.ephy_gconf_bridge.connect("changed::downloads_folder",
                                       lambda gb: self._ephy_downloads_folder_changed())
        self._ephy_downloads_folder_changed()

    def _ephy_downloads_folder_changed(self):
        dir = self.ephy_gconf_bridge.get("downloads_folder", "")
        if not dir:
            return

        self.ephy_directory_source = DirectorySource(dir)
        self.ephy_directory_source.connect("reload", lambda x: self.emit("reload"))
        self.emit("reload") # Notify listeners

    def get_enabled(self):
        return self.ephy_directory_source and self.ephy_directory_source.get_enabled()

    def get_items(self):
        if self.ephy_directory_source:
            for item in self.ephy_directory_source.get_items():
                yield item


class MozillaDownloadsSource(ItemSource):
    def __init__(self, name = "Mozilla Downloads", icon = None):
        ItemSource.__init__(self, name=name, icon=icon)
        self.download_rdf_monitors = {}

    def get_download_rdf_paths(self):
        '''
        Returns a list of paths to Mozilla downloads.rdf files.  It only returns
        files in the "default" profile, to avoid porn.  Maybe this should be
        revisited.
        '''
        return glob.glob(os.path.expanduser("~/.mozilla/*/*default*/downloads.rdf"))

    def get_enabled(self):
        if not self.download_rdf_monitors:
            self._monitor_download_rdf_paths()
        return len(self.download_rdf_monitors) > 0

    def _monitor_download_rdf_paths(self):
        for download_rdf in self.get_download_rdf_paths():
            if not self.download_rdf_monitors.has_key(download_rdf):
                # Emit reload on download.rdf change
                mon = FileMonitor(download_rdf)
                mon.connect("event", lambda m, uri, ev: self.emit("reload"))
                mon.open()
                self.download_rdf_monitors[download_rdf] = mon

    def get_items_uncached(self):
        if not self.download_rdf_monitors:
            self._monitor_download_rdf_paths()

        for download_rdf in self.download_rdf_monitors:
            try:
                # Read previous download locations
                download_doc = parse(download_rdf)
                li_list = download_doc.getElementsByTagName("RDF:li")

                for li_elem in li_list:
                    uri = str(li_elem.getAttribute("RDF:resource"))
                    # Sometimes contains absolute paths instead of URLs
                    if os.path.isabs(uri):
                        uri = "file://" + uri

                    yield FileItem(uri)
            except (IOError, ExpatError), err:
                print " !!! Error parsing Mozilla download file '%s': %s" % (download_rdf, err)


class ThunderbirdAttachmentsSource(MozillaDownloadsSource):
    '''
    A MozillaDownloadsSource subclass that reads Thunderbird downloads.rdf files.
    '''
    def __init__(self):
        MozillaDownloadsSource.__init__(self, name=_("Attachments"), icon="stock_attach")

    def get_download_rdf_paths(self):
        '''Returns a list of paths to Mozilla Thunderbird downloads.rdf files.'''
        return glob.glob(os.path.expanduser("~/.*thunderbird/*/downloads.rdf"))


class DownloadsSource(RecentAggregate):
    '''
    Aggregate ItemSource subclass that lists files from: ~/Downloads,
    Mozilla/Firefox downloads.rdf files, and the Epiphany download directory.
    '''
    def __init__(self, name = _("Downloads"), icon = "stock_internet"):
        moz_source = MozillaDownloadsSource()
        ephy_source = EpiphanyDownloadsSource()

        if os.environ.has_key("DOWNLOAD_PATH"):
            path = os.environ["DOWNLOAD_PATH"]
        else:
            path = "~/Downloads"
        download_dir_source = DirectorySource(path)

        RecentAggregate.__init__(self,
                                 name=name,
                                 icon=icon,
                                 sources=[moz_source, ephy_source, download_dir_source])


class RecentlyUsedDocumentsSource(RecentlyUsedOfMimeType):
    ### FIXME: This is lame, we should generate this list somehow.
    DOCUMENT_MIMETYPES = [
        # Covers:
        #   vnd.corel-draw
        #   vnd.ms-powerpoint
        #   vnd.ms-excel
        #   vnd.oasis.opendocument.*
        #   vnd.stardivision.*
        #   vnd.sun.xml.*
        re.compile("application/vnd.*"),
        # Covers: x-applix-word, x-applix-spreadsheet, x-applix-presents
        re.compile("application/x-applix-*"),
        # Covers: x-kword, x-kspread, x-kpresenter, x-killustrator
        re.compile("application/x-k(word|spread|presenter|illustrator)"),
        re.compile("text/*"),
        re.compile("image/*"),
        "application/ms-powerpoint",
        "application/msword",
        "application/pdf",
        "application/postscript",
        "application/ps",
        "application/rtf",
        "application/x-abiword",
        "application/x-asp",
        "application/x-bittorrent",
        "application/x-blender",
        "application/x-cgi",
        "application/x-dia-diagram",
        "application/x-dvi",
        "application/x-glade",
        "application/x-gnucash",
        "application/x-gnumeric",
        "application/x-iso-image",
        "application/x-jbuilder-project",
        "application/x-magicpoint",
        "application/x-mrproject",
        "application/x-php",
        ]
    
    def __init__(self):
        RecentlyUsedOfMimeType.__init__(self,
                                        name=_("Documents"),
                                        icon="stock_new-presentation",
                                        mimetype_list=self.DOCUMENT_MIMETYPES)

    def get_items_uncached(self):
        for item in RecentlyUsedOfMimeType.get_items_uncached(self):
            yield FileItem(uri=item.get_uri(), timestamp=item.get_timestamp())


class RecentlyUsedMediaSource(RecentlyUsedOfMimeType):
    ### FIXME: This is lame, we should generate this list somehow.
    MEDIA_MIMETYPES = [
        re.compile("video/*"),
        re.compile("audio/*"),
        "application/ogg"
        ]

    def __init__(self):
        RecentlyUsedOfMimeType.__init__(self,
                                        name=_("Music & Movies"),
                                        icon="gnome-mime-video",
                                        mimetype_list=self.MEDIA_MIMETYPES)

    def get_items_uncached(self):
        for item in RecentlyUsedOfMimeType.get_items_uncached(self):
            yield FileItem(uri=item.get_uri(), timestamp=item.get_timestamp())


#
# Toolbar Items
#

class NewFromTemplateDialog(gtk.FileChooserDialog):
    '''
    Dialog to create a new document from a template
    '''
    __gsignals__ = {
        "response" : "override"
        }

    def __init__(self, parent, name, source_uri):
        # Extract the template's file extension
        try:
            self.file_extension = name[name.rindex('.'):]
            name = name[:name.rindex('.')]
        except ValueError:
            self.file_extension = None
        self.source_uri = source_uri

        gtk.FileChooserDialog.__init__(self,
                                       _("New Document"),
                                       parent,
                                       gtk.FILE_CHOOSER_ACTION_SAVE,
                                       (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                        gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT))
        self.set_current_name(name)
        self.set_current_folder(os.path.expanduser("~/Desktop"))
        self.set_do_overwrite_confirmation(True)
        self.set_default_response(gtk.RESPONSE_ACCEPT)

    def do_response(self, response):
        if response == gtk.RESPONSE_ACCEPT:
            file_uri = self.get_filename()

            # Add the file extension back unless the user did themselves
            if self.file_extension and not file_uri.endswith(self.file_extension):
                file_uri = "%s%s" % (self.source_uri, self.file_extension)

            # Create a new document from the template and display it
            try:
                if not self.source_uri:
                    # Create an empty file
                    f = open(file_uri, 'w')
                    f.close()
                else:
                    shutil.copyfile(self.source_uri, file_uri)
                launcher.launch_uri(file_uri)
            except IOError:
                pass

        self.destroy()


class NewDocumentMenuButton(ToolMenuButton):
    def __init__(self, tooltips):
        img = icon_factory.load_image("stock_new-template", gtk.ICON_SIZE_LARGE_TOOLBAR)

        ToolMenuButton.__init__(self, img, _("New Document"))
        self.set_tooltip(tooltips, _("Create a new document"))
        
        # Monitor the templates directory
        self.template_monitor = FileMonitor(os.path.expanduser("~/Templates"))
        self.template_monitor.connect("created", self._template_changed)
        self.template_monitor.connect("deleted", self._template_changed)
        self.template_monitor.open()
        self._template_changed(None, None)

    def _template_changed(self, monitor, uri):
        menu = gtk.Menu()
        self._add_templates(menu)
        self.set_menu(menu)

    def _add_template_item(self, menu, name, uri, icon_name):
        menu_item = gtk.ImageMenuItem(name)
        menu_item.set_image(icon_factory.load_image(icon_name, gtk.ICON_SIZE_LARGE_TOOLBAR))
        menu_item.show()
        menu_item.connect("activate", self._show_new_from_template_dialog, name, uri)
        return menu_item

    def _add_templates(self, menu):
        # Get all the templates
        template_dir = os.path.expanduser("~/Templates")
	try:
        	templates = os.listdir(template_dir)
	except:
		templates = []

        for template in templates:
            item = FileItem(os.path.join(template_dir, template))
            menu.append(self._add_template_item(menu,
                                                item.get_name(),
                                                item.get_uri(),
                                                item.get_icon(gtk.ICON_SIZE_LARGE_TOOLBAR)))
        if len(templates) == 0:
            empty_item = gtk.MenuItem(_("No templates available"))
            empty_item.set_sensitive(False)
            empty_item.show()
            menu.append(empty_item)

        sep = gtk.SeparatorMenuItem()
        sep.show()
        menu.append(sep)

        menu.append(self._add_template_item(menu, _("Empty File"), None, "stock_new"))

        sep = gtk.SeparatorMenuItem()
        sep.show()
        menu.append(sep)

        # Add a link to the templates directory
        mi = gtk.ImageMenuItem(_("Templates"))
        mi.set_image(icon_factory.load_image("gnome-fs-directory", gtk.ICON_SIZE_LARGE_TOOLBAR))
        mi.show()
        mi.connect("activate", lambda mi, uri: launcher.launch_uri(uri), template_dir)
        menu.append(mi)

    def _show_new_from_template_dialog(self, b, name, uri):        
        dlg = NewFromTemplateDialog(b.get_toplevel(), name, uri)
        dlg.show()


class PlacesMenu(gtk.Menu):
    def __init__(self):
        gtk.Menu.__init__(self)

        # Include all the mounted drives
        computer = gimmie_get_topic_for_uri("topic://Computer")
        device_source = computer.get_source_for_uri("source://Devices")
        for item in device_source.get_items():
            if isinstance(item, DriveItem) and item.get_is_mounted():
                self.append(self._add_place_item(item.get_name(),
                                                 item.get_uri(),
                                                 item.get_icon(gtk.ICON_SIZE_LARGE_TOOLBAR)))

        sep = gtk.SeparatorMenuItem()
        sep.show()
        self.append(sep)

        # Include all the Gtk bookmarks
        for uri, name, mime, icon in places.get_places():
            self.append(self._add_place_item(name, uri, icon))

        sep = gtk.SeparatorMenuItem()
        sep.show()
        self.append(sep)

        # Add the trash
        if trash_monitor.is_empty():
            self.append(self._add_place_item(_("Trash"), "trash://", "gnome-fs-trash-empty"))
        else:
            self.append(self._add_place_item(_("Trash"), "trash://", "gnome-fs-trash-full"))

    def _add_place_item(self, name, uri, icon_name = "gnome-fs-directory"):
        menu_item = gtk.ImageMenuItem(name)
        menu_item.set_image(icon_factory.load_image(icon_name, gtk.ICON_SIZE_LARGE_TOOLBAR))
        menu_item.show()
        menu_item.connect("activate", lambda mi, uri: launcher.launch_uri(uri), uri)
        return menu_item


class PlacesMenuButton(ToolMenuButton):
    def __init__(self, tooltips):
        img = icon_factory.load_image("gnome-fs-bookmark", gtk.ICON_SIZE_LARGE_TOOLBAR)
        ToolMenuButton.__init__(self, img, _("Places"))
        self.set_tooltip(tooltips, _("Open commonly used locations"))
        self.set_menu(PlacesMenu())


class TrashButton(gtk.ToolButton):
    def __init__(self, tooltips):
        img = icon_factory.load_image("gnome-fs-trash-full", gtk.ICON_SIZE_LARGE_TOOLBAR)
        gtk.ToolButton.__init__(self, img, _("Trash"))
        self.set_tooltip(tooltips, _("Open the deleted files trashcan"))
        self.connect("clicked", lambda x: launcher.launch_uri("trash://"))


class PrintersMenuButton(gtk.ToolButton):
    __gsignals__ = {
        "clicked" : "override"
        }

    def __init__(self, tooltips):
        img = icon_factory.load_image(gtk.STOCK_PRINT, gtk.ICON_SIZE_LARGE_TOOLBAR)
        gtk.ToolButton.__init__(self, img, _("Printers"))
        self.set_tooltip(tooltips, _("View printers available for document printing"))

    def do_clicked(self):
        topic = gimmie_get_topic_for_uri("topic://Computer")
        topicwin = topic.get_topic_window()
        topicwin.set_source_by_uri("source://Printers")
        topicwin.present()


#
# Topic Implementation
#

class DocumentsTopic(Topic):
    '''
    Lists recently opened/edited documents from ~/.recently-used, and some other
    categories of files such as movies and music.  Placeholders for recent email
    attachments, marked emails, and browser downloads.  In the future categories
    displayed should be pluggable.
    '''
    def __init__(self):
        Topic.__init__(self,
                       _("Library"),
                       uri="topic://Documents",
                       icon="stock_new-template")

        from gimmie_running import RunningDocuments
        self.set_running_source_factory(lambda: RunningDocuments())

    def do_reload(self):
        source_list = [None,
                       RecentlyUsedDocumentsSource(),
                       tomboy_source, # Tomboy
                       RecentlyUsedMediaSource(),
                       None,
                       DownloadsSource()]

        attachments = ThunderbirdAttachmentsSource()
        if attachments.get_enabled():
            source_list.append(attachments)

        source_list.insert(0, RecentAggregate(sources=[x for x in source_list if x]))

        self.set_sidebar_source_list(source_list)

    def get_hint_color(self):
        return gtk.gdk.color_parse("lightgreen")

    def get_toolbar_items(self, tooltips):
        tools = []

        btn = NewDocumentMenuButton(tooltips)
        btn.set_is_important(True)
        tools.append(btn)

        btn = PlacesMenuButton(tooltips)
        btn.set_is_important(True)
        tools.append(btn)

        ### Uncomment to include a trashcan in the toolbar
        #btn = TrashButton(tooltips)
        #btn.set_is_important(True)
        #tools.append(btn)

        if not gimmie_is_panel_applet():
            tools.append(None) # Spacer
            btn = PrintersMenuButton(tooltips)
            btn.set_is_important(True)
            tools.append(btn)

        return tools
