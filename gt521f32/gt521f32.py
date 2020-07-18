# pylint: disable=bad-continuation # Black and pylint disagree on this
# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-many-public-methods
import logging
import contextlib
import threading
import time
from typing import ContextManager, Optional, Callable, Tuple, ClassVar, Union, Type
import PIL  # type: ignore
import PIL.Image  # type: ignore

from . import packets
from .interfaces import SCSIInterface, SerialInterface, InterfaceException

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def retry(func: Callable[..., bool], count: int = 3) -> Callable[..., bool]:
    def wrapper(*args, **kwargs) -> bool:
        for _ in range(count):
            if func(*args, **kwargs):
                return True
        return False

    return wrapper


def save_bitmap_to_file(path: str, bitmap: bytes) -> None:
    img = PIL.Image.frombytes("L", (202, 258), bitmap, "raw")
    img.save(path, "BMP")


class GT521F32Exception(Exception):
    pass


class GT521F32:
    _PROMPT_INTERVAL: ClassVar[float] = 0.1
    _port: str
    _interface: Union[SerialInterface, SCSIInterface]
    _firmware_version: Optional[str] = None
    _iso_area_max_size: Optional[int] = None
    _device_serial_number: Optional[str] = None
    _cancel: threading.Event

    @staticmethod
    def _choose_interface_type(
        port,
    ) -> Union[Type[SerialInterface], Type[SCSIInterface]]:
        if any(
            port.startswith(_) for _ in ("COM", "/dev/tty")
        ):  # Any other path patterns?
            return SerialInterface
        if port.startswith("/dev/sg") or (
            port[0].isalpha() and port[1] == ":" and len(port) == 2
        ):
            return SCSIInterface

        raise GT521F32Exception("Could not derive interface type from port path")

    def __init__(self, port: str, baudrate: Optional[None] = None):
        self._port = port
        try:
            interface_cls = GT521F32._choose_interface_type(port)
            logger.debug("Chose interface type %s", interface_cls.__name__)
            if baudrate is not None:
                if interface_cls is not SerialInterface:
                    raise GT521F32Exception(
                        "Baud rate can only be given for serial interfaces."
                    )
                self._interface = interface_cls(port=port, baudrate=baudrate)
            else:
                self._interface = interface_cls(port=port)
        except InterfaceException as e:  # pylint: disable=invalid-name
            logger.error("Could not open the fingerprint device: %s", e)
            raise GT521F32Exception("Failed to open the fingerprint device.")

        self._cancel = threading.Event()

    @staticmethod
    def _delay(seconds: float) -> None:
        time.sleep(seconds)

    def send_command(self, command: str, parameter: int) -> Tuple[int, int]:
        if command not in packets.command_codes.keys():
            logger.error("Bad command.")
            raise GT521F32Exception("Invalid command.")

        command_code = packets.command_codes[command]
        command_packet = packets.CommandPacket(
            parameter=parameter, command=command_code
        )

        self._interface.write(command_packet.to_bytes())

        # read response
        to_read = packets.ResponsePacket().byte_size()
        response_bytes = self._interface.read(to_read)

        response_packet = packets.ResponsePacket.from_bytes(response_bytes)
        if response_packet is None:
            logger.error("Command failed.")
            raise GT521F32Exception("Command failed.")

        if not response_packet.ok:
            logger.debug(
                "Command responded with code %x and error %04x",
                response_packet.response_code,
                response_packet.parameter,
            )

        return response_packet.response_code, response_packet.parameter

    def usb_internal_check(self) -> None:
        _, _ = self.send_command("USB_INTERNAL_CHECK", 0)

    def change_baud_rate(self, baudrate: int) -> None:
        # Not really relevant for USB (scsi) mode, but the command
        # is still supported
        response_code, parameter = self.send_command("CHANGE_BAUDRATE", baudrate)
        if response_code != packets.ACK_OK:
            logger.error(
                "ChangeBaudRate error: %s",
                packets.reverse(packets.response_error)[parameter],
            )

    def change_baud_rate_and_reopen(self, baudrate: int) -> None:
        # We can send the command and it wont do any harm, but we dont want the
        # interface to be reopened, so unless we are already using a
        # serial interface, do not proceed
        if not isinstance(self._interface, SerialInterface):
            raise NotImplementedError(
                "Baud-rate not supported for interface type %s"
                % (type(self._interface),)
            )
        self.change_baud_rate(baudrate)
        self._interface.close()
        self._interface = SerialInterface(port=self._port, baudrate=baudrate)

    @property
    def firmware_version(self):
        return self._firmware_version

    @property
    def iso_area_max_size(self):
        return self._iso_area_max_size

    @property
    def device_serial_number(self):
        return self._device_serial_number

    def open(self) -> Tuple[str, int, str]:
        _, _ = self.send_command("OPEN", 1)

        # read data response
        to_read = packets.OpenDataPacket().byte_size()
        response_bytes = self._interface.read(to_read)

        open_data_response = packets.OpenDataPacket.from_bytes(response_bytes)
        self._firmware_version, self._iso_area_max_size, self._device_serial_number = (
            open_data_response.firmware_version,
            open_data_response.iso_area_max_size,
            open_data_response.device_serial_number,
        )

        logger.info("Firmware version: %s", open_data_response.firmware_version)
        logger.info("Iso area max size: %s", open_data_response.iso_area_max_size)
        logger.info("Serial number: %s", open_data_response.device_serial_number)

        return (
            self.firmware_version,
            self.iso_area_max_size,
            self.device_serial_number,
        )

    def module_info(self) -> Tuple[str, str, int, int, int, int, int, int, int]:
        _, parameter = self.send_command("MODULE_INFO", 0)

        # read data response
        to_read = parameter + packets.DataPacket().byte_size()
        response_bytes = self._interface.read(to_read)

        module_info_known_size = packets.ModuleInfoDataPacket().byte_size()
        if to_read > module_info_known_size:
            logger.error("Module info returned more bytes than expected.")

        module_info_packet = packets.ModuleInfoDataPacket.from_bytes(response_bytes)

        logger.info("Sensor: %s", module_info_packet.sensor)
        logger.info("Engine Version: %s", module_info_packet.engine_version)
        logger.info("Raw Image Width: %s", module_info_packet.raw_img_width)
        logger.info("Raw Image Height: %s", module_info_packet.raw_img_height)
        logger.info("Image Height: %s", module_info_packet.img_width)
        logger.info("Image Width: %s", module_info_packet.img_height)
        logger.info("Max record count: %s", module_info_packet.max_record_count)
        logger.info("Enroll count: %s", module_info_packet.enroll_count)
        logger.info("Template size: %s", module_info_packet.template_size)

        return (
            module_info_packet.sensor,
            module_info_packet.engine_version,
            module_info_packet.raw_img_width,
            module_info_packet.raw_img_height,
            module_info_packet.img_width,
            module_info_packet.img_height,
            module_info_packet.max_record_count,
            module_info_packet.enroll_count,
            module_info_packet.template_size,
        )

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        # does nothing
        self.send_command("CLOSE", 0)
        self.change_baud_rate(9600)
        self._interface.close()

    def enroll_start(self, user_id: int) -> bool:
        response_code, parameter = self.send_command("ENROLL_START", user_id)
        if response_code != packets.ACK_OK:
            logger.error(
                "EnrollStart error: %s",
                packets.reverse(packets.response_error)[parameter],
            )
            return False
        return True

    @retry
    def enroll_n(  # pylint: disable=invalid-name
        self, n: int, save_enroll_photos: bool = False
    ) -> bool:
        self.prompt_finger_and_capture()

        if save_enroll_photos:
            # Save image before proceeding
            out_path = "Enroll%d.bmp" % (n,)
            logger.info("Saving Enroll%d to %s", n, out_path)
            bitmap = self.get_image()
            if bitmap:
                save_bitmap_to_file(out_path, bitmap)
            else:
                logger.error("Could not save image for current enroll cycle.")

        response_code, parameter = self.send_command("ENROLL%d" % (n,), 0)
        if response_code != packets.ACK_OK:
            error_code = packets.reverse(packets.response_error).get(parameter, None)
            if error_code is None:
                logger.error("Enroll%d error: %s", n, f"Duplicate ID: {parameter}")
                return True  # fast fail

            logger.error("Enroll%d error: %s", n, error_code)
            return False  # Will lead to retry

        logger.debug("Enroll%d succeeded.", n)
        return True

    def enroll_user(self, user_id: int, save_enroll_photos: bool = False) -> bool:
        if not self.enroll_start(user_id):
            return False

        for i in range(1, 4):
            with self.prompt_finger():
                if not self.enroll_n(
                    i, save_enroll_photos
                ):  # Not sure why this only works when reentering
                    logger.debug("Enrollment for user id %d failed, aborting.", user_id)
                    break
        else:
            logger.debug("Enroll user id: %d succeeded.", user_id)
            return True

        return False

    def identify(self) -> Optional[int]:
        self.prompt_finger_and_capture()

        response_code, parameter = self.send_command("IDENTIFY", 0)
        if response_code != packets.ACK_OK:
            logger.error(
                "Identify error: %s", packets.reverse(packets.response_error)[parameter]
            )
            return None

        return parameter

    def get_raw_image_safe(self) -> Optional[bytes]:
        with self.led():  # Undocumented, but sensor crashes if led is off
            return self._get_raw_image()

    def _get_raw_image(self) -> Optional[bytes]:
        # Do not call this with the led off
        response_code, parameter = self.send_command("GET_RAWIMAGE", 0)
        if response_code != packets.ACK_OK:
            logger.error(
                "GetRawImage error: %s",
                packets.reverse(packets.response_error)[parameter],
            )
            return None

        # read data response
        logger.info("Downloading raw image...")
        to_read = packets.GetRawImageDataPacket().byte_size()
        response_bytes = self._interface.read(to_read)

        get_raw_image_data_response = packets.GetRawImageDataPacket.from_bytes(
            response_bytes
        )

        return get_raw_image_data_response.raw_bitmap

    def get_image(self) -> Optional[bytes]:
        response_code, parameter = self.send_command("GET_IMAGE", 0)
        if response_code != packets.ACK_OK:
            logger.error(
                "GetImage error: %s", packets.reverse(packets.response_error)[parameter]
            )
            return None

        # read data response
        logger.info("Downloading image...")
        to_read = packets.GetImageDataPacket().byte_size()
        response_bytes = self._interface.read(to_read)

        get_image_data_response = packets.GetImageDataPacket.from_bytes(response_bytes)

        return get_image_data_response.bitmap

    @contextlib.contextmanager  # type: ignore
    def led(self) -> ContextManager[None]:  # type: ignore
        self.set_led(True)
        yield None
        self.set_led(False)

    def set_led(self, onoff: bool) -> None:
        assert isinstance(onoff, bool)
        # Cannot fail
        _, _ = self.send_command("CMOS_LED", int(onoff))

    def capture(self, best_image: bool = False) -> bool:
        assert isinstance(best_image, bool)
        response_code, parameter = self.send_command("CAPTURE", int(best_image))
        if response_code != packets.ACK_OK:
            logger.error(
                "Capture error: %s", packets.reverse(packets.response_error)[parameter]
            )
            return False

        return True

    def get_enrolled_count(self) -> int:
        # Supposedly this cannot fail?
        _, parameter = self.send_command("ENROLL_COUNT", 0)
        return parameter

    def is_id_enrolled(self, user_id: int) -> bool:
        response_code, parameter = self.send_command("CHECK_ENROLLED", user_id)
        if response_code != packets.ACK_OK:
            logger.error(
                "CheckEnroll %d error: %s",
                user_id,
                packets.reverse(packets.response_error)[parameter],
            )
            return False
        return True

    def delete_id(self, user_id: int) -> bool:
        response_code, parameter = self.send_command("DELETE_ID", user_id)
        if response_code != packets.ACK_OK:
            logger.error(
                "DeleteID %d error: %s",
                user_id,
                packets.reverse(packets.response_error)[parameter],
            )
            return False

        return True

    def delete_all(self) -> bool:
        response_code, parameter = self.send_command("DELETE_ALL", 0)
        if response_code != packets.ACK_OK:
            logger.error(
                "DeleteAll error: %s",
                packets.reverse(packets.response_error)[parameter],
            )
            return False

        return True

    def verify(self, user_id: int) -> bool:
        self.prompt_finger_and_capture()

        response_code, parameter = self.send_command("VERIFY", user_id)
        if response_code != packets.ACK_OK:
            logger.error(
                "Verify %d error: %s",
                user_id,
                packets.reverse(packets.response_error)[parameter],
            )
            return False

        return True

    def save_image_to_bmp(self, path: str) -> None:
        self.prompt_finger_and_capture()
        bitmap = self.get_image()
        if bitmap:
            save_bitmap_to_file(path, bitmap)

    # Utitilies
    def is_finger_pressed(self) -> bool:
        response_code, parameter = self.send_command("IS_PRESS_FINGER", 0)
        if response_code != packets.ACK_OK:
            logger.error(
                "IsFingerPressed error: %s",
                packets.reverse(packets.response_error)[parameter],
            )
            return False
        return not bool(parameter)

    def cancel(self) -> None:
        self._cancel.set()

    def wait_for_finger_press(self, interval: float = _PROMPT_INTERVAL) -> None:
        while not self._cancel.is_set() and not self.is_finger_pressed():
            self._delay(interval)

        if self._cancel.is_set():
            logger.info("Cancelled action.")
            self._cancel.clear()

    def prompt_finger_and_capture(self) -> None:
        with self.prompt_finger():
            self.capture()

    @contextlib.contextmanager  # type: ignore
    def prompt_finger(self) -> ContextManager[None]:  # type: ignore
        with self.led():
            self.wait_for_finger_press(self._PROMPT_INTERVAL)
            yield
