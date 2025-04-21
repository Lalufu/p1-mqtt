"""
Class representing a P1 telegram and the messages contained within
"""

import collections
import logging
import time
from typing import Any, Type, cast

from p1_mqtt.p1.objects import parse_p1_object
from p1_mqtt.p1.p1object import P1Object, SupportsDeviceID, SupportsUnixtimestamp

LOGGER = logging.getLogger(__name__)


class P1Telegram:
    """
    A class representing a complete P1 telegram
    """

    @classmethod
    def from_objects(cls: Type["P1Telegram"], objects: list[P1Object]) -> "P1Telegram":
        """
        Create a new telegram populated with the given
        objects
        """
        # We have to pass a buffer, so pass one that only
        # consists of a checksum
        instance = cls(b"!18c0\n\r")

        instance._objects = objects.copy()

        return instance

    def __init__(self, buf: bytes) -> None:
        """
        Using the binary data in `buf`, attemt to parse the
        data as a telegram.

        The data we get must have a few guarantees already (which are upheld
        by the P1Builder class):

        - It will start with a '/' character
        - It will end with a '\n\r!....\n\r' sequence, where the .... are
          hex chars
        - The data between the initial / and the terminating ! does not contain
          any further / or !
        """
        self._meterid = ""
        self._buffer = buf
        self._validate_checksum()
        self._objects: list[P1Object] = []
        self.unparseable = 0  # Number of unparseable objects
        self._parse_objects()

    def __len__(self) -> int:
        """
        The length of a telegram is the length of the binary data it
        was parsed from. Objects created via from_objects do not have
        the binary data, and their length is 0.
        """

        if self._buffer == b"!18c0\n\r":
            # Created through from_objects
            return 0

        return len(self._buffer)

    def _validate_checksum(self) -> None:
        """
        Validate the checksum of the data in the internal buffer

        The checksum is a 16 bit number, encoded in the last four hex
        characters, and is calculated over everything from the start of
        the buffer up until and including the ! before the checksum

        The buffer ends with the checksum and \n\r, take this into
        consideration.
        """
        msgsum = int(self._buffer[-6:-2].decode("ascii"), 16)
        LOGGER.debug("In-message checksum: %04x", msgsum)

        # The checksum algorithm is CRC16, IBM style
        # Initial value is 0x0000, polynomial is 0xA001
        remainder = 0x0000
        for i in self._buffer[:-6]:
            remainder ^= i
            for _ in range(0, 8):
                if remainder & 0x0001:
                    remainder >>= 1
                    remainder ^= 0xA001
                else:
                    remainder >>= 1

        # The remainder at this point is the checksum
        LOGGER.debug("Calculated checksum: %04x", remainder)

        if remainder != msgsum:
            raise ValueError(
                f"Invalid checksum, expected {msgsum:04x}, got {remainder:04x}"
            )

    def _parse_objects(self) -> None:
        """
        Parse the telegram into a list of objects contained within.
        """

        # Turn the binary data into ASCII
        buf = self._buffer.decode("ASCII")

        for line in buf.splitlines():
            if line.startswith("/"):
                self._meterid = line[1:]
                continue

            if line.startswith("!"):
                # Checksum, ignore
                continue

            if line == "":
                continue

            # From here on, each line should contain one
            # object
            try:
                self._objects.append(parse_p1_object(line))
            except ValueError as exc:
                LOGGER.error("Could not parse object %s: %s", line, exc)
                self.unparseable += 1

    def to_mqtt(self) -> dict[str, Any]:
        """
        Return a dictionary representation of the telegram that can be
        fed to mqtt.

        This goes through all the objects from the telegram, calls their
        to_mqtt methods, and joins all outputs together

        In addition, if the telegram as a time stamp indicator,
        add this an additional field.
        """

        output: dict[str, Any] = {}

        for obj in self._objects:
            output.update(obj.to_mqtt())

        if self.timestamp is not None:
            output["p1mqtt_telegram_timestamp"] = int(self.timestamp)

        if self.device_id is not None:
            output["p1mqtt_device_id"] = self.device_id

        if self.channel is not None:
            output["p1mqtt_channel"] = self.channel

        output["p1mqtt_collector_timestamp"] = time.time()

        return output

    def split_by_channel(self) -> tuple["P1Telegram", ...]:
        """
        Return a tuple of new Telegrams, split by channel, where each new
        telegram only contains objects from one channel
        """

        telegrams: dict[int, list[P1Object]] = collections.defaultdict(list)

        for obj in self._objects:
            # We ignore channel 3 for now, it's sorta weird
            # and only contains the version field
            if obj.channel == 3:
                continue

            telegrams[obj.channel].append(obj)

        LOGGER.debug("Found split channels %s", telegrams.keys())

        return tuple(P1Telegram.from_objects(x) for x in telegrams.values())

    @property
    def timestamp(self) -> int | None:
        """
        Go through the objects and find ones that are marked as
        time stamp candidates. If there's only one, return the
        timestamp indicated.

        If there are none or more than one, return None
        """

        # I hope there's a more elegant way of doing this
        candidates: tuple[SupportsUnixtimestamp] = cast(
            tuple[SupportsUnixtimestamp],
            tuple(x for x in self._objects if x.is_timestamp),
        )

        if len(candidates) == 1:
            return candidates[0].to_unixtimestamp()

        return None

    @property
    def device_id(self) -> str | None:
        """
        Go through the objects and find ones that are marked as
        device ID candidates. If there's only one, return the
        device ID indicated.

        If there are none or more than one, return None
        """

        # I hope there's a more elegant way of doing this
        candidates: tuple[SupportsDeviceID] = cast(
            tuple[SupportsDeviceID],
            tuple(x for x in self._objects if x.is_device_id),
        )

        if len(candidates) == 1:
            return candidates[0].device_id()

        return None

    @property
    def channel(self) -> int | None:
        """
        If all objects in the telegram come from the same
        channel, return that channel number.

        Otherwise return None
        """

        channels = {x.channel for x in self._objects}

        if len(channels) == 1:
            return channels.pop()

        return None
