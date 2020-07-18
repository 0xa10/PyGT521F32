# pylint: disable=bad-continuation # Black and pylint disagree on this
# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
import ctypes
from ctypes.wintypes import UINT, ULONG, USHORT, DWORD, BOOL, HANDLE
from ctypes.wintypes import LPCWSTR
import serial.win32 as win32  # type: ignore

# an interface for communicating with reader over SCSI, implemented in the style of pyserial

DRIVE_REMOVABLE = 2
DRIVE_CDROM = 5

FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2

UCHAR = ctypes.c_ubyte
PVOID = win32.PVOID
LPOVERLAPPED = win32.LPOVERLAPPED
LPVOID = win32.LPVOID
LPDWORD = win32.LPDWORD

try:
    GetDriveTypeW = win32._stdcall_libraries[  # pylint: disable=invalid-name, protected-access
        "kernel32"
    ].GetDriveTypeW
    GetDriveTypeW.restype = UINT
    GetDriveTypeW.argtypes = [
        LPCWSTR,
    ]
    GetDriveType = GetDriveTypeW  # alias # pylint: disable=invalid-name
except AttributeError:
    from ctypes.wintypes import LPCSTR

    GetDriveTypeA = win32._stdcall_libraries[  # pylint: disable=invalid-name, protected-access
        "kernel32"
    ].GetDriveTypeA
    GetDriveTypeA.restype = UINT
    GetDriveTypeA.argtypes = [
        LPCSTR,
    ]
    GetDriveType = GetDriveTypeA  # alias # pylint: disable=invalid-name

DeviceIoControl = win32._stdcall_libraries[  # pylint: disable=invalid-name, protected-access
    "kernel32"
].DeviceIoControl
DeviceIoControl.restype = BOOL
DeviceIoControl.argtypes = [
    HANDLE,
    DWORD,
    LPVOID,
    DWORD,
    LPVOID,
    DWORD,
    LPDWORD,
    LPOVERLAPPED,
]


class SCSI_PASS_THROUGH_DIRECT(
    ctypes.Structure
):  # pylint: disable=invalid-name, too-few-public-methods
    pass


SCSI_PASS_THROUGH_DIRECT._fields_ = [  # pylint: disable=protected-access
    ("Length", USHORT),
    ("ScsiStatus", UCHAR),
    ("PathId", UCHAR),
    ("TargetId", UCHAR),
    ("Lun", UCHAR),
    ("CdbLength", UCHAR),
    ("SenseInfoLength", UCHAR),
    ("DataIn", UCHAR),
    ("DataTransferLength", ULONG),
    ("TimeOutValue", ULONG),
    ("DataBuffer", PVOID),
    ("SenseInfoOffset", ULONG),
    ("Cdb", UCHAR * 16),
]


class SCSI_PASS_THROUGH_DIRECT_WITH_BUFFER(
    ctypes.Structure
):  # pylint: disable=invalid-name, too-few-public-methods
    pass


SCSI_PASS_THROUGH_DIRECT_WITH_BUFFER._fields_ = [  # pylint: disable=protected-access
    ("sptd", SCSI_PASS_THROUGH_DIRECT),
    ("Filler", ULONG),
    ("ucSenseBuf", UCHAR * 32),
]


def CTL_CODE(DeviceType, Function, Method, Access):  # pylint: disable=invalid-name
    return (DeviceType << 16) | (Access << 14) | (Function << 2) | Method


FILE_DEVICE_CONTROLLER = 0x00000004
IOCTL_SCSI_BASE = FILE_DEVICE_CONTROLLER
CDB10GENERIC_LENGTH = 10
SCSI_IOCTL_DATA_OUT = 0
SCSI_IOCTL_DATA_IN = 1
SCSI_IOCTL_DATA_UNSPECIFIED = 2

METHOD_BUFFERED = 0
FILE_READ_ACCESS = 1
FILE_WRITE_ACCESS = 2
IOCTL_SCSI_PASS_THROUGH_DIRECT = CTL_CODE(
    IOCTL_SCSI_BASE, 0x0405, METHOD_BUFFERED, FILE_READ_ACCESS | FILE_WRITE_ACCESS
)


