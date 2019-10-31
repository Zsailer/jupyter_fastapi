import datetime

from hypothesis.strategies import(
    characters,
    integers,
    times,
    booleans,
    text,
    floats,
    dictionaries
)

from .strategies import (
    filepaths
)


types = {
    str: text,
    int: integers
    datetime.datetime: times,
    bool: booleans,
    float: floats,
    pathlib.Path: filepaths
    dict: dictionaries

}

def fieldtype_to_type(field):
    field.field_info.