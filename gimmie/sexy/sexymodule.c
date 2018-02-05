/* -*- Mode: C; c-basic-offset: 4 -*- */
#ifdef HAVE_CONFIG_H
#  include "config.h"
#endif

/* include this first, before NO_IMPORT_PYGOBJECT is defined */
#include <pygobject.h>

/* include any extra headers needed here */

void pysexy_register_classes(PyObject *d);
void pysexy_add_constants (PyObject *module, const gchar *strip_prefix);
extern PyMethodDef pysexy_functions[];

DL_EXPORT(void)
init_sexy(void)
{
    PyObject *m, *d;

    /* perform any initialisation required by the library here */
	init_pygobject();
	
    m = Py_InitModule("_sexy", pysexy_functions);
    d = PyModule_GetDict(m);
    
    /* add anything else to the module dictionary (such as constants) */
    pysexy_register_classes(d);
    pysexy_add_constants(m, "SEXY_");

    if (PyErr_Occurred())
        Py_FatalError("could not initialise module sexy");
}
