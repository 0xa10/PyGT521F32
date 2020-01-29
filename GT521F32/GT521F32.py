import logging
import serial
import os

logger = logging.getLogger(__name__)

SB_OEM_PKT_SIZE=12
SB_OEM_HEADER_SIZE=2
SB_OEM_DEV_ID_SIZE=2
SB_OEM_CHK_SUM_SIZE=2

class GT521F32(object):
    DEFAULT_BAUD_RATE=9600
    DEFAULT_BYTESIZE=serial.EIGHTBITS
    DEFAULT_TIMEOUT=2 #seconds
    def __init__(self, port):
        try:
            self._interface = serial.Serial(
                                        port=port,
                                        bytesize=GT521F32.DEFAULT_BYTESIZE,
                                        timeout=GT521F32.DEFAULT_TIMEOUT)
        except serial.SerialException as e:
            logger.error("Could not open the serial device", e)
            return None
        
        if self._interface.is_open:
            self._interface.close()

        self._interface.open()
        self._is_open = False

    def open(self):
        pass
    
    def close(self)
        pass

        

