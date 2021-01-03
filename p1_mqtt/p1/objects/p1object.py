"""
Object definition for the base P1Object
"""

import datetime
import logging
import re
from typing import Any, Dict, Tuple, Protocol

import pytz

LOGGER = logging.getLogger(__name__)


# This is a class describing the ability to support
# the to_unixtimestamp functionality
class SupportsUnixtimestamp(Protocol):
    def to_unixtimestamp(self) -> int:
        """
        Return a Unix time stamp representing a timestamp
        information within this object
        """
        ...


def _decode_p1_octetstring(string: str) -> bytearray:
    """
    Return a decoded version of a P1 octet string
    """
    return bytearray.fromhex(string)


def _decode_p1_tst(string: str) -> datetime.datetime:
    """
    Return a decoded version of a P1 TST (time stamp),
    complete with time zone.

    The P1 documentation does not seem to specify a time zone per
    se, only a summer time/winter time marker.

    Assume for now that S means GMT+2, and W means GMT+1.

    In an added twist, the time zones associated with these offsets in
    pytz are called "Etc/GMT-1" and "Etc/GMT-2".
    """

    if string.endswith("S"):
        timezone = pytz.timezone("Etc/GMT-2")
    elif string.endswith("W"):
        timezone = pytz.timezone("Etc/GMT-1")
    else:
        raise ValueError("%s is not a valid P1 TST" % (string,))

    string = string[:-1]

    return datetime.datetime.strptime(string, "%y%m%d%H%M%S").replace(tzinfo=timezone)


def _decode_p1_unitfloat(string: str) -> Tuple[float, str]:
    """
    Return a decoded version of a float with a unit attached
    """

    # Split off the unit
    fstr, unit = string.split("*")

    return float(fstr), unit


def _utc_unixtime(timestamp: datetime.datetime) -> int:
    """
    Turn a datetime with timezone into a UTC unix timestamp,
    in
    """
    return int(timestamp.astimezone(pytz.UTC).timestamp())


class P1Object:
    """
    This is the base class of all P1 objects. It provides a general
    parse routine whose results can be further parsed later
    """

    def __init__(self, string: str):
        """
        Take the data in string an parse it into a reference,
        a channel number, and a list of strings which
        can be further parsed by child classes

        The reference is everything before the first (
        The channel number the digit after the - character in the reference

        The remainder of the string is a list of values enclosed in brackets.
        We parse those out and put them in a list, interpreting them is
        up to the child classes
        """
        LOGGER.debug(
            "Attempting to initialize %s as a %s", string, self.__class__.__name__
        )

        self._mqtt_fields: Tuple[str, ...] = ()
        self.is_timestamp = False
        self.device_id = None

        # Find the reference
        index = string.index("(")
        self.reference: str = string[:index]
        remainder = string[index:]
        LOGGER.debug("Reference: %s", self.reference)

        self.channel: int = int(self.reference.split("-")[1][0])
        LOGGER.debug("Channel: %d", self.channel)

        self.values = re.findall(r"\((.*?)\)", remainder)
        LOGGER.debug("Encoded values: %s", self.values)

    def _mqtt_name(self) -> str:
        """
        Return a camel cased version of the class name
        """

        cname = self.__class__.__name__
        return re.sub(r"(?<!^)(?=[A-Z])", "_", cname).lower()

    def to_mqtt(self) -> Dict[str, Any]:
        """
        Return a representation of the object contents in a way
        that can be fed to mqtt as a dictionary.

        It does this by taking the name of the class, snake-casing it,
        and looking at the mqtt_fields tuple.

        If mqtt_fields contains only one entry, the name of the class
        itself will be used as the key.

        If there are multiple entries in mqtt_fields, the name of the class
        is concatenated with the name of the fields.

        All properties mentioned in here are added to the dictionary.
        datetime types are converted to a UTC timestamp first.

        More complex types are suggested to override this.
        """

        output: Dict[str, Any] = {}
        if len(self._mqtt_fields) == 0:
            return output

        if len(self._mqtt_fields) == 1:
            suffix = False
        else:
            suffix = True

        for field in self._mqtt_fields:
            if suffix:
                fieldname = self._mqtt_name() + "_" + field
            else:
                fieldname = self._mqtt_name()

            value = getattr(self, field)
            if isinstance(value, datetime.datetime):
                output[fieldname] = _utc_unixtime(value)
            else:
                output[fieldname] = value

        return output
