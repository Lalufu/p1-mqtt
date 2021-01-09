"""
P1 to MQTT gateway. Handle the serial port reading
and P1 telegram parsing
"""

import logging
import multiprocessing
from typing import Any, BinaryIO, Dict, Optional

import serial  # type: ignore

from p1_mqtt.p1.parser import P1Parser

LOGGER = logging.getLogger(__name__)

# Serial port parameters for different DSMR
# protocols
DSMR_PARAMETERS = {
    "2.2": {
        "speed": 9600,
        "databits": serial.SEVENBITS,
        "stopbits": serial.STOPBITS_ONE,
        "parity": serial.PARITY_EVEN,
    },
    "4.0": {
        "speed": 115200,
        "databits": serial.EIGHTBITS,
        "stopbits": serial.STOPBITS_ONE,
        "parity": serial.PARITY_NONE,
    },
}


def p1serial_main(queue: multiprocessing.Queue, config: Dict[str, Any]) -> None:
    """
    Main function for the P1 process.

    This will open the serial port, read data from it, feed it
    to the P1 parser, take the parsed P1 telegrams, and send a
    MQTT compatible serialized version to the queue
    """

    # Try to find out how many bytes to read from the serial port.
    #
    # Running the P1 parser is somewhat expensive, so ideally we want to
    # read one complete telegram from the serial port (and not more!) and then
    # run the parser to produce one telegram object, leaving no data in the
    # parser buffer. We do not know the length of a telegram.
    #
    # The length of a telegram is pretty static, though. Most fields have
    # a fixed length, and the fields that have a varying length change
    # rarely.
    #
    # Hence we assume that the next telegram to read will have the same
    # length as the last one parsed.
    #
    # If this assumption is wrong, one of two things will happen:
    #
    # - The new telegram is shorter than the old one. The parser will
    #   produce a telegram, and have data remaining in it, which constitutes
    #   the start of another telegram. In this case, adjust the read size
    #   to read the remainder of the next telegram. Once we are in sync
    #   again (the parser produced a telegram and has 0 bytes remaining
    #   in the buffer), readjust the read size to the new telegram size
    #
    # - The new telegram is longer than the old one. The parser will not
    #   produce a telegram, and have data remaining in it. In this case,
    #   adjust the read size down to the minimum (we're probably not missing
    #   a lot of data), and read data until we
    #   hit the first case, which will get us back into sync

    # This is the size of the last telegram parsed, and our best guess
    # as to the size of the next one.
    telegram_size = 0

    # This is the number of bytes to read from the serial port. As long as
    # the size of a telegram does not change, this will be identical to
    # telegram_size, but might change during telegram size changes.
    #
    # In any case, we'll never read less than 64 bytes to make sure we
    # make forward progress.
    #
    # Start with 1k bytes.
    serial_read_size = 1024

    # Whether we consider ourselves to be in sync (one read from the
    # serial port gets one telegram, and one telgram exactly)
    sync = False

    LOGGER.info("p1 process starting")

    # If needed, open the serial log file
    if "serial_dump" in config:
        dumpfile: Optional[BinaryIO] = open(config["serial_dump"], "wb")
        LOGGER.info("Writing serial data to %s", config["serial_dump"])
    else:
        dumpfile = None

    # Open the serial port.
    #
    # The timeout is mainly there to deal with wrong speed
    # settings, if we have not heard anything for 30 seconds it's
    # likely something is wrong
    portconf = DSMR_PARAMETERS[config["dsmr"]]
    ser = serial.Serial(
        config["device"],
        baudrate=portconf["speed"],
        bytesize=portconf["databits"],
        parity=portconf["parity"],
        stopbits=portconf["stopbits"],
        timeout=30,
    )

    parser = P1Parser()
    # In an endless loop, read data from the port
    while True:
        LOGGER.debug(
            "Reading from serial port, sync=%s, telegram_size=%d, serial_read_size=%d",
            sync,
            telegram_size,
            serial_read_size,
        )
        to_read = max(64, serial_read_size)
        data = ser.read(max(64, to_read))

        if len(data) != to_read:
            raise RuntimeError(
                "Timeout reading from serial port, check "
                "connection and that the DSMR setting is "
                "correct"
            )

        if dumpfile is not None:
            dumpfile.write(data)
            dumpfile.flush()

        # Feed data to the parser, receiving telegrams
        telegrams = parser.feed(data)

        if len(telegrams) == 0:
            # No telegrams received. Adjust the read size down,
            # and retry
            LOGGER.info("Telegram length increased (was %d), sync lost", telegram_size)
            serial_read_size = 0
            sync = False
            continue

        # We have at least one telegram. Adjust the telegram size
        LOGGER.debug("Received %d telegrams", len(telegrams))

        new_telegram_size = len(telegrams[-1])

        if new_telegram_size != telegram_size:
            LOGGER.info(
                "Telegram size changed %d -> %d, sync lost",
                telegram_size,
                new_telegram_size,
            )
            telegram_size = new_telegram_size
            sync = False

        # If there is data remaining in the parser, adjust our read size
        if not sync and len(parser) == 0:
            LOGGER.info("Sync reestablished, telegram size %d", telegram_size)
            sync = True

        serial_read_size = telegram_size - len(parser)

        # Split each telegram into per-channel telegrams, and send
        # those to the MQTT process
        for telegram in telegrams:
            for subtelegram in telegram.split_by_channel():
                queue.put(subtelegram.to_mqtt())
