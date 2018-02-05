
SUBDIRS = images


serverdir       = $(PANELAPPLET_SERVER_DIR)
server_in_files = GNOME_GimmieApplet.server.in
server_DATA     = $(server_in_files:.server.in=.server)

$(server_in_files): $(server_in_files:.server.in=.server.in.in) Makefile
	sed -e "s|\@libexecdir\@|$(libexecdir)|g" \
	   < $< > $@

@INTLTOOL_SERVER_RULE@


schemasdir	 = $(GCONF_SCHEMA_FILE_DIR)
schemas_in_files = gimmie.schemas.in
schemas_DATA     = $(schemas_in_files:.schemas.in=.schemas)

@INTLTOOL_SCHEMAS_RULE@

if GCONF_SCHEMAS_INSTALL
install-data-local:
	GCONF_CONFIG_SOURCE=$(GCONF_SCHEMA_CONFIG_SOURCE) \
	$(GCONFTOOL) --makefile-install-rule $(schemas_DATA)
endif


uidir   = $(datadir)/gnome-2.0/ui
ui_DATA	= GNOME_GimmieApplet.xml


EXTRA_DIST = 				\
	GNOME_GimmieApplet.server.in.in \
	$(schemas_in_files)     	\
	$(ui_DATA)

DISTCLEANFILES = 		\
	$(schemas_DATA)		\
	$(server_in_files) 	\
	$(server_DATA)