class WindowsSCSIInterfaceException(Exception):
    pass


class WindowsSCSIInterface:
    def __init__(self, port: str):
        self._drive = port

        self._open()

    def _open(self):
        dos_drive_path = self._drive
        ddk_drive_path = "\\\\.\\%s" % (self._drive,)

        # Check drive type
        drive_type = GetDriveType(dos_drive_path)
        if drive_type not in (DRIVE_REMOVABLE, DRIVE_CDROM):
            raise WindowsSCSIInterfaceException("Drive type is incorrect.")

        self._port_handle = win32.CreateFile(
            ddk_drive_path,
            win32.GENERIC_WRITE | win32.GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            win32.OPEN_EXISTING,
            win32.FILE_ATTRIBUTE_NORMAL,  # | win32.FILE_FLAG_OVERLAPPED,
            0,
        )

        if self._port_handle == win32.INVALID_HANDLE_VALUE:
            self._port_handle = None
            raise WindowsSCSIInterfaceException("Could not open drive.")

    def _scsi_operation(self, pbuf, size, read, timeout=10):
        sptdwb = SCSI_PASS_THROUGH_DIRECT_WITH_BUFFER()
        ctypes.memset(ctypes.addressof(sptdwb), 0, ctypes.sizeof(sptdwb))

        sptdwb.sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
        sptdwb.sptd.PathId = 0
        sptdwb.sptd.TargetId = 1
        sptdwb.sptd.Lun = 0
        sptdwb.sptd.CdbLength = CDB10GENERIC_LENGTH
        sptdwb.sptd.SenseInfoLength = 0
        sptdwb.sptd.DataIn = SCSI_IOCTL_DATA_IN if read else SCSI_IOCTL_DATA_OUT
        sptdwb.sptd.DataTransferLength = size
        sptdwb.sptd.TimeOutValue = timeout
        sptdwb.sptd.DataBuffer = pbuf
        sptdwb.sptd.SenseInfoOffset = (
            SCSI_PASS_THROUGH_DIRECT_WITH_BUFFER.ucSenseBuf.offset
        )
        sptdwb.sptd.Cdb[0] = 0xEF
        sptdwb.sptd.Cdb[1] = 0xFF if read else 0xFE

        length = DWORD(ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT_WITH_BUFFER))
        returned = DWORD(0)

        result_ok = DeviceIoControl(
            self._port_handle,
            IOCTL_SCSI_PASS_THROUGH_DIRECT,
            ctypes.pointer(sptdwb),
            length,
            ctypes.pointer(sptdwb),
            length,
            ctypes.byref(returned),
            None,
        )

        if not result_ok and win32.GetLastError() not in (
            win32.ERROR_SUCCESS,
            win32.ERROR_IO_PENDING,
        ):
            raise WindowsSCSIInterfaceException(
                "DeviceIoControl failed ({!r})".format(ctypes.WinError())
            )

        if returned.value < (
            SCSI_PASS_THROUGH_DIRECT.ScsiStatus.offset
            + SCSI_PASS_THROUGH_DIRECT.ScsiStatus.size
        ):
            raise WindowsSCSIInterfaceException(
                "Not enough SCSI information returned to determine error"
            )

        if sptdwb.sptd.ScsiStatus != 0:
            raise WindowsSCSIInterfaceException(
                "SCSI Operation returned %d" % (sptdwb.sptd.ScsiStatus,)
            )

        return sptdwb.sptd.DataTransferLength

    def read(self, size=1):
        assert size != 0
        # Allocate data
        buf = ctypes.create_string_buffer(size)
        data_read = self._scsi_operation(ctypes.addressof(buf), size, True)

        assert data_read == size
        return buf.raw[:data_read]

    def write(self, data):
        assert len(data) != 0
        buf = ctypes.create_string_buffer(len(data))
        buf.raw = data

        return self._scsi_operation(ctypes.addressof(buf), len(buf), False)

    def close(self):
        win32.CloseHandle(self._port_handle)
