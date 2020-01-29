import struct
import io
from collections import OrderedDict

reverse = lambda x: {v:k for k,v in x.items()}

CommandStartCode1 = ("B", (0x55,))
CommandStartCode2 = ("B", (0xAA,))

DeviceId = ("<H", (1,))

Parameter = lambda x: ("<L", (x,))
Command = lambda x: ("<H", (x,))
Response = lambda x: ("<H", (x,))

Checksum = lambda x: ("<H", (x,))
Data = lambda x : ("B"*len(x), (x,))

command_codes = {
        "OPEN"                  : 0x01,
        "CLOSE"                 : 0x02,
        "USB_INTERNAL_CHECK"    : 0x03,
        "CHANGE_BAUDRATE"       : 0x04,
        "MODULE_INFO"           : 0x06,

        "CMOS_LED"              : 0x12,

        "ENROLL_COUNT"          : 0x20,
        "CHECK_ENROLLED"        : 0x21,
        "ENROLL_START"          : 0x22,
        "ENROLL1"               : 0x23,
        "ENROLL2"               : 0x24,
        "ENROLL3"               : 0x25,
        "IS_PRESS_FINGER"       : 0x26,

        "DELETE_ID"             : 0x40,
        "DELETE_ALL"            : 0x41,

        "VERIFY"                : 0x50,
        "IDENTIFY"              : 0x51,
        "VERIFY_TEMPLATE"       : 0x52,
        "IDENTIFY_TEMPLATE"     : 0x53,

        "CAPTURE"               : 0x60,

        "MAKE_TEMPLATE"         : 0x61,

        "GET_IMAGE"             : 0x62,
        "GET_RAWIMAGE"          : 0x63,

        "GET_TEMPLATE"          : 0x70,
        "SET_TEMPLATE"          : 0x71,

        "GET_DATABASE_START"    : 0x72,
        "GET_DATABASE_END"      : 0x73,

        "FW_UPDATE"             : 0x80,
        "ISO_UPDATE"            : 0x81,
        "FAKE_DETECTOR"         : 0x91,

        "SET_SECURITY_LEVEL"    : 0xF0,
        "GET_SECURITY_LEVEL"    : 0xF1,

        "IDENTIFY_TEMPLATE_2"   : 0XF4,

        "STANDBY_MODE"          : 0XF9, 

        "ACK_OK"                : 0x30,
        "NACK_INFO"             : 0x31
}

response_error = {
        "NACK_TIMEOUT"               : 0x1001,              
        "NACK_INVALID_BAUDRATE"      : 0x1002,      
        "NACK_INVALID_POS"           : 0x1003,          
        "NACK_IS_NOT_USED"           : 0x1004,          
        "NACK_IS_ALREADY_USED"       : 0x1005,      
        "NACK_COMM_ERR"              : 0x1006,              
        "NACK_VERIFY_FAILED"         : 0x1007,          
        "NACK_IDENTIFY_FAILED"       : 0x1008,      
        "NACK_DB_IS_FULL"            : 0x1009,              
        "NACK_DB_IS_EMPTY"           : 0x100A,          
        "NACK_TURN_ERR"              : 0x100B,              
        "NACK_BAD_FINGER"            : 0x100C,
        "NACK_ENROLL_FAILED"         : 0x100D,
        "NACK_IS_NOT_SUPPORTED"      : 0x100E,
        "NACK_DEV_ERR"               : 0x100F,
        "NACK_CAPTURE_CANCELED"      : 0x1010,
        "NACK_INVALID_PARAM"         : 0x1011,
        "NACK_FINGER_IS_NOT_PRESSED" : 0x1012
        }

class Packet(object):
    def __init__(self):
        self._fields = OrderedDict()
        self._fields["CommandStartCode1"] = CommandStartCode1
        self._fields["CommandStartCode2"] = CommandStartCode2
        self._fields["DeviceId"] = DeviceId

    def _checksum(self):
        return (sum(self._field_bytes()) % 2**16)

    def byte_size(self):
        field_byte_size = sum(struct.calcsize(field) for field, _ in self._fields.values())
        checksum_field, _ = Checksum(0)
        return field_byte_size + struct.calcsize(checksum_field)

    def _field_bytes(self):
        field_bytes = bytes()
        for _, (field, contents) in self._fields.items():
            field_bytes += struct.pack(field, *contents)
        return field_bytes
            
    def to_bytes(self):
        field_bytes = self._field_bytes()
        checksum_field, checksum_content = Checksum(self._checksum())

        return (field_bytes + struct.pack(checksum_field, *checksum_content))

    @classmethod
    def from_bytes(cls, input_bytes):
        instance = cls()
        byte_stream = io.BytesIO(input_bytes)
        import pdb;pdb.set_trace()
        for key, (field, _) in instance._fields.items():
            field_size = struct.calcsize(field)
            field_content = byte_stream.read(field_size)
            if len(field_content) == 0:
                print("Could not parse %s" % (cls),)
                return None

            unpacked_value = struct.unpack(field, field_content)
            instance._fields[key] = (field, unpacked_value)

        # verify checksum
        checksum_field, _= Checksum(0)
        checksum_bytes = byte_stream.read(struct.calcsize(checksum_field))
        if len(checksum_bytes) == 0:
            print("Checksum bytes are missing.")
            return None

        checksum = struct.unpack(checksum_field, checksum_bytes)[0]
        if checksum != instance._checksum():
            print("Bad checksum.")
            return None

        if byte_stream.tell() < len(input_bytes):
            print("Extra bytes in packet, returning in second param")

        return instance, input_bytes[byte_stream.tell():]

class CommandPacket(Packet):
    def __init__(self, parameter=0, command=0):
        super().__init__()
        self._fields["Parameter"] = Parameter(parameter)
        self._fields["Command"] = Command(command)

    @property
    def parameter(self):
        return self._fields["Parameter"][1][0]

    @property
    def command(self):
        return self._fields["Command"][1][0]

class ReponsePacket(Packet):
    def __init__(self, parameter=0, response=0):
        super().__init__()
        self._fields["Parameter"] = Parameter(parameter)
        self._fields["Response"] = Response(response)

    @property
    def parameter(self):
        return self._fields["Parameter"][1][0]

    @property
    def response_code(self):
        return self._fields["Response"][1][0]

class DataPacket(Packet):
    def __init__(self, data):
        super().__init__()
        self._fields["Data"] = Parameter(parameter)
        
    @property
    def data(self):
        return self._fields["Data"][1]

FirmwareVersion = lambda x: ("<L", x)
IsoAreaMaxSize = lambda x: ("<L", x)
DeviceSerialNumber = lambda x: ("B"*16, x)
class OpenDataPacket(Packet):
    def __init__(self, firmware_version=0, iso_area_max_size=0, device_serial_number=b"0"*16):
        super().__init__()
        self._fields["FirmwareVersion"] = FirmwareVersion(firmware_version)
        self._fields["IsoAreaMaxSize"] = IsoAreaMaxSize(iso_area_max_size)
        self._fields["DeviceSerialNumber"] = DeviceSerialNumber(device_serial_number)

    @property
    def firmware_version(self):
        return self._fields["FirmwareVersion"][1][0]

    @property
    def iso_area_max_size(self):
        return self._fields["IsoAreaMaxSize"][1][0]

    @property
    def device_serial_number(self):
        return bytes(self._fields["DeviceSerialNumber"][1]).hex().upper()


