#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

/* include this first, before NO_IMPORT_PYGOBJECT is defined */
#include <pygobject.h>

void _gnomecups_register_classes (PyObject *d);
void _gnomecups_add_constants(PyObject *module, const gchar *strip_prefix);
extern PyMethodDef _gnomecups_functions[];

DL_EXPORT(void)
init_gnomecups(void)
{
	PyObject *m, *d;

	/* Initialize libgnomecups with no auth function */
	gnome_cups_init(NULL);

	init_pygobject ();

	m = Py_InitModule ("_gnomecups", _gnomecups_functions);
	d = PyModule_GetDict (m);

	_gnomecups_register_classes (d);
	_gnomecups_add_constants (m, "GNOME_CUPS_");

	if (PyErr_Occurred ())
		Py_FatalError("could not initialise module _gnomecups");
}
