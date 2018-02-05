NULL =

INCLUDES =				\
	-DGMENU_I_KNOW_THIS_IS_UNSTABLE	\
	$(WARN_CFLAGS)			\
	$(NO_STRICT_ALIASING_CFLAGS)	\
	$(GIMMIE_CFLAGS)		\
	$(PYTHON_INCLUDES)		\
	$(DISABLE_DEPRECATED_CFLAGS)	\
	$(DEBUG_CFLAGS)			\
	$(NULL)

gmenudir = $(pyexecdir)/gimmie/gmenu
gmenu_LTLIBRARIES = gmenu.la
gmenu_PYTHON = __init__.py

gmenu_la_LDFLAGS = -module -avoid-version -fPIC -export-symbols-regex initgmenu
gmenu_la_LIBADD  = $(GIMMIE_LIBS)
gmenu_la_SOURCES = gmenu.c
