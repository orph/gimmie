## Process this file with automake to produce Makefile.in
INCLUDES = $(PYTHON_INCLUDES) $(GIMMIE_CFLAGS) -DEGG_COMPILATION

_eggdir = $(pyexecdir)/gimmie/traymanager
_egg_LTLIBRARIES = _egg.la
_egg_PYTHON = __init__.py
_egg_la_LDFLAGS = -module -avoid-version -export-symbols-regex init_egg
_egg_la_LIBADD = $(GIMMIE_LIBS)
#_egg_la_CFLAGS = $(PYTHON_INCLUDES) $(GIMMIE_CFLAGS) -DEGG_COMPILATION
_egg_la_SOURCES =		\
	eggtraymanager.c	\
	eggtraymanager.h	\
	eggmarshalers.c		\
	eggmarshalers.h		\
	_eggmodule.c

nodist__egg_la_SOURCES = _egg.c

CLEANFILES = _egg.c
EXTRA_DIST = _egg.override _egg.defs

_egg.c: _egg.override _egg.defs
.defs.c:
	(cd $(srcdir) \
	 && $(PYGTK_CODEGEN) \
	    --override $*.override \
	    --register $(PYGTK_DEFSDIR)/gtk-types.defs \
	    --register $(PYGTK_DEFSDIR)/gdk-types.defs \
	    --prefix py$* $*.defs) > gen-$*.c \
	&& cp gen-$*.c $*.c \
	&& rm -f gen-$*.c
