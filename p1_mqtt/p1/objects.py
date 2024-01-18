"""
Object definitions for P1 objects
"""

import datetime
import functools
import logging
import re
from typing import Dict, List, Tuple, Type

import pytz

from .p1object import (
    P1Object,
    _decode_p1_octetstring,
    _decode_p1_tst,
    _decode_p1_unitfloat,
    _utc_unixtime,
)

LOGGER = logging.getLogger(__name__)

# List of registered P1 object classes
P1CLASSES: Dict[str, Type[P1Object]] = {}


def parse_p1_object(string: str) -> P1Object:
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
        raise ValueError(f"Ignoring object '{string}', unknown reference'")

    return tclass(string)


def register_p1(reference: str):
    """
    A decorator to register P1 objects. Takes a reference (which is
    a regular expression) that matches the reference in the message
    """

    def decorator_register_p1(cls: Type[P1Object]):
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


class P1OctetString(P1Object):
    """
    A helper class where the single value of the object
    is an octet-string
    """

    def __init__(self, string: str):
        super().__init__(string)
        self.string = _decode_p1_octetstring(self.values[0])
        LOGGER.debug("Decoded string value to '%s'", self.string)


class P1TST(P1Object):
    """
    A helper class where the single value of the object
    is a time stamp.

    These also get marked as potential candidate timestamp
    objects to give a timestamp to the whole telegram
    """

    def __init__(self, string: str):
        super().__init__(string)
        self._mqtt_fields = ("timestamp",)
        self.is_timestamp = True

        self.timestamp = _decode_p1_tst(self.values[0])
        LOGGER.debug("Decoded time stamp to '%s'", self.timestamp)

    def to_unixtimestamp(self) -> int:
        """
        Return the value of the object as an UTC unix timestamp
        """

        return _utc_unixtime(self.timestamp)


class P1Float(P1Object):
    """
    A helper class where the single value of the object
    is a float
    """

    def __init__(self, string: str):
        super().__init__(string)
        self._mqtt_fields = ("float",)

        self.float = float(self.values[0])
        LOGGER.debug("Decoded float as %f", self.float)


class P1UnitFloat(P1Object):
    """
    A helper class where the single value of the object
    is a float with a unit attached
    """

    def __init__(self, string: str):
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

    def __init__(self, string: str):
        super().__init__(string)
        self.is_device_id = True

    def device_id(self) -> str:
        """
        Return a string representing a device ID
        information within this object
        """
        return self.string.decode("ASCII")


@register_p1(r"1-0:1\.8\.1")
class P1EnergyConsumedTariff1(P1UnitFloat):
    """
    Represent energy delivered to client, tariff 1
    """


@register_p1(r"1-0:1\.8\.2")
class P1EnergyConsumedTariff2(P1UnitFloat):
    """
    Represent energy delivered to client, tariff 2
    """


@register_p1(r"1-0:2\.8\.1")
class P1EnergyProducedTariff1(P1UnitFloat):
    """
    Represent energy produced by client, tariff 1
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
class P1PowerFailureCount(P1Float):
    """
    Represent the number of power failures in any phase
    """


@register_p1(r"0-0:96\.7\.9")
class P1LongPowerFailureCount(P1Float):
    """
    Represent the number of long power failures in any phase
    """


@register_p1(r"1-0:99\.97\.0")
class P1LongFailureLog(P1Object):
    """
    Represent a list of last long power failures
    """

    def __init__(self, string: str):
        super().__init__(string)
        self.log: List[Tuple[datetime.datetime, float]] = []

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

    def __init__(self, string: str):
        super().__init__(string)
        self.is_device_id = True

    def device_id(self) -> str:
        """
        Return a string representing a device ID
        information within this object
        """
        return self.string.decode("ASCII")


@register_p1(r"0-\d:24\.2\.1")
class P1GasConsumed(P1Object):
    """
    Represent a measurement of m3 of gas delivered, together with a
    time stamp of the measurement, which might not be the same as the
    time stamp on the telegram

    This can serve as a time stamp indicator for a channel.
    """

    def __init__(self, string: str):
        super().__init__(string)
        self._mqtt_fields = ("timestamp", "volume")
        self.is_timestamp = True

        self.timestamp = _decode_p1_tst(self.values[0])
        self.volume, _ = _decode_p1_unitfloat(self.values[1])

        LOGGER.debug(
            "Decoded gas consumption: %f m3, at time %s", self.volume, self.timestamp
        )

    def to_unixtimestamp(self) -> int:
        """
        Return the value of the object as an UTC unix timestamp
        """

        return _utc_unixtime(self.timestamp)
