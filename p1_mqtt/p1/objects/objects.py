"""
Object definitions for P1 objects
"""

import datetime
import logging
import re

import pytz

from .util import register_p1

LOGGER = logging.getLogger(__name__)


def _decode_p1_octetstring(string):
    """
    Return a decoded version of a P1 octet string
    """
    return bytearray.fromhex(string)


def _decode_p1_tst(string):
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


def _decode_p1_unitfloat(string):
    """
    Return a decoded version of a float with a unit attached
    """

    # Split off the unit
    fstr, unit = string.split("*")

    return float(fstr), unit


class P1Object:
    """
    This is the base class of all P1 objects. It provides a general
    parse routine whose results can be further parsed later
    """

    def __init__(self, string):
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

        self._mqtt_fields = ()

        # Find the reference
        index = string.index("(")
        self.reference = string[:index]
        remainder = string[index:]
        LOGGER.debug("Reference: %s", self.reference)

        self.channel = int(self.reference.split("-")[1][0])
        LOGGER.debug("Channel: %d", self.channel)

        self.values = re.findall(r"\((.*?)\)", remainder)
        LOGGER.debug("Encoded values: %s", self.values)

    def _mqtt_name(self):
        """
        Return a camel cased version of the class name
        """

        cname = self.__class__.__name__
        return re.sub(r"(?<!^)(?=[A-Z])", "_", cname).lower()

    def to_mqtt(self):
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

        output = {}
        if len(self._mqtt_fields) == 0:
            return output

        if len(self._mqtt_fields) == 1:
            suffix = False
        else:
            suffix = True

        for field in self._mqtt_fields:
            if suffix:
                fieldname = self._mqtt_name() + '_' + field
            else:
                fieldname = self._mqtt_name()

            value = getattr(self, field)
            if isinstance(value, datetime.datetime):
                output[fieldname] = value.astimezone(pytz.UTC).timestamp()
            else:
                output[fieldname] = value

        return output


class P1OctetString(P1Object):
    """
    A helper class where the single value of the object
    is an octet-string
    """

    def __init__(self, string):
        super().__init__(string)
        self.string = _decode_p1_octetstring(self.values[0])
        LOGGER.debug("Decoded string value to '%s'", self.string)


class P1TST(P1Object):
    """
    A helper class where the single value of the object
    is a time stamp
    """

    def __init__(self, string):
        super().__init__(string)
        self._mqtt_fields = ("timestamp",)

        self.timestamp = _decode_p1_tst(self.values[0])
        LOGGER.debug("Decoded time stamp to '%s'", self.timestamp)


class P1Float(P1Object):
    """
    A helper class where the single value of the object
    is a float
    """

    def __init__(self, string):
        super().__init__(string)
        self._mqtt_fields = ("float",)

        self.float = float(self.values[0])
        LOGGER.debug("Decoded float as %f", self.float)


class P1UnitFloat(P1Object):
    """
    A helper class where the single value of the object
    is a float with a unit attached
    """

    def __init__(self, string):
        super().__init__(string)
        self._mqtt_fields = ("float",)

        # Split off the unit
        self.float, self.unit = _decode_p1_unitfloat(self.values[0])

        LOGGER.debug("Decoded unit float as %f, unit %s", self.float, self.unit)


@register_p1(r"1-3:0\.2\.8")
class P1Version(P1OctetString):
    """
    Represent a P1 version object
    """


@register_p1(r"0-0:1\.0\.0")
class P1Timestamp(P1TST):
    """
    Represent the timestamp of the P1 telegram
    """


@register_p1(r"0-0:96\.1\.1")
class P1EquipmentIdentfier(P1OctetString):
    """
    Represent the P1 equipment identifier
    """


@register_p1(r"1-0:1\.8\.1")
class P1EnergyConsumedTariff1(P1UnitFloat):
    """
    Represent energy delivered to client, tariff 1
    """


@register_p1(r"1-0:1\.8\.2")
class P1EnergyProducedTariff1(P1UnitFloat):
    """
    Represent energy produced by client, tariff 1
    """


@register_p1(r"1-0:2\.8\.1")
class P1EnergyConsumedTariff2(P1UnitFloat):
    """
    Represent energy delivered to client, tariff 2
    """


@register_p1(r"1-0:2\.8\.2")
class P1EnergyProducedTariff2(P1UnitFloat):
    """
    Represent energy produced by client, tariff 2
    """


@register_p1(r"0-0:96\.14\.0")
class P1EnergyTariff(P1OctetString):
    """
    Represent the current tariff
    """


@register_p1(r"1-0:1\.7\.0")
class P1ActualPowerConsuming(P1UnitFloat):
    """
    Represent the actual power delivered at this moment
    """


@register_p1(r"1-0:2\.7\.0")
class P1ActualPowerProducing(P1UnitFloat):
    """
    Represent the actual power produced at this moment
    """


@register_p1(r"0-0:96\.7\.21")
class P1PowerFaiilureCount(P1Float):
    """
    Represent the number of power failures in any phase
    """


@register_p1(r"0-0:96\.7\.9")
class P1LongPowerFaiilureCount(P1Float):
    """
    Represent the number of long power failures in any phase
    """


