"""
P1 to MQTT gateway. Handle reading from the data source (serial port or
TCP socket) and P1 telegram parsing
"""

import logging
import multiprocessing
import socket
import time
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


class TCPFullReader:
    """
    A slight abstraction over a socket that will block until the whole
    buffersize passed to read() is available
    """

    def __init__(self, host: str, port: int) -> None:
        self.buffer = b""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            self.socket.settimeout(30)
        except ConnectionRefusedError:
            LOGGER.error(
                "Could not connect to P1 source at %s:%d: Connection refused",
                host,
                port,
            )
            raise SystemExit(1)  # pylint: disable=raise-missing-from

    def read(self, size: int) -> bytes:
        """
        Block reading from the socket until we can return `size` bytes

        If a timeout occurs, return b''
        """
        try:
            while len(self.buffer) < size:
                LOGGER.debug("Attemping to read %d bytes from socket", size)
                newdata = self.socket.recv(size)
                LOGGER.debug("Read %d bytes from socket", len(newdata))
                if len(newdata) == 0:
                    # EOF from socket
                    LOGGER.error("EOF from socket, connection closed?")
                    return b""
                self.buffer += newdata

            data, self.buffer = self.buffer[:size], self.buffer[size:]
            return data
        except socket.timeout:
            LOGGER.error("Timeout reading %d bytes from TCP socket", size)
            return b""


def p1io_main(queue: multiprocessing.Queue, config: Dict[str, Any]) -> None:
    """
    Main function for the P1 process.

    This will open the data source (serial port or TCP socket) data from it,
    feed it to the P1 parser, take the parsed P1 telegrams, and send a MQTT
    compatible serialized version to the queue
    """

    # Try to find out how many bytes to read from the data source
    #
    # Running the P1 parser is somewhat expensive, so ideally we want to
    # read one complete telegram from the source (and not more!) and then
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

    # This is the number of bytes to read from the source. As long as
    # the size of a telegram does not change, this will be identical to
    # telegram_size, but might change during telegram size changes.
    #
    # In any case, we'll never read less than 64 bytes to make sure we
    # make forward progress.
    #
    # Start with 1k bytes.
    source_read_size = 1024

    # Whether we consider ourselves to be in sync (one read from the
    # source gets one telegram, and one telgram exactly)
    sync = False

    LOGGER.info("p1 process starting")

    # If needed, open the source log file
    dumpfilename = config.get("source_dump")
    dumpfile: Optional[BinaryIO] = None
    if dumpfilename:
        dumpfile = open(dumpfilename, "wb")  # pylint: disable=consider-using-with
        LOGGER.info("Writing source data to %s", dumpfilename)

    # Open the data source.
    # If a host and port were given, prefer those over a serial port.
    if "host" in config and "port" in config:
        # Open the TCP port
        LOGGER.info(
            "Attempting TCP connection to %s:%s", config["host"], config["port"]
        )
        p1source = TCPFullReader(config["host"], config["port"])
    elif "device" in config:
        # Open the serial port.
        #
        # The timeout is mainly there to deal with wrong speed
        # settings, if we have not heard anything for 30 seconds it's
        # likely something is wrong
        LOGGER.info("Attempting to open serial port %s", config["device"])
        portconf = DSMR_PARAMETERS[config["dsmr"]]
        p1source = serial.Serial(
            config["device"],
            baudrate=portconf["speed"],
            bytesize=portconf["databits"],
            parity=portconf["parity"],
            stopbits=portconf["stopbits"],
            timeout=30,
        )
    else:
        # This cannot be hit, because of the way configuration parsing works,
        # but pylint can't figure that out
        raise ValueError("Neither host nor device given")

    parser = P1Parser()
    # In an endless loop, read data from the port
    while True:
        LOGGER.debug(
            "Reading from source, sync=%s, telegram_size=%d, source_read_size=%d",
            sync,
            telegram_size,
            source_read_size,
        )
        to_read = max(64, source_read_size)
        LOGGER.debug("to_read=%s", to_read)
        data = p1source.read(to_read)

        if len(data) != to_read:
            raise RuntimeError(
                "Timeout reading from source, check "
                "connection parameters and that the DSMR setting is "
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
            LOGGER.info(
                "Incomplete telegram read (size was %d), sync lost", telegram_size
            )
            source_read_size = 0
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

        source_read_size = telegram_size - len(parser)

        # Split each telegram into per-channel telegrams, and send
        # those to the MQTT process
        for telegram in telegrams:
            for subtelegram in telegram.split_by_channel():
                # Look at the time stamp of the telegram, and compare with
                # the local time
                LOGGER.debug(
                    "Local time: %f, telegram time: %f",
                    time.time(),
                    subtelegram.timestamp,
                )
                # Ignore errors here
                try:
                    queue.put(subtelegram.to_mqtt())
                except Exception:
                    pass
