#!/bin/sh

LIBSEXYDIR="./libsexy"
python `pkg-config pygtk-2.0 --variable=codegendir`/h2def.py \
$LIBSEXYDIR/{sexy-icon-entry.h,sexy-tooltip.h} \
> sexy.defs

