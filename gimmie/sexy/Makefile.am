INCLUDES = $(PYTHON_INCLUDES) $(GIMMIE_CFLAGS)

_sexydir = $(pyexecdir)/gimmie/sexy

_sexy_PYTHON = __init__.py

_sexy_LTLIBRARIES = _sexy.la
_sexy_la_CFLAGS = $(GIMMIE_CFLAGS)
_sexy_la_LDFLAGS = -module -avoid-version -export-symbols-regex init_sexy
_sexy_la_LIBADD = $(GIMMIE_LIBS)
_sexy_la_SOURCES = \
	sexymodule.c \
	libsexy/sexy-enum-types.c \
	libsexy/sexy-enum-types.h \
	libsexy/sexy-icon-entry.c \
	libsexy/sexy-icon-entry.h \
	libsexy/sexy-tooltip.c \
	libsexy/sexy-tooltip.h

nodist__sexy_la_SOURCES = sexy.c

CLEANFILES = sexy.c
EXTRA_DIST = sexy.defs sexy.override gen-defs.sh
sexy.c: sexy.defs sexy.override

.defs.c:
	(cd $(srcdir) \
	 && $(PYGTK_CODEGEN) \
	    --override $*.override \
	    --register $(PYGTK_DEFSDIR)/gtk-types.defs \
	    --register $(PYGTK_DEFSDIR)/gdk-types.defs \
	    --prefix py$* $*.defs) > gen-$*.c \
	&& cp gen-$*.c $*.c \
	&& rm -f gen-$*.c

