"""
P1 to MQTT gateway

This file contains the mqtt specific code
"""

import json
import logging
import multiprocessing
import threading
import time
from typing import Any, Dict

import paho.mqtt.client as mqtt  # type: ignore
from typing_extensions import TypedDict

LOGGER = logging.getLogger(__name__)


def mqtt_main(queue: multiprocessing.Queue, config: Dict[str, Any]) -> None:
    """
    Main function for the MQTT process

    Connect to the server, read from the queue, and publish
    messages
    """

    # connected is tracking the connection state to MQTT.
    # connected_cv is a condition variable that is protecing
    # access to connected, because it is modified from a different
    # thread.
    ConnectStatus = TypedDict(  # pylint: disable=invalid-name
        "ConnectStatus", {"connected": bool, "connected_cv": threading.Condition}
    )
    connect_status: ConnectStatus = {
        "connected": False,
        "connected_cv": threading.Condition(),
    }

    def mqtt_on_connect(
        client: mqtt.Client, userdata: Any, flags: Dict[str, Any], rc: int
    ) -> None:
        """
        Callback for the on_connect event

        This is called from a different thread
        """
        del client
        LOGGER.debug("mqtt on_connect called, flags=%s, rc=%d", flags, rc)

        with userdata["connected_cv"]:
            userdata["connected"] = rc == 0
            if userdata["connected"]:
                LOGGER.info("Connected to MQTT")
                userdata["connected_cv"].notify()

    def mqtt_on_disconnect(client: mqtt.Client, userdata: Any, rc: int) -> None:
        """
        Callback for the on_disconnect event

        This is called from a different thread
        """
        del client
        LOGGER.debug("mqtt on_disconnect called, rc=%d", rc)
        if rc != 0:
            # Unexpected disconnect
            LOGGER.error("Unexpected disconnect from MQTT")

        with userdata["connected_cv"]:
            userdata["connected"] = False

            # We do not have to wake up the waiter for this,
            # because they'll just go back to sleep anyway

    LOGGER.info("mqtt process starting")

    client = mqtt.Client(config["mqtt_client_id"], userdata=connect_status)
    client.on_connect = mqtt_on_connect
    client.on_disconnect = mqtt_on_disconnect

    # This will spawn a thread that handles events and reconnects
    client.loop_start()

    # We're going to loop until the connection succeeds, once
    # it does the paho state machine will take care of reconnects
    while True:
        try:
            client.connect(config["mqtt_host"], port=config["mqtt_port"])
        except Exception as exc:
            LOGGER.info(
                "Could not connect to %s:%s, retrying (%s)",
                config["mqtt_host"],
                config["mqtt_port"],
                exc,
            )
            time.sleep(2)
            continue

        break

    rate = config["mqtt_rate"]
    last_message = 0

    while True:
        # This will sleep unless we're connected
        with connect_status["connected_cv"]:
            connect_status["connected_cv"].wait_for(lambda: connect_status["connected"])

        data = queue.get(block=True)
        LOGGER.debug("Read from queue: %s", data)

        now = time.monotonic()
        if now - last_message < rate:
            continue

        last_message = now

        # The paho thread may have died (see
        # https://github.com/eclipse/paho.mqtt.python/pull/674)
        # Check for this and die completely if true
        if not client._thread.is_alive():  # pylint: disable=protected-access
            LOGGER.error("mqtt publishing thread died, bailing out")
            raise SystemExit(1)

        # Set the required accuracy for time stamps
        if config["time_ms"]:
            data["p1mqtt_collector_timestamp"] = int(
                data["p1mqtt_collector_timestamp"] * 1000
            )
            data["p1mqtt_telegram_timestamp"] = int(
                data["p1mqtt_telegram_timestamp"] * 1000
            )
        else:
            # Round times properly here
            data["p1mqtt_collector_timestamp"] = int(
                data["p1mqtt_collector_timestamp"] + 0.5
            )
            data["p1mqtt_telegram_timestamp"] = int(
                data["p1mqtt_telegram_timestamp"] + 0.5
            )

        # See which timestamp we want to use as
        # authoritative
        if config["prefer_local_timestamp"]:
            data["p1mqtt_timestamp"] = data["p1mqtt_collector_timestamp"]
        else:
            data["p1mqtt_timestamp"] = data["p1mqtt_telegram_timestamp"]

        LOGGER.debug("Sent to mqtt: %s", data)

        client.publish(
            config["mqtt_topic"]
            % {
                "device_id": data["p1mqtt_device_id"],
                "channel": data["p1mqtt_channel"],
            },
            json.dumps(data),
        )
