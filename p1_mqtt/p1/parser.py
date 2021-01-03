"""
Class to handle a byte stream that may contain one or multiple P1
teletrams
"""

import logging
import re
from typing import List, Tuple

from p1_mqtt.p1.telegram import P1Telegram

LOGGER = logging.getLogger(__name__)


class P1Parser:
    """
    This class consumes a bytestream of arbitrary length and returns
    P1Telegrams as soon as they are completely read.

    It can discard incomplete data if needed
    """

    def __init__(self):
        self._buffer = b""

    def feed(self, inputdata: bytes) -> Tuple[P1Telegram, ...]:
        """
        Add `inputdata` to the internal buffer, and try to see if there
        is a potential complete telegram to be found.

        Returns a list of found telegrams (which may be empty)
        """

        found_telegrams: List[P1Telegram] = []
        self._buffer += inputdata

        LOGGER.debug("Buffer after consuming inputdata: %s", self._buffer)

        # Lopp to find all telegrams
        while True:
            # A telegram starts with a / character (which appears nowhere else in
            # a telegram). Find the first occurrence
            try:
                index = self._buffer.index(b"/")
            except ValueError:
                # There is no slash in the buffer. Discard everything in it, and
                # break the loop
                LOGGER.debug("No start character, discarding entire buffer")
                self._buffer = b""
                break

            # If the first occurrence is not at the beginning of the buffer discard
            # everything until the slash, so the buffer now starts with it
            LOGGER.debug("Discarding %d bytes in front of buffer", index)
            self._buffer = self._buffer[index:]

            # A potential telegram ends with "\r\n!<checksum>", where checksum
            # is four hex characters representing a 16 bit number.
            match = re.search(b"\r\n\\![0-9a-fA-F]{4}", self._buffer)

            if match:
                tstring = self._buffer[0 : match.end()]
                self._buffer = self._buffer[match.end() :]

                # It is possible that, due to a communication error,
                # the buffer we just sliced contains multiple beginnings
                # of telegrams before the final end marker.
                #
                # Search for the last / character in the buffer, and take
                # that as the start point of the telegram string
                index = tstring.rindex(b"/")

                if index != 0:
                    LOGGER.error(
                        "Potential incomplete data detected, discarding %d bytes",
                        index,
                    )

                    tstring = tstring[index:]

                # Make sure there are no further | inside the buffer,
                # which would indicate some other sort of transmission
                # error
                if tstring.count(b"!") > 1:
                    LOGGER.error("Stray end marker detected, dropping message")
                    continue

                LOGGER.debug(
                    "Found potential telegram of length %d: %s", len(tstring), tstring
                )
                try:
                    telegram = P1Telegram(tstring)
                except Exception as exc:
                    LOGGER.error(
                        "Could not parse message as valid Telegram: %s", exc,
                    )
                    continue

                found_telegrams.append(telegram)

            else:
                # No potential telegram found, break the loop
                break

        return tuple(found_telegrams)
