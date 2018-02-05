
/* Generated data (by glib-mkenums) */

#include <libgnomecups/gnome-cups-printer.h>
#include <libgnomecups/gnome-cups-util.h>

/* enumerations from "/usr/include/libgnomecups-1/libgnomecups/gnome-cups-printer.h" */
GType
gnome_cups_printer_refresh_get_type (void)
{
  static GType etype = 0;
  if (etype == 0) {
    static const GEnumValue values[] = {
      { GNOME_CUPS_PRINTER_REFRESH_PPD, "GNOME_CUPS_PRINTER_REFRESH_PPD", "ppd" },
      { GNOME_CUPS_PRINTER_REFRESH_OPTIONS, "GNOME_CUPS_PRINTER_REFRESH_OPTIONS", "options" },
      { GNOME_CUPS_PRINTER_REFRESH_ALL, "GNOME_CUPS_PRINTER_REFRESH_ALL", "all" },
      { 0, NULL, NULL }
    };
    etype = g_enum_register_static ("GnomeCupsPrinterRefresh", values);
  }
  return etype;
}

/* enumerations from "/usr/include/libgnomecups-1/libgnomecups/gnome-cups-util.h" */
GType
gnome_cups_unsafe_character_set_get_type (void)
{
  static GType etype = 0;
  if (etype == 0) {
    static const GEnumValue values[] = {
      { GNOME_CUPS_UNSAFE_ALL, "GNOME_CUPS_UNSAFE_ALL", "all" },
      { GNOME_CUPS_UNSAFE_ALLOW_PLUS, "GNOME_CUPS_UNSAFE_ALLOW_PLUS", "allow-plus" },
      { GNOME_CUPS_UNSAFE_PATH, "GNOME_CUPS_UNSAFE_PATH", "path" },
      { GNOME_CUPS_UNSAFE_HOST, "GNOME_CUPS_UNSAFE_HOST", "host" },
      { GNOME_CUPS_UNSAFE_SLASHES, "GNOME_CUPS_UNSAFE_SLASHES", "slashes" },
      { 0, NULL, NULL }
    };
    etype = g_enum_register_static ("GnomeCupsUnsafeCharacterSet", values);
  }
  return etype;
}

/* Generated data ends here */

