"""
Class representing a P1 telegram and the messages contained within
"""

import logging

from p1_mqtt.p1.objects import parse_p1_object

LOGGER = logging.getLogger(__name__)


class P1Telegram:
    """
    A class representing a complete P1 telegram
    """

    def __init__(self, buf):
        """
        Using the binary data in `buf`, attemt to parse the
        data as a telegram.

        The data we get must have a few guarantees already (which are upheld
        by the P1Builder class):

        - It will start with a '/' character
        - It will end with a '\n\r|....' sequence, where the .... can be
          hex chars
        - The data between the initial / and the terminating | does not contain
          any further
        """
        self._meterid = ""
        self._buffer = buf
        self._validate_checksum()
        self._objects = []
        self.unparseable = 0  # Number of unparseable objects
        self._parse_objects()

    def _validate_checksum(self):
        """
        Validate the checksum of the data in the internal buffer

        The checksum is a 16 bit number, encoded in the last four hex
        characters, and is calculated over everything from the star of
        the buffer up until and including the ! before the checksum
        """
        msgsum = int(self._buffer[-4:].decode("ascii"), 16)
        LOGGER.debug("In-message checksum: %04x", msgsum)

        # The checksum algorithm is CRC16, IBM style
        # Initial value is 0x0000, polynomial is 0xA001
        remainder = 0x0000
        for i in self._buffer[:-4]:
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
                "Invalid checksum, expected %04x, got %04x" % (msgsum, remainder)
            )

    def _parse_objects(self):
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
            except ValueError:
                LOGGER.error("Could not parse object %s", line)
                self.unparseable += 1

    def to_mqtt(self):
        """
        Return a dictionary representation of the telegram that can be
        fed to mqtt.

        This goes through all the objects from the telegram, calls their
        to_mqtt methods, and joins all outputs together
        """

        output = {}

        for obj in self._objects:
            output.update(obj.to_mqtt())

        LOGGER.info(output)
        return output
