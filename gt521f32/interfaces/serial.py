# pylint: disable=bad-continuation # Black and pylint disagree on this
# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
import logging
import time
import serial  # type: ignore

from .exception import InterfaceException

logger = logging.getLogger(__name__)  # pylint: disable=C0103


class SerialInterfaceException(InterfaceException):
    pass


class SerialInterface:
    _DEFAULT_BAUD_RATE = 9600
    _DEFAULT_BYTESIZE = serial.EIGHTBITS
    _DEFAULT_TIMEOUT = 2  # seconds
    _BUFFERED_DELAY = 0.05
    _FRAGMENT_SIZE = 512

    def __init__(
        self,
        port,
        baudrate=_DEFAULT_BAUD_RATE,
        bytesize=_DEFAULT_BYTESIZE,
        timeout=_DEFAULT_TIMEOUT,
    ):
        self._port = port
        try:
            self._serial = serial.Serial(
                port=self._port, baudrate=baudrate, bytesize=bytesize, timeout=timeout
            )
        except serial.SerialException as e:  # pylint: disable=C0103
            logger.error("Could not open the serial device: %s", e)
            raise SerialInterfaceException(e)

        if self._serial.is_open:
            self._serial.close()

        self._serial.open()
        self._serial.reset_output_buffer()
        self._serial.reset_input_buffer()

    def _flush(self):
        while len(self._serial.read(self._serial.in_waiting)) > 0:
            self._delay(self._BUFFERED_DELAY)

    def _buffered_read(self, count):
        data = bytes()
        fragment = self._serial.read(self._serial.in_waiting)
        while len(data) < count:
            self._delay(self._BUFFERED_DELAY)
            logger.debug("Read fragment of %d size", len(fragment))
            data += fragment
            fragment = self._serial.read(self._serial.in_waiting)

        assert len(data) == count
        return data

    @staticmethod
    def _delay(seconds):
        time.sleep(seconds)

    def write(self, data):
        return self._serial.write(data)

    def read(self, to_read):
        if to_read > SerialInterface._FRAGMENT_SIZE:
            return self._buffered_read(to_read)
        return self._serial.read(to_read)

    def close(self):
        return self._serial.close()
