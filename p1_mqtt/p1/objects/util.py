"""
Helper functions for P1 object definitions
"""

import logging
import re
import functools

LOGGER = logging.getLogger(__name__)

# List of registered P1 object classes
P1CLASSES = {}


def parse_p1_object(string):
    """
    Given a string representation of a P1 object, return a
    parsed object of the right type
    """

    tclass = None

    for known_class in P1CLASSES:
        if re.match(r"^" + known_class + r"\(", string):
            tclass = P1CLASSES[known_class]
            break

    if tclass is None:
        raise ValueError("Ignoring object '%s', unknown reference'" % (string,))

    return tclass(string)


def register_p1(reference):
    """
    A decorator to register P1 objects. Takes a reference (which is
    a regular expression) that matches the reference in the message
    """

    def decorator_register_p1(cls):
        @functools.wraps(cls)
        def wrapper_register_p1(*args, **kwargs):
            return cls(*args, **kwargs)

        if reference in P1CLASSES:
            raise KeyError(
                "Reference %s already registered for class %s "
                "while attempting to register class %s"
                % (reference, P1CLASSES[reference], cls)
            )
        P1CLASSES[reference] = cls
        return wrapper_register_p1

    return decorator_register_p1
