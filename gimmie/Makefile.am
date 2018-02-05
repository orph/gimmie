
SUBDIRS = gdmclient gmenu iconentry sexy traymanager
if ENABLE_GNOMECUPS
SUBDIRS += gnomecups
endif

bin_SCRIPTS = gimmie
libexec_SCRIPTS = gimmie_applet

gimmie gimmie_applet: gimmie.in Makefile
	sed -e s!\@pyexecdir\@!@pyexecdir@! \
	    -e s!\@PYTHON\@!@PYTHON@! \
	    -e s!\@MODULE\@!$@! \
	    -e s!\@VERSION\@!@VERSION@! \
	    < $< > $@
	chmod a+x $@

gimmiedir = $(pyexecdir)/gimmie
gimmie_PYTHON = 		\
	__init__.py		\
	\
	W3CDate.py		\
	\
	gimmie.py		\
	gimmie_applet.py	\
	gimmie_applications.py	\
	gimmie_bar.py		\
	gimmie_base.py		\
	gimmie_computer.py	\
	gimmie_file.py		\
	gimmie_gaim.py		\
	gimmie_globals.py	\
	gimmie_gui.py		\
	gimmie_library.py	\
	gimmie_logout.py	\
	gimmie_people.py	\
	gimmie_pidgin.py	\
	gimmie_recent.py	\
	gimmie_running.py	\
	gimmie_threads.py	\
	gimmie_tomboy.py	\
	gimmie_topicwin.py	\
	gimmie_trash.py		\
	gimmie_util.py		\
	gimmie_prefs.py


CLEANFILES = gimmie_globals.py


DISTCLEANFILES =                \
	gimmie			\
	gimmie_applet


EXTRA_DIST =  			\
	gimmie.in		\
	gimmie_globals.py.in	\
	ltihooks.py

