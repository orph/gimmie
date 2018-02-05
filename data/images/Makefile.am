
pixmapdir = $(datadir)/pixmaps
pixmap_DATA = gimmie.png

hicolordir = $(datadir)/icons/hicolor

tango_icons = 				\
	gimmie-16.png			\
	gimmie-32.png			\
	gimmie.png			\
	gimmie.svg

install-data-local:
	@-$(mkinstalldirs) $(DESTDIR)$(hicolordir)/16x16/apps
	$(INSTALL_DATA) $(srcdir)/gimmie-16.png $(DESTDIR)$(hicolordir)/16x16/apps/gimmie.png
	@-$(mkinstalldirs) $(DESTDIR)$(hicolordir)/32x32/apps
	$(INSTALL_DATA) $(srcdir)/gimmie-32.png $(DESTDIR)$(hicolordir)/32x32/apps/gimmie.png
	@-$(mkinstalldirs) $(DESTDIR)$(hicolordir)/48x48/apps
	$(INSTALL_DATA) $(srcdir)/gimmie.png $(DESTDIR)$(hicolordir)/48x48/apps/gimmie.png
	@-$(mkinstalldirs) $(DESTDIR)$(hicolordir)/scalable/apps
	$(INSTALL_DATA) $(srcdir)/gimmie.svg $(DESTDIR)$(hicolordir)/scalable/apps/gimmie.svg

gtk_update_icon_cache = gtk-update-icon-cache -f -t $(datadir)/icons/hicolor

install-data-hook:
	@-if test -z "$(DESTDIR)"; then \
		echo "Updating Gtk icon cache."; \
		$(gtk_update_icon_cache); \
	else \
		echo "*** Icon cache not updated.  After install, run this:"; \
		echo "***   $(gtk_update_icon_cache)"; \
	fi

uninstall-hook:
	rm -f $(DESTDIR)$(hicolordir)/scalable/apps/gimmie.svg
	rm -f $(DESTDIR)$(hicolordir)/16x16/apps/gimmie.png
	rm -f $(DESTDIR)$(hicolordir)/32x32/apps/gimmie.png
	rm -f $(DESTDIR)$(hicolordir)/48x48/apps/gimmie.png

noinst_DATA = gimmie-128.png

EXTRA_DIST = $(noinst_DATA) $(pixmap_DATA) $(tango_icons)
