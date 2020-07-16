import logging
import serial
import sgio
import time

from .exception import InterfaceException

from typing import BinaryIO

logger = logging.getLogger(__name__)


class LinuxSCSIInterfaceException(InterfaceException):
    pass


class LinuxSCSIInterface(object):
    _port: str
    _file: BinaryIO

    def __init__(self, port: str):
        self._port = port
        try:
            # The CAP_SYS_RAWIO capability is required to communicate over SGIO
            # sudo setcap CAP_SYS_RAWIO=+ep /usr/bin/python3.8
            self._file = open(self._port, "wb")
        except (FileNotFoundError, PermissionError) as e:
            logger.error("Could not open the SCSI device: %s" % (e,))
            raise LinuxSCSIInterfaceException(e)

    def read(self, size=1):
        assert size != 0
        # Allocate data
        cdb = bytearray(0x10)
        cdb[0] = 0xEF
        cdb[1] = 0xFF  # read
        data_in = bytearray(size)
        sgio.execute(self._file, cdb, None, data_in)

        return data_in

    def write(self, data):
        # Allocate data
        cdb = bytearray(0x10)
        cdb[0] = 0xEF
        cdb[1] = 0xFE  # write
        data_out = bytearray(data)
        sgio.execute(self._file, cdb, data_out, None)

        return data_out

    def close(self):
        self._file.close()
