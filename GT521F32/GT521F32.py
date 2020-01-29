import logging
import serial
import packets
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

    def send_command(self, command, parameter):
        if command not in packets.command_codes.keys():
            logger.error("Bad command.")
            return

        command_code = packets.command_codes[command]
        command_packet = packets.CommandPacket(parameter=parameter, command=command_code)
        
        self._interface.write(command_packet.to_bytes())

        # read response
        to_read = packets.ResponsePacket().byte_size()
        response_bytes = self._interface.read(to_read)

        response_packet, _ = packets.ResponsePacket.from_bytes(response_bytes)
        if not response_packet.ok:
            logger.error("Command responded with code %x and error %04x" % (response_packet.response_code, response_packet.parameter))

    def open(self):
        self.send_command("OPEN", 1)

        # read data response
        to_read = packets.OpenDataPacket().byte_size()
        response_bytes = self._interface.read(to_read)

        open_data_response, _ = packets.OpenDataPacket.from_bytes(response_bytes)
        logger.info("Firmware version: %s" % (open_data_response.firmware_version,))
        logger.info("Iso area max size: %s" % (open_data_response.iso_area_max_size,))
        logger.info("Serial number: %s" % (open_data_response.device_serial_number,))
    
    def close(self):
        # does nothing
        if False:
            self.send_command("CLOSE", 0)
        self._interface.close()

        

