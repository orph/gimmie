/* -*- Mode: C; c-basic-offset: 4 -*- */

/* include this first, before NO_IMPORT_PYGOBJECT is defined */
#include <pygobject.h>

void py_egg_register_classes (PyObject *d);

extern PyMethodDef py_egg_functions[];

DL_EXPORT(void)
init_egg(void)
{
    PyObject *m, *d;

    init_pygobject();

    m = Py_InitModule("_egg", py_egg_functions);
    d = PyModule_GetDict(m);

    py_egg_register_classes(d);

    if (PyErr_Occurred()) {
	Py_FatalError("could not initialise module _egg");
    }
}