@register_p1(r"1-0:99\.97\.0")
class P1LongFailureLog(P1Object):
    """
    Represent a list of last long power failures
    """

    def __init__(self, string):
        super().__init__(string)
        self.log = []

        # The first value is the number of entries in the log
        logcount = int(self.values[0])

        # The second value in the log is a OBIS code, and I've
        # been unable so far to find out what it signifies.
        #
        # The remaining values are pairs of timestamps (indicating when
        # power returned), and seconds (indicating the duration
        # of failure)

        if len(self.values) - 2 != logcount / 2:
            ValueError("Inconsistent log buffer length")

        index = 2
        while logcount > 0:
            timestamp = _decode_p1_tst(self.values[index])
            duration, _ = _decode_p1_unitfloat(self.values[index + 1])

            self.log.append((timestamp, duration))
            index += 2
            logcount -= 1

        LOGGER.debug("Decoded power loss log: %s", self.log)


@register_p1(r"1-0:32\.32\.0")
class P1VoltageSagL1Count(P1Float):
    """
    Represent the number of voltage sags in phase L1
    """


@register_p1(r"1-0:52\.32\.0")
class P1VoltageSagL2Count(P1Float):
    """
    Represent the number of voltage sags in phase L2
    """


@register_p1(r"1-0:72\.32\.0")
class P1VoltageSagL3Count(P1Float):
    """
    Represent the number of voltage sags in phase L2
    """


@register_p1(r"1-0:32\.36\.0")
class P1VoltageSwellL1Count(P1Float):
    """
    Represent the number of voltage swells in phase L1
    """


@register_p1(r"1-0:52\.36\.0")
class P1VoltageSwellL2Count(P1Float):
    """
    Represent the number of voltage swells in phase L2
    """


@register_p1(r"1-0:72\.36\.0")
class P1VoltageSwellL3Count(P1Float):
    """
    Represent the number of voltage swells in phase L2
    """


@register_p1(r"0-0:96\.13\.1")
class P1UserMessageNumeric(P1OctetString):
    """
    Represent a numeric message shown to the user
    """


@register_p1(r"0-0:96\.13\.0")
class P1UserMessageText(P1OctetString):
    """
    Represent a text message shown to the user
    """


@register_p1(r"1-0:31\.7\.0")
class P1CurrentL1(P1UnitFloat):
    """
    Represent the instantaneous current on phase L1
    """


@register_p1(r"1-0:51\.7\.0")
class P1CurrentL2(P1UnitFloat):
    """
    Represent the instantaneous current on phase L2
    """


@register_p1(r"1-0:71\.7\.0")
class P1CurrentL3(P1UnitFloat):
    """
    Represent the instantaneous current on phase L3
    """


@register_p1(r"1-0:32\.7\.0")
class P1VoltageL1(P1UnitFloat):
    """
    Represent the instantaneous voltage on phase L1
    """


@register_p1(r"1-0:52\.7\.0")
class P1VoltageL2(P1UnitFloat):
    """
    Represent the instantaneous voltage on phase L2
    """


@register_p1(r"1-0:72\.7\.0")
class P1VoltageL3(P1UnitFloat):
    """
    Represent the instantaneous voltage on phase L3
    """


@register_p1(r"1-0:21\.7\.0")
class P1ActualPowerConsumingL1(P1UnitFloat):
    """
    Represent the instantaneous active power consumed on phase L1
    """


@register_p1(r"1-0:41\.7\.0")
class P1ActualPowerConsumingL2(P1UnitFloat):
    """
    Represent the instantaneous active power consumed on phase L2
    """


@register_p1(r"1-0:61\.7\.0")
class P1ActualPowerConsumingL3(P1UnitFloat):
    """
    Represent the instantaneous active power consumed on phase L3
    """


@register_p1(r"1-0:22\.7\.0")
class P1ActualPowerProducingL1(P1UnitFloat):
    """
    Represent the instantaneous active power produced on phase L1
    """


@register_p1(r"1-0:42\.7\.0")
class P1ActualPowerProducingL2(P1UnitFloat):
    """
    Represent the instantaneous active power produced on phase L2
    """


@register_p1(r"1-0:62\.7\.0")
class P1ActualPowerProducingL3(P1UnitFloat):
    """
    Represent the instantaneous active power produced on phase L3
    """


@register_p1(r"0-\d:24\.1\.0")
class P1DeviceType(P1Float):
    """
    Represent the type of device at channel X
    """


@register_p1(r"0-\d:96\.1\.0")
class P1GasEquipmentIdentfier(P1OctetString):
    """
    Represent the P1 gas equipment identifier at channel X
    """


@register_p1(r"0-\d:24\.2\.1")
class P1GasConsumed(P1Object):
    """
    Represent a measurement of m3 of gas delivered, together with a
    time stamp of the measurement, which might not be the same as the
    time stamp on the telegram
    """

    def __init__(self, string):
        super().__init__(string)
        self._mqtt_fields = ('timestamp', 'volume')

        self.timestamp = _decode_p1_tst(self.values[0])
        self.volume, _ = _decode_p1_unitfloat(self.values[1])

        LOGGER.debug(
            "Decoded gas consumption: %f m3, at time %s", self.volume, self.timestamp
        )
