# pylint: disable=bad-continuation # Black and pylint disagree on this
# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
import sys
from .exception import InterfaceException
from .serial import SerialInterfaceException, SerialInterface

if sys.platform == "linux":
    from .scsi_linux import LinuxSCSIInterface as SCSIInterface
    from .scsi_linux import LinuxSCSIInterfaceException as SCSIInterfaceException
elif sys.platform == "win32":
    from .scsi_windows import WindowsSCSIInterface as SCSIInterface
    from .scsi_windows import WindowsSCSIInterfaceException as SCSIInterfaceException
else:
    raise NotImplementedError("%s not supported by this library" % (sys.platform,))
