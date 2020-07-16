from .exception import InterfaceException
from .serial import SerialInterfaceException, SerialInterface
import sys

if sys.platform == "linux":
    from .scsi_linux import LinuxSCSIInterface as SCSIInterface
    from .scsi_linux import LinuxSCSIInterfaceException as SCSIInterfaceException
elif sys.platform == "win32":
    from .scsi_windows import WindowsSCSIInterface as SCSIInterface
    from .scsi_windows import WindowsSCSIInterfaceException as SCSIInterfaceException
else:
    raise NotImplemented("%s not supported by this library" % (sys.platform,))
