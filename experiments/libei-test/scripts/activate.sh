#!/bin/bash
# Set GI_TYPELIB_PATH so pygobject can find typelibs
export GI_TYPELIB_PATH="$CONDA_PREFIX/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
