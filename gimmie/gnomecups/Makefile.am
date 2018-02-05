INCLUDES = $(PYTHON_INCLUDES) $(GIMMIE_CFLAGS) $(GNOMECUPS_CFLAGS)

_gnomecupsdir = $(pyexecdir)/gimmie/gnomecups
_gnomecups_LTLIBRARIES = _gnomecups.la
_gnomecups_la_LDFLAGS = -module -avoid-version -export-symbols-regex init_gnomecups
_gnomecups_la_LIBADD = $(GIMMIE_CFLAGS) $(GNOMECUPS_LIBS)
_gnomecups_la_SOURCES = 		\
        _gnomecupsmodule.c		\
	_gnomecupstypebuiltins.c	\
	_gnomecupstypebuiltins.h

nodist__gnomecups_la_SOURCES = _gnomecups.c

_gnomecups_PYTHON =		\
	__init__.py

CLEANFILES = _gnomecups.c
EXTRA_DIST = 			\
	_gnomecups.defs		\
	_gnomecups.override

_gnomecups.c: _gnomecups.defs _gnomecups.override
.defs.c:
	(cd $(srcdir) \
	 && $(PYGTK_CODEGEN) \
	    --override $*.override \
	    --prefix $* $*.defs) > gen-$*.c \
	 && cp gen-$*.c $*.c \
	 && rm -f gen-$*.c
