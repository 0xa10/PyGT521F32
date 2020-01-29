import logging
import contextlib
import serial
import packets
import time
import os
import PIL
import PIL.Image
import functools

logger = logging.getLogger(__name__)

SB_OEM_PKT_SIZE=12
SB_OEM_HEADER_SIZE=2
SB_OEM_DEV_ID_SIZE=2
SB_OEM_CHK_SUM_SIZE=2

def retry_three_times(func):
    def wrapper(*args, **kwargs):
        for _ in range(3):
            if func(*args, **kwargs):
                return
    return wrapper

def save_bitmap_to_file(path, bitmap):
    img = PIL.Image.frombytes("L", (202, 258), bitmap, 'raw')
    img.save(path, "BMP")

class GT521F32(object):
    DEFAULT_BAUD_RATE=9600
    DEFAULT_BYTESIZE=serial.EIGHTBITS
    DEFAULT_TIMEOUT=2 #seconds
    _BUFFERED_DELAY=0.05
    def __init__(self, port):
        self._port = port
        try:
            self._interface = serial.Serial(
                                        port=self._port,
                                        baudrate=9600,
                                        bytesize=GT521F32.DEFAULT_BYTESIZE,
                                        timeout=GT521F32.DEFAULT_TIMEOUT)
        except serial.SerialException as e:
            logger.error("Could not open the serial device: %s" % (e,))
            return None
        
        if self._interface.is_open:
            self._interface.close()

        self._interface.open()
        self._is_open = False

    def _delay(self, seconds):
        time.sleep(seconds)

    def _buffered_read(self, count):
        data = bytes()
        fragment = self._interface.read(self._interface.in_waiting)
        while len(data) < count:
            self._delay(self._BUFFERED_DELAY)
            logger.debug("Read fragment of %d size" % (len(fragment),))
            data += fragment
            fragment = self._interface.read(self._interface.in_waiting)
        
        assert len(data) == count
        return data

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
        if response_packet is None:
            logger.error("Command failed.")
            return 0, 0

        if not response_packet.ok:
            logger.error("Command responded with code %x and error %04x" % (response_packet.response_code, response_packet.parameter))

        return response_packet.response_code, response_packet.parameter
    
    def change_baud_rate_and_reopen(self, baud_rate):
        self.change_baud_rate(baud_rate)
        self._interface.close()
        self._interface = serial.Serial(
                                    port=self._port,
                                    baudrate=baud_rate,
                                    bytesize=GT521F32.DEFAULT_BYTESIZE,
                                    timeout=GT521F32.DEFAULT_TIMEOUT)

    def change_baud_rate(self, baud_rate):
        try:
            self.send_command("CHANGE_BAUDRATE", baud_rate)
        except TypeError:
            return

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
        self.change_baud_rate(9600)
        self._interface.close()

    def enroll_start(self, user_id):
        response_code, parameter = self.send_command("ENROLL_START", user_id)
        if response_code is not 0x30:
            logger.error("EnrollStart error: %s" % (packets.reverse(packets.response_error)[parameter],))
            return False
        return True

    @retry_three_times
    def enroll_n(self, n):
        self.prompt_finger(self.capture)
        response_code, parameter = self.send_command("ENROLL%d" % (n,), 0)
        if response_code is not 0x30:
            error_code = packets.reverse(packets.response_error).get(
                        parameter,
                        None
                    )
            if error_code is None:
                logger.error("Enroll%d error: %s" % (n, "Duplicate ID: %d" % (parameter,)))
                return True # fast fail

            logger.error("Enroll%d error: %s" % (n, error_code))
            return False # Will lead to retry
            
        logger.debug("Enroll%d succeeded." % (n,))
        return True

    def enroll_user(self, user_id):
        attempts = 0
        if not self.enroll_start(user_id):
            return False

        for i in range(1,4):
            self.prompt_finger(functools.partial(self.enroll_n, i))

        logger.debug("Enroll user id: %d succeeded." % (user_id,))

    def identify(self):
        self.prompt_finger(self.capture)
        response_code, parameter = self.send_command("IDENTIFY", 0)
        if response_code is not 0x30:
            logger.error("Identify error: %s" % (packets.reverse(packets.response_error)[parameter],))
            return None
        return parameter

    def get_image(self):
        self.send_command("GET_IMAGE", 0)

        # read data response
        logger.info("Downloading image...")
        to_read = packets.GetImageDataPacket().byte_size()
        response_bytes = self._buffered_read(to_read)

        get_image_data_response, _ = packets.GetImageDataPacket.from_bytes(response_bytes)

        return get_image_data_response.bitmap

    @contextlib.contextmanager
    def led(self):
        self.set_led(True)
        yield
        self.set_led(False)

    def set_led(self, onoff):
        assert type(onoff) is bool
        self.send_command("CMOS_LED", int(onoff))

    def capture(self):
        self.send_command("CAPTURE", 0)

    def get_enrolled_count(self):
        response_code, parameter = self.send_command("ENROLL_COUNT", 0)
        # Supposedly this cannot fail?
        return parameter

    def is_id_enrolled(self, user_id):
        response_code, parameter = self.send_command("CHECK_ENROLLED", user_id)
        if response_code is not 0x30:
            logger.error("CheckEnroll %d error: %s" % (user_id, packets.reverse(packets.response_error)[parameter]))
            return False
        return True

    def delete_id(self, user_id):
        response_code, parameter = self.send_command("DELETE_ID", user_id)
        if response_code is not 0x30:
            logger.error("DeleteID %d error: %s" % (user_id, packets.reverse(packets.response_error)[parameter]))
            return False
        return True

    def delete_all(self):
        response_code, parameter = self.send_command("DELETE_ALL", 0)
        if response_code is not 0x30:
            logger.error("DeleteAll error: %s" % (packets.reverse(packets.response_error)[parameter],))
            return False
        return True

    def verify(self, user_id):
        self.prompt_finger(self.capture)
        response_code, parameter = self.send_command("VERIFY", user_id)
        if response_code is not 0x30:
            logger.error("Verify %d error: %s" % (user_id, packets.reverse(packets.response_error)[parameter]))
            return False
        return True

    def save_image_to_bmp(self, path):
        self.prompt_finger(self.capture)
        save_bitmap_to_file(path, self.get_image())

    # Utitilies
    def is_finger_pressed(self):
        _, parameter = self.send_command("IS_PRESS_FINGER", 0)
        return not bool(parameter)

    def wait_for_finger_press(self, interval=0.1):
        while not self.is_finger_pressed():
            self._delay(interval)

    def prompt_finger(self, action, interval=0.1):
        with self.led():
            self.wait_for_finger_press(interval)
            return action()

