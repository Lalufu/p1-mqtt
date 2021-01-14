# P1-MQTT gateway

This is a simple application that reads information from Dutch smart
power meters via the so called P1 port and sends them to an MQTT gateway.
See the website of [Netbeheer Nederland](https://www.netbeheernederland.nl/dossiers/slimme-meter-15/documenten)
for information on the protocol and message format.

The P1 protocol supports a bus of meters, where measurements from multiple
meters can be deliviered through a single telegram. A common setup is to
report on both electricity and gas consumption.

In case multiple meters deliver data in a single telegram, multiple
separate measurements will be sent to MQTT, one for each meter.

This project uses [pyserial](https://pypi.org/project/pyserial/) to communicate
with the serial port, and [paho-mqtt](https://pypi.org/project/paho-mqtt/)
for talking to MQTT.

## Installation

This project uses [Poetry](https://python-poetry.org/) for dependency
management, and it's probably easiest to use this, Executing `poetry install 
--no-dev` followed by `poetry run p1-mqtt` from the git checkout root should
set up a venv, install the required dependencies into a venv and run
the main program.

Installation via pip into a venv is also possible with `pip install .` from
the git checkout root. This will also create the executable scripts in the
`bin` dir of the checkout.

In case you want to do things manually, the main entry point into
the program is `p1_mqtt/cli.py:p1_mqtt()`.

## Running

`--config`
: Specify a configuration file to load. See the section `Configuration file`
  for details on the syntax. Command line options given in addition to the
  config file override settings in the config file.

`--device`
: Device file of the serial port to use.

  Config file: Section `general`, `device`

`--mqtt-host`
: The MQTT host name to connect to. This is a required parameter.

  Config file: Section `general`, `mqtt-host`

`--mqtt-port`
: The MQTT port number to connect to. Defaults to 1883.

  Config file: Section `general`, `mqtt-port`

`--buffer-size`
: The size of the buffer (in number of measurements) that can be locally
  saved when the MQTT server is unavailable. The buffer is not persistent,
  and will be lost when the program exits. Defaults to 100000.

  Config file: Section `general`, `buffer-size`

`--mqtt-topic`
: The MQTT topic to publish the information to. This is a string that is put
  through python formatting, and can contain references to the variables `device_id`
  and `channel`. `device_id` will contain the serial number of the meter, which
  is part of the P1 telegram.
  `channel` will contain the channel assigned to a meter. The mail electicity
  meter will use channel 0, while other meters on the bus use channels 1
  and up.
  The default is `p1-mqtt/tele/%(channel)s/%(device_id)s/SENSOR`.

  Config file: Section `general`, `mqtt-topic`

`--mqtt-client-id`
: The client identifier used when connecting to the MQTT gateway. This needs
  to be unique for all clients connecting to the same gateway, only one
  client can be connected with the same name at a time. The default is
  `p1-mqtt-gateway`.

  Config file: Section `general`, `mqtt-client-id`

`--dsmr-22`
: Use DSMR 2.2 compatible parameters when setting up the serial port. This
  might be needed for older meters, try this when the default settings do
  not produce any data. The default is to use DSMR 4.0 and later parameters.

`--serial-dump`
: Takes a file name, and will record all data received from the serial
  port into the given file. This is mainly useful to capture data for
  debugging.

  Config file: Section `general`, `serial-dump`

## Configuration file
The program supports a configuration file to define behaviour. The
configuration file is in .ini file syntax, and can contain multiple sections.
The `[general]` section contains settings that define overall program
behaviour.

### Example configuration file

```
[general]
device = /dev/ttyUSB0
mqtt-client-id = p1-gateway-01
mqtt-host = mqtt.example.com
serial-dump = /tmp/dumpfile

```
## Data pushed to MQTT

The script pushes the data received from the P1 meter to MQTT as a JSON
string. Information received from the meter(s) are presented as values
under keys starting with `p1_`.

In addition the following fields are added:

- a `p1mqtt_timestamp` field is added, containing the time the measurement
  was taken. This information is contained in the P1 telegram, and relies
  on the clock in the meter. Note that not all meters update values at
  the same frequency that telegrams are sent, multiple subsequent telegrams
  might contain the same timestamp and readings.

- a `p1mqtt_device_id` field is added, containing the serial number of the meter
  that this set of measurements belongs to.

- a `p1mqtt_channel` field with added, containing the channel number
  of the meter that this set of measurements belong to.


## Optimized serial reads

To minimize delay in reading and processing data, the script tries to detect
the size of a single telegram sent by the meter, and to read exactly one telegram
at once. If it succeeds in doing so, it considers itself to be 'in sync'.
Changes in telegram size, which should be rare, result in messages to the
console. These are usually harmless, and mainly for informational purposes.
Since the script does not know the telegram size at startup there will be
at least some messages about loss of sync, and resync, during startup. This
is normal.
