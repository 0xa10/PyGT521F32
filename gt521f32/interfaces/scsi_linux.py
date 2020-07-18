# pylint: disable=bad-continuation # Black and pylint disagree on this
# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
import logging
from typing import BinaryIO
import sgio  # type: ignore

from .exception import InterfaceException


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class LinuxSCSIInterfaceException(InterfaceException):
    pass


class LinuxSCSIInterface:
    _port: str
    _file: BinaryIO

    def __init__(self, port: str):
        self._port = port
        try:
            # The CAP_SYS_RAWIO capability is required to communicate over SGIO
            # sudo setcap CAP_SYS_RAWIO=+ep /usr/bin/python3.8
            self._file = open(self._port, "wb")
        except (  # pylint: disable=invalid-name
            FileNotFoundError,
            PermissionError,
        ) as e:
            logger.error("Could not open the SCSI device: %s", e)
            raise LinuxSCSIInterfaceException(e)

    def read(self, size=1):
        assert size != 0
        # Allocate data
        cdb = bytearray(0x10)
        cdb[0] = 0xEF
        cdb[1] = 0xFF  # read
        data_in = bytearray(size)
        sgio.execute(  # pylint: disable=c-extension-no-member
            self._file, cdb, None, data_in
        )

        return data_in

    def write(self, data):
        # Allocate data
        cdb = bytearray(0x10)
        cdb[0] = 0xEF
        cdb[1] = 0xFE  # write
        data_out = bytearray(data)
        sgio.execute(  # pylint: disable=c-extension-no-member
            self._file, cdb, data_out, None
        )

        return data_out

    def close(self):
        self._file.close()
